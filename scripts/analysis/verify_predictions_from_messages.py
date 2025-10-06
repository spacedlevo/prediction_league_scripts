#!/usr/bin/env python3
"""
Predictions Verification Tool - Read-Only Analysis

Compares predictions in database against WhatsApp messages and text files
in Dropbox /Messages folder. Generates reports showing differences without
modifying the database.

FUNCTIONALITY:
- Discovers all .txt files and .zip files in Dropbox /Messages folder
- Parses WhatsApp chat exports and standard prediction text files
- Compares message predictions vs database predictions
- Generates detailed comparison reports (CSV + console output)

OUTPUT CATEGORIES:
- Matches: Same player/fixture/score in both sources
- Score Mismatches: Same player/fixture, different scores
- In Messages Only: Prediction found in messages but not in database
- In Database Only: Prediction in database but not found in messages
"""

import json
import requests
import sqlite3 as sql
import csv
import re
import logging
import argparse
import zipfile
import io
import glob
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Configuration
CURRENT_SEASON_DB = "2025/2026"
DROPBOX_MESSAGES_FOLDER = "/Messages"

# Name aliases - map message variations to database names
NAME_ALIASES = {
    'ed fenna': 'edward fenna',
    'steven harrison': 'ste harrison',
    'steve harrison': 'ste harrison',
    'thomas levin': 'tom levin',
    'tom levo': 'tom levin',
    'olly spence-robb': 'olly spence robb',
}

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
keys_file = Path(__file__).parent.parent.parent / "keys.json"
reports_dir = Path(__file__).parent.parent.parent / "analysis_reports"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
reports_dir.mkdir(parents=True, exist_ok=True)
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"verify_predictions_{datetime.now().strftime('%Y%m%d')}.log"

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

def refresh_dropbox_token(config, logger):
    """Refresh Dropbox access token"""
    try:
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
            return token_data['access_token']
        else:
            logger.error(f"Failed to refresh Dropbox token: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error refreshing Dropbox token: {e}")
        return None

def list_dropbox_files(token, logger):
    """List all .txt and .zip files in Dropbox Messages folder"""
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        data = {
            'path': DROPBOX_MESSAGES_FOLDER,
            'recursive': False
        }

        response = requests.post(
            'https://api.dropboxapi.com/2/files/list_folder',
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            result = response.json()
            txt_files = []
            zip_files = []

            for entry in result.get('entries', []):
                if entry.get('.tag') == 'file':
                    name = entry['name']
                    if name.endswith('.txt'):
                        txt_files.append({
                            'name': name,
                            'path': entry['path_lower'],
                            'size': entry.get('size', 0)
                        })
                    elif name.endswith('.zip'):
                        zip_files.append({
                            'name': name,
                            'path': entry['path_lower'],
                            'size': entry.get('size', 0)
                        })

            logger.info(f"Found {len(txt_files)} .txt files and {len(zip_files)} .zip files")
            return txt_files, zip_files
        else:
            logger.error(f"Failed to list Dropbox files: {response.status_code}")
            return [], []

    except Exception as e:
        logger.error(f"Error listing Dropbox files: {e}")
        return [], []

def download_dropbox_file(file_path, token, logger):
    """Download file content from Dropbox"""
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'Dropbox-API-Arg': json.dumps({'path': file_path})
        }

        response = requests.post(
            'https://content.dropboxapi.com/2/files/download',
            headers=headers
        )

        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to download {file_path}: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error downloading {file_path}: {e}")
        return None

def extract_zip_file(zip_content, logger):
    """Extract _chat.txt from WhatsApp zip file"""
    try:
        zip_data = io.BytesIO(zip_content)
        with zipfile.ZipFile(zip_data) as z:
            # Find .txt file in zip
            txt_files = [f for f in z.namelist() if f.endswith('.txt')]
            if txt_files:
                with z.open(txt_files[0]) as f:
                    return f.read().decode('utf-8')
            else:
                logger.warning("No .txt file found in zip")
                return None

    except Exception as e:
        logger.error(f"Error extracting zip file: {e}")
        return None

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
    if current_score:
        goals.append(int(current_score))
    return goals

