#!/usr/bin/env python3
"""
Fixtures and Gameweeks Data Management Script

Fetches fixture and gameweek data from FPL API and maintains the fixtures and gameweeks tables
with efficient upsert operations, proper team mapping, and JSON caching.

FUNCTIONALITY:
- Fetches gameweek information from FPL bootstrap API
- Fetches fixture data from FPL fixtures API
- Maps FPL team IDs to database team_id values
- Handles timezone conversion for UK kickoff times
- Maintains sample data for testing and debugging

DATABASE OPERATIONS:
- Creates/updates fixtures table with proper foreign keys
- Creates/updates gameweeks table with deadline information
- Uses efficient batch operations for database updates
- Maintains transaction integrity with rollback on errors

TIMESTAMP UPDATES:
- Fixed Aug 2025: Now updates both "fixtures" and "fixtures_gameweeks" timestamps
- Previous version only updated "fixtures_gameweeks" despite modifying both tables
- Ensures upload monitoring can detect when fixtures are updated
- Critical for automated database synchronization

COMMAND LINE OPTIONS:
- --test: Use cached sample data for development
- --dry-run: Preview changes without database updates
- --season SEASON: Specify season (default: 2025/2026)
- --cleanup-count N: Number of sample files to keep (default: 5)
"""

import json
import requests
import sqlite3 as sql
import logging
import argparse
import glob
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from requests.exceptions import RequestException, Timeout

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import centralized configuration
from scripts.config import CURRENT_SEASON

# Gameweek validator integration removed - now handled by master_scheduler

# Configuration
BASE_URL = "https://fantasy.premierleague.com/api/"
# UK timezone (UTC+0 in summer, UTC+1 in winter - using UTC+0 for simplicity)
UK_TZ = timezone.utc

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"
samples_dir = Path(__file__).parent.parent.parent / "samples" / "fixtures"

# Create directories
log_dir.mkdir(exist_ok=True)
samples_dir.mkdir(parents=True, exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"fixtures_gameweeks_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def cleanup_old_sample_files(keep_count=5, logger=None):
    """Keep only the latest N sample files, remove older ones"""
    pattern = samples_dir / "fixtures_gameweeks_*.json"
    files = list(glob.glob(str(pattern)))
    
    if len(files) <= keep_count:
        if logger:
            logger.info(f"Only {len(files)} fixtures sample files found, no cleanup needed")
        return
    
    # Sort files by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Remove files beyond the keep_count
    files_to_remove = files[keep_count:]
    
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old fixtures sample file: {Path(file_path).name}")
        except Exception as e:
            if logger:
                logger.error(f"Error removing fixtures sample file {file_path}: {e}")

def create_fixtures_table(cursor):
    """Create fixtures table if it doesn't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            fpl_fixture_id INTEGER NOT NULL,
            fixture_id INTEGER PRIMARY KEY AUTOINCREMENT,
            kickoff_dttm DATETIME,
            home_teamid INTEGER NOT NULL,
            away_teamid INTEGER NOT NULL,
            finished BOOLEAN DEFAULT 0,
            started BOOLEAN DEFAULT 0,
            provisional_finished BOOLEAN DEFAULT 0,
            season TEXT,
            gameweek INTEGER,
            pulse_id INTEGER,
            home_win_odds REAL,
            draw_odds REAL,
            away_win_odds REAL,
            FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
            FOREIGN KEY (away_teamid) REFERENCES teams(team_id)
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fixtures_season 
        ON fixtures(season)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fixtures_gameweek 
        ON fixtures(gameweek)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fixtures_fpl_id 
        ON fixtures(fpl_fixture_id)
    """)

def create_gameweeks_table(cursor):
    """Create gameweeks table if it doesn't exist (matches existing schema)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gameweeks (
            gameweek INTEGER NOT NULL,
            deadline_dttm DATETIME,
            deadline_date DATE,
            deadline_time TIME,
            current_gameweek BOOLEAN,
            next_gameweek BOOLEAN,
            finished BOOLEAN,
            PRIMARY KEY (gameweek)
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gameweeks_current 
        ON gameweeks(current_gameweek)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gameweeks_finished 
        ON gameweeks(finished)
    """)

