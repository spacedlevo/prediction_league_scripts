#!/usr/bin/env python3
"""
Sync odds_api_name for all available Premier League teams.

Fetches the current participant list from the Odds API and matches each team
against the database. Run this once per season after new_season_setup.py to
ensure newly promoted teams have their odds_api_name set correctly.

Usage:
    python scripts/odds-api/sync_odds_team_names.py --dry-run   # Preview changes
    python scripts/odds-api/sync_odds_team_names.py             # Apply changes
"""

import json
import sqlite3 as sql
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime
import requests
from requests.exceptions import RequestException, Timeout

db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
keys_file = Path(__file__).parent.parent.parent / "keys.json"
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# Maps Odds API team name (lowercase) to our abbreviated db team_name (lowercase).
# Add entries here whenever a new team has a name mismatch between the API and the database.
ODDS_API_NAME_ALIASES = {
    "nottingham forest": "nott'm forest",
    "manchester city": "man city",
    "manchester united": "man utd",
    "tottenham hotspur": "tottenham",
    "brighton and hove albion": "brighton",
    "wolverhampton wanderers": "wolves",
    "west ham united": "west ham",
    "leicester city": "leicester",
    "sheffield united": "sheffield utd",
    "ipswich town": "ipswich",
    "newcastle united": "newcastle",
    "leeds united": "leeds",
}


def setup_logging():
    log_file = log_dir / f"sync_odds_team_names_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
        description='Sync odds_api_name for all available Premier League teams'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview all changes without modifying the database')
    return parser.parse_args()


def load_api_key():
    with open(keys_file, 'r') as f:
        return json.load(f)["odds_api_key"]


def fetch_participants(api_key, logger):
    """Fetch the canonical team name list from the Odds API participants endpoint"""
    url = "https://api.the-odds-api.com/v4/sports/soccer_epl/participants"
    try:
        response = requests.get(url, params={"apiKey": api_key}, timeout=30)
        if response.status_code == 200:
            participants = response.json()
            logger.info(f"Fetched {len(participants)} participants from Odds API")
            return participants
        else:
            logger.error(f"Odds API returned status {response.status_code}: {response.text}")
            return None
    except Timeout:
        logger.error("Odds API request timed out")
        return None
    except RequestException as e:
        logger.error(f"Odds API request failed: {e}")
        return None


def load_available_teams(cursor):
    """Load all currently available (promoted/active) teams from the database"""
    cursor.execute("""
        SELECT team_id, team_name, odds_api_name
        FROM teams
        WHERE available = 1
        ORDER BY team_name
    """)
    return cursor.fetchall()


def build_sync_plan(db_teams, participants):
    """
    Match each available DB team to an Odds API participant name.

    Returns dict with:
      confirmed    - odds_api_name already set and still valid in the API
      to_update    - odds_api_name is NULL but was auto-matched via name/alias
      stale        - odds_api_name set but no longer in the API (team name may have changed)
      unmatched    - no odds_api_name and no auto-match found (needs a new alias entry)
    """
    # Build a lookup: lowercase participant name -> original-cased name
    participant_map = {p["full_name"].lower(): p["full_name"] for p in participants}

    confirmed = []
    to_update = []
    stale = []
    unmatched = []

    for team_id, team_name, odds_api_name in db_teams:
        if odds_api_name:
            # Verify the stored name is still in the current participant list
            if odds_api_name.lower() in participant_map:
                confirmed.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'odds_api_name': odds_api_name,
                })
            else:
                # Name set but not recognised by the API — try to re-match
                new_name = _auto_match(team_name, participant_map)
                stale.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'old_odds_api_name': odds_api_name,
                    'new_odds_api_name': new_name,
                })
        else:
            # No mapping yet — try to auto-match
            new_name = _auto_match(team_name, participant_map)
            if new_name:
                to_update.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'odds_api_name': new_name,
                })
            else:
                unmatched.append({
                    'team_id': team_id,
                    'team_name': team_name,
                })

    return {
        'confirmed': sorted(confirmed, key=lambda t: t['team_name']),
        'to_update': sorted(to_update, key=lambda t: t['team_name']),
        'stale': sorted(stale, key=lambda t: t['team_name']),
        'unmatched': sorted(unmatched, key=lambda t: t['team_name']),
    }


