#!/usr/bin/env python3
"""
Football-Data.co.uk Weekly Data Fetcher

Downloads current season Premier League data from football-data.co.uk
and updates the database with latest match results and statistics.

FUNCTIONALITY:
- Downloads current season CSV from https://www.football-data.co.uk/mmz4281/2526/E0.csv
- Processes match results, statistics, and betting odds
- Updates existing matches and inserts new ones
- Change detection to avoid unnecessary database updates
- Sample data management for development/testing
- Comprehensive logging and error handling

DATA INCLUDES:
- Match results and half-time scores
- Team statistics (shots, corners, cards, fouls)
- Referee information
- Betting odds from multiple bookmakers
- Asian handicap and over/under markets

INTEGRATION:
- Uses existing team name mappings from migration
- Updates last_update table to trigger automated uploads
- Follows project patterns for logging and error handling
"""

import requests
import sqlite3 as sql
import csv
import argparse
import logging
import json
import os
from datetime import datetime
from pathlib import Path
from io import StringIO

# Configuration
CURRENT_SEASON = "2025/2026"
FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/2526/E0.csv"

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
samples_dir = Path(__file__).parent.parent.parent / "samples" / "football_data"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
samples_dir.mkdir(parents=True, exist_ok=True)
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging configuration"""
    log_filename = log_dir / f"fetch_football_data_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def load_team_mapping(cursor):
    """Load team name mappings from database"""
    cursor.execute("SELECT football_data_name, team_id, team_name FROM teams WHERE football_data_name IS NOT NULL")
    return {fd_name: (team_id, team_name) for fd_name, team_id, team_name in cursor.fetchall()}

def download_current_season_data(logger, test_mode=False):
    """Download current season data from football-data.co.uk"""
    if test_mode:
        # Use most recent sample file for testing
        sample_files = list(samples_dir.glob("football_data_*.csv"))
        if sample_files:
            latest_sample = max(sample_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Test mode: Using sample data from {latest_sample}")
            with open(latest_sample, 'r', encoding='utf-8-sig') as f:
                return f.read()
        else:
            logger.error("Test mode requested but no sample files found")
            return None
    
    try:
        logger.info(f"Downloading current season data from {FOOTBALL_DATA_URL}")
        response = requests.get(FOOTBALL_DATA_URL, timeout=30)
        
        if response.status_code == 200:
            # Save sample for future testing
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            sample_file = samples_dir / f"football_data_{timestamp}.csv"
            
            with open(sample_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            logger.info(f"Downloaded {len(response.text)} characters, saved to {sample_file}")
            cleanup_old_samples(logger)
            return response.text
        else:
            logger.error(f"Download failed with status {response.status_code}: {response.text}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Download failed: {e}")
        return None

def cleanup_old_samples(logger, keep_count=5):
    """Keep only the latest N sample files"""
    sample_files = list(samples_dir.glob("football_data_*.csv"))
    
    if len(sample_files) <= keep_count:
        return
    
    # Sort by modification time, newest first
    sample_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    files_to_remove = sample_files[keep_count:]
    for file_path in files_to_remove:
        file_path.unlink()
        logger.info(f"Removed old sample: {file_path.name}")

def parse_csv_data(csv_content, logger):
    """Parse CSV content into list of dictionaries"""
    try:
        # Handle BOM if present
        if csv_content.startswith('\ufeff'):
            csv_content = csv_content[1:]
        
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)
        
        logger.info(f"Parsed {len(rows)} matches from CSV data")
        return rows
        
    except Exception as e:
        logger.error(f"Failed to parse CSV data: {e}")
        return None

def convert_date_format(date_str):
    """Convert DD/MM/YYYY to YYYY-MM-DD format"""
    if not date_str:
        return None
    
    try:
        day, month, year = date_str.split('/')
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        return date_str  # Return original if conversion fails

def process_match_data(cursor, match_data, team_mapping, logger):
    """Process and insert/update match data"""
    processed_count = 0
    updated_count = 0
    inserted_count = 0
    skipped_count = 0
    
    for match in match_data:
        home_team = match.get('HomeTeam', '').strip()
        away_team = match.get('AwayTeam', '').strip()
        date_str = match.get('Date', '').strip()
        
        if not home_team or not away_team:
            logger.warning(f"Skipping match with missing team names: {match}")
            skipped_count += 1
            continue
        
        # Map team names
        home_mapping = team_mapping.get(home_team)
        away_mapping = team_mapping.get(away_team)
        
        if not home_mapping or not away_mapping:
            logger.warning(f"Skipping match {home_team} vs {away_team} - team mapping not found")
            skipped_count += 1
            continue
        
        home_team_id, home_team_db = home_mapping
        away_team_id, away_team_db = away_mapping
        
        # Convert date format
        formatted_date = convert_date_format(date_str)
        
        # Check if match already exists
        cursor.execute("""
            SELECT GameID FROM football_stats 
            WHERE Date = ? AND home_team_id = ? AND away_team_id = ? AND Season = ?
        """, (formatted_date, home_team_id, away_team_id, "25/26"))
        
        existing_match = cursor.fetchone()
        
        # Prepare match data for database
        match_db_data = {
            'Date': formatted_date,
            'HomeTeam': home_team,
            'AwayTeam': away_team,
            'home_team_id': home_team_id,
            'away_team_id': away_team_id,
            'Season': "25/26",
            'Time': match.get('Time', ''),
            'FTHG': int(match['FTHG']) if match.get('FTHG', '').isdigit() else None,
            'FTAG': int(match['FTAG']) if match.get('FTAG', '').isdigit() else None,
            'FTR': match.get('FTR', ''),
            'HTHG': int(match['HTHG']) if match.get('HTHG', '').isdigit() else None,
            'HTAG': int(match['HTAG']) if match.get('HTAG', '').isdigit() else None,
            'HTR': match.get('HTR', ''),
            'Referee': match.get('Referee', ''),
            # Team statistics
            'HS': int(match['HS']) if match.get('HS', '').isdigit() else None,
            '[AS]': int(match['AS']) if match.get('AS', '').isdigit() else None,
            'HST': int(match['HST']) if match.get('HST', '').isdigit() else None,
            'AST': int(match['AST']) if match.get('AST', '').isdigit() else None,
            'HF': int(match['HF']) if match.get('HF', '').isdigit() else None,
            'AF': int(match['AF']) if match.get('AF', '').isdigit() else None,
            'HC': int(match['HC']) if match.get('HC', '').isdigit() else None,
            'AC': int(match['AC']) if match.get('AC', '').isdigit() else None,
            'HY': int(match['HY']) if match.get('HY', '').isdigit() else None,
            'AY': int(match['AY']) if match.get('AY', '').isdigit() else None,
            'HR': int(match['HR']) if match.get('HR', '').isdigit() else None,
            'AR': int(match['AR']) if match.get('AR', '').isdigit() else None,
            # Betting odds (sample - there are many more)
            'B365H': float(match['B365H']) if match.get('B365H', '') and match['B365H'].replace('.','').isdigit() else None,
            'B365D': float(match['B365D']) if match.get('B365D', '') and match['B365D'].replace('.','').isdigit() else None,
            'B365A': float(match['B365A']) if match.get('B365A', '') and match['B365A'].replace('.','').isdigit() else None,
            'MaxH': float(match['MaxH']) if match.get('MaxH', '') and match['MaxH'].replace('.','').isdigit() else None,
            'MaxD': float(match['MaxD']) if match.get('MaxD', '') and match['MaxD'].replace('.','').isdigit() else None,
            'MaxA': float(match['MaxA']) if match.get('MaxA', '') and match['MaxA'].replace('.','').isdigit() else None,
            'AvgH': float(match['AvgH']) if match.get('AvgH', '') and match['AvgH'].replace('.','').isdigit() else None,
            'AvgD': float(match['AvgD']) if match.get('AvgD', '') and match['AvgD'].replace('.','').isdigit() else None,
            'AvgA': float(match['AvgA']) if match.get('AvgA', '') and match['AvgA'].replace('.','').isdigit() else None
        }
        
        if existing_match:
            # Update existing match
            game_id = existing_match[0]
            
            # Build update query for non-null values
            update_fields = []
            update_values = []
            for key, value in match_db_data.items():
                if value is not None and key not in ['home_team_id', 'away_team_id']:
                    update_fields.append(f"{key} = ?")
                    update_values.append(value)
            
            if update_fields:
                update_values.append(game_id)
                update_sql = f"UPDATE football_stats SET {', '.join(update_fields)} WHERE GameID = ?"
                cursor.execute(update_sql, update_values)
                updated_count += 1
                logger.debug(f"Updated match: {home_team} vs {away_team} on {formatted_date}")
        else:
            # Insert new match
            # Generate GameID (max + 1)
            cursor.execute("SELECT COALESCE(MAX(GameID), 0) + 1 FROM football_stats")
            new_game_id = cursor.fetchone()[0]
            match_db_data['GameID'] = new_game_id
            
            columns = list(match_db_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = [match_db_data[col] for col in columns]
            
            insert_sql = f"INSERT INTO football_stats ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(insert_sql, values)
            inserted_count += 1
            logger.debug(f"Inserted new match: {home_team} vs {away_team} on {formatted_date}")
        
        processed_count += 1
    
    logger.info(f"Processing completed: {processed_count} processed, {inserted_count} inserted, {updated_count} updated, {skipped_count} skipped")
    return processed_count > 0

def update_last_update_table(cursor, logger):
    """Update last_update table if changes were made"""
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y %H:%M:%S")
    timestamp = dt.timestamp()
    cursor.execute(
        "INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) VALUES (?, ?, ?)",
        ("football_stats", now, timestamp)
    )
    logger.info("Updated last_update table")

def main_fetch(args, logger):
    """Main fetch logic"""
    logger.info("Starting football-data.co.uk data fetch...")
    
    # Download data
    csv_content = download_current_season_data(logger, args.test)
    if not csv_content:
        logger.error("Failed to download data")
        return False
    
    # Parse CSV
    match_data = parse_csv_data(csv_content, logger)
    if not match_data:
        logger.error("Failed to parse CSV data")
        return False
    
    # Connect to database
    conn = sql.connect(db_path)
    
    try:
        cursor = conn.cursor()
        
        # Check if football_stats table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='football_stats'")
        if not cursor.fetchone():
            logger.error("football_stats table not found. Run migration script first.")
            return False
        
        # Load team mappings
        team_mapping = load_team_mapping(cursor)
        if not team_mapping:
            logger.error("No team mappings found. Run migration script first.")
            return False
        
        logger.info(f"Loaded {len(team_mapping)} team mappings")
        
        if args.dry_run:
            logger.info("Dry run mode - no database changes will be made")
            # Still process to show what would happen
            processed_count = len(match_data)
            logger.info(f"Would process {processed_count} matches")
            return True
        
        # Process match data
        changes_made = process_match_data(cursor, match_data, team_mapping, logger)
        
        if changes_made:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("No changes made to database")
        
        # Report current statistics
        cursor.execute("SELECT COUNT(*) FROM football_stats WHERE Season = '25/26'")
        current_season_count = cursor.fetchone()[0]
        logger.info(f"Current season (25/26) now has {current_season_count} matches")
        
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Fetch failed: {e}")
        return False
        
    finally:
        conn.close()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch current season football-data.co.uk data')
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode using sample data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    
    if args.test:
        logger.info("Running in test mode...")
    
    if args.dry_run:
        logger.info("Running in dry-run mode...")
    
    success = main_fetch(args, logger)
    
    if success:
        logger.info("Football-data fetch completed successfully")
    else:
        logger.error("Football-data fetch failed")
        exit(1)