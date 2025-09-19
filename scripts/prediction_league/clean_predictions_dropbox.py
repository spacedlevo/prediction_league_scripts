#!/usr/bin/env python3
"""
Dropbox-Based Prediction Cleaning System

Monitors .txt files in Dropbox predictions folder, downloads and processes changed files,
then saves cleaned predictions as CSV files locally.

FUNCTIONALITY:
- Uses Dropbox API to monitor predictions_league/Predictions/2025_26/ folder
- Compares file timestamps against file_metadata table for change detection
- Downloads and processes changed prediction files
- Cleans team names and extracts scores using existing logic
- Saves cleaned predictions to data/predictions/2025_26/ as CSV files
- Updates database tracking tables

DUPLICATE PREVENTION:
- Fixed fixture matching logic to handle team order mismatches (Aug 2025)
- Added unique constraint on (player_id, fixture_id) to prevent duplicate predictions
- Uses INSERT OR REPLACE to handle conflicts gracefully
- Processes 260 predictions per gameweek (26 players × 10 fixtures)

FIXTURE MATCHING:
- get_fixture_id() tries both team orders to handle CSV vs database differences
- Example: CSV "burnley,man utd" matches DB fixture "man utd vs burnley"
- This prevents predictions being skipped due to team order mismatches
"""

import json
import requests
import sqlite3 as sql
import csv
import re
import os
import logging
import argparse
import tempfile
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

# Configuration
CURRENT_SEASON = "2025_26"
CURRENT_SEASON_DB = "2025/2026"
DROPBOX_FOLDER = "/Predictions/2025_26"  # App-sandboxed path (no /Apps prefix needed)

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
keys_file = Path(__file__).parent.parent.parent / "keys.json"
predictions_dir = Path(__file__).parent.parent.parent / "data" / "predictions" / CURRENT_SEASON
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
predictions_dir.mkdir(parents=True, exist_ok=True)
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"clean_predictions_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def load_config():
    """Load API keys and configuration"""
    with open(keys_file, 'r') as f:
        return json.load(f)

def update_keys_file(config, logger):
    """Safely update keys.json file with new configuration"""
    try:
        # Create temporary file in same directory for atomic update
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            dir=keys_file.parent, 
            delete=False,
            suffix='.tmp'
        )
        
        try:
            # Write updated config to temp file
            json.dump(config, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            
            # Atomic move to replace original file, preserving permissions
            # Capture original file permissions before replacing
            original_stat = os.stat(keys_file)
            shutil.move(temp_file.name, keys_file)
            # Restore original permissions and ownership
            os.chmod(keys_file, original_stat.st_mode)
            os.chown(keys_file, original_stat.st_uid, original_stat.st_gid)
            logger.info("Successfully updated keys.json with new Dropbox token (permissions preserved)")
            return True
            
        except Exception as e:
            temp_file.close()
            # Clean up temp file if something went wrong
            try:
                os.unlink(temp_file.name)
            except:
                pass
            raise e
            
    except Exception as e:
        logger.error(f"Failed to update keys.json: {e}")
        return False

def refresh_dropbox_token(config, logger):
    """Refresh expired Dropbox token using refresh token"""
    try:
        # Check if we have required credentials for refresh
        required_keys = ['dropbox_app_key', 'dropbox_app_secret']
        if not all(key in config for key in required_keys):
            logger.error("Missing dropbox_app_key or dropbox_app_secret for token refresh")
            return False
        
        # Check if we have a refresh token
        if 'dropbox_refresh_token' not in config:
            logger.warning("No refresh token available. This appears to be a legacy long-lived token.")
            logger.warning("Long-lived tokens cannot be refreshed automatically.")
            logger.warning("SOLUTIONS:")
            logger.warning("1. Run: python scripts/prediction_league/setup_dropbox_oauth.py")
            logger.warning("2. Or generate a new token from: https://www.dropbox.com/developers/apps")
            logger.warning("3. Or manually add 'dropbox_refresh_token' to keys.json if you have one")
            return False
        
        # Attempt to refresh the token
        logger.info("Attempting to refresh Dropbox access token...")
        
        refresh_data = {
            'grant_type': 'refresh_token',
            'refresh_token': config['dropbox_refresh_token'],
            'client_id': config['dropbox_app_key'],
            'client_secret': config['dropbox_app_secret']
        }
        
        response = requests.post(
            'https://api.dropboxapi.com/oauth2/token',
            data=refresh_data
        )
        
        if response.status_code == 200:
            token_data = response.json()
            
            # Update the access token in config (fix typo: oath -> oauth)
            config['dropbox_oath_token'] = token_data['access_token']
            
            # Update refresh token if provided
            if 'refresh_token' in token_data:
                config['dropbox_refresh_token'] = token_data['refresh_token']
            
            # Save updated config to file
            if update_keys_file(config, logger):
                logger.info("Successfully refreshed and saved new Dropbox access token")
                return True
            else:
                logger.error("Failed to save refreshed token to keys.json")
                return False
        else:
            logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"Error during token refresh: {e}")
        return False

