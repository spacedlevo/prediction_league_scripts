#!/usr/bin/env python3
"""
Pulse Live API Data Fetching Script

Fetches detailed match data from Pulse Live API including match officials, team lists,
and match events. Designed for efficient data collection with change detection,
error handling, and minimal API usage.

PERFORMANCE OPTIMIZATIONS:
- Change Detection: Only fetches data for finished fixtures missing pulse data
- Rate Limiting: Respectful API usage with configurable delays
- Error Recovery: Robust handling of API failures with retry logic
- Concurrent Processing: Optional threading for faster data collection
- Smart Caching: Saves successful responses to avoid re-fetching

DATABASE INTEGRATION:
- Uses existing tables: match_officials, team_list, match_events
- Foreign key relationships via pulse_id to fixtures table
- Team mapping between pulse team IDs and database team_id
- Transaction integrity with rollback on errors

COMMAND LINE OPTIONS:
- --max-workers N: Concurrent API requests (default: 3, recommended: 1-5)
- --delay N: Delay between requests in seconds (default: 2.0)
- --dry-run: Preview changes without database updates
- --test: Use cached sample data for development
- --season: Process specific season (default: current season)
- --cleanup-count: Number of sample files to keep (default: 10)
- --force-all: Force fetch all fixtures regardless of existing data
- --force-refresh: Delete existing pulse data and re-fetch all fixtures
- --fix-team-ids: Drop tables and re-fetch to fix team_id data quality issues

DATA QUALITY FIX:
The --fix-team-ids flag addresses historical inconsistencies where early gameweeks
stored Pulse API team IDs instead of database team_ids in the match_events table.
This flag drops and recreates all pulse API tables with proper foreign key constraints,
then re-fetches all data with correct team_id mappings.
"""

import json
import requests
import sqlite3 as sql
import time
import logging
import argparse
import glob
import os
from pathlib import Path
from datetime import datetime
from random import uniform
from tqdm import tqdm
from requests.exceptions import RequestException, Timeout
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Any

# Configuration
BASE_URL = "https://footballapi.pulselive.com/football/fixtures/{id}"
CURRENT_SEASON = "2025/2026"
DEFAULT_DELAY = 2.0  # Seconds between API requests
MAX_RETRIES = 3

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"
SAMPLES_DIR = PROJECT_ROOT / "samples" / "pulse_api"

# Create directories
LOG_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> logging.Logger:
    """Setup logging with both file and console output"""
    log_file = LOG_DIR / f"pulse_api_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def cleanup_old_sample_files(keep_count: int = 10, logger: Optional[logging.Logger] = None) -> None:
    """Keep only the latest N sample files, remove older ones"""
    pattern = SAMPLES_DIR / "pulse_data_*.json"
    files = list(glob.glob(str(pattern)))
    
    if len(files) <= keep_count:
        if logger:
            logger.info(f"Only {len(files)} pulse sample files found, no cleanup needed")
        return
    
    # Sort files by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Remove files beyond the keep_count
    files_to_remove = files[keep_count:]
    
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old pulse sample file: {Path(file_path).name}")
        except Exception as e:
            if logger:
                logger.error(f"Error removing pulse sample file {file_path}: {e}")


