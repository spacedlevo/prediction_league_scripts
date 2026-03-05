#!/usr/bin/env python3
"""
Create MySQL Schema for Prediction League

Creates all necessary tables in the PythonAnywhere MySQL database.
Run this once after setting up MySQL credentials.

Usage:
    python create_mysql_schema.py
"""

import sys
import json
from pathlib import Path
from sshtunnel import SSHTunnelForwarder
import pymysql
import logging

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
KEYS_PATH = PROJECT_ROOT / "keys.json"

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MySQL Schema SQL
SCHEMA_SQL = """
-- Teams table - Premier League teams
CREATE TABLE teams (
    team_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_id INT,
    team_name VARCHAR(100),
    available TINYINT(1) DEFAULT 0,
    strength INT,
    strength_overall_home INT,
    strength_overall_away INT,
    strength_attack_home INT,
    strength_attack_away INT,
    strength_defence_home INT,
    strength_defence_away INT,
    pulse_id INT,
    football_data_name VARCHAR(100),
    odds_api_name VARCHAR(100)
) ENGINE=InnoDB;

-- Gameweeks table - Premier League gameweek information
CREATE TABLE gameweeks (
    gameweek INT PRIMARY KEY,
    deadline_dttm DATETIME,
    deadline_date DATE,
    deadline_time TIME,
    current_gameweek TINYINT(1),
    next_gameweek TINYINT(1),
    finished TINYINT(1)
) ENGINE=InnoDB;

CREATE INDEX idx_gameweeks_current ON gameweeks(current_gameweek);
CREATE INDEX idx_gameweeks_finished ON gameweeks(finished);

-- Players table - Prediction league participants
CREATE TABLE players (
    player_id INT PRIMARY KEY,
    player_name VARCHAR(100),
    paid TINYINT(1) NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 0,
    mini_league TINYINT(1) NOT NULL DEFAULT 0,
    mini_league_paid TINYINT(1) NOT NULL DEFAULT 0,
    pundit TINYINT(1) NOT NULL DEFAULT 0,
    web_name VARCHAR(100)
) ENGINE=InnoDB;

-- Fixtures table - Match schedule and basic info
CREATE TABLE fixtures (
    fixture_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_fixture_id INT NOT NULL,
    kickoff_dttm DATETIME,
    home_teamid INT NOT NULL,
    away_teamid INT NOT NULL,
    finished TINYINT(1) DEFAULT 1,
    season VARCHAR(20),
    home_win_odds DECIMAL(8,3),
    draw_odds DECIMAL(8,3),
    away_win_odds DECIMAL(8,3),
    pulse_id INT,
    gameweek INT,
    started TINYINT(1) DEFAULT 0,
    provisional_finished TINYINT(1) DEFAULT 0,
    FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
    FOREIGN KEY (away_teamid) REFERENCES teams(team_id),
    UNIQUE KEY unique_fixture (fixture_id)
) ENGINE=InnoDB;

CREATE INDEX idx_fixtures_season ON fixtures(season);
CREATE INDEX idx_fixtures_gameweek ON fixtures(gameweek);
CREATE INDEX idx_fixtures_fpl_id ON fixtures(fpl_fixture_id);

-- Results table - Actual match results
CREATE TABLE results (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_fixture_id INT NOT NULL,
    fixture_id INT,
    home_goals INT,
    away_goals INT,
    result VARCHAR(1),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
) ENGINE=InnoDB;

-- Predictions table - User predictions
CREATE TABLE predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT,
    fixture_id INT,
    fpl_fixture_id INT,
    home_goals INT,
    away_goals INT,
    predicted_result VARCHAR(1),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    UNIQUE KEY idx_unique_player_fixture (player_id, fixture_id)
) ENGINE=InnoDB;

-- Last update table - Change tracking for sync
CREATE TABLE last_update (
    table_name VARCHAR(50) PRIMARY KEY,
    updated VARCHAR(100),
    timestamp DECIMAL(15,6)
) ENGINE=InnoDB;
"""

def load_config():
    """Load configuration from keys.json"""
    try:
        with open(KEYS_PATH, 'r') as f:
            config = json.load(f)
        
        required_keys = ['mysql_host', 'mysql_database', 'mysql_username', 'mysql_password', 
                        'pythonanywhere_username', 'pythonanywhere_password']
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            raise ValueError(f"Missing required keys: {', '.join(missing_keys)}")
        
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {KEYS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")

def create_schema():
    """Create the MySQL schema via SSH tunnel"""
    tunnel = None
    mysql_conn = None
    
    try:
        logger.info("Loading configuration...")
        config = load_config()
        
        logger.info("Creating SSH tunnel to PythonAnywhere...")
        tunnel = SSHTunnelForwarder(
            ('ssh.pythonanywhere.com', 22),
            ssh_username=config['pythonanywhere_username'],
            ssh_password=config['pythonanywhere_password'],
            remote_bind_address=(config['mysql_host'], 3306),
            local_bind_address=('127.0.0.1', 3306)
        )
        
        tunnel.start()
        logger.info(f"SSH tunnel established on local port {tunnel.local_bind_port}")
        
        logger.info("Connecting to MySQL...")
        mysql_conn = pymysql.connect(
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            user=config['mysql_username'],
            password=config['mysql_password'],
            database=config['mysql_database'],
            charset='utf8mb4',
            autocommit=False
        )
        
        cursor = mysql_conn.cursor()
        logger.info("MySQL connection successful")
        
        # Check MySQL version
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        logger.info(f"MySQL Version: {version}")
        
        logger.info("Creating tables...")
        
        # Split schema into individual statements and execute
        statements = [stmt.strip() for stmt in SCHEMA_SQL.split(';') if stmt.strip()]
        
        for i, statement in enumerate(statements):
            if statement:
                try:
                    cursor.execute(statement)
                    if statement.upper().startswith('CREATE TABLE'):
                        table_name = statement.split()[2] if len(statement.split()) > 2 else "unknown"
                        logger.info(f"Created table: {table_name}")
                    elif statement.upper().startswith('CREATE INDEX'):
                        index_name = statement.split()[2] if len(statement.split()) > 2 else "unknown"
                        logger.info(f"Created index: {index_name}")
                except Exception as e:
                    logger.error(f"Error executing statement {i+1}: {e}")
                    logger.error(f"Statement: {statement[:100]}...")
                    raise
        
        mysql_conn.commit()
        logger.info("Schema creation completed successfully!")
        
        # Verify tables were created
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Created {len(tables)} tables: {', '.join(sorted(tables))}")
        
        return True
        
    except Exception as e:
        logger.error(f"Schema creation failed: {e}")
        if mysql_conn:
            mysql_conn.rollback()
        return False
        
    finally:
        if mysql_conn:
            mysql_conn.close()
        if tunnel:
            tunnel.stop()
            logger.info("SSH tunnel closed")

if __name__ == "__main__":
    try:
        success = create_schema()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)