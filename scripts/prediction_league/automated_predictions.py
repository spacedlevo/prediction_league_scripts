#!/usr/bin/env python3
"""
Automated Predictions Script with Intelligent Strategy Recommendations

This script checks for upcoming gameweeks and automatically generates predictions
based on odds data using the intelligent season recommendation system. It uploads
predictions to Dropbox and sends notifications via Pushover.

FUNCTIONALITY:
- **PREDICTIONS**: Generated when deadline is within 12 hours
- **FIXTURES**: Notification sent when deadline is within 36 hours
- Uses intelligent season recommendations to determine optimal strategy (1-0 vs 2-1)
- Generates predictions based on current season analysis:
  * 1-0 strategy when >47% matches are low-scoring
  * 2-1 strategy when ≤47% matches are low-scoring
- Uploads predictions to two Dropbox locations:
  * /predictions_league/odds-api/predictions{gameweek}.txt (new file)
  * /predictions_league/Predictions/2025_26/gameweek{gameweek}.txt (append/create)
- Sends notifications via Pushover API with UK timezone conversion
- Prevents duplicate runs using database tracking

TIMING LOGIC:
- Script runs hourly via scheduler but uses different timing windows:
  * Predictions: Only generated within 12 hours of deadline
  * Fixtures: Notification sent within 36 hours of deadline
- This allows fixtures list to be sent earlier while predictions remain close to deadline

INTELLIGENT STRATEGY INTEGRATION:
- Queries season_recommendations table for current optimal strategy
- Adapts prediction format based on real-time season analysis
- Falls back to 2-1 strategy if recommendation system unavailable
- Logs strategy selection and reasoning for transparency

DROPBOX INTEGRATION:
- Downloads existing gameweek predictions file if it exists
- Appends new predictions to existing content
- Creates new gameweek file if none exists
- Handles both upload locations independently with error recovery
"""

import json
import requests
import sqlite3 as sql
from datetime import datetime, timezone
from pathlib import Path
import pytz
import logging
import argparse
import subprocess
import sys

# Configuration
CURRENT_SEASON = "2025/2026"

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
keys_file = Path(__file__).parent.parent.parent / "keys.json"

def load_config():
    """Load API keys and configuration"""
    with open(keys_file, 'r') as f:
        return json.load(f)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Automated predictions script with intelligent strategy recommendations')
    parser.add_argument('--force', action='store_true',
                       help='Force run the script ignoring all checks (deadline, existing files, recent processing)')
    parser.add_argument('--gameweek', type=int,
                       help='Force specific gameweek (requires --force)')
    return parser.parse_args()

def setup_logging():
    """Setup file-based logging for this script"""
    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).parent.parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Create log filename with current date
    log_filename = f"automated_predictions_{datetime.now().strftime('%Y%m%d')}.log"
    log_path = logs_dir / log_filename

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler()  # Also log to console
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized - log file: {log_path}")
    return logger

def get_current_season_recommendation(season=CURRENT_SEASON, logger=None):
    """Get the current recommended strategy for the season from the recommendation system"""
    if not logger:
        logger = logging.getLogger(__name__)

    try:
        conn = sql.connect(db_path)
        cursor = conn.cursor()

        # Get latest recommendation for the season
        cursor.execute('''
            SELECT recommended_strategy, confidence_level, low_scoring_percentage
            FROM season_recommendations
            WHERE season = ?
            ORDER BY last_updated DESC
            LIMIT 1
        ''', (season,))

        result = cursor.fetchone()
        conn.close()

        if result:
            strategy, confidence, percentage = result
            logger.info(f"Retrieved season recommendation: {strategy} strategy (confidence: {confidence}, {percentage:.1f}% low-scoring)")
            return strategy
        else:
            logger.info(f"No recommendation found for season {season}, using default 2-1 strategy")
            return '2-1'

    except Exception as e:
        logger.error(f"Error retrieving season recommendation: {e}")
        logger.info("Falling back to default 2-1 strategy")
        return '2-1'

