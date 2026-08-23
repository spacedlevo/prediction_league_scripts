#!/usr/bin/env python3
"""
Premier League Timeline Data Fetching Script

Fetches match timeline events from the PL API for finished fixtures and stores them
in the pl_match_events table. Replaces the old Pulse Live API (fetch_pulse_data.py).

API endpoint: https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v1/matches/<code>/timeline

Event types captured: GOAL, YELLOW_CARD, RED_CARD, PLAYER_SUBSTITUTE_ON, PLAYER_SUBSTITUTE_OFF,
FIRST_HALF_START, FIRST_HALF_END, SECOND_HALF_START, SECOND_HALF_END, and others.

Team IDs in the API response are team codes that map to teams.code in the database.
Player IDs in the API response are player codes that map to fpl_players_bootstrap.code.

COMMAND LINE OPTIONS:
- --test: Use cached sample data for development
- --dry-run: Preview changes without database updates
- --max-workers N: Concurrent API requests (default: 3)
- --delay N: Delay between requests in seconds (default: 2.0)
- --season SEASON: Process specific season (default: current season)
- --force-refresh: Clear existing timeline data and re-fetch all finished fixtures
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

BASE_URL = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v1/matches/{code}/timeline"
DEFAULT_DELAY = 2.0
MAX_RETRIES = 3

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"
SAMPLES_DIR = PROJECT_ROOT / "samples" / "pl_api"

LOG_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_file = LOG_DIR / f"pl_timeline_{datetime.now().strftime('%Y%m%d')}.log"
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
    """Keep only the latest N sample files, remove older ones"""
    files = list(glob.glob(str(SAMPLES_DIR / "timeline_*.json")))
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
    """Create pl_match_events table and indexes if they don't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pl_match_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            code INTEGER NOT NULL,
            period_id INTEGER,
            minutes INTEGER,
            seconds INTEGER,
            event_type TEXT NOT NULL,
            tag TEXT,
            team_id INTEGER,
            player_code INTEGER,
            timestamp_utc TEXT,
            FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_match_events_fixture_id
        ON pl_match_events(fixture_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_match_events_event_type
        ON pl_match_events(event_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_match_events_code
        ON pl_match_events(code)
    """)


def load_team_code_mapping(cursor):
    """Load mapping from PL API team code to database team_id"""
    cursor.execute("SELECT code, team_id FROM teams WHERE code IS NOT NULL")
    return {code: team_id for code, team_id in cursor.fetchall()}


def get_fixtures_needing_timeline(cursor, season, force_all=False):
    """Get finished fixtures that are missing timeline data"""
    if force_all:
        cursor.execute("""
            SELECT f.code, f.fixture_id, f.gameweek
            FROM fixtures f
            WHERE f.code IS NOT NULL
            AND f.provisional_finished = 1
            AND f.season = ?
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    else:
        cursor.execute("""
            SELECT f.code, f.fixture_id, f.gameweek
            FROM fixtures f
            LEFT JOIN pl_match_events pme ON f.fixture_id = pme.fixture_id
            WHERE f.code IS NOT NULL
            AND f.provisional_finished = 1
            AND f.season = ?
            AND pme.fixture_id IS NULL
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    return cursor.fetchall()


def fetch_timeline(code, logger, delay=DEFAULT_DELAY):
    """Fetch timeline events from the PL API with retry and rate limiting"""
    url = BASE_URL.format(code=code)

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                wait_time = delay * (2 ** attempt) + uniform(0.5, 1.5)
                logger.debug(f"Retry {attempt} for code {code}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            elif delay > 0:
                time.sleep(uniform(delay * 0.8, delay * 1.2))

            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"code {code} not found (404)")
                return None
            elif response.status_code == 429:
                wait_time = delay * (2 ** (attempt + 2))
                logger.warning(f"Rate limited for code {code}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                continue
            else:
                logger.warning(f"API returned {response.status_code} for code {code}")
                if attempt == MAX_RETRIES - 1:
                    return None

        except Timeout:
            logger.warning(f"Timeout fetching code {code} (attempt {attempt + 1})")
            if attempt == MAX_RETRIES - 1:
                return None
        except RequestException as e:
            logger.warning(f"Request failed for code {code}: {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    logger.error(f"Failed to fetch timeline for code {code} after {MAX_RETRIES} attempts")
    return None


def fetch_timelines_concurrently(fixtures, logger, max_workers=3, delay=DEFAULT_DELAY):
    """Fetch timeline data for multiple fixtures concurrently"""
    results = {}
    failed = []

    def fetch_one(fixture_info):
        code, fixture_id, gameweek = fixture_info
        data = fetch_timeline(code, logger, delay)
        return code, fixture_id, data

    if max_workers == 1:
        for fixture_info in tqdm(fixtures, desc="Fetching timelines"):
            code, fixture_id, data = fetch_one(fixture_info)
            if data is not None:
                results[fixture_id] = (code, data)
            else:
                failed.append(fixture_id)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, f): f for f in fixtures}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching timelines"):
                code, fixture_id, data = future.result()
                if data is not None:
                    results[fixture_id] = (code, data)
                else:
                    failed.append(fixture_id)

    logger.info(f"Fetched {len(results)} timelines successfully, {len(failed)} failed")
    return results, failed


def store_timeline_events(cursor, fixture_id, code, events, team_code_mapping, logger):
    """Insert timeline events for a single fixture"""
    inserted = 0
    for event in events:
        event_type = event.get("eventType")
        if not event_type:
            continue

        team_code_str = event.get("teamId")
        team_id = None
        if team_code_str is not None:
            try:
                team_id = team_code_mapping.get(int(team_code_str))
            except (ValueError, TypeError):
                pass

        player_code_str = event.get("playerId")
        player_code = None
        if player_code_str is not None:
            try:
                player_code = int(player_code_str)
            except (ValueError, TypeError):
                pass

        period_id_str = event.get("periodId")
        period_id = None
        if period_id_str is not None:
            try:
                period_id = int(period_id_str)
            except (ValueError, TypeError):
                pass

        cursor.execute("""
            INSERT INTO pl_match_events
                (fixture_id, code, period_id, minutes, seconds, event_type, tag, team_id, player_code, timestamp_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fixture_id,
            code,
            period_id,
            event.get("minutes"),
            event.get("seconds"),
            event_type,
            event.get("tag"),
            team_id,
            player_code,
            event.get("timestampUtc"),
        ))
        inserted += 1

    return inserted


def clear_timeline_data(cursor, conn, season, logger):
    """Delete all timeline data for fixtures in the given season"""
    cursor.execute("""
        DELETE FROM pl_match_events
        WHERE fixture_id IN (
            SELECT fixture_id FROM fixtures WHERE season = ? AND code IS NOT NULL
        )
    """, (season,))
    deleted = cursor.rowcount
    conn.commit()
    logger.info(f"Cleared {deleted} timeline events for season {season}")


def update_last_update_table(cursor, logger):
    """Record that pl_match_events was updated"""
    try:
        dt = datetime.now()
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("pl_match_events", dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))
    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")


def save_sample_data(code, fixture_id, events, logger):
    """Save a timeline API response as a JSON sample"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = SAMPLES_DIR / f"timeline_{code}_{timestamp}.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(events, f, indent=2)
        logger.debug(f"Saved sample data: {output_file.name}")
    except OSError as e:
        logger.error(f"Failed to save sample data: {e}")


def load_sample_data(logger):
    """Load the most recent sample file for testing"""
    files = list(glob.glob(str(SAMPLES_DIR / "timeline_*.json")))
    if not files:
        logger.error("No sample files found in samples/pl_api/")
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
            logger.info(f"Force refresh: clearing existing timeline data for season {season}")
            if not dry_run:
                clear_timeline_data(cursor, conn, season, logger)

        team_code_mapping = load_team_code_mapping(cursor)
        logger.info(f"Loaded {len(team_code_mapping)} team code mappings")

        fixtures = get_fixtures_needing_timeline(cursor, season, force_all=force_refresh)
        logger.info(f"Found {len(fixtures)} fixtures needing timeline data for season {season}")

        if not fixtures:
            logger.info("No fixtures to process — all up to date")
            return

        timeline_results, failed = fetch_timelines_concurrently(fixtures, logger, max_workers, delay)

        total_inserted = 0
        for fixture_id, (code, events) in timeline_results.items():
            if not events:
                logger.warning(f"Empty timeline for fixture_id {fixture_id} (code {code})")
                continue

            if save_samples:
                save_sample_data(code, fixture_id, events, logger)

            if dry_run:
                logger.info(f"DRY RUN: fixture_id {fixture_id} would insert {len(events)} events")
                continue

            try:
                inserted = store_timeline_events(cursor, fixture_id, code, events, team_code_mapping, logger)
                total_inserted += inserted
                logger.debug(f"fixture_id {fixture_id}: inserted {inserted} events")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing events for fixture_id {fixture_id}: {e}")
                continue

        if not dry_run:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info(f"Committed {total_inserted} timeline events across {len(timeline_results)} fixtures")
        else:
            logger.info("DRY RUN complete — no changes made")

        if failed:
            logger.warning(f"Failed to fetch timeline for {len(failed)} fixtures: {failed}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        conn.close()


def test_with_sample_data(logger):
    """Process the most recent sample file against the database (dry run)"""
    events = load_sample_data(logger)
    if not events:
        return

    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        create_table(cursor)
        team_code_mapping = load_team_code_mapping(cursor)
        logger.info(f"Sample has {len(events)} events")
        logger.info(f"Event types: {set(e.get('eventType') for e in events)}")
        logger.info(f"Team codes seen: {set(e.get('teamId') for e in events if e.get('teamId'))}")
        for code_str in set(e.get('teamId') for e in events if e.get('teamId')):
            try:
                db_id = team_code_mapping.get(int(code_str))
                logger.info(f"  team code {code_str} -> team_id {db_id}")
            except (ValueError, TypeError):
                logger.warning(f"  team code {code_str} -> could not map")
    finally:
        conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch PL match timeline data and store in pl_match_events table')
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
        logger.info(f"Starting PL timeline fetch for season {args.season}...")
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
