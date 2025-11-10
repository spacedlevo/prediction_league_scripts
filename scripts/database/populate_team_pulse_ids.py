#!/usr/bin/env python3
"""
Populate teams table with pulse_id values by extracting them from cached Pulse API data.

This script efficiently updates the teams table by:
1. Parsing cached Pulse API sample files to extract team data
2. Matching Pulse API team names to database team names
3. Updating teams table with discovered pulse_ids

Usage:
    python populate_team_pulse_ids.py --dry-run  # Preview changes
    python populate_team_pulse_ids.py             # Apply updates
"""

import logging
import sqlite3 as sql
import json
from pathlib import Path
from datetime import datetime
import argparse
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"populate_team_pulse_ids_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def parse_pulse_samples(sample_dir: Path, logger: logging.Logger) -> Dict[int, str]:
    """
    Extract pulse team IDs and names from cached Pulse API sample files.

    Returns:
        Dict mapping pulse_id to team name
    """
    pulse_teams = {}
    sample_files = list(sample_dir.glob("pulse_data_*.json"))

    if not sample_files:
        logger.warning(f"No sample files found in {sample_dir}")
        return pulse_teams

    logger.info(f"Found {len(sample_files)} sample files to parse")

    for sample_file in sample_files:
        try:
            with open(sample_file, 'r') as f:
                sample_data = json.load(f)

            # Handle the nested structure: metadata + data
            fixtures_data = sample_data.get('data', {})

            for pulse_id_key, fixture_data in fixtures_data.items():
                teams = fixture_data.get('teams', [])
                for team_entry in teams:
                    team_info = team_entry.get('team', {})
                    pulse_id = team_info.get('id')
                    team_name = team_info.get('name')

                    if pulse_id and team_name:
                        pulse_teams[pulse_id] = team_name

        except Exception as e:
            logger.error(f"Error parsing {sample_file}: {e}")
            continue

    logger.info(f"Extracted {len(pulse_teams)} unique teams from Pulse API samples")
    return pulse_teams


def get_database_teams(cursor: sql.Cursor, logger: logging.Logger) -> List[Tuple[int, str, Optional[int]]]:
    """
    Get all teams from database with their current pulse_id status.

    Returns:
        List of tuples (team_id, team_name, pulse_id)
    """
    cursor.execute("""
        SELECT team_id, team_name, pulse_id
        FROM teams
        ORDER BY team_name
    """)
    teams = cursor.fetchall()
    logger.info(f"Loaded {len(teams)} teams from database")
    return teams


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def is_valid_match(db_name: str, pulse_name: str, score: float) -> bool:
    """
    Validate that a match is legitimate, not a false positive.

    Checks:
    - If db_name is a substring of pulse_name (e.g., "Leicester" in "Leicester City")
    - If pulse_name starts with db_name (e.g., "Ipswich" → "Ipswich Town")
    - Prevents short name false positives (e.g., "barnsley" vs "Burnley")
    - Prevents generic suffix matches (e.g., "bolton wanderers" vs "wolverhampton wanderers")
    """
    db_lower = db_name.lower()
    pulse_lower = pulse_name.lower()

    # Split into primary name and suffix for compound names
    common_suffixes = ['city', 'united', 'town', 'wanderers', 'athletic', 'rovers', 'county',
                       'albion', 'hotspur', 'palace', 'forest', 'villa', 'ham']

    def get_primary_name(name: str) -> str:
        """Extract primary team name before common suffixes"""
        parts = name.lower().split()
        for i, part in enumerate(parts):
            if part in common_suffixes:
                return ' '.join(parts[:i]) if i > 0 else name
        return name

    db_primary = get_primary_name(db_lower)
    pulse_primary = get_primary_name(pulse_lower)

    # Check if primary names match (one contains the other)
    if db_primary in pulse_primary or pulse_primary in db_primary:
        # Ensure the match is substantial (at least 4 characters)
        matching_part = db_primary if len(db_primary) <= len(pulse_primary) else pulse_primary
        if len(matching_part) >= 4:
            return True

    # Exact substring match (case insensitive) - full name check
    if db_lower in pulse_lower:
        return True

    if pulse_lower in db_lower:
        # Only accept if pulse name is substantial part of db name
        return len(pulse_lower) >= len(db_lower) * 0.6

    # Check if one starts with the other for compound names
    if pulse_lower.startswith(db_lower):
        remaining = pulse_lower[len(db_lower):].strip()
        # Reject if only small difference (e.g., "barnsley" vs "burnley")
        if len(remaining) <= 2:
            return score >= 0.85
        return True

    # For short names, require higher similarity
    if len(db_lower) <= 8:
        return score >= 0.85

    return False


