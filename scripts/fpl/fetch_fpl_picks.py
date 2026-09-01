#!/usr/bin/env python3
"""
FPL Team Picks Fetching Script

Fetches team picks and gameweek summary data from the FPL API and stores them
in the database for historical tracking.

Endpoints used:
- GET /api/entry/{team_id}/event/{gw}/picks/ - Squad picks per gameweek
- GET /api/entry/{team_id}/history/ - Season history (points, rank, transfers)

Only fetches gameweeks that are finished and not already stored.
"""

import json
import requests
import sqlite3 as sql
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime
from requests.exceptions import RequestException, Timeout

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.config import CURRENT_SEASON

BASE_URL = "https://fantasy.premierleague.com/api/"

db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"
samples_dir = Path(__file__).parent.parent.parent / "samples" / "fpl_picks"
webapp_config_path = Path(__file__).parent.parent.parent / "webapp" / "config.json"

log_dir.mkdir(exist_ok=True)
samples_dir.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_file = log_dir / f"fpl_picks_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def load_fpl_team_id():
    """Load FPL team ID from webapp config"""
    with open(webapp_config_path, 'r') as f:
        config = json.load(f)
    return config["fpl_team_id"]


def get_finished_gameweeks(cursor):
    """Get list of finished gameweek numbers from the database"""
    cursor.execute("""
        SELECT gameweek FROM gameweeks
        WHERE finished = 1
        ORDER BY gameweek
    """)
    return [row[0] for row in cursor.fetchall()]


def get_stored_pick_gameweeks(cursor):
    """Get gameweeks that already have picks stored"""
    cursor.execute("""
        SELECT DISTINCT gameweek FROM fpl_team_picks
        WHERE season = ?
        ORDER BY gameweek
    """, (CURRENT_SEASON,))
    return [row[0] for row in cursor.fetchall()]


def fetch_picks_for_gameweek(team_id, gameweek, logger):
    """Fetch team picks for a specific gameweek from FPL API"""
    url = f"{BASE_URL}entry/{team_id}/event/{gameweek}/picks/"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Picks API returned status {response.status_code} for GW{gameweek}")
            return None
    except Timeout:
        logger.error(f"Picks request timed out for GW{gameweek}")
        return None
    except RequestException as e:
        logger.error(f"Picks request failed for GW{gameweek}: {e}")
        return None


def fetch_season_history(team_id, logger):
    """Fetch full season history from FPL API"""
    url = f"{BASE_URL}entry/{team_id}/history/"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"History API returned status {response.status_code}")
            return None
    except Timeout:
        logger.error("History request timed out")
        return None
    except RequestException as e:
        logger.error(f"History request failed: {e}")
        return None


def build_chip_map(history_data):
    """Build a mapping of gameweek -> chip used from history data"""
    chip_map = {}
    for chip in history_data.get('chips', []):
        chip_map[chip['event']] = chip['name']
    return chip_map


def store_picks(cursor, gameweek, picks_data, logger):
    """Store player picks for a gameweek"""
    picks = picks_data.get('picks', [])
    if not picks:
        logger.warning(f"No picks data for GW{gameweek}")
        return 0

    stored_count = 0
    for pick in picks:
        cursor.execute("""
            INSERT OR REPLACE INTO fpl_team_picks
            (season, gameweek, player_id, position, is_captain, is_vice_captain, multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            CURRENT_SEASON,
            gameweek,
            pick['element'],
            pick['position'],
            1 if pick.get('is_captain') else 0,
            1 if pick.get('is_vice_captain') else 0,
            pick.get('multiplier', 1)
        ))
        stored_count += 1

    return stored_count


def store_gameweek_summary(cursor, gameweek, picks_data, history_gw_data, chip_map, logger):
    """Store gameweek summary from picks entry_history and season history"""
    entry_history = picks_data.get('entry_history', {})

    total_points = entry_history.get('points', history_gw_data.get('points'))
    gameweek_rank = entry_history.get('rank', history_gw_data.get('rank'))
    overall_rank = entry_history.get('overall_rank', history_gw_data.get('overall_rank'))
    bank = entry_history.get('bank', history_gw_data.get('bank'))
    squad_value = entry_history.get('value', history_gw_data.get('value'))
    points_on_bench = entry_history.get('points_on_bench', history_gw_data.get('points_on_bench'))
    transfers_made = entry_history.get('event_transfers', history_gw_data.get('event_transfers'))
    transfers_cost = entry_history.get('event_transfers_cost', history_gw_data.get('event_transfers_cost'))
    chip_used = chip_map.get(gameweek)

    cursor.execute("""
        INSERT OR REPLACE INTO fpl_team_gameweek_summary
        (season, gameweek, total_points, gameweek_rank, overall_rank, bank, squad_value,
         points_on_bench, transfers_made, transfers_cost, chip_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        CURRENT_SEASON, gameweek, total_points, gameweek_rank, overall_rank,
        bank, squad_value, points_on_bench, transfers_made, transfers_cost, chip_used
    ))


