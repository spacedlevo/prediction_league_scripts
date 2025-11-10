#!/usr/bin/env python3
"""
Import historical fixture data from CSV files into the database.

This script imports backdated fixture data from FPL CSV exports, using the
master_team_list.csv for accurate team ID mapping across different seasons.
"""

import sqlite3 as sql
import csv
import logging
import argparse
from pathlib import Path
from datetime import datetime
import pytz

# FPL team names to database team names mapping
FPL_TO_DB_NAME_MAP = {
    'cardiff': 'cardiff city',
    'huddersfield': 'huddersfield town',
    'hull': 'hull city',
    'stoke': 'stoke city',
    'swansea': 'swansea city',
    'west brom': 'west bromwich albion',
}


def setup_logging():
    """Setup logging configuration"""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"import_backdated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def load_master_team_list(csv_path, logger):
    """
    Load master team list CSV into season-based lookup dictionary

    Returns:
        dict: {season: {fpl_id: team_name}}
    """
    logger.info(f"Loading master team list from {csv_path}")

    master_teams = {}

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            season = row['season']
            fpl_id = int(row['team'])
            team_name = row['team_name']

            if season not in master_teams:
                master_teams[season] = {}

            master_teams[season][fpl_id] = team_name

    logger.info(f"Loaded {len(master_teams)} seasons with team mappings")
    return master_teams


def load_team_cache(cursor, logger):
    """
    Load database team mappings into cache

    Returns:
        dict: {team_name_lower: team_id}
    """
    logger.info("Loading team cache from database...")

    cursor.execute("SELECT team_id, team_name FROM teams")
    team_cache = {name.lower(): team_id for team_id, name in cursor.fetchall()}

    logger.info(f"Loaded {len(team_cache)} teams from database")
    return team_cache


def get_db_team_id(fpl_team_id, season, master_teams, team_cache, logger):
    """
    Convert FPL team ID to database team_id

    Args:
        fpl_team_id: Team ID from CSV file
        season: Season string (e.g., "2018-19")
        master_teams: Dict of {season: {fpl_id: team_name}}
        team_cache: Dict of {db_team_name_lower: db_team_id}
        logger: Logger instance

    Returns:
        team_id from database, or None if not found
    """
    # Look up FPL team name from master list
    if season not in master_teams:
        logger.error(f"Season {season} not found in master team list")
        return None

    if fpl_team_id not in master_teams[season]:
        logger.error(f"FPL team ID {fpl_team_id} not found in season {season}")
        return None

    fpl_team_name = master_teams[season][fpl_team_id]
    fpl_name_lower = fpl_team_name.lower()

    # Apply name mapping if needed
    db_name_lower = FPL_TO_DB_NAME_MAP.get(fpl_name_lower, fpl_name_lower)

    # Look up in database
    team_id = team_cache.get(db_name_lower)

    if team_id is None:
        logger.warning(f"Team '{fpl_team_name}' (mapped to '{db_name_lower}') not found in database")

    return team_id


def parse_season_from_filename(filename):
    """
    Convert filename like '20182019.csv' to ('2018/2019', '2018-19')

    Returns:
        tuple: (db_season, csv_season) for database and master_team_list lookups
    """
    name = filename.stem  # Remove .csv extension
    if len(name) == 8 and name.isdigit():
        year1 = name[:4]
        year2 = name[4:]
        db_season = f"{year1}/{year2}"
        csv_season = f"{year1}-{year2[2:]}"  # 2018-19
        return db_season, csv_season
    return None, None


def convert_season_format(csv_season):
    """
    Convert season format from '2018-19' to '2018/2019'
    """
    if '-' in csv_season:
        parts = csv_season.split('-')
        year1 = parts[0]
        year2 = parts[1]
        # Handle 2-digit year
        if len(year2) == 2:
            year2 = year1[:2] + year2
        return f"{year1}/{year2}"
    return csv_season


def fixture_exists(cursor, season, fpl_fixture_id):
    """
    Check if fixture already exists in database

    Returns:
        tuple: (exists, fixture_id, needs_update, needs_result)
    """
    cursor.execute("""
        SELECT f.fixture_id, f.pulse_id, f.finished, f.kickoff_dttm, r.home_goals, r.away_goals
        FROM fixtures f
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ? AND f.fpl_fixture_id = ?
    """, (season, fpl_fixture_id))

    row = cursor.fetchone()

    if row is None:
        return False, None, False, False

    fixture_id, pulse_id, finished, kickoff_dttm, home_goals, away_goals = row

    # Check if fixture fields need updating
    needs_update = (
        pulse_id is None or
        finished is None or
        finished == 0 or
        kickoff_dttm is None
    )

    # Check if result record is missing or incomplete
    needs_result = (
        home_goals is None or
        away_goals is None
    )

    return True, fixture_id, needs_update, needs_result