def create_indexes_and_constraints(cursor: sql.Cursor, logger: logging.Logger) -> None:
    """Create indexes and ensure foreign key constraints for pulse API tables"""
    try:
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_officials_pulseid 
            ON match_officials(pulseid)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_team_list_pulseid 
            ON team_list(pulseid)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_team_list_team_id 
            ON team_list(team_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_events_pulseid 
            ON match_events(pulseid)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_events_team_id 
            ON match_events(team_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_events_event_type 
            ON match_events(event_type)
        """)
        
        # Ensure tables exist with proper structure (based on legacy implementation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_officials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matchOfficialID INTEGER NOT NULL,
                pulseid INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pulseid INTEGER NOT NULL,
                team_id INTEGER,
                person_id INTEGER,
                player_name TEXT NOT NULL,
                match_shirt_number INTEGER,
                is_captain BOOLEAN,
                position TEXT NOT NULL,
                is_starting BOOLEAN,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pulseid INTEGER NOT NULL,
                person_id INTEGER,
                team_id INTEGER,
                assist_id INTEGER,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id)
            )
        """)
        
        logger.info("Database schema and indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating database schema: {e}")
        raise


def load_team_mapping(cursor: sql.Cursor, logger: logging.Logger) -> Dict[int, int]:
    """Load mapping from pulse team IDs to database team_id"""
    try:
        cursor.execute("""
            SELECT pulse_id, team_id 
            FROM teams 
            WHERE pulse_id IS NOT NULL
        """)
        
        mapping = {pulse_id: team_id for pulse_id, team_id in cursor.fetchall()}
        logger.info(f"Loaded {len(mapping)} team mappings")
        return mapping
        
    except Exception as e:
        logger.error(f"Error loading team mapping: {e}")
        return {}


def clear_existing_pulse_data(cursor: sql.Cursor, conn: sql.Connection, season: str, logger: logging.Logger) -> None:
    """Clear all existing pulse data for the specified season"""
    try:
        logger.info(f"Clearing existing pulse data for season {season}...")

        # Get all pulse_ids for the season first
        cursor.execute("""
            SELECT COUNT(DISTINCT f.pulse_id)
            FROM fixtures f
            LEFT JOIN match_events me ON f.pulse_id = me.pulseid
            WHERE f.season = ? AND me.pulseid IS NOT NULL
        """, (season,))
        count_before = cursor.fetchone()[0]

        # Delete from all pulse API tables for fixtures in this season
        cursor.execute("""
            DELETE FROM match_events WHERE pulseid IN (
                SELECT pulse_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
            )
        """, (season,))
        events_deleted = cursor.rowcount

        cursor.execute("""
            DELETE FROM team_list WHERE pulseid IN (
                SELECT pulse_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
            )
        """, (season,))
        team_list_deleted = cursor.rowcount

        cursor.execute("""
            DELETE FROM match_officials WHERE pulseid IN (
                SELECT pulse_id FROM fixtures WHERE season = ? AND pulse_id IS NOT NULL
            )
        """, (season,))
        officials_deleted = cursor.rowcount

        conn.commit()

        logger.info(f"Cleared pulse data for season {season}: "
                   f"{officials_deleted} officials, {team_list_deleted} team list entries, "
                   f"{events_deleted} events from {count_before} fixtures")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error clearing pulse data for season {season}: {e}")
        raise


def drop_and_recreate_pulse_tables(cursor: sql.Cursor, conn: sql.Connection, logger: logging.Logger) -> None:
    """Drop and recreate all pulse API tables to fix data quality issues"""
    try:
        logger.info("Dropping existing pulse API tables...")

        # Get counts before dropping
        cursor.execute("SELECT COUNT(*) FROM match_events")
        events_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM team_list")
        team_list_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM match_officials")
        officials_count = cursor.fetchone()[0]

        logger.info(f"Removing {events_count} match events, {team_list_count} team list entries, "
                   f"{officials_count} match officials")

        # Drop existing tables
        cursor.execute("DROP TABLE IF EXISTS match_events")
        cursor.execute("DROP TABLE IF EXISTS team_list")
        cursor.execute("DROP TABLE IF EXISTS match_officials")

        # Recreate tables with proper structure
        cursor.execute("""
            CREATE TABLE match_officials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matchOfficialID INTEGER NOT NULL,
                pulseid INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE team_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pulseid INTEGER NOT NULL,
                team_id INTEGER,
                person_id INTEGER,
                player_name TEXT NOT NULL,
                match_shirt_number INTEGER,
                is_captain BOOLEAN,
                position TEXT NOT NULL,
                is_starting BOOLEAN,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id),
                FOREIGN KEY (team_id) REFERENCES teams(team_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE match_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pulseid INTEGER NOT NULL,
                person_id INTEGER,
                team_id INTEGER,
                assist_id INTEGER,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id),
                FOREIGN KEY (team_id) REFERENCES teams(team_id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX idx_match_officials_pulseid ON match_officials(pulseid)")
        cursor.execute("CREATE INDEX idx_team_list_pulseid ON team_list(pulseid)")
        cursor.execute("CREATE INDEX idx_team_list_team_id ON team_list(team_id)")
        cursor.execute("CREATE INDEX idx_match_events_pulseid ON match_events(pulseid)")
        cursor.execute("CREATE INDEX idx_match_events_team_id ON match_events(team_id)")
        cursor.execute("CREATE INDEX idx_match_events_event_type ON match_events(event_type)")

        conn.commit()

        logger.info("Successfully dropped and recreated pulse API tables with proper foreign keys")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error dropping and recreating pulse tables: {e}")
        raise


def get_fixtures_needing_pulse_data(cursor: sql.Cursor, season: str, force_all: bool = False, logger: Optional[logging.Logger] = None) -> List[Tuple[int, int, str]]:
    """Get fixtures that need pulse API data fetching"""
    try:
        if force_all:
            # Get all finished fixtures with pulse_id for the season
            query = """
                SELECT f.pulse_id, f.fixture_id, f.gameweek
                FROM fixtures f
                WHERE f.pulse_id IS NOT NULL 
                AND f.finished = 1 
                AND f.season = ?
                ORDER BY f.gameweek, f.fixture_id
            """
            cursor.execute(query, (season,))
        else:
            # Get only fixtures missing pulse data (no match events)
            query = """
                SELECT f.pulse_id, f.fixture_id, f.gameweek
                FROM fixtures f
                LEFT JOIN match_events me ON f.pulse_id = me.pulseid
                WHERE f.pulse_id IS NOT NULL 
                AND f.finished = 1 
                AND f.season = ?
                AND me.pulseid IS NULL
                ORDER BY f.gameweek, f.fixture_id
            """
            cursor.execute(query, (season,))
        
        fixtures = cursor.fetchall()
        
        if logger:
            if force_all:
                logger.info(f"Found {len(fixtures)} finished fixtures with pulse_id for season {season}")
            else:
                logger.info(f"Found {len(fixtures)} fixtures missing pulse data for season {season}")
        
        return fixtures
        
    except Exception as e:
        if logger:
            logger.error(f"Error querying fixtures needing pulse data: {e}")
        return []


def has_existing_pulse_data(cursor: sql.Cursor, pulse_id: int) -> bool:
    """Check if pulse data already exists for a fixture"""
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM match_events WHERE pulseid = ?
        """, (pulse_id,))

        count = cursor.fetchone()[0]
        return count > 0

    except Exception:
        return False


def get_processing_stats(cursor: sql.Cursor, season: str, logger: logging.Logger) -> Dict[str, int]:
    """Get statistics about pulse data processing for the season"""
    try:
        # Total fixtures with pulse_id
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures 
            WHERE pulse_id IS NOT NULL AND season = ?
        """, (season,))
        total_with_pulse_id = cursor.fetchone()[0]
        
        # Finished fixtures with pulse_id
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures 
            WHERE pulse_id IS NOT NULL AND finished = 1 AND season = ?
        """, (season,))
        finished_with_pulse_id = cursor.fetchone()[0]
        
        # Fixtures with pulse data
        cursor.execute("""
            SELECT COUNT(DISTINCT f.pulse_id) 
            FROM fixtures f
            JOIN match_events me ON f.pulse_id = me.pulseid
            WHERE f.season = ?
        """, (season,))
        with_pulse_data = cursor.fetchone()[0]
        
        # Total match events for the season
        cursor.execute("""
            SELECT COUNT(*) 
            FROM match_events me
            JOIN fixtures f ON me.pulseid = f.pulse_id
            WHERE f.season = ?
        """, (season,))
        total_events = cursor.fetchone()[0]
        
        stats = {
            'total_with_pulse_id': total_with_pulse_id,
            'finished_with_pulse_id': finished_with_pulse_id,
            'with_pulse_data': with_pulse_data,
            'missing_pulse_data': finished_with_pulse_id - with_pulse_data,
            'total_events': total_events
        }
        
        logger.info(f"Season {season} pulse data stats: "
                   f"{stats['with_pulse_data']}/{stats['finished_with_pulse_id']} finished fixtures have pulse data "
                   f"({stats['missing_pulse_data']} missing), {stats['total_events']} total events")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting processing stats: {e}")
        return {}