def extract_teams_from_line(line, teams):
    """Extract team names from line based on their position in the text"""
    team_positions = []

    for team in teams:
        if team in line:
            pos = line.find(team)
            team_positions.append((pos, team))

    # Sort by position in text (earliest first)
    team_positions.sort(key=lambda x: x[0])

    # Return teams in order they appear in text
    return [team for pos, team in team_positions]

def parse_whatsapp_messages(content, teams, players, logger):
    """
    Parse WhatsApp chat export format
    Example: [21/09/2025, 18:51:42] James Forshaw: Liverpool 2 v 1 Everton
    """
    predictions = []
    lines = content.split('\n')
    current_player = None

    # WhatsApp message pattern: [date, time] Player: prediction
    whatsapp_pattern = r'\[(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}:\d{2})\] ([^:]+): (.+)'

    for line in lines:
        match = re.match(whatsapp_pattern, line)
        if match:
            date_str, time_str, player_name, message = match.groups()

            # Check if player name is in our database (with alias support)
            player_lower = player_name.strip().lower()
            normalized_player = NAME_ALIASES.get(player_lower, player_lower)
            if normalized_player in [p.lower() for p in players]:
                current_player = next((p for p in players if p.lower() == normalized_player), None)

                # Try to parse prediction from message
                message_clean = message.strip()

                # Look for team names in message (preserve text order)
                found_teams = extract_teams_from_line(message_clean.lower(), teams)

                # Extract scores
                scores = find_scores(message_clean)

                if len(found_teams) == 2 and len(scores) >= 2:
                    prediction = {
                        'player': current_player,
                        'home_team': found_teams[0],
                        'away_team': found_teams[1],
                        'home_goals': scores[0],
                        'away_goals': scores[1],
                        'date': date_str,
                        'time': time_str
                    }
                    predictions.append(prediction)
                    logger.debug(f"WhatsApp prediction: {current_player} - {found_teams[0]} {scores[0]}-{scores[1]} {found_teams[1]}")
        else:
            # Handle continuation lines (predictions spanning multiple lines)
            if current_player and line.strip():
                # Check if this is a continuation of predictions (preserve text order)
                found_teams = extract_teams_from_line(line.lower(), teams)

                scores = find_scores(line)

                if len(found_teams) == 2 and len(scores) >= 2:
                    prediction = {
                        'player': current_player,
                        'home_team': found_teams[0],
                        'away_team': found_teams[1],
                        'home_goals': scores[0],
                        'away_goals': scores[1],
                        'date': 'continuation',
                        'time': ''
                    }
                    predictions.append(prediction)
                    logger.debug(f"WhatsApp continuation: {current_player} - {found_teams[0]} {scores[0]}-{scores[1]} {found_teams[1]}")

    return predictions

def parse_standard_text_file(content, teams, players, logger):
    """
    Parse standard prediction text format
    Example:
    Graham Kay

    Bournemouth 2 v 1 Fulham
    Leeds 1 v 2 Spurs
    """
    predictions = []
    lines = content.lower().splitlines()
    current_player = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if line contains a player name (with alias support)
        normalized_line = NAME_ALIASES.get(line, line)
        if normalized_line in [p.lower() for p in players]:
            current_player = next((p for p in players if p.lower() == normalized_line), None)
            continue

        # Process prediction lines
        if current_player:
            # Extract teams in order they appear in text
            found_teams = extract_teams_from_line(line, teams)

            scores = find_scores(line)

            if len(found_teams) == 2:
                home_goals = scores[0] if len(scores) >= 1 else 9
                away_goals = scores[1] if len(scores) >= 2 else 9

                prediction = {
                    'player': current_player,
                    'home_team': found_teams[0],
                    'away_team': found_teams[1],
                    'home_goals': home_goals,
                    'away_goals': away_goals
                }
                predictions.append(prediction)
                logger.debug(f"Standard prediction: {current_player} - {found_teams[0]} {home_goals}-{away_goals} {found_teams[1]}")

    return predictions

