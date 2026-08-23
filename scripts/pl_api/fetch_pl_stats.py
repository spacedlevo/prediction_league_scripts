#!/usr/bin/env python3
"""
Premier League Match Stats Fetching Script

Fetches per-team match statistics from the PL API for finished fixtures and stores
them in the pl_match_stats table (one row per team per fixture, 192 stat columns).

API endpoint: https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v3/matches/<pulse_id>/stats

Team IDs in the API response are team codes that map to teams.code in the database.
The nested fastestPlayer.playerId is stored as fastest_player_code (maps to fpl_players_bootstrap.code).

COMMAND LINE OPTIONS:
- --test: Process most recent sample file without hitting the API
- --dry-run: Fetch data but make no database changes
- --max-workers N: Concurrent API requests (default: 3)
- --delay N: Delay between requests in seconds (default: 2.0)
- --season SEASON: Season to process (default: current season)
- --force-refresh: Clear existing stats and re-fetch all finished fixtures
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

BASE_URL = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v3/matches/{code}/stats"
DEFAULT_DELAY = 2.0
MAX_RETRIES = 3

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"
SAMPLES_DIR = PROJECT_ROOT / "samples" / "pl_api"

LOG_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# All stat fields sourced from API — INTEGER unless listed in REAL_STAT_FIELDS
INTEGER_STAT_FIELDS = [
    "accurateBackZonePass", "accurateChippedPass", "accurateCross", "accurateCrossNocorner",
    "accurateFlickOn", "accurateFwdZonePass", "accurateGoalKicks", "accurateKeeperSweeper",
    "accurateKeeperThrows", "accurateLaunches", "accurateLayoffs", "accurateLongBalls",
    "accuratePass", "accuratePullBack", "accurateThrows", "aerialLost", "aerialWon",
    "attAssistOpenplay", "attBxCentre", "attBxLeft", "attBxRight", "attCmissHigh",
    "attCmissLeft", "attCorner", "attFastbreak", "attFreekickGoal", "attFreekickMiss",
    "attFreekickTotal", "attGoalHighCentre", "attGoalHighLeft", "attGoalHighRight",
    "attGoalLowCentre", "attGoalLowLeft", "attGoalLowRight", "attHdGoal", "attHdTarget",
    "attHdTotal", "attIboxBlocked", "attIboxGoal", "attIboxMiss", "attIboxTarget",
    "attLfGoal", "attLfTarget", "attLfTotal", "attMissHigh", "attMissHighRight",
    "attMissLeft", "attMissRight", "attOboxBlocked", "attOboxGoal", "attOboxMiss",
    "attOboxTarget", "attObpGoal", "attObxCentre", "attOpenplay", "attPenGoal",
    "attRfGoal", "attRfTarget", "attRfTotal", "attSvHighCentre", "attSvLowCentre",
    "attSvLowLeft", "attSvLowRight", "attemptedTackleFoul", "attemptsConcededIbox",
    "attemptsConcededObox", "attemptsIbox", "attemptsObox", "backwardPass", "ballRecovery",
    "bigChanceCreated", "bigChanceMissed", "bigChanceScored", "blockedCross", "blockedPass",
    "blockedScoringAtt", "challengeLost", "cleanSheet", "clearanceOffLine", "cornerTaken",
    "crosses18yard", "crosses18yardplus", "defenderGoals", "dispossessed", "divingSave",
    "duelLost", "duelWon", "effectiveBlockedCross", "effectiveClearance", "effectiveHeadClearance",
    "errorLeadToGoal", "errorLeadToShot", "finalThirdEntries", "fkFoulLost", "fkFoulWon",
    "forwardGoals", "fouledFinalThird", "freekickCross", "freekickTotal", "fwdPass",
    "goalAssist", "goalAssistIntentional", "goalAssistOpenplay", "goalFastbreak", "goalKicks",
    "goals", "goalsConceded", "goalsConcededIbox", "goalsConcededObox", "goalsOpenplay",
    "goodHighClaim", "headClearance", "interception", "interceptionWon", "interceptionsInBox",
    "keeperGoals", "keeperThrows", "leftsidePass", "longPassOwnToOpp", "longPassOwnToOppSuccess",
    "lostCorners", "midfielderGoals", "offtargetAttAssist", "ontargetAttAssist",
    "ontargetScoringAtt", "openPlayPass", "outfielderBlock", "overrun", "ownGoals",
    "passesLeft", "passesRight", "penAreaEntries", "possLostAll", "possLostCtrl",
    "possWonAtt3rd", "possWonDef3rd", "possWonMid3rd", "putThrough", "redCard",
    "rightsidePass", "savedIbox", "savedObox", "saves", "shieldBallOop", "shotFastbreak",
    "shotOffTarget", "sixYardBlock", "subsGoals", "subsMade", "successfulFinalThirdPasses",
    "successfulOpenPlayPass", "successfulPutThrough", "totalAttAssist", "totalBackZonePass",
    "totalChippedPass", "totalClearance", "totalContest", "totalCornersIntobox", "totalCross",
    "totalCrossNocorner", "totalFastbreak", "totalFinalThirdPasses", "totalFlickOn",
    "totalFwdZonePass", "totalHighClaim", "totalKeeperSweeper", "totalLaunches", "totalLayoffs",
    "totalLongBalls", "totalOffside", "totalPass", "totalPullBack", "totalRedCard",
    "totalScoringAtt", "totalTackle", "totalThroughBall", "totalThrows", "totalYelCard",
    "touches", "touchesInOppBox", "unsuccessfulTouch", "winningGoal", "wonContest",
    "wonCorners", "wonTackle", "yellowCard",
]

REAL_STAT_FIELDS = [
    "expectedAssists",
    "expectedGoals",
    "expectedGoalsFreekick",
    "expectedGoalsOnTarget",
    "expectedGoalsOnTargetConceded",
    "possessionPercentage",
]

ALL_STAT_FIELDS = INTEGER_STAT_FIELDS + REAL_STAT_FIELDS


def setup_logging():
    log_file = LOG_DIR / f"pl_stats_{datetime.now().strftime('%Y%m%d')}.log"
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
    """Keep only the latest N stats sample files"""
    files = list(glob.glob(str(SAMPLES_DIR / "stats_*.json")))
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
    """Create pl_match_stats table and indexes if they don't exist"""
    int_col_defs = "\n".join(f"    {f} INTEGER," for f in INTEGER_STAT_FIELDS)
    real_col_defs = "\n".join(f"    {f} REAL," for f in REAL_STAT_FIELDS)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS pl_match_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            pulse_id INTEGER NOT NULL,
            team_id INTEGER,
            side TEXT,
            fastest_player_code INTEGER,
{int_col_defs}
{real_col_defs}
            FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_match_stats_fixture_id
        ON pl_match_stats(fixture_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pl_match_stats_team_id
        ON pl_match_stats(team_id)
    """)


def load_team_code_mapping(cursor):
    """Load mapping from PL API team code to database team_id"""
    cursor.execute("SELECT code, team_id FROM teams WHERE code IS NOT NULL")
    return {code: team_id for code, team_id in cursor.fetchall()}


def get_fixtures_needing_stats(cursor, season, force_all=False):
    """Get finished fixtures that are missing stats data"""
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
            LEFT JOIN pl_match_stats pms ON f.fixture_id = pms.fixture_id
            WHERE f.pulse_id IS NOT NULL
            AND f.finished = 1
            AND f.season = ?
            AND pms.fixture_id IS NULL
            ORDER BY f.gameweek, f.fixture_id
        """, (season,))
    return cursor.fetchall()