def update_last_update_table(cursor, logger):
    """Update the last_update table for upload tracking"""
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y %H:%M:%S")
    timestamp = dt.timestamp()

    cursor.execute("""
        INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
        VALUES (?, ?, ?)
    """, ("fpl_team_picks", now, timestamp))

    logger.info("Updated last_update table for 'fpl_team_picks'")


def save_sample_data(data, logger):
    """Save fetched data as sample for test mode"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = samples_dir / f"fpl_picks_{timestamp}.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Sample data saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to save sample data: {e}")


def load_sample_data(logger):
    """Load most recent sample data for test mode"""
    import glob as glob_mod
    import os
    pattern = samples_dir / "fpl_picks_*.json"
    files = list(glob_mod.glob(str(pattern)))
    if not files:
        logger.error("No sample data files found for fpl_picks")
        return None

    sample_file = max(files, key=lambda f: os.path.getmtime(f))
    logger.info(f"Loading sample data from: {Path(sample_file).name}")
    with open(sample_file, 'r') as f:
        return json.load(f)


def main():
    logger = setup_logging()
    args = parse_arguments()

    logger.info("Starting FPL picks fetch...")
    team_id = load_fpl_team_id()
    logger.info(f"FPL team ID: {team_id}, Season: {CURRENT_SEASON}")

    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        finished_gameweeks = get_finished_gameweeks(cursor)
        stored_gameweeks = get_stored_pick_gameweeks(cursor)
        missing_gameweeks = [gw for gw in finished_gameweeks if gw not in stored_gameweeks]

        logger.info(f"Finished gameweeks: {len(finished_gameweeks)}, "
                    f"Already stored: {len(stored_gameweeks)}, "
                    f"Missing: {len(missing_gameweeks)}")

        if not missing_gameweeks:
            logger.info("All finished gameweeks already have picks stored - nothing to do")
            return

        # Fetch season history once (contains all gameweek summaries)
        history_data = fetch_season_history(team_id, logger)
        if not history_data:
            logger.error("Failed to fetch season history - aborting")
            return

        # Build lookup of history data by gameweek
        history_by_gw = {}
        for gw_data in history_data.get('current', []):
            history_by_gw[gw_data['event']] = gw_data

        chip_map = build_chip_map(history_data)

        # Collect all data for sample saving
        all_fetched_data = {
            'history': history_data,
            'picks_by_gameweek': {}
        }

        total_picks_stored = 0
        for gw in missing_gameweeks:
            logger.info(f"Fetching picks for GW{gw}...")
            picks_data = fetch_picks_for_gameweek(team_id, gw, logger)
            if not picks_data:
                logger.warning(f"Skipping GW{gw} - no picks data returned")
                continue

            all_fetched_data['picks_by_gameweek'][gw] = picks_data

            picks_count = store_picks(cursor, gw, picks_data, logger)
            total_picks_stored += picks_count

            history_gw_data = history_by_gw.get(gw, {})
            store_gameweek_summary(cursor, gw, picks_data, history_gw_data, chip_map, logger)

            logger.info(f"GW{gw}: stored {picks_count} picks")

        if total_picks_stored > 0:
            update_last_update_table(cursor, logger)
            save_sample_data(all_fetched_data, logger)

        conn.commit()
        logger.info(f"Completed: stored picks for {len(missing_gameweeks)} gameweeks "
                    f"({total_picks_stored} total picks)")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error fetching FPL picks: {e}")
        raise
    finally:
        conn.close()


def test_with_sample_data():
    """Test mode: load sample data and process into database"""
    logger = setup_logging()
    logger.info("Starting FPL picks test with sample data...")

    sample_data = load_sample_data(logger)
    if not sample_data:
        logger.error("No sample data available for testing")
        return

    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        history_data = sample_data.get('history', {})
        picks_by_gw = sample_data.get('picks_by_gameweek', {})

        history_by_gw = {}
        for gw_data in history_data.get('current', []):
            history_by_gw[gw_data['event']] = gw_data

        chip_map = build_chip_map(history_data)

        total_picks = 0
        for gw_str, picks_data in picks_by_gw.items():
            gw = int(gw_str)
            picks_count = store_picks(cursor, gw, picks_data, logger)
            total_picks += picks_count

            history_gw_data = history_by_gw.get(gw, {})
            store_gameweek_summary(cursor, gw, picks_data, history_gw_data, chip_map, logger)
            logger.info(f"GW{gw}: stored {picks_count} picks")

        if total_picks > 0:
            update_last_update_table(cursor, logger)

        conn.commit()
        logger.info(f"Test completed: processed {len(picks_by_gw)} gameweeks ({total_picks} picks)")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error in test mode: {e}")
        raise
    finally:
        conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch FPL team picks and store in database')
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode with sample data')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    if args.test:
        test_with_sample_data()
    else:
        main()
