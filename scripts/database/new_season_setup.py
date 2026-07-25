#!/usr/bin/env python3
"""
New season setup script — updates the teams table for a new Premier League season.

FPL reassigns team IDs 1-20 each season. This script fetches the current FPL team
list, updates fpl_id and strength fields for all continuing teams, relegates teams
no longer in the PL, and activates promoted teams. It also clears any pre-existing
fixtures for the target season so they can be re-inserted correctly.

Run this once at the start of each season, before fetch_fixtures_gameweeks.py.

Usage:
    python scripts/database/new_season_setup.py --dry-run   # Preview changes
    python scripts/database/new_season_setup.py             # Apply changes
    python scripts/database/new_season_setup.py --season 2027/2028  # Override season
"""

import requests
import shutil
import sqlite3 as sql
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime
from requests.exceptions import RequestException, Timeout

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import CURRENT_SEASON

# FPL API names that differ from our database team_name values
FPL_NAME_ALIASES = {
    "spurs": "tottenham",
    "ipswich town": "ipswich",
    "tottenham hotspur": "tottenham",
    "nottingham forest": "nott'm forest",
    "brighton & hove albion": "brighton",
    "wolverhampton wanderers": "wolves",
    "west ham united": "west ham",
    "leicester city": "leicester",
    "sheffield united": "sheffield utd",
}

db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)


def setup_logging():
    log_file = log_dir / f"new_season_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Update teams table for a new Premier League season'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview all changes without modifying the database')
    parser.add_argument('--season', type=str, default=CURRENT_SEASON,
                        help=f'Season to set up (default: {CURRENT_SEASON})')
    return parser.parse_args()


def create_backup(logger):
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f"database_before_new_season_setup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    logger.info(f"Database backed up to: {backup_path}")
    return backup_path


def fetch_fpl_teams(logger):
    """Fetch current team list from FPL bootstrap API"""
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            teams = response.json().get("teams", [])
            logger.info(f"Fetched {len(teams)} teams from FPL API")
            return teams
        else:
            logger.error(f"FPL API returned status {response.status_code}")
            return None
    except Timeout:
        logger.error("FPL API request timed out")
        return None
    except RequestException as e:
        logger.error(f"FPL API request failed: {e}")
        return None


def load_db_teams(cursor):
    """Load all teams from database, keyed by lowercase team_name"""
    cursor.execute("""
        SELECT team_id, team_name, fpl_id, available,
               strength, strength_overall_home, strength_overall_away,
               strength_attack_home, strength_attack_away,
               strength_defence_home, strength_defence_away
        FROM teams
    """)
    rows = cursor.fetchall()
    by_name = {row[1].lower(): row for row in rows}
    by_id = {row[0]: row for row in rows}
    return by_name, by_id


def match_fpl_team_to_db(fpl_name, db_teams_by_name):
    """Match an FPL API team name to a database team row using exact then alias lookup"""
    fpl_lower = fpl_name.lower()

    if fpl_lower in db_teams_by_name:
        return db_teams_by_name[fpl_lower]

    alias = FPL_NAME_ALIASES.get(fpl_lower)
    if alias and alias in db_teams_by_name:
        return db_teams_by_name[alias]

    return None


def build_season_plan(fpl_teams, db_teams_by_name, db_teams_by_id):
    """
    Compute the full change plan without touching the database.

    Returns dict with:
      to_update   - teams getting new fpl_id / strength / available=1
      to_relegate - currently available teams not in new FPL list
      unmatched   - FPL teams that couldn't be matched (fatal if non-empty)
    """
    matched_team_ids = set()
    to_update = []
    unmatched = []

    for fpl_team in fpl_teams:
        fpl_name = fpl_team["name"]
        db_row = match_fpl_team_to_db(fpl_name, db_teams_by_name)

        if db_row is None:
            unmatched.append(fpl_team)
            continue

        team_id = db_row[0]
        matched_team_ids.add(team_id)

        to_update.append({
            'team_id': team_id,
            'team_name': db_row[1],
            'old_fpl_id': db_row[2],
            'new_fpl_id': fpl_team["id"],
            'old_available': db_row[3],
            'strength': fpl_team.get("strength"),
            'strength_overall_home': fpl_team.get("strength_overall_home"),
            'strength_overall_away': fpl_team.get("strength_overall_away"),
            'strength_attack_home': fpl_team.get("strength_attack_home"),
            'strength_attack_away': fpl_team.get("strength_attack_away"),
            'strength_defence_home': fpl_team.get("strength_defence_home"),
            'strength_defence_away': fpl_team.get("strength_defence_away"),
        })

    # Teams currently in the PL that weren't matched are being relegated
    to_relegate = [
        {'team_id': row[0], 'team_name': row[1], 'old_fpl_id': row[2]}
        for row in db_teams_by_id.values()
        if row[3] == 1 and row[0] not in matched_team_ids
    ]

    return {
        'to_update': sorted(to_update, key=lambda t: t['new_fpl_id']),
        'to_relegate': sorted(to_relegate, key=lambda t: t['team_name']),
        'unmatched': unmatched,
    }