def get_database_connection():
    """Get database connection and cursor"""
    conn = sql.connect(db_path)
    return conn, conn.cursor()

def create_file_metadata_table(cursor):
    """Ensure file_metadata table exists"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            filename TEXT PRIMARY KEY,
            last_modified TIMESTAMP
        )
    """)

def load_teams_and_players(cursor, logger):
    """Load teams and active players from database"""
    # Load teams
    cursor.execute("SELECT team_name FROM teams WHERE available = 1")
    teams = [team[0].lower() for team in cursor.fetchall()]
    
    # Load active players
    cursor.execute("SELECT player_name FROM players WHERE active = 1")
    players = [player[0] for player in cursor.fetchall()]
    
    logger.info(f"Loaded {len(teams)} teams and {len(players)} active players")
    return teams, players

def list_dropbox_files(config, logger):
    """List all .txt files in Dropbox predictions folder with token refresh capability"""
    def make_request():
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'path': DROPBOX_FOLDER,
            'recursive': False
        }
        
        return requests.post(
            'https://api.dropboxapi.com/2/files/list_folder',
            headers=headers,
            json=data
        )
    
    try:
        response = make_request()
        
        # Check if token is expired
        if response.status_code == 401:
            logger.warning("Dropbox token expired, attempting refresh...")
            if refresh_dropbox_token(config, logger):
                # If refresh successful, reload config and retry
                config = load_config()
                response = make_request()
            else:
                logger.error("Token refresh failed")
                return []
        
        if response.status_code == 200:
            result = response.json()
            txt_files = []
            
            for entry in result.get('entries', []):
                if entry.get('name', '').endswith('.txt') and entry.get('.tag') == 'file':
                    txt_files.append({
                        'name': entry['name'],
                        'path': entry['path_lower'],
                        'modified': entry['server_modified']
                    })
            
            logger.info(f"Found {len(txt_files)} .txt files in Dropbox folder")
            return txt_files
        else:
            logger.error(f"Failed to list Dropbox files: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        logger.error(f"Error listing Dropbox files: {e}")
        return []

def get_file_modification_timestamp(modified_str):
    """Convert Dropbox timestamp to Unix timestamp"""
    try:
        # Parse Dropbox timestamp format: "2025-08-29T10:00:00Z"
        dt = datetime.fromisoformat(modified_str.replace('Z', '+00:00'))
        return dt.timestamp()
    except Exception:
        return 0

def is_file_modified(file_info, cursor, logger):
    """Check if file has been modified since last processing"""
    filename = file_info['name']
    dropbox_timestamp = get_file_modification_timestamp(file_info['modified'])
    
    cursor.execute("""
        SELECT last_modified FROM file_metadata WHERE filename = ?
    """, (filename,))
    
    result = cursor.fetchone()
    
    if result is None:
        logger.info(f"File {filename} is new and will be processed")
        return True
    elif dropbox_timestamp > result[0]:
        logger.info(f"File {filename} has been modified and will be processed")
        return True
    else:
        logger.debug(f"File {filename} has not been modified")
        return False

def download_dropbox_file(file_info, config, logger):
    """Download file content from Dropbox with token refresh capability"""
    def make_request():
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Dropbox-API-Arg': json.dumps({'path': file_info['path']})
        }
        
        return requests.post(
            'https://content.dropboxapi.com/2/files/download',
            headers=headers
        )
    
    try:
        response = make_request()
        
        # Check if token is expired
        if response.status_code == 401:
            logger.warning("Dropbox token expired during download, attempting refresh...")
            if refresh_dropbox_token(config, logger):
                # If refresh successful, reload config and retry
                config = load_config()
                response = make_request()
            else:
                logger.error("Token refresh failed during download")
                return None
        
        if response.status_code == 200:
            content = response.content.decode('utf-8-sig')
            logger.info(f"Successfully downloaded {file_info['name']}")
            return content
        else:
            logger.error(f"Failed to download {file_info['name']}: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error downloading {file_info['name']}: {e}")
        return None