def load_database_data(cursor, logger):
    """Load teams, players, and fixtures from database"""
    # Load teams
    cursor.execute("SELECT team_name FROM teams WHERE available = 1")
    teams = [team[0].lower() for team in cursor.fetchall()]

    # Load active players
    cursor.execute("SELECT player_name FROM players WHERE active = 1")
    players = [player[0] for player in cursor.fetchall()]

    # Load fixtures for season
    cursor.execute("""
        SELECT
            f.fixture_id,
            f.gameweek,
            ht.team_name as home_team,
            at.team_name as away_team
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE f.season = ?
    """, (CURRENT_SEASON_DB,))

    fixtures = {}
    for fixture_id, gameweek, home_team, away_team in cursor.fetchall():
        key = (home_team.lower(), away_team.lower())
        fixtures[key] = {
            'fixture_id': fixture_id,
            'gameweek': gameweek,
            'home_team': home_team,
            'away_team': away_team
        }

    logger.info(f"Loaded {len(teams)} teams, {len(players)} players, {len(fixtures)} fixtures")
    return teams, players, fixtures

def load_database_predictions(cursor, logger):
    """Load all predictions from database"""
    cursor.execute("""
        SELECT
            p.player_id,
            pl.player_name,
            f.fixture_id,
            f.gameweek,
            ht.team_name as home_team,
            at.team_name as away_team,
            p.home_goals,
            p.away_goals
        FROM predictions p
        JOIN players pl ON p.player_id = pl.player_id
        JOIN fixtures f ON p.fixture_id = f.fixture_id
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE f.season = ?
    """, (CURRENT_SEASON_DB,))

    predictions = {}
    for player_id, player_name, fixture_id, gameweek, home_team, away_team, home_goals, away_goals in cursor.fetchall():
        key = (player_name.lower(), home_team.lower(), away_team.lower())
        predictions[key] = {
            'player': player_name,
            'gameweek': gameweek,
            'home_team': home_team,
            'away_team': away_team,
            'home_goals': home_goals,
            'away_goals': away_goals
        }

    logger.info(f"Loaded {len(predictions)} predictions from database")
    return predictions

def match_prediction_to_fixture(prediction, fixtures, logger):
    """Match a prediction to a fixture, trying both team orders"""
    home_team = prediction['home_team']
    away_team = prediction['away_team']

    # Try exact order
    key = (home_team, away_team)
    if key in fixtures:
        return fixtures[key], False

    # Try reverse order
    key_reverse = (away_team, home_team)
    if key_reverse in fixtures:
        # Swap goals to match correct order
        return fixtures[key_reverse], True  # Return flag indicating teams were swapped

    return None, False