def convert_to_uk_time(utc_time_str):
    """
    Convert UTC timestamp to UK time (BST/GMT)
    """
    if not utc_time_str:
        return None

    # Parse UTC time
    utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')
    utc_time = pytz.UTC.localize(utc_time)

    # Convert to UK time
    uk_tz = pytz.timezone('Europe/London')
    uk_time = utc_time.astimezone(uk_tz)

    # Return in database format (no timezone info)
    return uk_time.strftime('%Y-%m-%d %H:%M:%S')


def import_csv_file(csv_path, cursor, master_teams, team_cache, logger, test_mode=False):
    """
    Import fixtures from a single CSV file

    Returns:
        dict: Statistics (inserted, updated, skipped, errors)
    """
    stats = {
        'inserted': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    # Parse season from filename
    db_season, csv_season = parse_season_from_filename(csv_path)
    if not db_season or not csv_season:
        logger.error(f"Could not parse season from filename: {csv_path.name}")
        return stats

    logger.info(f"Processing {csv_path.name} (Season: {db_season}, CSV season: {csv_season})")

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                # Parse CSV fields
                fpl_fixture_id = int(row['id'])
                gameweek = int(row['event'])
                kickoff_time = convert_to_uk_time(row['kickoff_time'])
                fpl_home_team = int(row['team_h'])
                fpl_away_team = int(row['team_a'])
                home_goals = int(row['team_h_score']) if row['team_h_score'] else None
                away_goals = int(row['team_a_score']) if row['team_a_score'] else None
                # pulse_id may not exist in older CSV exports
                pulse_id = int(row['pulse_id']) if 'pulse_id' in row and row['pulse_id'] else None
                finished = 1 if row['finished'] == 'True' else 0
                started = 1 if row['started'] == 'True' else 0

                # Map team IDs
                home_team_id = get_db_team_id(fpl_home_team, csv_season, master_teams, team_cache, logger)
                away_team_id = get_db_team_id(fpl_away_team, csv_season, master_teams, team_cache, logger)

                if home_team_id is None or away_team_id is None:
                    logger.warning(f"Skipping fixture {fpl_fixture_id} - could not map teams")
                    stats['skipped'] += 1
                    continue

                # Check if fixture exists
                exists, fixture_id, needs_update, needs_result = fixture_exists(cursor, db_season, fpl_fixture_id)

                if exists and not needs_update and not needs_result:
                    # Fixture and result both exist and are complete
                    stats['skipped'] += 1
                    continue

                if test_mode:
                    if exists:
                        logger.info(f"[TEST] Would update fixture {fpl_fixture_id} (GW{gameweek})")
                        stats['updated'] += 1
                    else:
                        logger.info(f"[TEST] Would insert fixture {fpl_fixture_id} (GW{gameweek})")
                        stats['inserted'] += 1
                    continue

                if exists:
                    # Update existing fixture if needed
                    if needs_update:
                        cursor.execute("""
                            UPDATE fixtures
                            SET pulse_id = COALESCE(pulse_id, ?),
                                finished = COALESCE(finished, ?),
                                started = COALESCE(started, ?),
                                provisional_finished = COALESCE(provisional_finished, ?),
                                kickoff_dttm = COALESCE(kickoff_dttm, ?)
                            WHERE fixture_id = ?
                        """, (pulse_id, finished, started, finished, kickoff_time, fixture_id))

                    # Insert or update result
                    if needs_result:
                        # Check if result row exists
                        cursor.execute("SELECT result_id FROM results WHERE fixture_id = ?", (fixture_id,))
                        result_exists = cursor.fetchone() is not None

                        if result_exists:
                            cursor.execute("""
                                UPDATE results
                                SET home_goals = COALESCE(home_goals, ?),
                                    away_goals = COALESCE(away_goals, ?),
                                    result = CASE
                                        WHEN ? > ? THEN 'H'
                                        WHEN ? < ? THEN 'A'
                                        ELSE 'D'
                                    END
                                WHERE fixture_id = ?
                            """, (home_goals, away_goals, home_goals, away_goals, home_goals, away_goals, fixture_id))
                        else:
                            # Determine result
                            if home_goals > away_goals:
                                result = 'H'
                            elif home_goals < away_goals:
                                result = 'A'
                            else:
                                result = 'D'

                            cursor.execute("""
                                INSERT INTO results (fpl_fixture_id, fixture_id, home_goals, away_goals, result)
                                VALUES (?, ?, ?, ?, ?)
                            """, (fpl_fixture_id, fixture_id, home_goals, away_goals, result))

                    logger.info(f"Updated fixture {fpl_fixture_id} (GW{gameweek}) - filled missing fields")
                    stats['updated'] += 1

                else:
                    # Insert new fixture
                    cursor.execute("""
                        INSERT INTO fixtures (
                            fpl_fixture_id, season, gameweek, kickoff_dttm,
                            home_teamid, away_teamid, pulse_id, finished, started
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        fpl_fixture_id, db_season, gameweek, kickoff_time,
                        home_team_id, away_team_id, pulse_id, finished, started
                    ))

                    # Get the new fixture_id
                    new_fixture_id = cursor.lastrowid

                    # Insert result
                    if home_goals is not None and away_goals is not None:
                        # Determine result
                        if home_goals > away_goals:
                            result = 'H'
                        elif home_goals < away_goals:
                            result = 'A'
                        else:
                            result = 'D'

                        cursor.execute("""
                            INSERT INTO results (fpl_fixture_id, fixture_id, home_goals, away_goals, result)
                            VALUES (?, ?, ?, ?, ?)
                        """, (fpl_fixture_id, new_fixture_id, home_goals, away_goals, result))

                    logger.info(f"Inserted fixture {fpl_fixture_id} (GW{gameweek}): Team {home_team_id} vs Team {away_team_id} ({home_goals}-{away_goals})")
                    stats['inserted'] += 1

            except Exception as e:
                logger.error(f"Error processing row: {e}")
                logger.error(f"Row data: {row}")
                stats['errors'] += 1
                continue

    return stats


def update_last_update_table(cursor, logger, test_mode=False):
    """Update last_update table with current timestamp"""
    if test_mode:
        logger.info("[TEST] Would update last_update table")
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for table_name in ['fixtures', 'fixtures_gameweeks']:
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, timestamp)
            VALUES (?, ?)
        """, (table_name, timestamp))

    logger.info("Updated last_update table timestamps")


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Import backdated fixture data from CSV files'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run in test mode (dry-run, no database changes)'
    )
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 80)
    logger.info("Starting backdated fixtures import")
    logger.info(f"Test mode: {args.test}")
    logger.info("=" * 80)

    # Setup paths
    base_dir = Path(__file__).parent.parent.parent
    db_path = base_dir / "data" / "database.db"
    backdated_dir = base_dir / "data" / "backdated"
    master_team_list = backdated_dir / "master_team_list.csv"

    # Find all CSV files
    csv_files = sorted(backdated_dir.glob("*.csv"))
    csv_files = [f for f in csv_files if f.name != 'master_team_list.csv']

    if not csv_files:
        logger.error("No CSV files found in backdated directory")
        return

    logger.info(f"Found {len(csv_files)} CSV files to process")

    # Connect to database
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Load master team list
        master_teams = load_master_team_list(master_team_list, logger)

        # Load team cache from database
        team_cache = load_team_cache(cursor, logger)

        # Process each CSV file
        total_stats = {
            'inserted': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }

        for csv_file in csv_files:
            logger.info("")
            logger.info("-" * 80)
            stats = import_csv_file(
                csv_file, cursor, master_teams, team_cache, logger, args.test
            )

            # Accumulate stats
            for key in total_stats:
                total_stats[key] += stats[key]

            logger.info(f"Season complete - Inserted: {stats['inserted']}, "
                       f"Updated: {stats['updated']}, Skipped: {stats['skipped']}, "
                       f"Errors: {stats['errors']}")

        # Update last_update table
        if total_stats['inserted'] > 0 or total_stats['updated'] > 0:
            update_last_update_table(cursor, logger, args.test)

        # Commit transaction
        if not args.test:
            conn.commit()
            logger.info("Database changes committed successfully")
        else:
            logger.info("[TEST] No changes made to database (dry-run)")

        # Print summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total fixtures inserted: {total_stats['inserted']}")
        logger.info(f"Total fixtures updated:  {total_stats['updated']}")
        logger.info(f"Total fixtures skipped:  {total_stats['skipped']}")
        logger.info(f"Total errors:            {total_stats['errors']}")
        logger.info("=" * 80)

    except Exception as e:
        conn.rollback()
        logger.error(f"Import failed: {e}")
        raise

    finally:
        conn.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    main()
