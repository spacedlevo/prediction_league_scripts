#!/usr/bin/env python3
"""
Premier League Match Officials Fetching Script

Fetches match official data from the PL API for finished fixtures and stores them
in the pl_officials table (one row per official per fixture).

API endpoint: https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v1/matches/<pulse_id>/officials

Official types: Referee, Assistant Referee#1, Assistant Referee#2, Fourth official,
Video Assistant Referee, Assistant VAR Official.

COMMAND LINE OPTIONS:
- --test: Process most recent sample file without hitting the API
- --dry-run: Fetch data but make no database changes
- --max-workers N: Concurrent API requests (default: 3)
- --delay N: Delay between requests in seconds (default: 2.0)
- --season SEASON: Season to process (default: current season)
- --force-refresh: Clear existing officials data and re-fetch all finished fixtures
- --cleanup-count N: Number of sample files to keep (default: 10)
"""

import json
import requests
import sqlite3 as sql
import time
import logging
import argparse
import glob
import os
import sys
from pathlib import Path
from datetime import datetime
from random import uniform
from tqdm import tqdm
from requests.exceptions import RequestException, Timeout
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import CURRENT_SEASON

BASE_URL = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v1/matches/{code}/officials"
DEFAULT_DELAY = 2.0
MAX_RETRIES = 3

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"
SAMPLES_DIR = PROJECT_ROOT / "samples" / "pl_api"

LOG_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_file = LOG_DIR / f"pl_officials_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def cleanup_old_sample_files(keep_count=10, logger=None):
    """Keep only the latest N officials sample files"""
    files = list(glob.glob(str(SAMPLES_DIR / "officials_*.json")))
    if len(files) <= keep_count:
        return
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    for file_path in files[keep_count:]:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old sample file: {Path(file_path).name}")
        except OSError as e:
            if logger:
                logger.error(f"Error removing sample file {file_path}: {e}")


def create_table(cursor):
    """Create pl_officials table and indexes if they don't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pl_officials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            pulse_id INTEGER NOT NULL,
            first_name TEXT,
            last_name TEXT,
            name TEXT,
            type TEXT,
            FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_officials_fixture_id
        ON pl_officials(fixture_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_officials_type
        ON pl_officials(type)
    """)