def fetch_next_gameweek(logger):
    """Get the next upcoming gameweek and its deadline"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT gameweek, deadline_dttm
            FROM gameweeks 
            WHERE deadline_dttm > datetime('now') 
            ORDER BY deadline_dttm ASC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            gameweek, deadline_str = result
            # Convert deadline string to timestamp (UTC to UK timezone)
            deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '')).replace(tzinfo=timezone.utc)
            # Convert to UK timezone (UTC+0 for simplicity, could add proper BST/GMT handling)
            uk_deadline = deadline_dt.replace(tzinfo=timezone.utc)
            deadline_timestamp = int(uk_deadline.timestamp())
            logger.info(f"Next gameweek: {gameweek}, deadline: {uk_deadline}")
            return gameweek, deadline_timestamp
        else:
            logger.info("No upcoming gameweeks found")
            return None, None

    except Exception as e:
        logger.error(f"Error fetching next gameweek: {e}")
        return None, None
    finally:
        conn.close()

def is_within_12_hours(deadline_timestamp, logger):
    """Check if deadline is within the next 12 hours (for predictions generation)"""
    if not deadline_timestamp:
        return False

    now = datetime.now().timestamp()
    hours_until_deadline = (deadline_timestamp - now) / 3600

    logger.info(f"Hours until deadline: {hours_until_deadline:.2f}")

    # Check if deadline is in the future and within 12 hours
    is_future = deadline_timestamp > now
    is_within_window = 0 < hours_until_deadline <= 12

    result = is_future and is_within_window
    logger.info(f"Within 12 hours (predictions): {result}")

    return result

def is_within_36_hours(deadline_timestamp, logger):
    """Check if deadline is within the next 36 hours (for fixtures notification)"""
    if not deadline_timestamp:
        return False

    now = datetime.now().timestamp()
    hours_until_deadline = (deadline_timestamp - now) / 3600

    logger.info(f"Hours until deadline: {hours_until_deadline:.2f}")

    # Check if deadline is in the future and within 36 hours
    is_future = deadline_timestamp > now
    is_within_window = 0 < hours_until_deadline <= 36

    result = is_future and is_within_window
    logger.info(f"Within 36 hours (fixtures): {result}")

    return result

def update_odds_data(logger):
    """Update odds data by calling the fetch_odds.py script"""
    logger.info("Updating odds data before generating predictions...")

    try:
        # Path to the fetch_odds.py script
        fetch_odds_script = Path(__file__).parent.parent / "odds-api" / "fetch_odds.py"

        # Path to the virtual environment python
        venv_python = Path(__file__).parent.parent.parent / "venv" / "bin" / "python"

        # Run the fetch_odds.py script with --include-totals for comprehensive data
        result = subprocess.run(
            [str(venv_python), str(fetch_odds_script), "--include-totals"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("Successfully updated odds data")
            # Log any output from the odds script
            if result.stdout:
                logger.info(f"Odds update output: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"Failed to update odds data (exit code {result.returncode})")
            if result.stderr:
                logger.error(f"Odds update error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Odds update timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Error updating odds data: {e}")
        return False

def get_gameweek_odds(gameweek, logger):
    """Get odds data for the specified gameweek using the SQL file"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Read the SQL query from file
        sql_file = Path(__file__).parent / "SQL" / "gameweek_odds.sql"
        with open(sql_file, 'r') as f:
            sql_query = f.read()

        cursor.execute(sql_query, (CURRENT_SEASON, gameweek))
        results = cursor.fetchall()

        logger.info(f"Found {len(results)} fixtures with odds for gameweek {gameweek}")
        return results

    except Exception as e:
        logger.error(f"Error fetching odds data: {e}")
        return []
    finally:
        conn.close()