def update_file_metadata(file_info, cursor, logger):
    """Update file metadata in database"""
    filename = file_info['name']
    timestamp = get_file_modification_timestamp(file_info['modified'])
    
    try:
        cursor.execute("""
            INSERT INTO file_metadata (filename, last_modified)
            VALUES (?, ?)
            ON CONFLICT(filename) DO UPDATE SET last_modified=excluded.last_modified
        """, (filename, timestamp))
        
        logger.info(f"Updated metadata for file {filename}")
        
    except Exception as e:
        logger.error(f"Failed to update metadata for file {filename}: {e}")

def find_scores(line):
    """Extract scores from a line of text"""
    goals = []
    current_score = ""
    for char in line:
        if char.isdigit():
            current_score += char
        elif current_score:
            goals.append(int(current_score))
            current_score = ""
    if current_score:  # Add the last score if any
        goals.append(int(current_score))
    return goals

def extract_teams_from_line(line, teams, logger):
    """Extract team names from a line using regex patterns"""
    sides = []
    line_lower = line.lower()
    
    # First try exact matching
    for team in teams:
        if team in line_lower:
            sides.append(team)
    
    # If we found exactly 2 teams, return them
    if len(sides) == 2:
        return sides
    
    # Try regex pattern matching as fallback
    sides = []
    found = re.findall(r"\s?[v]?\s?[a-z']+\s?[a-z']+\s?", line, re.IGNORECASE)
    
    for potential_match in found:
        for team in teams:
            if re.search(r'\b{}\b'.format(re.escape(team)), potential_match.lower()):
                if team not in sides:  # Avoid duplicates
                    sides.append(team)
                break
    
    return sides[:2]  # Return max 2 teams

def clean_predictions_content(content, teams, players, gameweek, logger):
    """Clean and process prediction file content"""
    predictions = []
    lines = content.lower().splitlines()
    current_player = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line contains a player name
        if line in [p.lower() for p in players]:
            # Find the actual player name with proper casing
            current_player = next((p for p in players if p.lower() == line), None)
            continue
        
        # Process prediction lines
        if current_player:
            sides = extract_teams_from_line(line, teams, logger)
            scores = find_scores(line)
            
            if len(sides) == 2:
                try:
                    home_goals = scores[0] if len(scores) >= 1 else 9
                    away_goals = scores[1] if len(scores) >= 2 else 9
                    
                    prediction = [
                        gameweek,
                        current_player,
                        sides[0],
                        sides[1],
                        home_goals,
                        away_goals
                    ]
                    predictions.append(prediction)
                    logger.debug(f"Added prediction: {prediction}")
                    
                except (IndexError, ValueError) as e:
                    logger.warning(f"Error processing line '{line}' for {current_player}: {e}")
                    
                    # Add default prediction
                    prediction = [gameweek, current_player, sides[0], sides[1], 9, 9]
                    predictions.append(prediction)
    
    logger.info(f"Processed {len(predictions)} predictions from file content")
    return predictions

def check_for_missing_players(predictions, players, gameweek, cursor, logger):
    """Add default predictions for players who haven't submitted"""
    submitted_players = set([pred[1] for pred in predictions])
    missing_players = [p for p in players if p not in submitted_players]
    
    if not missing_players:
        return predictions
    
    logger.info(f"Adding default predictions for {len(missing_players)} missing players")
    
    # Get fixtures for this gameweek
    cursor.execute("""
        SELECT ht.team_name, at.team_name
        FROM fixtures
        JOIN teams AS ht ON ht.team_id = fixtures.home_teamid
        JOIN teams AS at ON at.team_id = fixtures.away_teamid
        WHERE gameweek = ? AND season = ?
    """, (gameweek, CURRENT_SEASON_DB))
    
    fixtures = cursor.fetchall()
    
    for player in missing_players:
        for home_team, away_team in fixtures:
            default_prediction = [gameweek, player, home_team.lower(), away_team.lower(), 9, 9]
            predictions.append(default_prediction)
    
    return predictions