def get_fixtures_needing_officials(cursor, season, force_all=False):
    """Get finished fixtures that are missing officials data"""
    if force_all:
        cursor.execute("""
            SELECT f.pulse_id, f.fixture_id, f.gameweek
            FROM fixtures f
            WHERE f.pulse_id IS NOT NULL
            AND f.finished = 1
            AND f.season = ?
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    else:
        cursor.execute("""
            SELECT f.pulse_id, f.fixture_id, f.gameweek
            FROM fixtures f
            LEFT JOIN pl_officials po ON f.fixture_id = po.fixture_id
            WHERE f.pulse_id IS NOT NULL
            AND f.finished = 1
            AND f.season = ?
            AND po.fixture_id IS NULL
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    return cursor.fetchall()


def fetch_officials(pulse_id, logger, delay=DEFAULT_DELAY):
    """Fetch officials data from the PL API with retry and rate limiting"""
    url = BASE_URL.format(code=pulse_id)

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                wait_time = delay * (2 ** attempt) + uniform(0.5, 1.5)
                logger.debug(f"Retry {attempt} for pulse_id {pulse_id}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            elif delay > 0:
                time.sleep(uniform(delay * 0.8, delay * 1.2))

            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"pulse_id {pulse_id} not found (404)")
                return None
            elif response.status_code == 429:
                wait_time = delay * (2 ** (attempt + 2))
                logger.warning(f"Rate limited for pulse_id {pulse_id}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                continue
            else:
                logger.warning(f"API returned {response.status_code} for pulse_id {pulse_id}")
                if attempt == MAX_RETRIES - 1:
                    return None

        except Timeout:
            logger.warning(f"Timeout fetching pulse_id {pulse_id} (attempt {attempt + 1})")
            if attempt == MAX_RETRIES - 1:
                return None
        except RequestException as e:
            logger.warning(f"Request failed for pulse_id {pulse_id}: {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    logger.error(f"Failed to fetch officials for pulse_id {pulse_id} after {MAX_RETRIES} attempts")
    return None


def fetch_officials_concurrently(fixtures, logger, max_workers=3, delay=DEFAULT_DELAY):
    """Fetch officials data for multiple fixtures concurrently"""
    results = {}
    failed = []

    def fetch_one(fixture_info):
        pulse_id, fixture_id, gameweek = fixture_info
        data = fetch_officials(pulse_id, logger, delay)
        return pulse_id, fixture_id, data

    if max_workers == 1:
        for fixture_info in tqdm(fixtures, desc="Fetching officials"):
            pulse_id, fixture_id, data = fetch_one(fixture_info)
            if data is not None:
                results[fixture_id] = (pulse_id, data)
            else:
                failed.append(fixture_id)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, f): f for f in fixtures}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching officials"):
                pulse_id, fixture_id, data = future.result()
                if data is not None:
                    results[fixture_id] = (pulse_id, data)
                else:
                    failed.append(fixture_id)

    logger.info(f"Fetched officials for {len(results)} fixtures, {len(failed)} failed")
    return results, failed


def store_officials(cursor, fixture_id, pulse_id, data):
    """Insert official rows for a fixture"""
    inserted = 0
    for entry in data.get("matchOfficials", []):
        official = entry.get("official", {})
        cursor.execute("""
            INSERT INTO pl_officials (fixture_id, pulse_id, first_name, last_name, name, type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fixture_id,
            pulse_id,
            official.get("firstName"),
            official.get("lastName"),
            official.get("name"),
            entry.get("type"),
        ))
        inserted += 1
    return inserted


def clear_officials_data(cursor, conn, season, logger):
    """Delete all officials rows for fixtures in the given season"""
    cursor.execute("""
        DELETE FROM pl_officials
        WHERE fixture_id IN (
            SELECT fixture_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
        )
    """, (season,))
    deleted = cursor.rowcount
    conn.commit()
    logger.info(f"Cleared {deleted} official records for season {season}")


def update_last_update_table(cursor, logger):
    """Record that pl_officials was updated"""
    try:
        dt = datetime.now()
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("pl_officials", dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))
    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")


def save_sample_data(pulse_id, data, logger):
    """Save an officials API response as a JSON sample"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = SAMPLES_DIR / f"officials_{pulse_id}_{timestamp}.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved sample data: {output_file.name}")
    except OSError as e:
        logger.error(f"Failed to save sample data: {e}")


def load_sample_data(logger):
    """Load the most recent officials sample file for testing"""
    files = list(glob.glob(str(SAMPLES_DIR / "officials_*.json")))
    if not files:
        logger.error("No officials sample files found in samples/pl_api/")
        return None
    sample_file = max(files, key=os.path.getmtime)
    logger.info(f"Loading sample from: {Path(sample_file).name}")
    try:
        with open(sample_file) as f:
            return json.load(f)
    except OSError as e:
        logger.error(f"Failed to load sample: {e}")
        return None


def run(season, max_workers=3, delay=DEFAULT_DELAY, dry_run=False, force_refresh=False, save_samples=True, logger=None):
    """Main processing logic"""
    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        create_table(cursor)

        if force_refresh:
            logger.info(f"Force refresh: clearing existing officials data for season {season}")
            if not dry_run:
                clear_officials_data(cursor, conn, season, logger)

        fixtures = get_fixtures_needing_officials(cursor, season, force_all=force_refresh)
        logger.info(f"Found {len(fixtures)} fixtures needing officials data for season {season}")

        if not fixtures:
            logger.info("No fixtures to process — all up to date")
            return

        results, failed = fetch_officials_concurrently(fixtures, logger, max_workers, delay)

        total_inserted = 0
        for fixture_id, (pulse_id, data) in results.items():
            if save_samples:
                save_sample_data(pulse_id, data, logger)

            if dry_run:
                count = len(data.get("matchOfficials", []))
                logger.info(f"DRY RUN: fixture_id {fixture_id} would insert {count} officials")
                continue

            try:
                inserted = store_officials(cursor, fixture_id, pulse_id, data)
                total_inserted += inserted
                logger.debug(f"fixture_id {fixture_id}: inserted {inserted} officials")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing officials for fixture_id {fixture_id}: {e}")
                continue

        if not dry_run:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info(f"Committed {total_inserted} official records across {len(results)} fixtures")
        else:
            logger.info("DRY RUN complete — no changes made")

        if failed:
            logger.warning(f"Failed to fetch officials for {len(failed)} fixtures: {failed}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        conn.close()


def test_with_sample_data(logger):
    """Process the most recent sample file and show what would be stored"""
    data = load_sample_data(logger)
    if not data:
        return
    logger.info(f"match_id: {data.get('matchId')}")
    for entry in data.get("matchOfficials", []):
        official = entry.get("official", {})
        logger.info(f"  {entry.get('type')}: {official.get('name')}")


def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch PL match officials and store in pl_officials table')
    parser.add_argument('--test', action='store_true', help='Process most recent sample file')
    parser.add_argument('--dry-run', action='store_true', help='Fetch data but make no database changes')
    parser.add_argument('--max-workers', type=int, default=3, help='Concurrent API requests (default: 3)')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY, help='Delay between requests in seconds (default: 2.0)')
    parser.add_argument('--season', type=str, default=CURRENT_SEASON, help=f'Season to process (default: {CURRENT_SEASON})')
    parser.add_argument('--force-refresh', action='store_true', help='Clear existing data and re-fetch all finished fixtures')
    parser.add_argument('--cleanup-count', type=int, default=10, help='Number of sample files to keep (default: 10)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()

    if args.test:
        logger.info("Running in test mode with sample data...")
        test_with_sample_data(logger)
    else:
        logger.info(f"Starting PL officials fetch for season {args.season}...")
        run(
            season=args.season,
            max_workers=args.max_workers,
            delay=args.delay,
            dry_run=args.dry_run,
            force_refresh=args.force_refresh,
            logger=logger,
        )
        if args.cleanup_count > 0:
            cleanup_old_sample_files(keep_count=args.cleanup_count, logger=logger)
        logger.info("Done.")
