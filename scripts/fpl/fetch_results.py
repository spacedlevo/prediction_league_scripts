#!/usr/bin/env python3
"""
Modern FPL Results Fetching System

Monitors match results and updates fixtures/results tables only when:
1. It's match day (fixtures scheduled for today)
2. Current time is within match window (first kickoff to last kickoff + 2.5 hours)
3. There are actual changes to process

FUNCTIONALITY:
- Smart timing: Only runs during active match periods
- Change detection: Only updates database when results actually change
- Dual updates: Updates both fixtures status and results data
- API efficiency: No unnecessary calls outside match windows
- Sample data support: Test mode for development

TIMEZONE HANDLING:
- Fixed Aug 2025: Database kickoff times are stored as UTC
- Match window detection now correctly handles UTC timestamps
- Eliminates timezone conversion bugs that prevented results fetching

TIMESTAMP UPDATES:
- Fixed Aug 2025: Critical transaction bug in last_update table updates
- Now correctly updates "results" timestamp after database changes
- Ensures upload monitoring can detect when results are updated
- Maintains transaction integrity for all database operations
"""

import json
import requests
import sqlite3 as sql
import argparse
import logging
import glob
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import centralized configuration
from scripts.config import CURRENT_SEASON

# Configuration
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
samples_dir = Path(__file__).parent.parent.parent / "samples" / "results"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
samples_dir.mkdir(parents=True, exist_ok=True)
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"fetch_results_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_database_connection():
    """Get database connection and cursor"""
    conn = sql.connect(db_path)
    return conn, conn.cursor()

def get_current_gameweek(cursor):
    """Get current gameweek from database"""
    try:
        cursor.execute("""
            SELECT gameweek FROM gameweeks 
            WHERE current_gameweek = 1
            LIMIT 1
        """)
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception:
        return None

def is_match_day_window(gameweek, cursor, logger):
    """Check if current time is within match day window for gameweek"""
    try:
        # Check if there are fixtures today
        cursor.execute("""
            SELECT 
                MIN(kickoff_dttm) as first_kickoff,
                MAX(kickoff_dttm) as last_kickoff,
                COUNT(*) as fixture_count
            FROM fixtures 
            WHERE gameweek = ? 
            AND season = ?
            AND DATE(kickoff_dttm) = DATE('now')
        """, (gameweek, CURRENT_SEASON))
        
        result = cursor.fetchone()
        if not result or result[2] == 0:
            logger.debug(f"No fixtures today for gameweek {gameweek}")
            return False, "No fixtures scheduled for today"
        
        first_kickoff, last_kickoff, fixture_count = result
        logger.info(f"Found {fixture_count} fixtures today for gameweek {gameweek}")
        
        # Parse kickoff times - database stores naive datetimes as UTC time
        # Convert to timezone-aware UTC for comparison
        try:
            # Handle both formats: with and without 'Z' suffix
            first_kickoff_str = first_kickoff.replace('Z', '') if first_kickoff.endswith('Z') else first_kickoff
            last_kickoff_str = last_kickoff.replace('Z', '') if last_kickoff.endswith('Z') else last_kickoff
            
            # Parse as naive datetime (database stores UTC time)
            first_kickoff_naive = datetime.fromisoformat(first_kickoff_str)
            last_kickoff_naive = datetime.fromisoformat(last_kickoff_str)
            
            # Convert to timezone-aware UTC (database times are UTC)
            first_kickoff_dt = first_kickoff_naive.replace(tzinfo=timezone.utc)
            last_kickoff_dt = last_kickoff_naive.replace(tzinfo=timezone.utc)
            
            # Current time in UTC
            current_time = datetime.now(timezone.utc)
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing kickoff times: {e}")
            logger.debug(f"first_kickoff: {first_kickoff}, last_kickoff: {last_kickoff}")
            return False, f"Error parsing kickoff times: {e}"
        
        # Check if within window (first kickoff to last kickoff + 2.5 hours)
        window_end = last_kickoff_dt + timedelta(hours=2, minutes=30)
        
        if first_kickoff_dt <= current_time <= window_end:
            logger.info(f"Within match window (UTC): {first_kickoff_dt} to {window_end} (current: {current_time})")
            return True, f"Active match window ({fixture_count} fixtures)"
        else:
            logger.info(f"Outside match window (UTC). Current: {current_time}, Window: {first_kickoff_dt} to {window_end}")
            return False, f"Outside match window ({fixture_count} fixtures scheduled)"
        
    except Exception as e:
        logger.error(f"Error checking match day window: {e}")
        return False, f"Error checking window: {e}"