def keep_latest_predictions(predictions):
    """Keep only the latest prediction per player per fixture"""
    # Group predictions by (player, home_team, away_team)
    fixture_groups = {}
    
    for prediction in predictions:
        gameweek, player, home_team, away_team, home_goals, away_goals = prediction
        fixture_key = (player, home_team, away_team)
        
        # Always keep the latest (last in file) - this overwrites any previous prediction
        fixture_groups[fixture_key] = prediction
    
    # Return all unique predictions (latest per player per fixture)
    unique_predictions = list(fixture_groups.values())
    return unique_predictions

def save_predictions_to_csv(predictions, gameweek, logger):
    """Save predictions to CSV file"""
    csv_file = predictions_dir / f"predictions{gameweek}.csv"
    header = ["gameweek", "player", "home_team", "away_team", "home_goals", "away_goals"]
    
    try:
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(predictions)
        
        logger.info(f"Saved {len(predictions)} predictions to {csv_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving predictions to CSV: {e}")
        return False

def update_last_update_table(cursor, logger):
    """Update the last_update table with current timestamp"""
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y %H:%M:%S")
        timestamp = dt.timestamp()
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES ('cleaned_predictions', ?, ?)
        """, (now, timestamp))
        
        logger.info("Updated last_update table for 'cleaned_predictions'")
        
    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")

def extract_gameweek_from_filename(filename):
    """Extract gameweek number from filename like 'gameweek3.txt'"""
    match = re.search(r'gameweek(\d+)\.txt', filename.lower())
    if match:
        return int(match.group(1))
    return None

def get_player_id(player_name, cursor):
    """Get player_id from player name"""
    try:
        cursor.execute("""
            SELECT player_id FROM players 
            WHERE LOWER(player_name) = LOWER(?)
        """, (player_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception:
        return None

def get_fixture_id(home_team, away_team, gameweek, cursor):
    """
    Get fixture_id by matching teams and gameweek (tries both team orders)
    
    FIXED Aug 2025: Previously only tried exact team order, causing prediction
    mismatches when CSV had different team order than database fixtures.
    Now tries both orders to ensure all fixtures are properly matched.
    """
    try:
        # Try exact order first
        cursor.execute("""
            SELECT f.fixture_id, f.fpl_fixture_id, ht.team_name, at.team_name
            FROM fixtures f
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            WHERE LOWER(ht.team_name) = LOWER(?)
            AND LOWER(at.team_name) = LOWER(?)
            AND f.gameweek = ?
            AND f.season = ?
        """, (home_team, away_team, gameweek, CURRENT_SEASON_DB))
        result = cursor.fetchone()
        if result:
            return result[0], result[1]  # Return fixture_id, fpl_fixture_id
        
        # Try reverse order if exact order didn't work
        cursor.execute("""
            SELECT f.fixture_id, f.fpl_fixture_id, ht.team_name, at.team_name
            FROM fixtures f
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            WHERE LOWER(ht.team_name) = LOWER(?)
            AND LOWER(at.team_name) = LOWER(?)
            AND f.gameweek = ?
            AND f.season = ?
        """, (away_team, home_team, gameweek, CURRENT_SEASON_DB))
        result = cursor.fetchone()
        return result[:2] if result else (None, None)  # Return fixture_id, fpl_fixture_id
    except Exception:
        return (None, None)

def calculate_predicted_result(home_goals, away_goals):
    """Calculate predicted result (H/D/A) from goals"""
    if home_goals > away_goals:
        return 'H'
    elif home_goals < away_goals:
        return 'A'
    else:
        return 'D'

def insert_predictions_to_database(predictions, gameweek, cursor, logger):
    """Insert predictions into database with conflict resolution"""
    inserted_count = 0
    skipped_count = 0
    
    for prediction in predictions:
        gameweek_num, player_name, home_team, away_team, home_goals, away_goals = prediction
        
        # Get player_id
        player_id = get_player_id(player_name, cursor)
        if not player_id:
            logger.warning(f"Player '{player_name}' not found in database - skipping prediction")
            skipped_count += 1
            continue
        
        # Get fixture_id and fpl_fixture_id
        fixture_id, fpl_fixture_id = get_fixture_id(home_team, away_team, gameweek, cursor)
        if not fixture_id:
            logger.warning(f"Fixture '{home_team} vs {away_team}' for gameweek {gameweek} not found - skipping prediction")
            skipped_count += 1
            continue
        
        # Calculate predicted result
        predicted_result = calculate_predicted_result(home_goals, away_goals)
        
        try:
            # Insert or replace prediction
            cursor.execute("""
                INSERT OR REPLACE INTO predictions (
                    player_id, fixture_id, fpl_fixture_id, 
                    home_goals, away_goals, predicted_result
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (player_id, fixture_id, fpl_fixture_id, home_goals, away_goals, predicted_result))
            
            inserted_count += 1
            logger.debug(f"Inserted prediction: {player_name} -> {home_team} {home_goals}-{away_goals} {away_team}")
            
        except Exception as e:
            logger.error(f"Error inserting prediction for {player_name}: {e}")
            skipped_count += 1
    
    logger.info(f"Database insertion: {inserted_count} inserted, {skipped_count} skipped")
    return inserted_count, skipped_count