def fetch_stats(pulse_id, logger, delay=DEFAULT_DELAY):
    """Fetch match stats from the PL API with retry and rate limiting"""
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

    logger.error(f"Failed to fetch stats for pulse_id {pulse_id} after {MAX_RETRIES} attempts")
    return None


def fetch_stats_concurrently(fixtures, logger, max_workers=3, delay=DEFAULT_DELAY):
    """Fetch stats for multiple fixtures concurrently"""
    results = {}
    failed = []

    def fetch_one(fixture_info):
        pulse_id, fixture_id, gameweek = fixture_info
        data = fetch_stats(pulse_id, logger, delay)
        return pulse_id, fixture_id, data

    if max_workers == 1:
        for fixture_info in tqdm(fixtures, desc="Fetching stats"):
            pulse_id, fixture_id, data = fetch_one(fixture_info)
            if data is not None:
                results[fixture_id] = (pulse_id, data)
            else:
                failed.append(fixture_id)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, f): f for f in fixtures}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching stats"):
                pulse_id, fixture_id, data = future.result()
                if data is not None:
                    results[fixture_id] = (pulse_id, data)
                else:
                    failed.append(fixture_id)

    logger.info(f"Fetched stats for {len(results)} fixtures, {len(failed)} failed")
    return results, failed