def compare_predictions(message_predictions, db_predictions, fixtures, logger):
    """Compare message predictions vs database predictions"""
    results = {
        'matches': [],
        'score_mismatches': [],
        'in_messages_only': [],
        'in_database_only': []
    }

    # Process message predictions
    message_dict = {}
    for pred in message_predictions:
        fixture_info, swapped = match_prediction_to_fixture(pred, fixtures, logger)
        if fixture_info:
            player_lower = pred['player'].lower()
            home_team = fixture_info['home_team'].lower()
            away_team = fixture_info['away_team'].lower()

            key = (player_lower, home_team, away_team)

            # Adjust goals if teams were swapped
            if swapped:
                message_dict[key] = {
                    **pred,
                    'home_goals': pred['away_goals'],
                    'away_goals': pred['home_goals'],
                    'gameweek': fixture_info['gameweek']
                }
            else:
                message_dict[key] = {
                    **pred,
                    'gameweek': fixture_info['gameweek']
                }

    # Keep only latest prediction per player/fixture
    latest_message_predictions = {}
    for key, pred in message_dict.items():
        if key not in latest_message_predictions:
            latest_message_predictions[key] = pred
        else:
            # Keep the one with later date if available
            if pred.get('date') and pred['date'] != 'continuation':
                latest_message_predictions[key] = pred

    # Compare
    all_keys = set(latest_message_predictions.keys()) | set(db_predictions.keys())

    for key in all_keys:
        message_pred = latest_message_predictions.get(key)
        db_pred = db_predictions.get(key)

        if message_pred and db_pred:
            # Both exist - check if scores match
            if (message_pred['home_goals'] == db_pred['home_goals'] and
                message_pred['away_goals'] == db_pred['away_goals']):
                results['matches'].append({
                    'player': db_pred['player'],
                    'gameweek': db_pred['gameweek'],
                    'home_team': db_pred['home_team'],
                    'away_team': db_pred['away_team'],
                    'score': f"{db_pred['home_goals']}-{db_pred['away_goals']}"
                })
            else:
                results['score_mismatches'].append({
                    'player': db_pred['player'],
                    'gameweek': db_pred['gameweek'],
                    'home_team': db_pred['home_team'],
                    'away_team': db_pred['away_team'],
                    'db_score': f"{db_pred['home_goals']}-{db_pred['away_goals']}",
                    'message_score': f"{message_pred['home_goals']}-{message_pred['away_goals']}"
                })
        elif message_pred:
            results['in_messages_only'].append({
                'player': message_pred['player'],
                'gameweek': message_pred.get('gameweek', 'unknown'),
                'home_team': message_pred['home_team'],
                'away_team': message_pred['away_team'],
                'score': f"{message_pred['home_goals']}-{message_pred['away_goals']}"
            })
        elif db_pred:
            results['in_database_only'].append({
                'player': db_pred['player'],
                'gameweek': db_pred['gameweek'],
                'home_team': db_pred['home_team'],
                'away_team': db_pred['away_team'],
                'score': f"{db_pred['home_goals']}-{db_pred['away_goals']}"
            })

    return results

def save_to_database(results, fixtures, cursor, logger):
    """Save verification results to database"""
    try:
        # Clear existing verification data
        cursor.execute("DELETE FROM prediction_verification")

        inserted_count = 0

        # Process matches
        for match in results['matches']:
            player_id = get_player_id(match['player'], cursor)
            fixture_id = get_fixture_id_from_teams(match['home_team'], match['away_team'], match['gameweek'], cursor)

            if player_id and fixture_id:
                # Parse score
                home_goals, away_goals = map(int, match['score'].split('-'))

                cursor.execute('''
                    INSERT INTO prediction_verification
                    (category, player_id, fixture_id, db_home_goals, db_away_goals,
                     message_home_goals, message_away_goals)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('Match', player_id, fixture_id, home_goals, away_goals, home_goals, away_goals))
                inserted_count += 1

        # Process score mismatches
        for mismatch in results['score_mismatches']:
            player_id = get_player_id(mismatch['player'], cursor)
            fixture_id = get_fixture_id_from_teams(mismatch['home_team'], mismatch['away_team'], mismatch['gameweek'], cursor)

            if player_id and fixture_id:
                db_home, db_away = map(int, mismatch['db_score'].split('-'))
                msg_home, msg_away = map(int, mismatch['message_score'].split('-'))

                cursor.execute('''
                    INSERT INTO prediction_verification
                    (category, player_id, fixture_id, db_home_goals, db_away_goals,
                     message_home_goals, message_away_goals)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('Score Mismatch', player_id, fixture_id, db_home, db_away, msg_home, msg_away))
                inserted_count += 1

        # Process in messages only
        for pred in results['in_messages_only']:
            player_id = get_player_id(pred['player'], cursor)
            fixture_id = get_fixture_id_from_teams(pred['home_team'], pred['away_team'], pred['gameweek'], cursor)

            if player_id and fixture_id:
                msg_home, msg_away = map(int, pred['score'].split('-'))

                cursor.execute('''
                    INSERT INTO prediction_verification
                    (category, player_id, fixture_id, db_home_goals, db_away_goals,
                     message_home_goals, message_away_goals)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('In Messages Only', player_id, fixture_id, None, None, msg_home, msg_away))
                inserted_count += 1

        # Process in database only
        for pred in results['in_database_only']:
            player_id = get_player_id(pred['player'], cursor)
            fixture_id = get_fixture_id_from_teams(pred['home_team'], pred['away_team'], pred['gameweek'], cursor)

            if player_id and fixture_id:
                db_home, db_away = map(int, pred['score'].split('-'))

                cursor.execute('''
                    INSERT INTO prediction_verification
                    (category, player_id, fixture_id, db_home_goals, db_away_goals,
                     message_home_goals, message_away_goals)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('In Database Only', player_id, fixture_id, db_home, db_away, None, None))
                inserted_count += 1

        logger.info(f"Inserted {inserted_count} verification records into database")
        return True

    except Exception as e:
        logger.error(f"Error saving to database: {e}")
        return False