def save_predictions_to_database(predictions, gameweek, cursor, logger, dry_run=False):
    """Save predictions to database with transaction handling"""
    if dry_run:
        logger.info(f"DRY RUN: Would insert {len(predictions)} predictions into database")
        return True
    
    try:
        # Insert predictions within existing transaction
        inserted_count, skipped_count = insert_predictions_to_database(predictions, gameweek, cursor, logger)
        
        if inserted_count > 0:
            logger.info(f"Successfully processed {inserted_count} predictions for database insertion")
        
        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count} predictions due to missing references")
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving predictions to database: {e}")
        return False

def process_file(file_info, config, teams, players, cursor, logger, dry_run=False):
    """Process a single prediction file"""
    filename = file_info['name']
    gameweek = extract_gameweek_from_filename(filename)
    
    if not gameweek:
        logger.warning(f"Could not extract gameweek from filename: {filename}")
        return False
    
    logger.info(f"Processing {filename} for gameweek {gameweek}")
    
    # Download file content
    content = download_dropbox_file(file_info, config, logger)
    if not content:
        return False
    
    # Clean and process predictions
    predictions = clean_predictions_content(content, teams, players, gameweek, logger)
    
    # Add missing players
    predictions = check_for_missing_players(predictions, players, gameweek, cursor, logger)
    
    # Keep only latest predictions per player per fixture
    predictions = keep_latest_predictions(predictions)
    
    if dry_run:
        logger.info(f"DRY RUN: Would save {len(predictions)} predictions for gameweek {gameweek}")
        logger.info(f"DRY RUN: Would insert {len(predictions)} predictions into database")
        return True
    
    # Save to database first (most important)
    database_success = save_predictions_to_database(predictions, gameweek, cursor, logger, dry_run)
    
    # Save to CSV (backup/reference)
    csv_success = save_predictions_to_csv(predictions, gameweek, logger)
    
    # Update file metadata if at least one save method succeeded
    if database_success or csv_success:
        update_file_metadata(file_info, cursor, logger)
        return True
    
    return False

def main(dry_run=False, specific_gameweek=None):
    """Main execution function"""
    logger = setup_logging()
    logger.info("Starting Dropbox-based prediction cleaning process")
    
    try:
        # Load configuration
        config = load_config()
        
        # Setup database
        conn, cursor = get_database_connection()
        create_file_metadata_table(cursor)
        
        # Load teams and players
        teams, players = load_teams_and_players(cursor, logger)
        
        # List files in Dropbox
        dropbox_files = list_dropbox_files(config, logger)
        if not dropbox_files:
            logger.warning("No files found in Dropbox folder")
            return
        
        # Filter by specific gameweek if requested
        if specific_gameweek:
            dropbox_files = [f for f in dropbox_files 
                           if extract_gameweek_from_filename(f['name']) == specific_gameweek]
            logger.info(f"Filtered to gameweek {specific_gameweek}: {len(dropbox_files)} files")
        
        # Process files
        processed_count = 0
        for file_info in dropbox_files:
            if is_file_modified(file_info, cursor, logger):
                if process_file(file_info, config, teams, players, cursor, logger, dry_run):
                    processed_count += 1
                else:
                    logger.error(f"Failed to process {file_info['name']}")
            else:
                logger.debug(f"Skipping unmodified file: {file_info['name']}")
        
        if processed_count > 0 and not dry_run:
            # Update database tracking
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info(f"Successfully processed {processed_count} files")
        elif dry_run:
            logger.info(f"DRY RUN: Would have processed {processed_count} files")
        else:
            logger.info("No files required processing")
            
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()
        logger.info("Prediction cleaning process completed")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Clean predictions from Dropbox files')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without making changes')
    parser.add_argument('--gameweek', type=int,
                       help='Process only specific gameweek')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main(dry_run=args.dry_run, specific_gameweek=args.gameweek)