def fetch_pulse_data(pulse_id: int, logger: logging.Logger, delay: float = DEFAULT_DELAY, retries: int = MAX_RETRIES) -> Optional[Dict[str, Any]]:
    """Fetch pulse data from API with error handling and rate limiting"""
    url = BASE_URL.format(id=pulse_id)
    
    for attempt in range(retries):
        try:
            # Rate limiting - add random jitter to avoid thundering herd
            if attempt > 0:
                wait_time = delay * (2 ** attempt) + uniform(0.5, 1.5)
                logger.debug(f"Retry {attempt} for pulse_id {pulse_id}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            elif delay > 0:
                time.sleep(uniform(delay * 0.8, delay * 1.2))
            
            logger.debug(f"Fetching pulse data for ID {pulse_id} (attempt {attempt + 1})")
            
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Successfully fetched pulse data for ID {pulse_id}")
                return data
            elif response.status_code == 404:
                logger.warning(f"Pulse ID {pulse_id} not found (404) - may be invalid or removed")
                return None
            elif response.status_code == 429:
                # Rate limited - wait longer
                wait_time = delay * (2 ** (attempt + 2))
                logger.warning(f"Rate limited for pulse_id {pulse_id}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                continue
            else:
                logger.warning(f"API request failed for pulse_id {pulse_id} with status {response.status_code}")
                if attempt == retries - 1:
                    return None
                    
        except Timeout:
            logger.warning(f"Timeout fetching pulse_id {pulse_id} (attempt {attempt + 1})")
            if attempt == retries - 1:
                return None
        except RequestException as e:
            logger.warning(f"Request failed for pulse_id {pulse_id}: {e} (attempt {attempt + 1})")
            if attempt == retries - 1:
                return None
        except Exception as e:
            logger.error(f"Unexpected error fetching pulse_id {pulse_id}: {e}")
            return None
    
    logger.error(f"Failed to fetch pulse data for ID {pulse_id} after {retries} attempts")
    return None


def fetch_pulse_data_batch(pulse_ids: List[Tuple[int, int, str]], logger: logging.Logger, 
                          max_workers: int = 3, delay: float = DEFAULT_DELAY) -> Dict[int, Dict[str, Any]]:
    """Fetch pulse data for multiple fixtures with concurrent processing"""
    successful_data = {}
    failed_fetches = []
    
    def fetch_single(pulse_info: Tuple[int, int, str]) -> Tuple[int, Optional[Dict[str, Any]]]:
        pulse_id, _fixture_id, _gameweek = pulse_info
        data = fetch_pulse_data(pulse_id, logger, delay)
        return pulse_id, data
    
    if max_workers == 1:
        # Sequential processing for respectful API usage
        logger.info(f"Fetching {len(pulse_ids)} fixtures sequentially...")
        for pulse_info in tqdm(pulse_ids, desc="Fetching pulse data"):
            pulse_id, data = fetch_single(pulse_info)
            if data:
                successful_data[pulse_id] = data
            else:
                failed_fetches.append(pulse_id)
    else:
        # Concurrent processing with controlled workers
        logger.info(f"Fetching {len(pulse_ids)} fixtures with {max_workers} concurrent workers...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_pulse = {executor.submit(fetch_single, pulse_info): pulse_info for pulse_info in pulse_ids}
            
            # Process results with progress bar
            for future in tqdm(as_completed(future_to_pulse), total=len(pulse_ids), desc="Processing pulse data"):
                pulse_id, data = future.result()
                if data:
                    successful_data[pulse_id] = data
                else:
                    failed_fetches.append(pulse_id)
    
    logger.info(f"Successfully fetched {len(successful_data)} fixtures, {len(failed_fetches)} failed")
    if failed_fetches:
        logger.warning(f"Failed pulse IDs: {failed_fetches}")
    
    return successful_data


def insert_match_officials(cursor: sql.Cursor, pulse_id: int, officials: List[Dict[str, Any]], logger: logging.Logger) -> int:
    """Insert match officials data into database"""
    inserted_count = 0
    
    try:
        for official in officials:
            role = official.get("role", "LINEOFFICIAL")
            cursor.execute("""
                INSERT OR REPLACE INTO match_officials (matchOfficialID, pulseid, name, role)
                VALUES (?, ?, ?, ?)
            """, (
                official["matchOfficialId"],
                pulse_id,
                official["name"]["display"],
                role,
            ))
            inserted_count += 1
        
        logger.debug(f"Inserted {inserted_count} match officials for pulse_id {pulse_id}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"Error inserting match officials for pulse_id {pulse_id}: {e}")
        raise


def insert_team_list(cursor: sql.Cursor, pulse_id: int, teams: List[Dict[str, Any]], 
                     team_mapping: Dict[int, int], logger: logging.Logger) -> int:
    """Insert team list data (lineups and substitutes) into database"""
    inserted_count = 0
    
    try:
        for team in teams:
            pulse_team_id = team.get("teamId")
            db_team_id = team_mapping.get(pulse_team_id)
            
            # Insert starting lineup
            for player in team.get("lineup", []):
                cursor.execute("""
                    INSERT OR REPLACE INTO team_list 
                    (pulseid, player_name, match_shirt_number, is_captain, position, is_starting, person_id, team_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pulse_id,
                    player["name"]["display"],
                    player.get("matchShirtNumber"),
                    player.get("captain", False),
                    player.get("matchPosition"),
                    True,  # is_starting
                    player["id"],
                    db_team_id,
                ))
                inserted_count += 1
            
            # Insert substitutes
            for player in team.get("substitutes", []):
                cursor.execute("""
                    INSERT OR REPLACE INTO team_list 
                    (pulseid, player_name, match_shirt_number, is_captain, position, is_starting, person_id, team_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pulse_id,
                    player["name"]["display"],
                    player.get("matchShirtNumber"),
                    player.get("captain", False),
                    player.get("matchPosition"),
                    False,  # is_starting
                    player["id"],
                    db_team_id,
                ))
                inserted_count += 1
        
        logger.debug(f"Inserted {inserted_count} team list entries for pulse_id {pulse_id}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"Error inserting team list for pulse_id {pulse_id}: {e}")
        raise


def insert_match_events(cursor: sql.Cursor, pulse_id: int, events: List[Dict[str, Any]], 
                       team_mapping: Dict[int, int], logger: logging.Logger) -> int:
    """Insert match events data into database"""
    inserted_count = 0
    
    try:
        for event in events:
            person_id = event.get("personId")
            pulse_team_id = event.get("teamId")
            db_team_id = team_mapping.get(pulse_team_id) if pulse_team_id else None
            assist_id = event.get("assistId")
            
            cursor.execute("""
                INSERT INTO match_events (pulseid, event_type, event_time, person_id, team_id, assist_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                pulse_id,
                event["type"],
                event["clock"]["secs"],
                person_id,
                db_team_id,
                assist_id,
            ))
            inserted_count += 1
        
        logger.debug(f"Inserted {inserted_count} match events for pulse_id {pulse_id}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"Error inserting match events for pulse_id {pulse_id}: {e}")
        raise


def process_pulse_data(cursor: sql.Cursor, conn: sql.Connection, pulse_data: Dict[int, Dict[str, Any]], 
                      team_mapping: Dict[int, int], logger: logging.Logger, dry_run: bool = False) -> Dict[str, int]:
    """Process pulse data and insert into database"""
    stats = {
        'fixtures_processed': 0,
        'officials_inserted': 0,
        'team_list_inserted': 0,
        'events_inserted': 0,
        'fixtures_failed': 0
    }
    
    for pulse_id, data in pulse_data.items():
        try:
            if dry_run:
                logger.info(f"DRY RUN: Would process pulse_id {pulse_id}")
                # Count what would be inserted
                stats['fixtures_processed'] += 1
                stats['officials_inserted'] += len(data.get("matchOfficials", []))
                for team in data.get("teamLists", []):
                    stats['team_list_inserted'] += len(team.get("lineup", [])) + len(team.get("substitutes", []))
                stats['events_inserted'] += len(data.get("events", []))
                continue
            
            # Insert match officials
            officials_count = insert_match_officials(cursor, pulse_id, data.get("matchOfficials", []), logger)
            stats['officials_inserted'] += officials_count
            
            # Insert team lists
            team_list_count = insert_team_list(cursor, pulse_id, data.get("teamLists", []), team_mapping, logger)
            stats['team_list_inserted'] += team_list_count
            
            # Insert match events
            events_count = insert_match_events(cursor, pulse_id, data.get("events", []), team_mapping, logger)
            stats['events_inserted'] += events_count
            
            stats['fixtures_processed'] += 1
            logger.info(f"Processed pulse_id {pulse_id}: {officials_count} officials, "
                       f"{team_list_count} team list entries, {events_count} events")
            
        except Exception as e:
            stats['fixtures_failed'] += 1
            logger.error(f"Failed to process pulse_id {pulse_id}: {e}")
            # Continue processing other fixtures
    
    if not dry_run:
        # Commit all changes
        conn.commit()
        logger.info("Database transaction committed successfully")
    
    logger.info(f"Processing complete: {stats['fixtures_processed']} fixtures processed, "
               f"{stats['fixtures_failed']} failed")
    
    return stats


def save_sample_data(pulse_data: Dict[int, Dict[str, Any]], logger: logging.Logger) -> None:
    """Save pulse data as JSON sample with timestamp"""
    if not pulse_data:
        logger.debug("No pulse data to save")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pulse_data_{timestamp}.json"
    output_file = SAMPLES_DIR / filename
    
    try:
        # Convert to list format for easier reading
        sample_data = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'pulse_ids_count': len(pulse_data),
                'pulse_ids': list(pulse_data.keys())
            },
            'data': pulse_data
        }
        
        with open(output_file, 'w') as f:
            json.dump(sample_data, f, indent=2)
        
        logger.info(f"Pulse sample data saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Failed to save pulse sample data: {e}")


def load_sample_data(logger: logging.Logger) -> Optional[Dict[int, Dict[str, Any]]]:
    """Load the most recent sample data for testing"""
    pattern = SAMPLES_DIR / "pulse_data_*.json"
    sample_files = list(glob.glob(str(pattern)))
    
    if not sample_files:
        logger.error("No pulse sample data files found")
        return None
    
    # Use the most recent sample file
    sample_file = max(sample_files, key=lambda f: os.path.getmtime(f))
    logger.info(f"Loading sample data from: {Path(sample_file).name}")
    
    try:
        with open(sample_file, 'r') as f:
            sample_data = json.load(f)
        
        # Handle both old format (direct dict) and new format (with metadata)
        if 'data' in sample_data:
            pulse_data = sample_data['data']
            logger.info(f"Loaded sample data with {len(pulse_data)} fixtures")
        else:
            # Legacy format - assume the whole file is pulse data
            pulse_data = sample_data
            logger.info(f"Loaded legacy sample data with {len(pulse_data)} fixtures")
        
        # Convert string keys back to integers
        return {int(k): v for k, v in pulse_data.items()}
        
    except Exception as e:
        logger.error(f"Failed to load sample data: {e}")
        return None


def update_last_update_table(cursor: sql.Cursor, conn: sql.Connection, logger: logging.Logger) -> None:
    """Update last_update table to trigger automated uploads"""
    try:
        now = datetime.now()
        timestamp = now.timestamp()
        formatted_time = now.strftime("%d-%m-%Y %H:%M:%S")
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES (?, ?, ?)
        """, ("pulse_api_data", formatted_time, timestamp))
        
        conn.commit()
        logger.info(f"Updated last_update table: {formatted_time}")
        
    except Exception as e:
        logger.error(f"Failed to update last_update table: {e}")
        conn.rollback()


def test_with_sample_data(args: argparse.Namespace, logger: logging.Logger) -> None:
    """Test the script using existing sample data"""
    logger.info("Starting pulse API test with sample data...")
    
    # Load sample data
    pulse_data = load_sample_data(logger)
    if not pulse_data:
        logger.error("No sample data available for testing")
        return
    
    # Connect to database
    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create schema and load mappings
        create_indexes_and_constraints(cursor, logger)
        team_mapping = load_team_mapping(cursor, logger)
        
        # Process sample data
        logger.info("Processing sample pulse data...")
        stats = process_pulse_data(cursor, conn, pulse_data, team_mapping, logger, args.dry_run)
        
        if not args.dry_run:
            # Update last_update table
            update_last_update_table(cursor, conn, logger)
        
        logger.info(f"Test completed successfully: {stats}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error in test processing: {e}")
        raise
    finally:
        conn.close()


def main_process(args: argparse.Namespace, logger: logging.Logger) -> None:
    """Main processing logic"""
    logger.info(f"Starting pulse API data collection for season {args.season}...")

    # Connect to database
    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Handle fix-team-ids: drop and recreate tables to fix data quality issues
        if args.fix_team_ids:
            if args.dry_run:
                logger.info("DRY RUN: Would drop and recreate pulse API tables to fix team_id data quality issues")
            else:
                logger.warning("⚠️  FIX MODE: This will drop and recreate all pulse API tables")
                logger.warning("⚠️  All match_events, team_list, and match_officials data will be deleted")
                logger.warning("⚠️  Data will be re-fetched with corrected team_id mappings")
                drop_and_recreate_pulse_tables(cursor, conn, logger)
                logger.info("✓ Tables recreated successfully - proceeding to fetch all data")

        # Initialize database schema
        create_indexes_and_constraints(cursor, logger)

        # Load team mapping
        team_mapping = load_team_mapping(cursor, logger)
        if not team_mapping:
            logger.warning("No team mappings found - pulse team IDs won't be mapped to database team_id")

        # Get processing statistics
        get_processing_stats(cursor, args.season, logger)

        # Handle force-refresh: clear existing data first
        if args.force_refresh:
            if args.dry_run:
                logger.info("DRY RUN: Would clear all existing pulse data for season")
            else:
                clear_existing_pulse_data(cursor, conn, args.season, logger)

        # Find fixtures needing pulse data
        # If fix-team-ids mode, force fetch all fixtures to repopulate
        force_all_mode = args.force_all or args.force_refresh or args.fix_team_ids
        fixtures_to_process = get_fixtures_needing_pulse_data(
            cursor, args.season, force_all_mode, logger
        )

        if not fixtures_to_process:
            logger.info("No fixtures need pulse data processing")
            return

        # Fetch pulse data from API
        pulse_data = fetch_pulse_data_batch(
            fixtures_to_process, logger, args.max_workers, args.delay
        )

        if not pulse_data:
            logger.warning("No pulse data was successfully fetched")
            return

        # Save sample data for testing/debugging
        save_sample_data(pulse_data, logger)

        # Process data and insert into database
        stats = process_pulse_data(cursor, conn, pulse_data, team_mapping, logger, args.dry_run)

        if not args.dry_run:
            # Update last_update table to trigger automated upload
            update_last_update_table(cursor, conn, logger)

        # Clean up old sample files
        if args.cleanup_count > 0:
            logger.info(f"Cleaning up old sample files, keeping latest {args.cleanup_count}...")
            cleanup_old_sample_files(keep_count=args.cleanup_count, logger=logger)

        logger.info(f"Pulse API data collection completed successfully: {stats}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error in main process: {e}")
        raise
    finally:
        conn.close()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Fetch Pulse API data for match officials, team lists, and events'
    )
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode with sample data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without making database changes (shows what would happen)')
    parser.add_argument('--max-workers', type=int, default=3,
                       help='Maximum number of concurrent API requests (default: 3)')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY,
                       help='Delay between API requests in seconds (default: 2.0)')
    parser.add_argument('--season', type=str, default=CURRENT_SEASON,
                       help=f'Season to process (default: {CURRENT_SEASON})')
    parser.add_argument('--cleanup-count', type=int, default=10,
                       help='Number of sample files to keep (0 to disable cleanup)')
    parser.add_argument('--force-all', action='store_true',
                       help='Force fetch all fixtures regardless of existing data')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Delete existing pulse data and re-fetch all fixtures')
    parser.add_argument('--fix-team-ids', action='store_true',
                       help='Drop and recreate pulse tables to fix team_id data quality issues, then re-fetch all data')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    # Validate arguments
    if args.force_refresh and args.force_all:
        print("Error: Cannot use both --force-refresh and --force-all together")
        print("Use --force-refresh to clear existing data and re-fetch all fixtures")
        print("Use --force-all to fetch all fixtures without clearing existing data")
        exit(1)

    if args.fix_team_ids and (args.force_refresh or args.force_all):
        print("Error: --fix-team-ids cannot be used with --force-refresh or --force-all")
        print("The --fix-team-ids flag automatically handles table recreation and data fetching")
        exit(1)

    logger = setup_logging()
    logger.info("Starting Pulse API data fetch process...")

    try:
        if args.test:
            # Test mode with sample data
            test_with_sample_data(args, logger)
        else:
            # Normal operation with API fetching
            main_process(args, logger)

        logger.info("Pulse API data fetch process completed successfully")

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in pulse API process: {e}")
        raise