def create_last_update_table(cursor):
    """Create last_update tracking table if it doesn't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_update (
            table_name TEXT PRIMARY KEY,
            updated TEXT,
            timestamp NUMERIC
        )
    """)

def load_team_mapping(cursor):
    """Load FPL team ID to database team_id mapping"""
    cursor.execute("""
        SELECT fpl_id, team_id 
        FROM teams 
        WHERE fpl_id IS NOT NULL AND available = 1
    """)
    
    mapping = {fpl_id: team_id for fpl_id, team_id in cursor.fetchall()}
    return mapping

def get_existing_fixtures_data(cursor, season):
    """Get existing fixtures data for comparison"""
    cursor.execute("""
        SELECT 
            fpl_fixture_id, kickoff_dttm, home_teamid, away_teamid,
            finished, started, provisional_finished, gameweek, pulse_id
        FROM fixtures 
        WHERE season = ?
    """, (season,))
    
    existing_data = {}
    for row in cursor.fetchall():
        fpl_fixture_id = row[0]
        existing_data[fpl_fixture_id] = {
            'kickoff_dttm': row[1],
            'home_teamid': row[2], 
            'away_teamid': row[3],
            'finished': row[4],
            'started': row[5],
            'provisional_finished': row[6],
            'gameweek': row[7],
            'pulse_id': row[8]
        }
    
    return existing_data

def get_existing_gameweeks_data(cursor):
    """Get existing gameweeks data for comparison"""
    cursor.execute("""
        SELECT 
            gameweek, deadline_dttm, deadline_date, deadline_time,
            current_gameweek, next_gameweek, finished
        FROM gameweeks
    """)
    
    existing_data = {}
    for row in cursor.fetchall():
        gameweek = row[0]
        existing_data[gameweek] = {
            'deadline_dttm': row[1],
            'deadline_date': row[2],
            'deadline_time': row[3], 
            'current_gameweek': row[4],
            'next_gameweek': row[5],
            'finished': row[6]
        }
    
    return existing_data

def has_fixture_changed(existing_data, new_fixture_data):
    """Check if fixture data has changed compared to existing data"""
    if not existing_data:
        return True  # New fixture
    
    # Compare all relevant fields
    compare_fields = [
        'kickoff_dttm', 'home_teamid', 'away_teamid', 
        'finished', 'started', 'provisional_finished', 
        'gameweek', 'pulse_id'
    ]
    
    for field in compare_fields:
        existing_value = existing_data.get(field)
        new_value = new_fixture_data.get(field)
        
        # Handle None comparisons
        if (existing_value is None) != (new_value is None):
            return True
        
        # Handle boolean conversion for database fields (SQLite returns 0/1 for boolean)
        if field in ['finished', 'started', 'provisional_finished']:
            existing_bool = bool(existing_value) if existing_value is not None else False
            new_bool = bool(new_value) if new_value is not None else False
            if existing_bool != new_bool:
                return True
        else:
            # Standard comparison for other fields
            if existing_value != new_value:
                return True
    
    return False  # No changes detected

def has_gameweek_changed(existing_data, new_gameweek_data):
    """Check if gameweek data has changed compared to existing data"""
    if not existing_data:
        return True  # New gameweek
    
    # Compare all relevant fields  
    compare_fields = [
        'deadline_dttm', 'deadline_date', 'deadline_time',
        'current_gameweek', 'next_gameweek', 'finished'
    ]
    
    for field in compare_fields:
        existing_value = existing_data.get(field)
        new_value = new_gameweek_data.get(field)
        
        # Handle None comparisons
        if (existing_value is None) != (new_value is None):
            return True
        
        # Handle boolean conversion for database fields (SQLite returns 0/1 for boolean)
        if field in ['current_gameweek', 'next_gameweek', 'finished']:
            existing_bool = bool(existing_value) if existing_value is not None else False
            new_bool = bool(new_value) if new_value is not None else False
            if existing_bool != new_bool:
                return True
        else:
            # Standard comparison for other fields
            if existing_value != new_value:
                return True
    
    return False  # No changes detected

