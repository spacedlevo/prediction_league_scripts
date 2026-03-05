#!/usr/bin/env python3
"""
Add timestamp columns to MySQL tables on PythonAnywhere

Adds created_at and updated_at columns to the core tables:
- fixtures
- predictions  
- results
- fantasy_pl_scores (if exists)

Usage:
    python add_mysql_timestamps.py
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

# Tables to add timestamps to
TABLES_TO_UPDATE = ['fixtures', 'predictions', 'results']

# SQL to add timestamp columns
ADD_TIMESTAMPS_SQL = {
    'fixtures': """
        ALTER TABLE fixtures 
        ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
    """,
    'predictions': """
        ALTER TABLE predictions 
        ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
    """,
    'results': """
        ALTER TABLE results 
        ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
    """
}

def load_config():
    """Load MySQL configuration from keys.json"""
    try:
        with open(KEYS_PATH, 'r') as f:
            config = json.load(f)
        
        required_keys = ['mysql_host', 'mysql_database', 'mysql_username', 'mysql_password', 
                        'pythonanywhere_username', 'pythonanywhere_password']
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            logger.error(f"Missing required keys in {KEYS_PATH}: {', '.join(missing_keys)}")
            sys.exit(1)
        
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {KEYS_PATH}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)

def check_column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    cursor.execute("""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = %s 
        AND COLUMN_NAME = %s
    """, (table_name, column_name))
    return cursor.fetchone()[0] > 0

def add_timestamps_to_mysql(config: dict) -> bool:
    """Add timestamp columns to MySQL tables"""
    try:
        # Set up SSH tunnel
        logger.info("Setting up SSH tunnel to PythonAnywhere...")
        with SSHTunnelForwarder(
            ssh_address_or_host=('ssh.pythonanywhere.com', 22),
            ssh_username=config['pythonanywhere_username'],
            ssh_password=config['pythonanywhere_password'],
            remote_bind_address=(config['mysql_host'], 3306),
            local_bind_address=('127.0.0.1', 0)
        ) as tunnel:
            logger.info(f"SSH tunnel established on local port {tunnel.local_bind_port}")
            
            # Connect to MySQL through tunnel
            mysql_config = {
                'host': '127.0.0.1',
                'port': tunnel.local_bind_port,
                'user': config['mysql_username'],
                'password': config['mysql_password'],
                'database': config['mysql_database'],
                'charset': 'utf8mb4',
                'autocommit': True
            }
            
            logger.info("Connecting to MySQL database...")
            with pymysql.connect(**mysql_config) as connection:
                with connection.cursor() as cursor:
                    
                    for table_name in TABLES_TO_UPDATE:
                        logger.info(f"Processing table: {table_name}")
                        
                        # Check if table exists
                        cursor.execute("""
                            SELECT COUNT(*) 
                            FROM INFORMATION_SCHEMA.TABLES 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = %s
                        """, (table_name,))
                        
                        if cursor.fetchone()[0] == 0:
                            logger.warning(f"Table {table_name} does not exist, skipping...")
                            continue
                        
                        # Check if columns already exist
                        has_created_at = check_column_exists(cursor, table_name, 'created_at')
                        has_updated_at = check_column_exists(cursor, table_name, 'updated_at')
                        
                        if has_created_at and has_updated_at:
                            logger.info(f"Table {table_name}: Timestamp columns already exist")
                            continue
                        
                        # Add the columns
                        logger.info(f"Table {table_name}: Adding timestamp columns...")
                        try:
                            cursor.execute(ADD_TIMESTAMPS_SQL[table_name])
                            logger.info(f"Table {table_name}: Timestamp columns added successfully")
                        except pymysql.Error as e:
                            if "Duplicate column name" in str(e):
                                logger.info(f"Table {table_name}: Timestamp columns already exist")
                            else:
                                logger.error(f"Table {table_name}: Failed to add timestamp columns: {e}")
                                return False
                    
                    logger.info("All timestamp columns added successfully")
                    return True
                    
    except Exception as e:
        logger.error(f"Failed to add timestamp columns: {e}")
        return False

def main():
    """Main function"""
    logger.info("Starting MySQL timestamp column addition...")
    
    # Load configuration
    config = load_config()
    
    # Add timestamps to MySQL
    if add_timestamps_to_mysql(config):
        logger.info("MySQL timestamp columns added successfully")
        sys.exit(0)
    else:
        logger.error("Failed to add MySQL timestamp columns")
        sys.exit(1)

if __name__ == "__main__":
    main()