def create_predictions_string(odds_data, logger):
    """Create the predictions string based on odds data using intelligent season recommendations"""
    predictions = ["Tom Levin", ""]

    # Get current season's recommended strategy
    recommended_strategy = get_current_season_recommendation(CURRENT_SEASON, logger)
    logger.info(f"Using {recommended_strategy} strategy for automated predictions")

    for row in odds_data:
        home_team, away_team, home_odds, away_odds = row[:4]

        # Capitalize team names
        home_team = home_team.title()
        away_team = away_team.title()

        # Generate prediction based on recommended strategy
        if home_odds and away_odds:
            if home_odds <= away_odds:
                # Home team favorite
                if recommended_strategy == '1-0':
                    prediction = f"{home_team} 1-0 {away_team}"
                else:  # Default to 2-1 strategy
                    prediction = f"{home_team} 2-1 {away_team}"
            else:
                # Away team favorite
                if recommended_strategy == '1-0':
                    prediction = f"{home_team} 0-1 {away_team}"
                else:  # Default to 2-1 strategy
                    prediction = f"{home_team} 1-2 {away_team}"
        else:
            # Default if odds missing
            prediction = f"{home_team} 1-1 {away_team}"

        predictions.append(prediction)

    result = "\n".join(predictions)
    logger.info(f"Created {recommended_strategy} strategy predictions for {len(odds_data)} fixtures")
    return result

def check_file_exists_dropbox(file_path, config, logger):
    """Check if file already exists in Dropbox"""
    try:
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'path': file_path
        }
        
        response = requests.post(
            'https://api.dropboxapi.com/2/files/get_metadata',
            headers=headers,
            json=data
        )
        
        exists = response.status_code == 200
        logger.info(f"File {file_path} exists in Dropbox: {exists}")
        return exists

    except Exception as e:
        logger.error(f"Error checking Dropbox file: {e}")
        return False

def download_dropbox_file(file_path, config, logger):
    """Download file content from Dropbox"""
    try:
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Dropbox-API-Arg': json.dumps({'path': file_path})
        }
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/download',
            headers=headers
        )
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            logger.info(f"Successfully downloaded file: {file_path}")
            return content
        else:
            logger.error(f"Failed to download {file_path}: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error downloading {file_path}: {e}")
        return None

def upload_to_dropbox(predictions_string, gameweek, config, logger):
    """Upload predictions to Dropbox"""
    file_path = f"/predictions_league/odds-api/predictions{gameweek}.txt"
    
    try:
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Dropbox-API-Arg': json.dumps({
                'path': file_path,
                'mode': 'add',
                'autorename': True
            }),
            'Content-Type': 'application/octet-stream'
        }
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/upload',
            headers=headers,
            data=predictions_string.encode('utf-8')
        )
        
        if response.status_code == 200:
            logger.info(f"Successfully uploaded predictions to Dropbox: {file_path}")
            return True
        else:
            logger.error(f"Failed to upload to Dropbox: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error uploading to Dropbox: {e}")
        return False

def append_or_create_gameweek_predictions(predictions_string, gameweek, config, logger):
    """Append predictions to the main gameweek predictions file or create it if it doesn't exist"""
    file_path = f"/predictions_league/Predictions/2025_26/gameweek{gameweek}.txt"
    
    try:
        existing_content = ""
        
        # Check if file exists and download current content
        if check_file_exists_dropbox(file_path, config, logger):
            existing_content = download_dropbox_file(file_path, config, logger)
            if existing_content is None:
                logger.error(f"Failed to download existing file content for {file_path}")
                return False
            logger.info(f"Downloaded existing content from {file_path}")
        else:
            logger.info(f"File {file_path} doesn't exist, will create new file")
        
        # Combine existing content with new predictions
        if existing_content:
            # Add a newline between existing content and new predictions if needed
            if not existing_content.endswith('\n'):
                existing_content += '\n'
            combined_content = existing_content + predictions_string
        else:
            combined_content = predictions_string
        
        # Upload the combined content (overwrite mode to replace the entire file)
        headers = {
            'Authorization': f'Bearer {config["dropbox_oath_token"]}',
            'Dropbox-API-Arg': json.dumps({
                'path': file_path,
                'mode': 'overwrite',  # Overwrite the entire file with combined content
                'autorename': False
            }),
            'Content-Type': 'application/octet-stream'
        }
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/upload',
            headers=headers,
            data=combined_content.encode('utf-8')
        )
        
        if response.status_code == 200:
            logger.info(f"Successfully updated gameweek predictions file: {file_path}")
            return True
        else:
            logger.error(f"Failed to update gameweek predictions file: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error updating gameweek predictions file: {e}")
        return False