def match_team_names(db_teams: List[Tuple[int, str, Optional[int]]],
                     pulse_teams: Dict[int, str],
                     logger: logging.Logger,
                     similarity_threshold: float = 0.7) -> List[Tuple[int, str, int, str, float]]:
    """
    Match database team names to Pulse API team names.

    Returns:
        List of tuples (team_id, db_team_name, pulse_id, pulse_team_name, similarity_score)
    """
    matches = []

    for team_id, db_team_name, current_pulse_id in db_teams:
        if current_pulse_id is not None:
            logger.debug(f"Skipping {db_team_name} - already has pulse_id {current_pulse_id}")
            continue

        best_match = None
        best_score = 0.0

        for pulse_id, pulse_team_name in pulse_teams.items():
            score = calculate_similarity(db_team_name, pulse_team_name)

            if score > best_score:
                best_score = score
                best_match = (pulse_id, pulse_team_name)

        if best_match and best_score >= similarity_threshold:
            if is_valid_match(db_team_name, best_match[1], best_score):
                matches.append((team_id, db_team_name, best_match[0], best_match[1], best_score))
                logger.info(f"Matched '{db_team_name}' → '{best_match[1]}' (pulse_id: {best_match[0]}, score: {best_score:.2f})")
            else:
                logger.warning(f"Rejected potential false match: '{db_team_name}' → '{best_match[1]}' (score: {best_score:.2f})")
        else:
            logger.warning(f"No match found for '{db_team_name}' (best score: {best_score:.2f})")

    return matches


def display_matches_table(matches: List[Tuple[int, str, int, str, float]]):
    """Display proposed matches in a formatted table"""
    if not matches:
        print("\n⚠️  No matches found to update")
        return

    print("\n" + "="*100)
    print("PROPOSED PULSE_ID UPDATES")
    print("="*100)
    print(f"{'DB Team Name':<25} {'→':<3} {'Pulse Team Name':<25} {'Pulse ID':<10} {'Confidence':<10}")
    print("-"*100)

    for team_id, db_name, pulse_id, pulse_name, score in matches:
        print(f"{db_name:<25} {'→':<3} {pulse_name:<25} {pulse_id:<10} {score*100:>6.1f}%")

    print("-"*100)
    print(f"Total teams to update: {len(matches)}")
    print("="*100 + "\n")


def update_teams_table(cursor: sql.Cursor,
                       matches: List[Tuple[int, str, int, str, float]],
                       logger: logging.Logger) -> int:
    """
    Update teams table with pulse_ids.

    Returns:
        Number of teams updated
    """
    updated_count = 0

    for team_id, db_name, pulse_id, pulse_name, score in matches:
        try:
            cursor.execute("""
                UPDATE teams
                SET pulse_id = ?
                WHERE team_id = ?
            """, (pulse_id, team_id))
            updated_count += 1
            logger.info(f"Updated {db_name} with pulse_id {pulse_id}")
        except Exception as e:
            logger.error(f"Error updating {db_name}: {e}")

    return updated_count


def update_last_update_table(cursor: sql.Cursor, logger: logging.Logger):
    """Update last_update table to trigger database upload"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO last_update (table_name, timestamp)
        VALUES (?, ?)
    """, ('teams', timestamp))
    logger.info("Updated last_update table for 'teams'")


def main(args: argparse.Namespace, logger: logging.Logger):
    """Main execution logic"""
    logger.info("Starting team pulse_id population script")

    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "database.db"
    sample_dir = project_root / "samples" / "pulse_api"

    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return

    if not sample_dir.exists():
        logger.error(f"Sample directory not found at {sample_dir}")
        return

    logger.info(f"Using database: {db_path}")
    logger.info(f"Using samples from: {sample_dir}")

    if args.dry_run:
        logger.info("🔍 DRY-RUN MODE - No changes will be made to the database")

    # Parse cached Pulse API samples
    logger.info("Parsing cached Pulse API samples...")
    pulse_teams = parse_pulse_samples(sample_dir, logger)

    if not pulse_teams:
        logger.error("No team data extracted from samples. Exiting.")
        return

    # Connect to database
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get database teams
        logger.info("Loading teams from database...")
        db_teams = get_database_teams(cursor, logger)

        teams_without_pulse_id = sum(1 for _, _, pulse_id in db_teams if pulse_id is None)
        logger.info(f"Found {teams_without_pulse_id} teams without pulse_id")

        # Match team names
        logger.info(f"Matching team names (similarity threshold: {args.similarity_threshold})...")
        matches = match_team_names(db_teams, pulse_teams, logger, args.similarity_threshold)

        # Display proposed changes
        display_matches_table(matches)

        if not matches:
            logger.info("No updates to perform")
            return

        # Update database if not in dry-run mode
        if not args.dry_run:
            logger.info("Updating teams table...")
            updated_count = update_teams_table(cursor, matches, logger)

            if updated_count > 0:
                update_last_update_table(cursor, logger)
                conn.commit()
                logger.info(f"✅ Successfully updated {updated_count} teams with pulse_ids")
            else:
                logger.warning("No teams were updated")
        else:
            logger.info("Dry-run complete. Run without --dry-run to apply changes.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error during execution: {e}")
        raise

    finally:
        conn.close()

    logger.info("Script execution completed")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Populate teams table with pulse_id values from cached Pulse API data'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without updating the database'
    )
    parser.add_argument(
        '--similarity-threshold',
        type=float,
        default=0.7,
        help='Minimum similarity score for team name matching (0.0-1.0, default: 0.7)'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    main(args, logger)
