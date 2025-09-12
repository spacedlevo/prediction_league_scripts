#!/usr/bin/env python3
"""
Automated Predictions Script

This script checks for upcoming gameweeks and automatically generates predictions
based on odds data, uploads them to Dropbox, and sends notifications via Pushover.

FUNCTIONALITY:
- Checks if next gameweek deadline is within 36 hours
- Uses odds data to generate predictions (favorite wins 2-1)
- Uploads predictions file to Dropbox
- Sends notifications via Pushover API
- Prevents duplicate runs using database tracking
"""

import json
import requests
import sqlite3 as sql
from datetime import datetime, timezone
from pathlib import Path

# Configuration
CURRENT_SEASON = "2025/2026"

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
keys_file = Path(__file__).parent.parent.parent / "keys.json"

def load_config():
    """Load API keys and configuration"""
    with open(keys_file, 'r') as f:
        return json.load(f)

def setup_logging():
    """Simple print-based logging for this script"""
    def log(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} - {message}")
    return log

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
            logger(f"Next gameweek: {gameweek}, deadline: {uk_deadline}")
            return gameweek, deadline_timestamp
        else:
            logger("No upcoming gameweeks found")
            return None, None
            
    except Exception as e:
        logger(f"Error fetching next gameweek: {e}")
        return None, None
    finally:
        conn.close()

def is_within_36_hours(deadline_timestamp, logger):
    """Check if deadline is within the next 36 hours"""
    if not deadline_timestamp:
        return False
        
    now = datetime.now().timestamp()
    hours_until_deadline = (deadline_timestamp - now) / 3600
    
    logger(f"Hours until deadline: {hours_until_deadline:.2f}")
    
    # Check if deadline is in the future and within 36 hours
    is_future = deadline_timestamp > now
    is_within_window = 0 < hours_until_deadline <= 36
    
    result = is_future and is_within_window
    logger(f"Within 36 hours: {result}")
    
    return result

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
        
        logger(f"Found {len(results)} fixtures with odds for gameweek {gameweek}")
        return results
        
    except Exception as e:
        logger(f"Error fetching odds data: {e}")
        return []
    finally:
        conn.close()

def create_predictions_string(odds_data, logger):
    """Create the predictions string based on odds data"""
    predictions = ["Tom Levin", ""]
    
    for row in odds_data:
        home_team, away_team, home_odds, away_odds = row[:4]
        
        # Capitalize team names
        home_team = home_team.title()
        away_team = away_team.title()
        
        # Determine favorite (lower odds = favorite)
        if home_odds and away_odds:
            if home_odds <= away_odds:
                # Home team favorite
                prediction = f"{home_team} 2-1 {away_team}"
            else:
                # Away team favorite  
                prediction = f"{home_team} 1-2 {away_team}"
        else:
            # Default if odds missing
            prediction = f"{home_team} 1-1 {away_team}"
            
        predictions.append(prediction)
    
    result = "\n".join(predictions)
    logger(f"Created predictions for {len(odds_data)} fixtures")
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
        logger(f"File {file_path} exists in Dropbox: {exists}")
        return exists
        
    except Exception as e:
        logger(f"Error checking Dropbox file: {e}")
        return False

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
            logger(f"Successfully uploaded predictions to Dropbox: {file_path}")
            return True
        else:
            logger(f"Failed to upload to Dropbox: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger(f"Error uploading to Dropbox: {e}")
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
        logger(f"Found {len(fixtures)} fixtures for gameweek {gameweek}")
        return fixtures
        
    except Exception as e:
        logger(f"Error fetching fixtures: {e}")
        return []
    finally:
        conn.close()

def create_fixtures_string(gameweek, deadline_timestamp, logger):
    """Create fixtures string for notification"""
    fixtures = fetch_fixtures(gameweek, logger)
    
    fixtures_str = "\n".join(
        [f"{home.title()} v {away.title()}" for home, away, _ in fixtures]
    )
    
    # Convert timestamp to UK timezone for display
    deadline_dt = datetime.fromtimestamp(deadline_timestamp, tz=timezone.utc)
    deadline_time = deadline_dt.strftime("%H:%M")
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
            logger("Successfully sent Pushover notification")
            return True
        else:
            logger(f"Failed to send Pushover notification: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger(f"Error sending Pushover message: {e}")
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
        logger(f"Updated last_update table for '{table_name}'")
        
    except Exception as e:
        logger(f"Error updating last_update table: {e}")
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
                logger(f"Last {table_name}: {hours_since:.2f} hours ago, recently processed: {recently_processed}")
            return recently_processed
        else:
            if logger:
                logger(f"No previous {table_name} record found")
            return False
            
    except Exception as e:
        if logger:
            logger(f"Error checking {table_name} status: {e}")
        return False
    finally:
        conn.close()

def main():
    """Main execution function"""
    logger = setup_logging()
    logger("Starting automated predictions script")
    
    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger(f"Error loading configuration: {e}")
        return
    
    # Get next gameweek
    gameweek, deadline_timestamp = fetch_next_gameweek(logger)
    if not gameweek:
        logger("No upcoming gameweek found, exiting")
        return
    
    # Check if deadline is within 36 hours
    if not is_within_36_hours(deadline_timestamp, logger):
        logger("Deadline not within 36 hours, exiting")
        return
    
    # Check if predictions file already exists
    predictions_file = f"/predictions_league/odds-api/predictions{gameweek}.txt"
    if check_file_exists_dropbox(predictions_file, config, logger):
        logger("Predictions file already exists, skipping predictions creation")
    else:
        # Check if we've already processed predictions recently
        if check_already_processed("predictions", within_hours=1, logger=logger):
            logger("Predictions already processed recently, skipping")
        else:
            # Get odds data and create predictions
            odds_data = get_gameweek_odds(gameweek, logger)
            if odds_data:
                predictions_string = create_predictions_string(odds_data, logger)
                
                # Upload to Dropbox
                if upload_to_dropbox(predictions_string, gameweek, config, logger):
                    update_last_update_table("predictions", logger)
                    
                    # Send predictions via Pushover
                    send_pushover_message(predictions_string, config, logger)
                else:
                    logger("Failed to upload predictions, skipping notifications")
            else:
                logger("No odds data found for gameweek")
    
    # Check if we should send fixtures notification
    if check_already_processed("send_fixtures", within_hours=24, logger=logger):
        logger("Fixtures notification already sent recently, skipping")
    else:
        # Send fixtures notification
        fixtures_string = create_fixtures_string(gameweek, deadline_timestamp, logger)
        if send_pushover_message(fixtures_string, config, logger):
            update_last_update_table("send_fixtures", logger)
    
    logger("Automated predictions script completed")

if __name__ == "__main__":
    main()