def get_player_id(player_name, cursor):
    """Get player_id from player name"""
    cursor.execute("SELECT player_id FROM players WHERE LOWER(player_name) = LOWER(?)", (player_name,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_fixture_id_from_teams(home_team, away_team, gameweek, cursor):
    """Get fixture_id from team names and gameweek"""
    cursor.execute('''
        SELECT f.fixture_id
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE LOWER(ht.team_name) = LOWER(?)
        AND LOWER(at.team_name) = LOWER(?)
        AND f.gameweek = ?
        AND f.season = ?
    ''', (home_team, away_team, gameweek, CURRENT_SEASON_DB))
    result = cursor.fetchone()
    return result[0] if result else None

def cleanup_old_reports(keep_count=5, logger=None):
    """Keep only the latest N verification report files, remove older ones"""
    pattern = reports_dir / "prediction_verification_*.csv"
    files = list(glob.glob(str(pattern)))

    if len(files) <= keep_count:
        if logger:
            logger.debug(f"Only {len(files)} report files found, no cleanup needed")
        return

    # Sort files by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    # Remove files beyond the keep_count
    files_to_remove = files[keep_count:]
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old report: {os.path.basename(file_path)}")
        except Exception as e:
            if logger:
                logger.error(f"Error removing {file_path}: {e}")

def generate_reports(results, fixtures, cursor, logger):
    """Generate CSV report, save to database, and print console summary"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = reports_dir / f"prediction_verification_{timestamp}.csv"

    # Save to database
    save_to_database(results, fixtures, cursor, logger)

    # Write CSV report
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Category', 'Player', 'Gameweek', 'Fixture', 'DB Score', 'Message Score'])

        for match in results['matches']:
            writer.writerow([
                'Match',
                match['player'],
                match['gameweek'],
                f"{match['home_team']} vs {match['away_team']}",
                match['score'],
                match['score']
            ])

        for mismatch in results['score_mismatches']:
            writer.writerow([
                'Score Mismatch',
                mismatch['player'],
                mismatch['gameweek'],
                f"{mismatch['home_team']} vs {mismatch['away_team']}",
                mismatch['db_score'],
                mismatch['message_score']
            ])

        for pred in results['in_messages_only']:
            writer.writerow([
                'In Messages Only',
                pred['player'],
                pred['gameweek'],
                f"{pred['home_team']} vs {pred['away_team']}",
                '',
                pred['score']
            ])

        for pred in results['in_database_only']:
            writer.writerow([
                'In Database Only',
                pred['player'],
                pred['gameweek'],
                f"{pred['home_team']} vs {pred['away_team']}",
                pred['score'],
                ''
            ])

    logger.info(f"CSV report saved to: {csv_file}")

    # Cleanup old report files
    cleanup_old_reports(keep_count=5, logger=logger)

    # Print console summary
    print("\n" + "="*70)
    print("PREDICTION VERIFICATION SUMMARY")
    print("="*70)
    print(f"Matches: {len(results['matches'])}")
    print(f"Score Mismatches: {len(results['score_mismatches'])}")
    print(f"In Messages Only: {len(results['in_messages_only'])}")
    print(f"In Database Only: {len(results['in_database_only'])}")
    print("="*70)

    if results['score_mismatches']:
        print("\nSCORE MISMATCHES:")
        print("-" * 70)
        for mismatch in sorted(results['score_mismatches'], key=lambda x: (x['gameweek'], x['player'])):
            print(f"GW{mismatch['gameweek']:2d} | {mismatch['player']:20s} | {mismatch['home_team']:15s} vs {mismatch['away_team']:15s}")
            print(f"      DB: {mismatch['db_score']:5s} | Messages: {mismatch['message_score']:5s}")

    if results['in_messages_only']:
        print("\nIN MESSAGES BUT NOT IN DATABASE:")
        print("-" * 70)
        for pred in sorted(results['in_messages_only'], key=lambda x: (str(x['gameweek']), x['player'])):
            print(f"GW{pred['gameweek']} | {pred['player']:20s} | {pred['home_team']:15s} vs {pred['away_team']:15s} | {pred['score']}")

    print("\n" + "="*70)
    print(f"Full report saved to: {csv_file}")
    print("="*70 + "\n")

def create_verification_table(cursor, logger):
    """Create prediction_verification table if it doesn't exist"""
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_verification (
                verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                player_id INTEGER,
                fixture_id INTEGER,
                db_home_goals INTEGER,
                db_away_goals INTEGER,
                message_home_goals INTEGER,
                message_away_goals INTEGER,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players(player_id),
                FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
            )
        """)

        # Create indexes if they don't exist
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_category
            ON prediction_verification(category)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_player
            ON prediction_verification(player_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_fixture
            ON prediction_verification(fixture_id)
        """)

        logger.debug("Verification table and indexes created/verified")
        return True

    except Exception as e:
        logger.error(f"Error creating verification table: {e}")
        return False

def main(gameweek_filter=None, player_filter=None):
    """Main execution function"""
    logger = setup_logging()
    logger.info("Starting predictions verification from messages")

    try:
        # Load configuration
        config = load_config()

        # Refresh Dropbox token
        token = refresh_dropbox_token(config, logger)
        if not token:
            logger.error("Failed to get Dropbox access token")
            return

        # Load database data
        conn = sql.connect(db_path)
        cursor = conn.cursor()

        # Create verification table if it doesn't exist
        if not create_verification_table(cursor, logger):
            logger.error("Failed to create verification table")
            conn.close()
            return

        teams, players, fixtures = load_database_data(cursor, logger)
        db_predictions = load_database_predictions(cursor, logger)

        # List Dropbox files
        txt_files, zip_files = list_dropbox_files(token, logger)

        # Parse all message files
        all_message_predictions = []

        # Parse .txt files
        for file_info in txt_files:
            logger.info(f"Processing {file_info['name']}...")
            content = download_dropbox_file(file_info['path'], token, logger)
            if content:
                text_content = content.decode('utf-8-sig')
                predictions = parse_standard_text_file(text_content, teams, players, logger)
                all_message_predictions.extend(predictions)
                logger.info(f"  Found {len(predictions)} predictions")

        # Parse .zip files
        for file_info in zip_files:
            logger.info(f"Processing {file_info['name']}...")
            content = download_dropbox_file(file_info['path'], token, logger)
            if content:
                text_content = extract_zip_file(content, logger)
                if text_content:
                    predictions = parse_whatsapp_messages(text_content, teams, players, logger)
                    all_message_predictions.extend(predictions)
                    logger.info(f"  Found {len(predictions)} predictions")

        logger.info(f"Total predictions found in messages: {len(all_message_predictions)}")

        # Compare predictions
        results = compare_predictions(all_message_predictions, db_predictions, fixtures, logger)

        # Generate reports and save to database
        generate_reports(results, fixtures, cursor, logger)

        # Commit database changes
        conn.commit()
        conn.close()
        logger.info("Verification completed successfully")

    except Exception as e:
        logger.error(f"Error in main execution: {e}", exc_info=True)
        raise

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Verify predictions from Dropbox messages')
    parser.add_argument('--gameweek', type=int, help='Verify specific gameweek only')
    parser.add_argument('--player', type=str, help='Verify specific player only')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main(gameweek_filter=args.gameweek, player_filter=args.player)