def fetch_fixtures(gameweek, logger):
    """Fetch fixtures for the gameweek (based on legacy function)"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                ht.team_name,
                at.team_name,
                gw.deadline_time
            FROM 
                fixtures AS f
                JOIN teams AS ht ON ht.team_id = f.home_teamid
                JOIN teams AS at ON at.team_id = f.away_teamid 
                JOIN gameweeks AS gw ON gw.gameweek = f.gameweek
            WHERE 
                f.gameweek = ?
                AND f.season = ?
            ORDER BY f.kickoff_dttm
        """, (gameweek, CURRENT_SEASON))
        
        fixtures = cursor.fetchall()
        logger.info(f"Found {len(fixtures)} fixtures for gameweek {gameweek}")
        return fixtures

    except Exception as e:
        logger.error(f"Error fetching fixtures: {e}")
        return []
    finally:
        conn.close()

def create_fixtures_string(gameweek, deadline_timestamp, logger):
    """Create fixtures string for notification"""
    fixtures = fetch_fixtures(gameweek, logger)
    
    fixtures_str = "\n".join(
        [f"{home.title()} v {away.title()}" for home, away, _ in fixtures]
    )
    
    # Convert UTC timestamp to London time (handles both GMT and BST automatically)
    utc_dt = datetime.fromtimestamp(deadline_timestamp, tz=timezone.utc)
    london_tz = pytz.timezone('Europe/London')
    london_dt = utc_dt.astimezone(london_tz)
    deadline_time = london_dt.strftime("%H:%M")
    result = f"{fixtures_str}\n\nDeadline tomorrow at {deadline_time}"
    
    return result

def send_pushover_message(message, config, logger):
    """Send notification via Pushover API"""
    try:
        url = "https://api.pushover.net/1/messages.json"
        data = {
            "token": config["PUSHOVER_TOKEN"],
            "user": config["PUSHOVER_USER"],
            "message": message,
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            logger.info("Successfully sent Pushover notification")
            return True
        else:
            logger.error(f"Failed to send Pushover notification: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error sending Pushover message: {e}")
        return False

def update_last_update_table(table_name, logger):
    """Update the last_update table with current timestamp"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y %H:%M:%S")
        timestamp = dt.timestamp()
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES (?, ?, ?)
        """, (table_name, now, timestamp))
        
        conn.commit()
        logger.info(f"Updated last_update table for '{table_name}'")

    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")
    finally:
        conn.close()

def check_already_processed(table_name, within_hours=1, logger=None):
    """Check if we've already processed this recently"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT timestamp
            FROM last_update
            WHERE table_name = ?
        """, (table_name,))
        
        result = cursor.fetchone()
        if result:
            last_timestamp = result[0]
            now = datetime.now().timestamp()
            hours_since = (now - last_timestamp) / 3600
            
            recently_processed = hours_since <= within_hours
            if logger:
                logger.info(f"Last {table_name}: {hours_since:.2f} hours ago, recently processed: {recently_processed}")
            return recently_processed
        else:
            if logger:
                logger.info(f"No previous {table_name} record found")
            return False

    except Exception as e:
        if logger:
            logger.error(f"Error checking {table_name} status: {e}")
        return False
    finally:
        conn.close()