def check_missing_results(gameweek, cursor, logger):
    """Check for fixtures that have been played but don't have results yet"""
    try:
        cursor.execute("""
            SELECT 
                F.fixture_id,
                F.home_teamid,
                F.away_teamid,
                F.kickoff_dttm,
                F.started,
                F.finished,
                F.provisional_finished
            FROM fixtures AS F
            LEFT JOIN results AS R ON R.fixture_id = F.fixture_id 
            WHERE F.season = ? 
            AND F.gameweek = ?
            AND R.fixture_id IS NULL  -- No results found
            AND (F.started = 1 OR F.finished = 1)  -- But fixture has started/finished
        """, (CURRENT_SEASON, gameweek))
        
        missing_results = cursor.fetchall()
        
        if missing_results:
            logger.info(f"Found {len(missing_results)} fixtures with missing results:")
            for fixture in missing_results:
                fixture_id, home_team, away_team, kickoff, started, finished, prov_finished = fixture
                status_flags = f"started={started}, finished={finished}, provisional={prov_finished}"
                logger.info(f"  Fixture {fixture_id}: Teams {home_team} vs {away_team}, kickoff: {kickoff}, {status_flags}")
            
            return len(missing_results)
        else:
            logger.debug(f"No missing results found for gameweek {gameweek}")
            return 0
            
    except Exception as e:
        logger.error(f"Error checking missing results: {e}")
        return 0

def should_fetch_results(gameweek, cursor, logger, override_timing=False):
    """Determine if we should fetch results - timing window OR missing results OR override"""
    try:
        # Check 1: Missing results for played fixtures
        missing_count = check_missing_results(gameweek, cursor, logger)
        if missing_count > 0:
            return True, f"Missing results for {missing_count} played fixtures"
        
        # Check 2: Override mode (skip timing check)
        if override_timing:
            return True, "Override mode enabled"
            
        # Check 3: Timing window
        in_window, window_reason = is_match_day_window(gameweek, cursor, logger)
        if in_window:
            return True, window_reason
        
        # No reason to fetch results
        return False, window_reason
        
    except Exception as e:
        logger.error(f"Error in should_fetch_results: {e}")
        return False, f"Error checking fetch conditions: {e}"