def fetch_bootstrap_data(logger):
    """Fetch bootstrap data from FPL API for gameweeks information"""
    url = f"{BASE_URL}bootstrap-static/"
    
    try:
        logger.info("Fetching FPL bootstrap data for gameweeks...")
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            events = data.get("events", [])
            logger.info(f"Retrieved {len(events)} gameweeks from FPL API")
            return events
        else:
            logger.error(f"Bootstrap API request failed with status {response.status_code}")
            return None
            
    except Timeout:
        logger.error("Bootstrap API request timed out after 30 seconds")
        return None
    except RequestException as e:
        logger.error(f"Bootstrap API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching bootstrap data: {e}")
        return None

def fetch_fixtures_data(logger):
    """Fetch fixtures data from FPL API"""
    url = f"{BASE_URL}fixtures/"
    
    try:
        logger.info("Fetching FPL fixtures data...")
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Retrieved {len(data)} fixtures from FPL API")
            return data
        else:
            logger.error(f"Fixtures API request failed with status {response.status_code}")
            return None
            
    except Timeout:
        logger.error("Fixtures API request timed out after 30 seconds")
        return None
    except RequestException as e:
        logger.error(f"Fixtures API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching fixtures data: {e}")
        return None

def process_gameweeks(cursor, events_data, season, logger):
    """Process and upsert gameweeks data with change detection"""
    if not events_data:
        logger.warning("No gameweeks data to process")
        return 0, 0, 0  # Return counts for timestamp logic
    
    inserted_count = 0
    updated_count = 0
    unchanged_count = 0
    
    # Get existing gameweeks data for comparison
    logger.debug("Loading existing gameweeks for comparison...")
    existing_gameweeks_data = get_existing_gameweeks_data(cursor)
    logger.debug(f"Loaded {len(existing_gameweeks_data)} existing gameweeks for comparison")
    
    gameweeks_to_insert = []
    gameweeks_to_update = []
    
    for event in events_data:
        try:
            # Convert deadline time from UTC to UK time
            deadline_utc_str = event["deadline_time"].replace("Z", "")
            deadline_utc = datetime.strptime(deadline_utc_str, "%Y-%m-%dT%H:%M:%S")
            deadline_uk = deadline_utc.replace(tzinfo=timezone.utc)
            
            deadline_date = deadline_uk.strftime("%Y-%m-%d")
            deadline_time = deadline_uk.strftime("%H:%M")
            
            gameweek_id = event["id"]
            
            # Create new gameweek data dictionary for comparison
            new_gameweek_data = {
                'deadline_dttm': event["deadline_time"],
                'deadline_date': deadline_date,
                'deadline_time': deadline_time,
                'current_gameweek': event["is_current"],
                'next_gameweek': event["is_next"],
                'finished': event["finished"]
            }
            
            existing_data = existing_gameweeks_data.get(gameweek_id)
            
            if existing_data:
                # Check if gameweek has actually changed
                if has_gameweek_changed(existing_data, new_gameweek_data):
                    # Prepare data for update
                    gameweek_update_data = (
                        event["deadline_time"],         # deadline_dttm (UTC)
                        deadline_date,                  # deadline_date
                        deadline_time,                  # deadline_time
                        event["is_current"],           # current_gameweek
                        event["is_next"],              # next_gameweek
                        event["finished"],             # finished
                        gameweek_id                    # WHERE clause
                    )
                    gameweeks_to_update.append(gameweek_update_data)
                    updated_count += 1
                else:
                    # No changes detected
                    unchanged_count += 1
            else:
                # New gameweek - prepare for insert
                gameweek_insert_data = (
                    gameweek_id,                    # gameweek
                    event["deadline_time"],         # deadline_dttm (UTC)
                    deadline_date,                  # deadline_date
                    deadline_time,                  # deadline_time
                    event["is_current"],           # current_gameweek
                    event["is_next"],              # next_gameweek
                    event["finished"]             # finished
                )
                gameweeks_to_insert.append(gameweek_insert_data)
                inserted_count += 1
                
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Error processing gameweek {event.get('id', 'unknown')}: {e}")
            continue
    
    # Batch insert new gameweeks
    if gameweeks_to_insert:
        cursor.executemany("""
            INSERT INTO gameweeks (
                gameweek, deadline_dttm, deadline_date, deadline_time,
                current_gameweek, next_gameweek, finished
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, gameweeks_to_insert)
    
    # Batch update existing gameweeks
    if gameweeks_to_update:
        cursor.executemany("""
            UPDATE gameweeks SET 
                deadline_dttm = ?, deadline_date = ?, deadline_time = ?,
                current_gameweek = ?, next_gameweek = ?, finished = ?
            WHERE gameweek = ?
        """, gameweeks_to_update)
    
    logger.info(f"Gameweeks: {inserted_count} new, {updated_count} updated, {unchanged_count} unchanged")
    
    if inserted_count == 0 and updated_count == 0 and unchanged_count == 0:
        logger.warning("No valid gameweeks data to process")
    
    return inserted_count, updated_count, unchanged_count

def process_fixtures(cursor, fixtures_data, team_mapping, season, logger):
    """Process and upsert fixtures data with change detection"""
    if not fixtures_data:
        logger.warning("No fixtures data to process")
        return 0, 0, 0, 0  # Return counts for timestamp logic
    
    if not team_mapping:
        logger.error("No team mapping available - cannot process fixtures")
        return 0, 0, 0, 0  # Return counts for timestamp logic
    
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    unchanged_count = 0
    
    # Get existing fixtures data for comparison
    logger.debug("Loading existing fixtures for comparison...")
    existing_fixtures_data = get_existing_fixtures_data(cursor, season)
    logger.debug(f"Loaded {len(existing_fixtures_data)} existing fixtures for comparison")
    
    fixtures_to_insert = []
    fixtures_to_update = []
    
    for fixture in fixtures_data:
        try:
            # Map FPL team IDs to database team IDs
            home_team_id = team_mapping.get(fixture["team_h"])
            away_team_id = team_mapping.get(fixture["team_a"])
            
            if not home_team_id or not away_team_id:
                logger.warning(f"Skipping fixture {fixture['id']} - missing team mapping "
                             f"(home: {fixture['team_h']}, away: {fixture['team_a']})")
                skipped_count += 1
                continue
            
            # Parse kickoff time (can be None)
            kickoff_time = fixture.get("kickoff_time")
            if kickoff_time:
                # Remove 'Z' suffix if present and ensure proper format
                kickoff_time = kickoff_time.replace("Z", "")
            
            fpl_fixture_id = fixture["id"]
            
            # Create new fixture data dictionary for comparison
            new_fixture_data = {
                'kickoff_dttm': kickoff_time,
                'home_teamid': home_team_id,
                'away_teamid': away_team_id,
                'finished': fixture.get("finished", False),
                'started': fixture.get("started", False),
                'provisional_finished': fixture.get("finished_provisional", False),
                'gameweek': fixture.get("event"),
                'pulse_id': fixture.get("pulse_id")
            }
            
            existing_data = existing_fixtures_data.get(fpl_fixture_id)
            
            if existing_data:
                # Check if fixture has actually changed
                if has_fixture_changed(existing_data, new_fixture_data):
                    # Prepare data for update (exclude fpl_fixture_id from update)
                    fixture_update_data = (
                        kickoff_time,                                    # kickoff_dttm
                        home_team_id,                                   # home_teamid
                        away_team_id,                                   # away_teamid
                        fixture.get("finished", False),                 # finished
                        fixture.get("started", False),                  # started
                        fixture.get("finished_provisional", False),     # provisional_finished
                        season,                                         # season
                        fixture.get("event"),                          # gameweek
                        fixture.get("pulse_id"),                       # pulse_id
                        fpl_fixture_id,                                # WHERE clause
                        season                                          # WHERE clause
                    )
                    fixtures_to_update.append(fixture_update_data)
                    updated_count += 1
                else:
                    # No changes detected
                    unchanged_count += 1
            else:
                # New fixture - prepare for insert
                fixture_insert_data = (
                    fpl_fixture_id,                         # fpl_fixture_id
                    kickoff_time,                          # kickoff_dttm
                    home_team_id,                          # home_teamid
                    away_team_id,                          # away_teamid
                    fixture.get("finished", False),        # finished
                    fixture.get("started", False),         # started
                    fixture.get("finished_provisional", False),  # provisional_finished
                    season,                                # season
                    fixture.get("event"),                  # gameweek
                    fixture.get("pulse_id")                # pulse_id
                )
                fixtures_to_insert.append(fixture_insert_data)
                inserted_count += 1
                
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Error processing fixture {fixture.get('id', 'unknown')}: {e}")
            skipped_count += 1
            continue
    
    # Batch insert new fixtures
    if fixtures_to_insert:
        cursor.executemany("""
            INSERT INTO fixtures (
                fpl_fixture_id, kickoff_dttm, home_teamid, away_teamid,
                finished, started, provisional_finished, season, gameweek, pulse_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fixtures_to_insert)
        
    # Batch update existing fixtures
    if fixtures_to_update:
        cursor.executemany("""
            UPDATE fixtures SET 
                kickoff_dttm = ?, home_teamid = ?, away_teamid = ?,
                finished = ?, started = ?, provisional_finished = ?, 
                season = ?, gameweek = ?, pulse_id = ?
            WHERE fpl_fixture_id = ? AND season = ?
        """, fixtures_to_update)
    
    logger.info(f"Fixtures: {inserted_count} new, {updated_count} updated, {unchanged_count} unchanged, {skipped_count} skipped")
    
    if skipped_count > 0:
        logger.warning(f"Skipped {skipped_count} fixtures due to missing team mappings")
    
    return inserted_count, updated_count, unchanged_count, skipped_count

def save_sample_data(gameweeks_data, fixtures_data, team_mapping, logger):
    """Save API data as JSON sample with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fixtures_gameweeks_{timestamp}.json"
    output_file = samples_dir / filename
    
    sample_data = {
        'gameweeks': gameweeks_data,
        'fixtures': fixtures_data,
        'team_mapping': team_mapping,
        'metadata': {
            'fetch_time': datetime.now().isoformat(),
            'total_gameweeks': len(gameweeks_data) if gameweeks_data else 0,
            'total_fixtures': len(fixtures_data) if fixtures_data else 0,
            'team_mappings': len(team_mapping),
            'season': CURRENT_SEASON
        }
    }
    
    try:
        with open(output_file, 'w') as f:
            json.dump(sample_data, f, indent=2)
        logger.info(f"Sample data saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to save sample data: {e}")

def load_sample_data(logger):
    """Load the most recent sample data for testing"""
    pattern = samples_dir / "fixtures_gameweeks_*.json"
    sample_files = list(glob.glob(str(pattern)))
    
    if not sample_files:
        logger.error("No sample data files found")
        return None
    
    # Use the most recent sample file
    sample_file = max(sample_files, key=lambda f: os.path.getmtime(f))
    logger.info(f"Loading sample data from: {Path(sample_file).name}")
    
    try:
        with open(sample_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load sample data: {e}")
        return None

def update_last_update_timestamp(cursor, logger, gameweeks_changed=False, fixtures_changed=False):
    """Update the last_update table with current timestamp only when changes occur"""
    if not gameweeks_changed and not fixtures_changed:
        logger.info("No changes detected - skipping timestamp updates")
        return
    
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y %H:%M:%S")
    timestamp = dt.timestamp()
    
    try:
        tables_updated = []
        
        if gameweeks_changed:
            cursor.execute("""
                INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
                VALUES ('fixtures_gameweeks', ?, ?)
            """, (now, timestamp))
            tables_updated.append('fixtures_gameweeks')
        
        if fixtures_changed:
            cursor.execute("""
                INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
                VALUES ('fixtures', ?, ?)
            """, (now, timestamp))
            tables_updated.append('fixtures')
        
        logger.info(f"Updated last_update timestamps for {', '.join(tables_updated)}: {now}")
    except Exception as e:
        logger.error(f"Error updating last_update timestamps: {e}")

def collect_fixtures_gameweeks_data(logger):
    """Collect all fixtures and gameweeks data from FPL APIs"""
    # Fetch gameweeks data
    gameweeks_data = fetch_bootstrap_data(logger)
    if not gameweeks_data:
        logger.error("Failed to fetch gameweeks data")
        return None, None, None
    
    # Fetch fixtures data
    fixtures_data = fetch_fixtures_data(logger)
    if not fixtures_data:
        logger.error("Failed to fetch fixtures data")
        return None, None, None
    
    # Setup database connection to get team mapping
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Load team mapping
        logger.info("Loading team mapping...")
        team_mapping = load_team_mapping(cursor)
        logger.info(f"Loaded {len(team_mapping)} team mappings")
        
        if not team_mapping:
            logger.error("No team mappings found - ensure teams table is populated")
            return None, None, None
            
        return gameweeks_data, fixtures_data, team_mapping
        
    except Exception as e:
        logger.error(f"Error loading team mapping: {e}")
        return None, None, None
    finally:
        conn.close()

def process_fixtures_gameweeks_data(gameweeks_data, fixtures_data, team_mapping, season, logger, dry_run=False):
    """Process fixtures and gameweeks data and update database"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create tables if they don't exist
        create_fixtures_table(cursor)
        create_gameweeks_table(cursor)
        create_last_update_table(cursor)
        
        if dry_run:
            logger.info("DRY RUN MODE - No database changes will be made")
        
        # Process gameweeks data
        logger.info(f"Processing {len(gameweeks_data)} gameweeks...")
        gw_inserted, gw_updated, gw_unchanged = process_gameweeks(cursor, gameweeks_data, season, logger)
        
        # Process fixtures data
        logger.info(f"Processing {len(fixtures_data)} fixtures...")
        fix_inserted, fix_updated, fix_unchanged, fix_skipped = process_fixtures(cursor, fixtures_data, team_mapping, season, logger)
        
        # Update timestamp only if changes were made
        gameweeks_changed = (gw_inserted > 0 or gw_updated > 0)
        fixtures_changed = (fix_inserted > 0 or fix_updated > 0)
        update_last_update_timestamp(cursor, logger, gameweeks_changed, fixtures_changed)
        
        if dry_run:
            conn.rollback()
            logger.info("DRY RUN - Transaction rolled back")
        else:
            conn.commit()
            logger.info("Database transaction committed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing fixtures/gameweeks data: {e}")
        raise
    finally:
        conn.close()

def main(season=CURRENT_SEASON, dry_run=False, cleanup_count=5, force_refresh=False):
    """Main execution function - always fetches data and updates if changes detected"""
    logger = setup_logging()
    logger.info("Starting fixtures and gameweeks data fetch process...")
    
    # Always collect data from APIs (removed validation dependency)
    gameweeks_data, fixtures_data, team_mapping = collect_fixtures_gameweeks_data(logger)
    
    if gameweeks_data and fixtures_data and team_mapping:
        # Always save sample data
        save_sample_data(gameweeks_data, fixtures_data, team_mapping, logger)
        
        # Process data into database (will only update if changes detected)
        process_fixtures_gameweeks_data(gameweeks_data, fixtures_data, team_mapping, season, logger, dry_run=dry_run)
        
        # Clean up old sample files
        if cleanup_count > 0:
            logger.info(f"Cleaning up old sample files, keeping latest {cleanup_count}...")
            cleanup_old_sample_files(keep_count=cleanup_count, logger=logger)
        
        logger.info("Fixtures and gameweeks data fetch process completed successfully")
    else:
        logger.error("No data collected - aborting process")

def test_with_sample_data(season=CURRENT_SEASON, dry_run=False):
    """Test the script using existing sample data"""
    logger = setup_logging()
    logger.info("Starting fixtures/gameweeks test with sample data...")
    
    sample_data = load_sample_data(logger)
    
    if sample_data:
        gameweeks_data = sample_data.get('gameweeks', [])
        fixtures_data = sample_data.get('fixtures', [])
        team_mapping = sample_data.get('team_mapping', {})
        
        logger.info(f"Processing sample data: {len(gameweeks_data)} gameweeks, {len(fixtures_data)} fixtures")
        process_fixtures_gameweeks_data(gameweeks_data, fixtures_data, team_mapping, season, logger, dry_run=dry_run)
        logger.info("Test completed successfully")
    else:
        logger.error("No sample data available for testing")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch fixtures and gameweeks data from FPL API')
    parser.add_argument('--test', action='store_true', 
                       help='Run in test mode with sample data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without making database changes (shows what would happen)')
    parser.add_argument('--season', type=str, default=CURRENT_SEASON,
                       help=f'Season to process (default: {CURRENT_SEASON})')
    parser.add_argument('--cleanup-count', type=int, default=5,
                       help='Number of sample files to keep (0 to disable cleanup)')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force API refresh regardless of validation results')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.test:
        test_with_sample_data(season=args.season, dry_run=args.dry_run)
    else:
        main(season=args.season, dry_run=args.dry_run, cleanup_count=args.cleanup_count, force_refresh=args.force_refresh)