def main():
    """Main execution function"""
    args = parse_arguments()
    logger = setup_logging()

    if args.force:
        logger.info("Starting automated predictions script in FORCE mode - bypassing all checks")
    else:
        logger.info("Starting automated predictions script")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return

    # Check if gameweek specified without force mode
    if args.gameweek and not args.force:
        logger.error("--gameweek requires --force mode. Use --force --gameweek N")
        return

    # Get gameweek (either forced or next upcoming)
    if args.force and args.gameweek:
        gameweek = args.gameweek
        deadline_timestamp = None
        logger.info(f"Force mode: Using specified gameweek {gameweek}")
    else:
        gameweek, deadline_timestamp = fetch_next_gameweek(logger)
        if not gameweek:
            logger.info("No upcoming gameweek found, exiting")
            return

    # Check if deadline is within 12 hours for predictions (skip if force mode)
    if not args.force:
        if not is_within_12_hours(deadline_timestamp, logger):
            logger.info("Deadline not within 12 hours for predictions, checking fixtures only")
            # Don't return here - we might still need to send fixtures notification
        else:
            logger.info("Deadline within 12 hours - predictions will be generated")
    else:
        logger.info("Force mode: Skipping deadline check")
    
    # Check if predictions file already exists (skip if force mode)
    predictions_file = f"/predictions_league/odds-api/predictions{gameweek}.txt"
    should_create_predictions = True

    if not args.force:
        if check_file_exists_dropbox(predictions_file, config, logger):
            logger.info("Predictions file already exists, skipping predictions creation")
            should_create_predictions = False
        elif check_already_processed("predictions", within_hours=1, logger=logger):
            logger.info("Predictions already processed recently, skipping")
            should_create_predictions = False
    else:
        logger.info("Force mode: Skipping file existence and recent processing checks")

    # Only create predictions if within 12-hour window (or force mode)
    if should_create_predictions and (args.force or is_within_12_hours(deadline_timestamp, logger)):
        # Update odds data before generating predictions
        odds_update_success = update_odds_data(logger)
        if not odds_update_success:
            logger.warning("Failed to update odds data, but continuing with existing data")

        # Get odds data and create predictions
        odds_data = get_gameweek_odds(gameweek, logger)
        if odds_data:
            predictions_string = create_predictions_string(odds_data, logger)

            # Upload to Dropbox odds-api folder
            upload_success = upload_to_dropbox(predictions_string, gameweek, config, logger)

            # Also append/create predictions in the main gameweek file
            append_success = append_or_create_gameweek_predictions(predictions_string, gameweek, config, logger)

            if upload_success or append_success:
                if upload_success and append_success:
                    logger.info("Successfully uploaded to both odds-api and gameweek predictions files")
                elif upload_success:
                    logger.warning("Successfully uploaded to odds-api file, but failed to update gameweek predictions file")
                elif append_success:
                    logger.warning("Successfully updated gameweek predictions file, but failed to upload to odds-api file")

                update_last_update_table("predictions", logger)

                # Send predictions via Pushover
                send_pushover_message(predictions_string, config, logger)
            else:
                logger.error("Failed to upload predictions to both locations, skipping notifications")
        else:
            logger.warning("No odds data found for gameweek")
    
    # Check if we should send fixtures notification (requires 36-hour window, skip check if force mode)
    should_send_fixtures = True

    if not args.force:
        if check_already_processed("send_fixtures", within_hours=24, logger=logger):
            logger.info("Fixtures notification already sent recently, skipping")
            should_send_fixtures = False
        elif not is_within_36_hours(deadline_timestamp, logger):
            logger.info("Deadline not within 36 hours for fixtures notification, skipping")
            should_send_fixtures = False
    else:
        logger.info("Force mode: Skipping fixtures notification recent processing check")

    if should_send_fixtures and deadline_timestamp:
        # Send fixtures notification
        fixtures_string = create_fixtures_string(gameweek, deadline_timestamp, logger)
        if send_pushover_message(fixtures_string, config, logger):
            update_last_update_table("send_fixtures", logger)
    elif should_send_fixtures and not deadline_timestamp:
        logger.info("Force mode: Skipping fixtures notification (no deadline timestamp available)")

    logger.info("Automated predictions script completed")

if __name__ == "__main__":
    main()