def fetch_fixtures_data(gameweek, logger):
    """Fetch fixtures data from FPL API"""
    try:
        url = f"{FPL_FIXTURES_URL}?event={gameweek}"
        logger.info(f"Fetching fixtures data from: {url}")
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            fixtures_data = response.json()
            logger.info(f"Successfully retrieved {len(fixtures_data)} fixtures from FPL API")
            return fixtures_data
        else:
            logger.error(f"FPL API request failed with status {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("FPL API request timed out after 30 seconds")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"FPL API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching fixtures data: {e}")
        return None

def save_sample_data(fixtures_data, logger):
    """Save API response as sample data for testing"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sample_file = samples_dir / f"fixtures_data_{timestamp}.json"
        
        with open(sample_file, 'w') as f:
            json.dump(fixtures_data, f, indent=2)
        
        logger.info(f"Sample data saved to: {sample_file}")
        return sample_file
        
    except Exception as e:
        logger.error(f"Error saving sample data: {e}")
        return None

def load_latest_sample_data(logger):
    """Load most recent sample data for testing"""
    try:
        sample_files = list(glob.glob(str(samples_dir / "fixtures_data_*.json")))
        if not sample_files:
            logger.error("No sample data files found")
            return None
        
        # Get most recent file
        latest_file = max(sample_files, key=os.path.getmtime)
        logger.info(f"Loading sample data from: {latest_file}")
        
        with open(latest_file, 'r') as f:
            return json.load(f)
            
    except Exception as e:
        logger.error(f"Error loading sample data: {e}")
        return None

def cleanup_old_sample_files(keep_count=5, logger=None):
    """Keep only the latest N sample files, remove older ones"""
    try:
        sample_files = list(glob.glob(str(samples_dir / "fixtures_data_*.json")))
        
        if len(sample_files) <= keep_count:
            return
        
        # Sort files by modification time (newest first)
        sample_files.sort(key=os.path.getmtime, reverse=True)
        
        # Remove older files
        files_to_remove = sample_files[keep_count:]
        for file_path in files_to_remove:
            os.remove(file_path)
            if logger:
                logger.debug(f"Removed old sample file: {file_path}")
        
        if logger:
            logger.info(f"Cleaned up {len(files_to_remove)} old sample files (kept {keep_count})")
            
    except Exception as e:
        if logger:
            logger.error(f"Error cleaning up sample files: {e}")

def calculate_match_result(home_goals, away_goals):
    """Calculate match result: H (Home Win), A (Away Win), or D (Draw)"""
    if home_goals > away_goals:
        return "H"
    elif home_goals < away_goals:
        return "A"
    else:
        return "D"

def get_team_id_from_fpl_id(fpl_id, cursor):
    """Get team_id from FPL team ID"""
    try:
        cursor.execute("SELECT team_id FROM teams WHERE fpl_id = ? AND available = 1", (fpl_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception:
        return None

def process_fixtures_status_changes(fixtures_data, cursor, logger, dry_run=False):
    """Process and update fixture status changes (started, finished, provisional_finished)"""
    status_changes = {
        'started': 0,
        'finished': 0,
        'provisional_finished': 0,
        'total_updated': 0
    }
    
    for fixture in fixtures_data:
        try:
            fpl_fixture_id = fixture["id"]
            started_status = fixture.get("started", False)
            finished_status = fixture.get("finished", False)
            provisional_finished_status = fixture.get("finished_provisional", False)
            
            # Get current status from database
            cursor.execute("""
                SELECT started, finished, provisional_finished 
                FROM fixtures 
                WHERE fpl_fixture_id = ? AND season = ?
            """, (fpl_fixture_id, CURRENT_SEASON))
            
            current_status = cursor.fetchone()
            if not current_status:
                continue
            
            current_started, current_finished, current_provisional_finished = current_status
            status_changed = False
            
            # Check for changes
            if current_started != started_status:
                status_changes['started'] += 1
                status_changed = True
                logger.info(f"Fixture {fpl_fixture_id} started status: {current_started} -> {started_status}")
            
            if current_finished != finished_status:
                status_changes['finished'] += 1
                status_changed = True
                logger.info(f"Fixture {fpl_fixture_id} finished status: {current_finished} -> {finished_status}")
            
            if current_provisional_finished != provisional_finished_status:
                status_changes['provisional_finished'] += 1
                status_changed = True
                logger.info(f"Fixture {fpl_fixture_id} provisional_finished: {current_provisional_finished} -> {provisional_finished_status}")
            
            # Update database if status changed
            if status_changed and not dry_run:
                cursor.execute("""
                    UPDATE fixtures 
                    SET started = ?, finished = ?, provisional_finished = ?
                    WHERE fpl_fixture_id = ? AND season = ?
                """, (started_status, finished_status, provisional_finished_status, fpl_fixture_id, CURRENT_SEASON))
                
                if cursor.rowcount > 0:
                    status_changes['total_updated'] += 1
                    
        except Exception as e:
            logger.error(f"Error processing fixture {fixture.get('id', 'unknown')}: {e}")
    
    if dry_run:
        logger.info(f"DRY RUN: Would update {status_changes['total_updated']} fixture status records")
    elif status_changes['total_updated'] > 0:
        logger.info(f"Updated status for {status_changes['total_updated']} fixtures")
    
    return status_changes

def process_results_changes(fixtures_data, cursor, logger, dry_run=False):
    """Process and update match results"""
    results_changes = {
        'new_results': 0,
        'updated_results': 0,
        'total_processed': 0
    }
    
    for fixture in fixtures_data:
        try:
            # Only process fixtures with score data
            if not fixture.get("started") or fixture.get("team_h_score") is None or fixture.get("team_a_score") is None:
                continue
            
            fpl_fixture_id = fixture["id"]
            home_fpl_id = fixture["team_h"]
            away_fpl_id = fixture["team_a"]
            home_goals = fixture["team_h_score"]
            away_goals = fixture["team_a_score"]
            
            # Get team_ids and fixture_id
            home_team_id = get_team_id_from_fpl_id(home_fpl_id, cursor)
            away_team_id = get_team_id_from_fpl_id(away_fpl_id, cursor)
            
            if not home_team_id or not away_team_id:
                logger.warning(f"Could not find team IDs for FPL teams {home_fpl_id}, {away_fpl_id}")
                continue
            
            # Get fixture_id
            cursor.execute("""
                SELECT fixture_id FROM fixtures 
                WHERE home_teamid = ? AND away_teamid = ? AND season = ?
            """, (home_team_id, away_team_id, CURRENT_SEASON))
            
            fixture_result = cursor.fetchone()
            if not fixture_result:
                logger.warning(f"Could not find fixture for teams {home_team_id}, {away_team_id}")
                continue
            
            fixture_id = fixture_result[0]
            
            # Check if result already exists
            cursor.execute("SELECT home_goals, away_goals FROM results WHERE fixture_id = ?", (fixture_id,))
            existing_result = cursor.fetchone()
            
            match_result = calculate_match_result(home_goals, away_goals)
            
            if existing_result:
                # Check if result changed
                existing_home, existing_away = existing_result
                if existing_home != home_goals or existing_away != away_goals:
                    logger.info(f"Result changed for fixture {fixture_id}: ({existing_home}-{existing_away}) -> ({home_goals}-{away_goals})")
                    
                    if not dry_run:
                        cursor.execute("""
                            UPDATE results 
                            SET fpl_fixture_id = ?, home_goals = ?, away_goals = ?, result = ?
                            WHERE fixture_id = ?
                        """, (fpl_fixture_id, home_goals, away_goals, match_result, fixture_id))
                    
                    results_changes['updated_results'] += 1
                    results_changes['total_processed'] += 1
            else:
                # New result
                logger.info(f"New result for fixture {fixture_id}: {home_goals}-{away_goals}")
                
                if not dry_run:
                    cursor.execute("""
                        INSERT INTO results (fixture_id, fpl_fixture_id, home_goals, away_goals, result)
                        VALUES (?, ?, ?, ?, ?)
                    """, (fixture_id, fpl_fixture_id, home_goals, away_goals, match_result))
                
                results_changes['new_results'] += 1
                results_changes['total_processed'] += 1
                
        except Exception as e:
            logger.error(f"Error processing result for fixture {fixture.get('id', 'unknown')}: {e}")
    
    if dry_run:
        logger.info(f"DRY RUN: Would process {results_changes['total_processed']} result changes")
    elif results_changes['total_processed'] > 0:
        logger.info(f"Processed {results_changes['total_processed']} result changes: {results_changes['new_results']} new, {results_changes['updated_results']} updated")
    
    return results_changes

def update_last_update_table(table_name, cursor, logger):
    """Update the last_update table with current timestamp"""
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y %H:%M:%S")
        timestamp = dt.timestamp()
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES (?, ?, ?)
        """, (table_name, now, timestamp))
        
        logger.info(f"Updated last_update table for '{table_name}'")
        
    except Exception as e:
        logger.error(f"Error updating last_update table for '{table_name}': {e}")

