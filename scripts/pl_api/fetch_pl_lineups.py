#!/usr/bin/env python3
"""
Premier League Lineup Data Fetching Script

Fetches match lineup data from the PL API for finished fixtures and stores it across
two tables:
  - pl_lineups: one row per team per fixture (formation, manager)
  - pl_lineup_players: one row per player per fixture (starters and substitutes)

API endpoint: https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v3/matches/<pulse_id>/lineups

Team IDs in the API response are team codes that map to teams.code in the database.
Player IDs in the API response are player codes that map to fpl_players_bootstrap.code.

COMMAND LINE OPTIONS:
- --test: Process most recent sample file without hitting the API
- --dry-run: Fetch data but make no database changes
- --max-workers N: Concurrent API requests (default: 3)
- --delay N: Delay between requests in seconds (default: 2.0)
- --season SEASON: Season to process (default: current season)
- --force-refresh: Clear existing lineup data and re-fetch all finished fixtures
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

BASE_URL = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v3/matches/{code}/lineups"
DEFAULT_DELAY = 2.0
MAX_RETRIES = 3

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"
SAMPLES_DIR = PROJECT_ROOT / "samples" / "pl_api"

LOG_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_file = LOG_DIR / f"pl_lineups_{datetime.now().strftime('%Y%m%d')}.log"
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
    """Keep only the latest N lineup sample files"""
    files = list(glob.glob(str(SAMPLES_DIR / "lineups_*.json")))
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


def create_tables(cursor):
    """Create pl_lineups and pl_lineup_players tables and indexes if they don't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pl_lineups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            pulse_id INTEGER NOT NULL,
            team_id INTEGER,
            formation TEXT,
            manager_name TEXT,
            manager_code INTEGER,
            FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pl_lineup_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            pulse_id INTEGER NOT NULL,
            team_id INTEGER,
            player_code INTEGER,
            first_name TEXT,
            last_name TEXT,
            known_name TEXT,
            shirt_number TEXT,
            is_captain INTEGER DEFAULT 0,
            position TEXT,
            sub_position TEXT,
            is_starter INTEGER DEFAULT 1,
            FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_lineups_fixture_id
        ON pl_lineups(fixture_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_lineup_players_fixture_id
        ON pl_lineup_players(fixture_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_lineup_players_player_code
        ON pl_lineup_players(player_code)
    """)


def load_team_code_mapping(cursor):
    """Load mapping from PL API team code to database team_id"""
    cursor.execute("SELECT code, team_id FROM teams WHERE code IS NOT NULL")
    return {code: team_id for code, team_id in cursor.fetchall()}


def get_fixtures_needing_lineups(cursor, season, force_all=False):
    """Get finished fixtures that are missing lineup data"""
    if force_all:
        cursor.execute("""
            SELECT f.pulse_id, f.fixture_id, f.gameweek
            FROM fixtures f
            WHERE f.pulse_id IS NOT NULL
            AND f.provisional_finished = 1
            AND f.season = ?
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    else:
        cursor.execute("""
            SELECT f.pulse_id, f.fixture_id, f.gameweek
            FROM fixtures f
            LEFT JOIN pl_lineups pl ON f.fixture_id = pl.fixture_id
            WHERE f.pulse_id IS NOT NULL
            AND f.provisional_finished = 1
            AND f.season = ?
            AND pl.fixture_id IS NULL
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    return cursor.fetchall()


def fetch_lineups(pulse_id, logger, delay=DEFAULT_DELAY):
    """Fetch lineup data from the PL API with retry and rate limiting"""
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

    logger.error(f"Failed to fetch lineups for pulse_id {pulse_id} after {MAX_RETRIES} attempts")
    return None


def fetch_lineups_concurrently(fixtures, logger, max_workers=3, delay=DEFAULT_DELAY):
    """Fetch lineup data for multiple fixtures concurrently"""
    results = {}
    failed = []

    def fetch_one(fixture_info):
        pulse_id, fixture_id, gameweek = fixture_info
        data = fetch_lineups(pulse_id, logger, delay)
        return pulse_id, fixture_id, data

    if max_workers == 1:
        for fixture_info in tqdm(fixtures, desc="Fetching lineups"):
            pulse_id, fixture_id, data = fetch_one(fixture_info)
            if data is not None:
                results[fixture_id] = (pulse_id, data)
            else:
                failed.append(fixture_id)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, f): f for f in fixtures}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching lineups"):
                pulse_id, fixture_id, data = future.result()
                if data is not None:
                    results[fixture_id] = (pulse_id, data)
                else:
                    failed.append(fixture_id)

    logger.info(f"Fetched {len(results)} lineups successfully, {len(failed)} failed")
    return results, failed


def store_team_lineup(cursor, fixture_id, pulse_id, team_key, team_data, team_code_mapping, logger):
    """Insert lineup and player rows for one team in a fixture"""
    team_code_str = team_data.get("teamId")
    team_id = None
    if team_code_str is not None:
        try:
            team_id = team_code_mapping.get(int(team_code_str))
            if team_id is None:
                logger.warning(f"No team_id mapping for team code {team_code_str} ({team_key}, fixture_id {fixture_id})")
        except (ValueError, TypeError):
            logger.warning(f"Invalid team code '{team_code_str}' ({team_key}, fixture_id {fixture_id})")

    formation_str = team_data.get("formation", {}).get("formation")

    manager_name = None
    manager_code = None
    managers = team_data.get("managers", [])
    if managers:
        m = managers[0]
        first = m.get("firstName", "")
        last = m.get("lastName", "")
        manager_name = f"{first} {last}".strip() or None
        manager_id_str = m.get("id")
        if manager_id_str is not None:
            try:
                manager_code = int(manager_id_str)
            except (ValueError, TypeError):
                pass

    cursor.execute("""
        INSERT INTO pl_lineups (fixture_id, pulse_id, team_id, formation, manager_name, manager_code)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (fixture_id, pulse_id, team_id, formation_str, manager_name, manager_code))

    players_inserted = 0
    for player in team_data.get("players", []):
        player_code_str = player.get("id")
        player_code = None
        if player_code_str is not None:
            try:
                player_code = int(player_code_str)
            except (ValueError, TypeError):
                pass

        position = player.get("position", "")
        is_starter = 0 if position == "Substitute" else 1

        cursor.execute("""
            INSERT INTO pl_lineup_players
                (fixture_id, pulse_id, team_id, player_code, first_name, last_name, known_name,
                 shirt_number, is_captain, position, sub_position, is_starter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fixture_id,
            pulse_id,
            team_id,
            player_code,
            player.get("firstName"),
            player.get("lastName"),
            player.get("knownName"),
            player.get("shirtNum"),
            1 if player.get("isCaptain") else 0,
            position,
            player.get("subPosition"),
            is_starter,
        ))
        players_inserted += 1

    return players_inserted


def store_lineup_data(cursor, fixture_id, pulse_id, data, team_code_mapping, logger):
    """Insert all lineup data for a fixture (both teams)"""
    total_players = 0
    for team_key in ("home_team", "away_team"):
        team_data = data.get(team_key)
        if not team_data:
            logger.warning(f"Missing {team_key} data for fixture_id {fixture_id}")
            continue
        total_players += store_team_lineup(cursor, fixture_id, pulse_id, team_key, team_data, team_code_mapping, logger)
    return total_players


def clear_lineup_data(cursor, conn, season, logger):
    """Delete all lineup data for fixtures in the given season"""
    cursor.execute("""
        DELETE FROM pl_lineup_players
        WHERE fixture_id IN (
            SELECT fixture_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
        )
    """, (season,))
    players_deleted = cursor.rowcount

    cursor.execute("""
        DELETE FROM pl_lineups
        WHERE fixture_id IN (
            SELECT fixture_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
        )
    """, (season,))
    lineups_deleted = cursor.rowcount

    conn.commit()
    logger.info(f"Cleared {lineups_deleted} lineup records and {players_deleted} player records for season {season}")


def update_last_update_table(cursor, logger):
    """Record that pl_lineup_players was updated"""
    try:
        dt = datetime.now()
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("pl_lineup_players", dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))
    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")


def save_sample_data(pulse_id, data, logger):
    """Save a lineup API response as a JSON sample"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = SAMPLES_DIR / f"lineups_{pulse_id}_{timestamp}.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved sample data: {output_file.name}")
    except OSError as e:
        logger.error(f"Failed to save sample data: {e}")


def load_sample_data(logger):
    """Load the most recent lineup sample file for testing"""
    files = list(glob.glob(str(SAMPLES_DIR / "lineups_*.json")))
    if not files:
        logger.error("No lineup sample files found in samples/pl_api/")
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
        create_tables(cursor)

        if force_refresh:
            logger.info(f"Force refresh: clearing existing lineup data for season {season}")
            if not dry_run:
                clear_lineup_data(cursor, conn, season, logger)

        team_code_mapping = load_team_code_mapping(cursor)
        logger.info(f"Loaded {len(team_code_mapping)} team code mappings")

        fixtures = get_fixtures_needing_lineups(cursor, season, force_all=force_refresh)
        logger.info(f"Found {len(fixtures)} fixtures needing lineup data for season {season}")

        if not fixtures:
            logger.info("No fixtures to process — all up to date")
            return

        lineup_results, failed = fetch_lineups_concurrently(fixtures, logger, max_workers, delay)

        total_players = 0
        for fixture_id, (pulse_id, data) in lineup_results.items():
            if save_samples:
                save_sample_data(pulse_id, data, logger)

            if dry_run:
                home_count = len(data.get("home_team", {}).get("players", []))
                away_count = len(data.get("away_team", {}).get("players", []))
                logger.info(f"DRY RUN: fixture_id {fixture_id} would insert {home_count + away_count} players")
                continue

            try:
                inserted = store_lineup_data(cursor, fixture_id, pulse_id, data, team_code_mapping, logger)
                total_players += inserted
                logger.debug(f"fixture_id {fixture_id}: inserted {inserted} players")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing lineup for fixture_id {fixture_id}: {e}")
                continue

        if not dry_run:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info(f"Committed lineups for {len(lineup_results)} fixtures ({total_players} players total)")
        else:
            logger.info("DRY RUN complete — no changes made")

        if failed:
            logger.warning(f"Failed to fetch lineups for {len(failed)} fixtures: {failed}")

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

    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        team_code_mapping = load_team_code_mapping(cursor)
        for team_key in ("home_team", "away_team"):
            team_data = data.get(team_key, {})
            team_code = team_data.get("teamId")
            team_id = team_code_mapping.get(int(team_code)) if team_code else None
            formation = team_data.get("formation", {}).get("formation")
            players = team_data.get("players", [])
            starters = [p for p in players if p.get("position") != "Substitute"]
            subs = [p for p in players if p.get("position") == "Substitute"]
            managers = team_data.get("managers", [])
            manager = f"{managers[0].get('firstName')} {managers[0].get('lastName')}" if managers else "unknown"
            logger.info(f"{team_key}: team_code={team_code} -> team_id={team_id}, formation={formation}, manager={manager}")
            logger.info(f"  {len(starters)} starters, {len(subs)} substitutes")
    finally:
        conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch PL lineup data and store in pl_lineups and pl_lineup_players tables')
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
        logger.info(f"Starting PL lineup fetch for season {args.season}...")
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