def _auto_match(team_name, participant_map):
    """Try to find an Odds API participant name for a given db team_name"""
    team_lower = team_name.lower()

    # Direct exact match (e.g. "Arsenal" == "arsenal")
    if team_lower in participant_map:
        return participant_map[team_lower].lower()

    # Alias lookup (e.g. "man city" -> "Manchester City")
    for api_name_lower, db_name in ODDS_API_NAME_ALIASES.items():
        if db_name == team_lower and api_name_lower in participant_map:
            return participant_map[api_name_lower].lower()

    return None


def display_plan(plan, logger):
    logger.info("")
    logger.info("=" * 70)
    logger.info("ODDS API TEAM NAME SYNC PLAN")
    logger.info("=" * 70)

    logger.info(f"\nAlready confirmed ({len(plan['confirmed'])}) — no changes needed:")
    for team in plan['confirmed']:
        logger.info(f"  {team['team_name']:<22} odds_api_name = '{team['odds_api_name']}'")

    if plan['to_update']:
        logger.info(f"\nTo be set ({len(plan['to_update'])}) — odds_api_name is NULL, auto-matched:")
        for team in plan['to_update']:
            logger.info(f"  {team['team_name']:<22} -> '{team['odds_api_name']}'")

    if plan['stale']:
        logger.info(f"\nStale mappings ({len(plan['stale'])}) — current value not found in API:")
        for team in plan['stale']:
            if team['new_odds_api_name']:
                logger.info(f"  {team['team_name']:<22} '{team['old_odds_api_name']}' -> '{team['new_odds_api_name']}'")
            else:
                logger.warning(
                    f"  {team['team_name']:<22} '{team['old_odds_api_name']}' -> NO MATCH FOUND"
                )

    if plan['unmatched']:
        logger.info(f"\nUnmatched ({len(plan['unmatched'])}) — needs a new entry in ODDS_API_NAME_ALIASES:")
        for team in plan['unmatched']:
            logger.warning(f"  {team['team_name']} (team_id={team['team_id']}) — no match found")

    logger.info("")


def apply_sync(cursor, plan, logger):
    """Write all resolved mappings to the database inside the caller's transaction"""
    update_count = 0

    for team in plan['to_update']:
        cursor.execute(
            "UPDATE teams SET odds_api_name = ? WHERE team_id = ?",
            (team['odds_api_name'], team['team_id'])
        )
        logger.info(f"Set odds_api_name='{team['odds_api_name']}' for {team['team_name']}")
        update_count += 1

    for team in plan['stale']:
        if team['new_odds_api_name']:
            cursor.execute(
                "UPDATE teams SET odds_api_name = ? WHERE team_id = ?",
                (team['new_odds_api_name'], team['team_id'])
            )
            logger.info(
                f"Updated odds_api_name for {team['team_name']}: "
                f"'{team['old_odds_api_name']}' -> '{team['new_odds_api_name']}'"
            )
            update_count += 1

    if update_count > 0:
        dt = datetime.now()
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES ('teams', ?, ?)
        """, (dt.strftime("%d-%m-%Y %H:%M:%S"), dt.timestamp()))

    return update_count


def main():
    args = parse_arguments()
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("ODDS API TEAM NAME SYNC")
    logger.info("DRY RUN MODE - no changes will be made" if args.dry_run else "LIVE MODE - database will be modified")
    logger.info("=" * 70)

    api_key = load_api_key()
    participants = fetch_participants(api_key, logger)
    if not participants:
        logger.error("Aborting - could not fetch participants from Odds API")
        return 1

    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        db_teams = load_available_teams(cursor)
        logger.info(f"Loaded {len(db_teams)} available teams from database")

        plan = build_sync_plan(db_teams, participants)
        display_plan(plan, logger)

        needs_manual = [t for t in plan['stale'] if not t['new_odds_api_name']] + plan['unmatched']
        if needs_manual:
            logger.warning(
                f"{len(needs_manual)} team(s) could not be auto-matched. "
                f"Add the correct Odds API name to ODDS_API_NAME_ALIASES in this script and re-run."
            )

        if args.dry_run:
            logger.info("DRY RUN complete - run without --dry-run to apply these changes")
            return 0

        update_count = apply_sync(cursor, plan, logger)
        conn.commit()

        if update_count > 0:
            logger.info(f"Sync complete — updated {update_count} team(s)")
        else:
            logger.info("Sync complete — no updates needed")

        return 0

    except Exception as e:
        conn.rollback()
        logger.error(f"Sync failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