def main(test_mode=False, override_timing=False, dry_run=False, cleanup_count=5):
    """Main execution function"""
    logger = setup_logging()
    logger.info("Starting FPL results fetching process")
    
    try:
        # Setup database
        conn, cursor = get_database_connection()
        
        # Get current gameweek
        current_gameweek = get_current_gameweek(cursor)
        if not current_gameweek:
            logger.error("Could not determine current gameweek")
            return
        
        logger.info(f"Current gameweek: {current_gameweek}")
        
        # Check if we should fetch results (comprehensive logic)
        should_fetch, fetch_reason = should_fetch_results(current_gameweek, cursor, logger, override_timing)
        if not should_fetch:
            logger.info(f"Not running: {fetch_reason}")
            return
        
        logger.info(f"Proceeding with results fetch: {fetch_reason}")
        
        # Get fixtures data
        if test_mode:
            logger.info("Running in test mode with sample data")
            fixtures_data = load_latest_sample_data(logger)
            if not fixtures_data:
                logger.error("Could not load sample data")
                return
        else:
            fixtures_data = fetch_fixtures_data(current_gameweek, logger)
            if not fixtures_data:
                logger.error("Could not fetch fixtures data from API")
                return
            
            # Save sample data for future testing
            save_sample_data(fixtures_data, logger)
            
            # Cleanup old sample files
            cleanup_old_sample_files(cleanup_count, logger)
        
        if dry_run:
            logger.info("DRY RUN MODE: No database changes will be made")
        
        # Process fixture status changes
        status_changes = process_fixtures_status_changes(fixtures_data, cursor, logger, dry_run)
        
        # Process results changes  
        results_changes = process_results_changes(fixtures_data, cursor, logger, dry_run)
        
        # Commit changes and update tracking
        if not dry_run:
            if status_changes['total_updated'] > 0 or results_changes['total_processed'] > 0:
                update_last_update_table("results", cursor, logger)
                conn.commit()
                logger.info("Database changes committed successfully")
            else:
                logger.info("No changes to commit")
        
        # Summary
        total_changes = status_changes['total_updated'] + results_changes['total_processed']
        if total_changes > 0:
            logger.info(f"Processing complete: {status_changes['total_updated']} fixture updates, {results_changes['total_processed']} result changes")
        else:
            logger.info("Processing complete: No changes detected")
            
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()
        logger.info("FPL results fetching process completed")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch FPL results and update database')
    parser.add_argument('--test', action='store_true',
                       help='Run with sample data instead of live API')
    parser.add_argument('--override', action='store_true',
                       help='Override timing window (always run)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without making changes')
    parser.add_argument('--cleanup-count', type=int, default=5,
                       help='Number of sample files to keep (default: 5)')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main(
        test_mode=args.test,
        override_timing=args.override,
        dry_run=args.dry_run,
        cleanup_count=args.cleanup_count
    )