def display_plan(plan, season, logger):
    """Log a human-readable summary of the planned changes"""
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"SEASON SETUP PLAN FOR {season}")
    logger.info("=" * 70)

    logger.info(f"\nTeams being updated ({len(plan['to_update'])}):")
    logger.info(f"  {'FPL ID':<8} {'Team':<22} {'Old FPL ID':<12} {'Available change'}")
    logger.info(f"  {'-'*6:<8} {'-'*20:<22} {'-'*10:<12} {'-'*16}")
    for team in plan['to_update']:
        fpl_change = f"{team['old_fpl_id']} -> {team['new_fpl_id']}" if team['old_fpl_id'] != team['new_fpl_id'] else f"{team['new_fpl_id']} (unchanged)"
        avail_change = "0 -> 1 (PROMOTED)" if team['old_available'] == 0 else ""
        logger.info(f"  {team['new_fpl_id']:<8} {team['team_name']:<22} {fpl_change:<22} {avail_change}")

    if plan['to_relegate']:
        logger.info(f"\nTeams being relegated ({len(plan['to_relegate'])}):")
        for team in plan['to_relegate']:
            logger.info(f"  {team['team_name']} (team_id={team['team_id']}, was fpl_id={team['old_fpl_id']}) -> available=0, fpl_id=NULL")

    if plan['unmatched']:
        logger.info(f"\nUNMATCHED FPL teams ({len(plan['unmatched'])}):")
        for team in plan['unmatched']:
            logger.info(f"  FPL ID {team['id']}: {team['name']} - NOT FOUND IN DATABASE")

    logger.info("")


def apply_season_setup(cursor, plan, season, logger):
    """Execute all database changes inside the caller's transaction"""

    # Update fpl_id, available, and strengths for all current-season teams
    for team in plan['to_update']:
        cursor.execute("""
            UPDATE teams SET
                fpl_id = ?,
                available = 1,
                strength = ?,
                strength_overall_home = ?,
                strength_overall_away = ?,
                strength_attack_home = ?,
                strength_attack_away = ?,
                strength_defence_home = ?,
                strength_defence_away = ?
            WHERE team_id = ?
        """, (
            team['new_fpl_id'],
            team['strength'],
            team['strength_overall_home'],
            team['strength_overall_away'],
            team['strength_attack_home'],
            team['strength_attack_away'],
            team['strength_defence_home'],
            team['strength_defence_away'],
            team['team_id']
        ))

    logger.info(f"Updated {len(plan['to_update'])} teams with new FPL IDs and strength data")

    # Relegate teams no longer in the PL
    for team in plan['to_relegate']:
        cursor.execute("""
            UPDATE teams SET available = 0, fpl_id = NULL
            WHERE team_id = ?
        """, (team['team_id'],))

    if plan['to_relegate']:
        logger.info(f"Relegated {len(plan['to_relegate'])} teams: {', '.join(t['team_name'] for t in plan['to_relegate'])}")

    # Delete any pre-existing fixtures for the target season (e.g. stale data from a prior run)
    cursor.execute("SELECT COUNT(*) FROM fixtures WHERE season = ?", (season,))
    fixture_count = cursor.fetchone()[0]
    if fixture_count > 0:
        cursor.execute("DELETE FROM fixtures WHERE season = ?", (season,))
        logger.info(f"Deleted {fixture_count} pre-existing fixtures for {season}")
    else:
        logger.info(f"No existing fixtures for {season} to delete")

    # Record the update
    dt = datetime.now()
    cursor.execute("""
        INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
        VALUES ('teams', ?, ?)
    """, (dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))


def main():
    args = parse_arguments()
    logger = setup_logging()

    season = args.season
    dry_run = args.dry_run

    logger.info("=" * 70)
    logger.info(f"NEW SEASON SETUP - {season}")
    logger.info("DRY RUN MODE - no changes will be made" if dry_run else "LIVE MODE - database will be modified")
    logger.info("=" * 70)

    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return 1

    fpl_teams = fetch_fpl_teams(logger)
    if not fpl_teams:
        logger.error("Aborting - could not fetch FPL team data")
        return 1

    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        db_teams_by_name, db_teams_by_id = load_db_teams(cursor)
        plan = build_season_plan(fpl_teams, db_teams_by_name, db_teams_by_id)

        display_plan(plan, season, logger)

        if plan['unmatched']:
            logger.error(
                f"Cannot proceed - {len(plan['unmatched'])} FPL team(s) could not be matched to any "
                f"database record. Add the missing name(s) to FPL_NAME_ALIASES in this script and re-run."
            )
            return 1

        if dry_run:
            logger.info("DRY RUN complete - run without --dry-run to apply these changes")
            return 0

        create_backup(logger)
        apply_season_setup(cursor, plan, season, logger)
        conn.commit()

        logger.info("")
        logger.info("=" * 70)
        logger.info("Season setup completed successfully")
        logger.info(f"Next step: run scripts/fpl/fetch_fixtures_gameweeks.py to populate {season} fixtures")
        logger.info("Also update odds_api_name in the teams table for any newly promoted teams")
        logger.info("=" * 70)
        return 0

    except Exception as e:
        conn.rollback()
        logger.error(f"Season setup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