def store_team_stats(cursor, fixture_id, pulse_id, team_entry, team_code_mapping, logger):
    """Insert one row of stats for a single team in a fixture"""
    team_code_str = team_entry.get("teamId")
    team_id = None
    if team_code_str is not None:
        try:
            team_id = team_code_mapping.get(int(team_code_str))
            if team_id is None:
                logger.warning(f"No team_id mapping for team code {team_code_str} (fixture_id {fixture_id})")
        except (ValueError, TypeError):
            logger.warning(f"Invalid team code '{team_code_str}' (fixture_id {fixture_id})")

    stats = team_entry.get("stats", {})

    fastest_player_code = None
    fp = stats.get("fastestPlayer")
    if fp and fp.get("playerId"):
        try:
            fastest_player_code = int(fp["playerId"])
        except (ValueError, TypeError):
            pass

    # Build column list and values dynamically from known stat fields
    stat_values = {field: stats.get(field) for field in ALL_STAT_FIELDS}

    columns = ["fixture_id", "pulse_id", "team_id", "side", "fastest_player_code"] + ALL_STAT_FIELDS
    placeholders = ", ".join("?" for _ in columns)
    col_str = ", ".join(columns)

    values = [
        fixture_id,
        pulse_id,
        team_id,
        team_entry.get("side"),
        fastest_player_code,
    ] + [stat_values[f] for f in ALL_STAT_FIELDS]

    cursor.execute(
        f"INSERT INTO pl_match_stats ({col_str}) VALUES ({placeholders})",
        values,
    )


def store_match_stats(cursor, fixture_id, pulse_id, data, team_code_mapping, logger):
    """Insert stats rows for both teams in a fixture"""
    for team_entry in data:
        store_team_stats(cursor, fixture_id, pulse_id, team_entry, team_code_mapping, logger)


def clear_stats_data(cursor, conn, season, logger):
    """Delete all stats rows for fixtures in the given season"""
    cursor.execute("""
        DELETE FROM pl_match_stats
        WHERE fixture_id IN (
            SELECT fixture_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
        )
    """, (season,))
    deleted = cursor.rowcount
    conn.commit()
    logger.info(f"Cleared {deleted} stats rows for season {season}")


def update_last_update_table(cursor, logger):
    """Record that pl_match_stats was updated"""
    try:
        dt = datetime.now()
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("pl_match_stats", dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))
    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")


def save_sample_data(pulse_id, data, logger):
    """Save a stats API response as a JSON sample"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = SAMPLES_DIR / f"stats_{pulse_id}_{timestamp}.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved sample data: {output_file.name}")
    except OSError as e:
        logger.error(f"Failed to save sample data: {e}")


def load_sample_data(logger):
    """Load the most recent stats sample file for testing"""
    files = list(glob.glob(str(SAMPLES_DIR / "stats_*.json")))
    if not files:
        logger.error("No stats sample files found in samples/pl_api/")
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
            logger.info(f"Force refresh: clearing existing stats for season {season}")
            if not dry_run:
                clear_stats_data(cursor, conn, season, logger)

        team_code_mapping = load_team_code_mapping(cursor)
        logger.info(f"Loaded {len(team_code_mapping)} team code mappings")

        fixtures = get_fixtures_needing_stats(cursor, season, force_all=force_refresh)
        logger.info(f"Found {len(fixtures)} fixtures needing stats for season {season}")

        if not fixtures:
            logger.info("No fixtures to process — all up to date")
            return

        stats_results, failed = fetch_stats_concurrently(fixtures, logger, max_workers, delay)

        fixtures_stored = 0
        for fixture_id, (pulse_id, data) in stats_results.items():
            if not data:
                logger.warning(f"Empty stats response for fixture_id {fixture_id}")
                continue

            if save_samples:
                save_sample_data(pulse_id, data, logger)

            if dry_run:
                logger.info(f"DRY RUN: fixture_id {fixture_id} would insert {len(data)} team stat rows")
                continue

            try:
                store_match_stats(cursor, fixture_id, pulse_id, data, team_code_mapping, logger)
                fixtures_stored += 1
                logger.debug(f"fixture_id {fixture_id}: stored stats for {len(data)} teams")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing stats for fixture_id {fixture_id}: {e}")
                continue

        if not dry_run:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info(f"Committed stats for {fixtures_stored} fixtures ({fixtures_stored * 2} team rows)")
        else:
            logger.info("DRY RUN complete — no changes made")

        if failed:
            logger.warning(f"Failed to fetch stats for {len(failed)} fixtures: {failed}")

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
        for entry in data:
            side = entry.get("side")
            team_code = entry.get("teamId")
            team_id = team_code_mapping.get(int(team_code)) if team_code else None
            stats = entry.get("stats", {})
            logger.info(
                f"{side}: team_code={team_code} -> team_id={team_id}, "
                f"goals={stats.get('goals')}, xG={stats.get('expectedGoals')}, "
                f"possession={stats.get('possessionPercentage')}%, "
                f"passes={stats.get('totalPass')} ({stats.get('accuratePass')} accurate)"
            )
    finally:
        conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch PL match stats and store in pl_match_stats table')
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
        logger.info(f"Starting PL stats fetch for season {args.season}...")
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
