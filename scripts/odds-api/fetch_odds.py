import json
import requests
import sqlite3 as sql
from pathlib import Path
import os
from datetime import datetime
import glob
import logging
import argparse
from requests.exceptions import RequestException, Timeout

# Load API key from keys.json
keys_file = Path(__file__).parent.parent.parent / "keys.json"

with open(keys_file, 'r') as f:
    keys = json.load(f)
    
odds_api_key = keys["odds_api_key"]
api_base_url = "https://api.the-odds-api.com/v4"

# Database path
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

# Logging setup
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"odds_fetch_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Console output
        ]
    )
    return logging.getLogger(__name__)

def cleanup_old_sample_files(output_dir, keep_count=5, logger=None):
    """Keep only the latest N sample files, remove older ones"""
    pattern = output_dir / "*odds_data_*.json"
    files = list(glob.glob(str(pattern)))
    
    if len(files) <= keep_count:
        if logger:
            logger.info(f"Only {len(files)} files found, no cleanup needed")
        return
    
    # Sort files by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Remove files beyond the keep_count
    files_to_remove = files[keep_count:]
    
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old sample file: {Path(file_path).name}")
            else:
                print(f"Removed old sample file: {Path(file_path).name}")
        except Exception as e:
            if logger:
                logger.error(f"Error removing file {file_path}: {e}")
            else:
                print(f"Error removing file {file_path}: {e}")

def load_team_mapping(cursor):
    """Load all team mappings into memory for efficient lookups"""
    cursor.execute("SELECT odds_api_name, team_id FROM teams WHERE odds_api_name IS NOT NULL")
    return {name.lower(): team_id for name, team_id in cursor.fetchall()}

def get_team_id_by_odds_api_name(team_cache, team_name):
    """Get team_id from cached team mapping"""
    return team_cache.get(team_name.lower())

def get_fixture_id(cursor, home_team_id, away_team_id, kickoff_time):
    """Get fixture_id by matching home_team, away_team and kickoff time"""
    cursor.execute("""
        SELECT fixture_id FROM fixtures 
        WHERE home_teamid = ? AND away_teamid = ? 
        AND datetime(kickoff_dttm) = datetime(?)
    """, (home_team_id, away_team_id, kickoff_time))
    result = cursor.fetchone()
    return result[0] if result else None

def insert_or_update_bookmaker(cursor, bookmaker_name):
    """Insert bookmaker if not exists and return bookmaker_id"""
    cursor.execute("INSERT OR IGNORE INTO bookmakers (bookmaker_name) VALUES (?)", (bookmaker_name,))
    cursor.execute("SELECT bookmaker_id FROM bookmakers WHERE bookmaker_name = ?", (bookmaker_name,))
    return cursor.fetchone()[0]

def insert_or_update_odds(cursor, match_id, home_team_id, away_team_id, bet_type, fixture_id, bookmaker_id, price):
    """Insert or update odds record with price"""
    # Check if record exists
    cursor.execute("""
        SELECT odd_id FROM odds 
        WHERE match_id = ? AND bet_type = ? AND bookmaker_id = ?
    """, (match_id, bet_type, bookmaker_id))
    
    existing = cursor.fetchone()
    
    if existing:
        # Update existing record
        cursor.execute("""
            UPDATE odds 
            SET home_team_id = ?, away_team_id = ?, fixture_id = ?, price = ?
            WHERE odd_id = ?
        """, (home_team_id, away_team_id, fixture_id, price, existing[0]))
    else:
        # Insert new record
        cursor.execute("""
            INSERT INTO odds 
            (match_id, home_team_id, away_team_id, bet_type, fixture_id, bookmaker_id, price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (match_id, home_team_id, away_team_id, bet_type, fixture_id, bookmaker_id, price))

def process_odds_data(odds_data, logger):
    """Process odds data and insert/update into database"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    processed_count = 0
    skipped_count = 0
    
    try:
        # Load team mapping cache for efficient lookups
        logger.info("Loading team mappings...")
        team_cache = load_team_mapping(cursor)
        logger.info(f"Loaded {len(team_cache)} team mappings")
        
        logger.info(f"Processing {len(odds_data)} matches...")
        
        for match in odds_data:
            match_id = match['id']
            home_team = match['home_team']
            away_team = match['away_team']
            commence_time = match['commence_time']
            
            # Get team IDs using cache
            home_team_id = get_team_id_by_odds_api_name(team_cache, home_team)
            away_team_id = get_team_id_by_odds_api_name(team_cache, away_team)
            
            if not home_team_id or not away_team_id:
                logger.warning(f"Skipping match {home_team} vs {away_team} - teams not found in database")
                skipped_count += 1
                continue
            
            # Get fixture ID
            fixture_id = get_fixture_id(cursor, home_team_id, away_team_id, commence_time)
            
            # Process each bookmaker
            for bookmaker in match['bookmakers']:
                bookmaker_name = bookmaker['title'].lower()
                bookmaker_id = insert_or_update_bookmaker(cursor, bookmaker_name)
                
                # Process h2h market (head-to-head betting)
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            # Validate price exists
                            price = outcome.get('price')
                            if price is None:
                                logger.warning(f"Missing price for {outcome.get('name')} in match {home_team} vs {away_team}")
                                continue
                                
                            # Map outcome names to bet types
                            if outcome['name'] == home_team:
                                bet_type = 'home win'
                            elif outcome['name'] == away_team:
                                bet_type = 'away win'
                            elif outcome['name'] == 'Draw':
                                bet_type = 'draw'
                            else:
                                continue
                            
                            # Insert or update the odds with price
                            insert_or_update_odds(cursor, match_id, home_team_id, away_team_id, 
                                                bet_type, fixture_id, bookmaker_id, price)
                            processed_count += 1
        
        conn.commit()
        logger.info(f"Successfully processed {processed_count} odds records")
        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count} matches due to missing team mappings")
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing odds data: {e}")
        raise
    finally:
        conn.close()

def refresh_fixture_odds_summary(logger):
    """Refresh the fixture_odds_summary table with latest data"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        logger.info("Refreshing fixture odds summary table...")
        cursor.execute("""
            INSERT OR REPLACE INTO fixture_odds_summary (
                fixture_id,
                home_team_id,
                away_team_id,
                avg_home_win_odds,
                avg_draw_odds,
                avg_away_win_odds,
                bookmaker_count,
                last_updated
            )
            SELECT 
                fixture_id,
                home_team_id,
                away_team_id,
                AVG(CASE WHEN bet_type = 'home win' THEN price END) as avg_home_win_odds,
                AVG(CASE WHEN bet_type = 'draw' THEN price END) as avg_draw_odds,
                AVG(CASE WHEN bet_type = 'away win' THEN price END) as avg_away_win_odds,
                COUNT(DISTINCT bookmaker_id) as bookmaker_count,
                datetime('now') as last_updated
            FROM odds 
            WHERE fixture_id IS NOT NULL AND price IS NOT NULL
            GROUP BY fixture_id, home_team_id, away_team_id
        """)
        
        conn.commit()
        updated_count = cursor.execute("SELECT COUNT(*) FROM fixture_odds_summary").fetchone()[0]
        logger.info(f"Updated fixture_odds_summary table with {updated_count} fixture summaries")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error refreshing fixture_odds_summary: {e}")
        raise
    finally:
        conn.close()

def get_odds(api_key, logger):
    """Fetch odds data from API with timeout and error handling"""
    url = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
    params = {"regions": "uk", "oddsFormat": "decimal", "apiKey": api_key}
    
    logger.info("Fetching odds from API...")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        logger.info(f"API Request URL: {response.url}")
        
        if response.status_code == 200:
            odds_data = response.json()
            logger.info(f"Successfully retrieved {len(odds_data)} matches from API")
            
            # Log API usage if available in headers
            if 'x-requests-used' in response.headers:
                logger.info(f"API requests used: {response.headers['x-requests-used']}")
            if 'x-requests-remaining' in response.headers:
                logger.info(f"API requests remaining: {response.headers['x-requests-remaining']}")
                
            return odds_data
        else:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            return None
            
    except Timeout:
        logger.error("API request timed out after 30 seconds")
        return None
    except RequestException as e:
        logger.error(f"API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during API request: {e}")
        return None
    
def main(cleanup_count=5):
    logger = setup_logging()
    logger.info("Starting odds fetch process...")
    
    odds = get_odds(odds_api_key, logger)
    
    if odds:
        # Process the odds data into the database
        logger.info("Processing odds data into database...")
        process_odds_data(odds, logger)
        
        # Refresh the fixture odds summary table
        logger.info("Refreshing fixture odds summary...")
        refresh_fixture_odds_summary(logger)
        
        # Also save the JSON data as backup
        output_dir = Path(__file__).parent.parent.parent / "samples" / "odds_api"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"odds_data_{timestamp}.json"
        output_file = output_dir / filename
        
        # Save the JSON data
        with open(output_file, 'w') as f:
            json.dump(odds, f, indent=2)
        
        logger.info(f"Odds data also saved to: {output_file}")
        
        # Clean up old sample files
        if cleanup_count > 0:
            logger.info(f"Cleaning up old sample files, keeping latest {cleanup_count}...")
            cleanup_old_sample_files(output_dir, keep_count=cleanup_count, logger=logger)
        else:
            logger.info("File cleanup disabled")
            
        logger.info("Odds fetch process completed successfully")
    else:
        logger.error("No odds data to process")


def test_with_sample_data():
    """Test the script using existing sample data"""
    logger = setup_logging()
    logger.info("Starting test with sample data...")
    
    # Find any available sample file
    sample_dir = Path(__file__).parent.parent.parent / "samples" / "odds_api"
    sample_files = list(sample_dir.glob("odds_data_*.json"))
    
    if sample_files:
        # Use the most recent sample file
        sample_file = max(sample_files, key=lambda f: f.stat().st_mtime)
        logger.info(f"Testing with sample data from: {sample_file}")
        
        with open(sample_file, 'r') as f:
            odds_data = json.load(f)
        
        logger.info("Processing sample odds data into database...")
        process_odds_data(odds_data, logger)
        
        logger.info("Refreshing fixture odds summary...")
        refresh_fixture_odds_summary(logger)
        
        logger.info("Test completed successfully")
    else:
        logger.error("No sample data files found")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch odds data from API and update database')
    parser.add_argument('--test', action='store_true', help='Run in test mode with sample data')
    parser.add_argument('--cleanup-count', type=int, default=5, 
                       help='Number of sample files to keep (0 to disable cleanup)')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.test:
        test_with_sample_data()
    else:
        main(cleanup_count=args.cleanup_count)