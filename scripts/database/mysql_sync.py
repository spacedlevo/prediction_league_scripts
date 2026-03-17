#!/usr/bin/env python3
"""
Zero-Downtime MySQL Synchronization for Core Prediction League Tables

Syncs only essential tables from SQLite to PythonAnywhere MySQL:
- fixtures, gameweeks, last_update, players, predictions, results, teams

Uses atomic table swaps to ensure zero downtime during synchronization:
1. Creates temporary tables with same structure
2. Syncs data to temporary tables
3. Performs atomic RENAME TABLE operation
4. Cleans up backup tables

This enables real-time data availability on PythonAnywhere while keeping
all detailed data (FPL scores, odds, pulse data) in local SQLite.

Usage:
    python mysql_sync.py --test          # Test connection
    python mysql_sync.py --full-sync     # Zero-downtime atomic sync
    python mysql_sync.py --incremental   # Sync only changes
"""

import sys
import json
import sqlite3 as sql
import pymysql
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from sshtunnel import SSHTunnelForwarder

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
KEYS_PATH = PROJECT_ROOT / "keys.json"
LOG_DIR = PROJECT_ROOT / "logs"

# Core tables to sync (in dependency order for foreign keys)
SYNC_TABLES = [
    'teams',        # Referenced by fixtures
    'gameweeks',    # Standalone
    'players',      # Referenced by predictions
    'fixtures',     # References teams
    'results',      # References fixtures
    'predictions',  # References players and fixtures
    'last_update'   # Change tracking
]


def setup_logging(test_mode: bool = False) -> logging.Logger:
    """Setup daily logging configuration"""
    LOG_DIR.mkdir(exist_ok=True)
    
    log_filename = f"mysql_sync_{datetime.now().strftime('%Y%m%d')}.log"
    if test_mode:
        log_filename = f"mysql_sync_test_{datetime.now().strftime('%Y%m%d')}.log"
    
    log_path = LOG_DIR / log_filename
    
    # Always show console output for manual runs
    show_console = test_mode or sys.stdin.isatty()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler() if show_console else logging.NullHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def load_config() -> dict:
    """Load MySQL configuration from keys.json"""
    try:
        with open(KEYS_PATH, 'r') as f:
            config = json.load(f)
        
        required_keys = ['mysql_host', 'mysql_database', 'mysql_username', 'mysql_password']
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            raise ValueError(f"Missing required MySQL keys in {KEYS_PATH}: {', '.join(missing_keys)}")
        
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {KEYS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")


def get_mysql_connection(config: dict) -> Tuple[pymysql.Connection, Optional[SSHTunnelForwarder]]:
    """Create MySQL connection through SSH tunnel"""
    try:
        # Create SSH tunnel to PythonAnywhere
        tunnel = SSHTunnelForwarder(
            ('ssh.pythonanywhere.com', 22),
            ssh_username=config['pythonanywhere_username'],
            ssh_password=config['pythonanywhere_password'],
            remote_bind_address=(config['mysql_host'], 3306),
            local_bind_address=('127.0.0.1', 3306)
        )
        
        tunnel.start()
        
        # Connect to MySQL through the tunnel
        connection = pymysql.connect(
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            user=config['mysql_username'],
            password=config['mysql_password'],
            database=config['mysql_database'],
            charset='utf8mb4',
            autocommit=False
        )
        
        return connection, tunnel
        
    except Exception as e:
        if 'tunnel' in locals():
            tunnel.stop()
        raise Exception(f"Failed to connect to MySQL via SSH tunnel: {e}")


def get_sqlite_connection() -> sql.Connection:
    """Create SQLite connection"""
    try:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"SQLite database not found: {DB_PATH}")
        
        conn = sql.connect(DB_PATH)
        conn.row_factory = sql.Row  # Enable column name access
        return conn
    except Exception as e:
        raise Exception(f"Failed to connect to SQLite: {e}")


def get_table_columns(table_name: str, sqlite_cursor: sql.Cursor) -> List[str]:
    """Get column names for a table from SQLite"""
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in sqlite_cursor.fetchall()]
    return columns


def create_temp_table(table_name: str, mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> bool:
    """Create temporary table with same structure as original"""
    temp_table_name = f"{table_name}_temp"
    
    try:
        # Drop temp table if it exists from previous failed run
        mysql_cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
        
        # Create temp table with same structure as original
        mysql_cursor.execute(f"CREATE TABLE {temp_table_name} LIKE {table_name}")
        
        logger.info(f"Created temporary table: {temp_table_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create temp table {temp_table_name}: {e}")
        return False


def sync_table_to_temp(table_name: str, sqlite_cursor: sql.Cursor, 
                      mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> int:
    """Sync data from SQLite to temporary MySQL table"""
    temp_table_name = f"{table_name}_temp"
    
    try:
        # Get total count first
        sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = sqlite_cursor.fetchone()[0]
        
        if total_rows == 0:
            logger.info(f"Table {table_name}: No data to sync")
            return 0
        
        logger.info(f"Table {table_name}: Syncing {total_rows:,} records to temp table")
        
        # Get column names
        columns = get_table_columns(table_name, sqlite_cursor)
        
        # Prepare INSERT statement for temp table
        placeholders = ','.join(['%s'] * len(columns))
        column_names = ','.join(columns)
        insert_sql = f"INSERT INTO {temp_table_name} ({column_names}) VALUES ({placeholders})"
        
        # Process data in smaller batches for large tables
        batch_size = 500 if total_rows > 10000 else 1000
        total_inserted = 0
        
        offset = 0
        while offset < total_rows:
            # Get batch of data
            sqlite_cursor.execute(f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", (batch_size, offset))
            batch_rows = sqlite_cursor.fetchall()
            
            if not batch_rows:
                break
            
            # Convert rows to tuples for MySQL with timestamp validation
            data_tuples = []
            for row in batch_rows:
                if table_name == 'last_update':
                    # Validate timestamp for last_update table (MySQL limit: 2038-01-19)
                    row_list = list(row)
                    if len(row_list) >= 3 and row_list[2] is not None:  # timestamp column
                        timestamp_val = row_list[2]
                        
                        # Check for invalid timestamp values like 999999999.999999
                        if timestamp_val == 999999999.999999 or timestamp_val > 2147483647:
                            # Use current timestamp for invalid values
                            current_timestamp = datetime.now().timestamp()
                            logger.warning(f"Replacing invalid timestamp {timestamp_val} with current timestamp {current_timestamp} for table_name: {row_list[0]}")
                            row_list[2] = current_timestamp
                        elif timestamp_val < 0:
                            # Handle negative timestamps
                            current_timestamp = datetime.now().timestamp()
                            logger.warning(f"Replacing negative timestamp {timestamp_val} with current timestamp {current_timestamp} for table_name: {row_list[0]}")
                            row_list[2] = current_timestamp
                    data_tuples.append(tuple(row_list))
                else:
                    data_tuples.append(tuple(row))
            
            # Insert batch
            try:
                mysql_cursor.executemany(insert_sql, data_tuples)
                total_inserted += len(data_tuples)
                
                # Progress reporting for large tables
                if total_rows > 5000:
                    progress = (total_inserted / total_rows) * 100
                    logger.info(f"Table {table_name}: {total_inserted:,}/{total_rows:,} records ({progress:.1f}%)")
                
            except Exception as e:
                logger.error(f"Error inserting batch at offset {offset}: {e}")
                raise
            
            offset += batch_size
        
        logger.info(f"Table {table_name}: Successfully synced {total_inserted:,} records to temp table")
        return total_inserted
        
    except Exception as e:
        logger.error(f"Error syncing table {table_name} to temp: {e}")
        raise


def test_connection(config: dict, logger: logging.Logger) -> bool:
    """Test MySQL connection and basic functionality"""
    tunnel = None
    mysql_conn = None
    sqlite_conn = None
    
    try:
        logger.info("Testing MySQL connection via SSH tunnel...")
        
        # Test MySQL connection
        mysql_conn, tunnel = get_mysql_connection(config)
        mysql_cursor = mysql_conn.cursor()
        
        # Test basic query
        mysql_cursor.execute("SELECT VERSION()")
        version = mysql_cursor.fetchone()[0]
        logger.info(f"MySQL connection successful - Version: {version}")
        
        # Test SQLite connection
        sqlite_conn = get_sqlite_connection()
        sqlite_cursor = sqlite_conn.cursor()
        
        sqlite_cursor.execute("SELECT sqlite_version()")
        sqlite_version = sqlite_cursor.fetchone()[0]
        logger.info(f"SQLite connection successful - Version: {sqlite_version}")
        
        # Check if core tables exist in both databases
        for table_name in SYNC_TABLES:
            # Check SQLite
            sqlite_cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", 
                (table_name,)
            )
            if sqlite_cursor.fetchone()[0] == 0:
                logger.warning(f"Table {table_name} not found in SQLite")
                continue
            
            # Check MySQL
            mysql_cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            mysql_tables = mysql_cursor.fetchone()
            if not mysql_tables:
                logger.warning(f"Table {table_name} not found in MySQL")
                continue
            
            # Count records
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = sqlite_cursor.fetchone()[0]
            
            mysql_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            mysql_count = mysql_cursor.fetchone()[0]
            
            logger.info(f"Table {table_name}: SQLite={sqlite_count}, MySQL={mysql_count}")
        
        logger.info("Connection test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False
        
    finally:
        # Clean up connections
        if mysql_conn:
            mysql_conn.close()
        if sqlite_conn:
            sqlite_conn.close()
        if tunnel:
            tunnel.stop()


def cleanup_old_backup_tables(tables_to_cleanup: List[str], mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> None:
    """Clean up any existing backup tables from previous failed runs"""
    # Temporarily disable foreign key checks for cleanup
    mysql_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    
    for table_name in tables_to_cleanup:
        backup_table = f"{table_name}_backup"
        try:
            mysql_cursor.execute(f"DROP TABLE IF EXISTS {backup_table}")
            logger.info(f"Cleaned up old backup table: {backup_table}")
        except Exception as e:
            logger.warning(f"Failed to clean up old backup table {backup_table}: {e}")
    
    # Re-enable foreign key checks
    mysql_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def atomic_table_swap(tables_to_swap: List[str], mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> bool:
    """Perform atomic swap of all tables at once using RENAME TABLE"""
    try:
        logger.info("Starting atomic table swap...")
        
        # First, clean up any existing backup tables from previous failed runs
        logger.info("Cleaning up any existing backup tables...")
        cleanup_old_backup_tables(tables_to_swap, mysql_cursor, logger)
        
        # Build the RENAME TABLE statement for all tables
        # Format: RENAME TABLE old1 TO backup1, temp1 TO old1, old2 TO backup2, temp2 TO old2, ...
        rename_parts = []
        
        for table_name in tables_to_swap:
            temp_table = f"{table_name}_temp"
            backup_table = f"{table_name}_backup"
            
            # Move current table to backup, temp table to current
            rename_parts.append(f"{table_name} TO {backup_table}")
            rename_parts.append(f"{temp_table} TO {table_name}")
        
        rename_sql = "RENAME TABLE " + ", ".join(rename_parts)
        
        logger.info(f"Executing atomic rename: {rename_sql}")
        mysql_cursor.execute(rename_sql)
        
        logger.info(f"Successfully swapped {len(tables_to_swap)} tables atomically")
        return True
        
    except Exception as e:
        logger.error(f"Atomic table swap failed: {e}")
        return False


def cleanup_backup_tables(tables_to_cleanup: List[str], mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> None:
    """Clean up backup tables after successful swap"""
    for table_name in tables_to_cleanup:
        backup_table = f"{table_name}_backup"
        try:
            mysql_cursor.execute(f"DROP TABLE IF EXISTS {backup_table}")
            logger.info(f"Cleaned up backup table: {backup_table}")
        except Exception as e:
            logger.warning(f"Failed to clean up backup table {backup_table}: {e}")


def rollback_table_swap(tables_to_rollback: List[str], mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> bool:
    """Rollback table swap by restoring from backup tables"""
    try:
        logger.warning("Rolling back table swap...")
        
        # First check what tables actually exist
        existing_tables = set()
        mysql_cursor.execute("SHOW TABLES")
        for (table_name,) in mysql_cursor.fetchall():
            existing_tables.add(table_name)
        
        logger.info(f"Existing tables: {sorted(existing_tables)}")
        
        # Clean up any conflicting temp tables first
        for table_name in tables_to_rollback:
            temp_table = f"{table_name}_temp"
            if temp_table in existing_tables:
                logger.info(f"Dropping conflicting temp table: {temp_table}")
                mysql_cursor.execute(f"DROP TABLE {temp_table}")
        
        # Build rollback RENAME statement only for tables that exist
        rename_parts = []
        
        for table_name in tables_to_rollback:
            backup_table = f"{table_name}_backup"
            temp_table = f"{table_name}_temp"
            
            # Only proceed if backup table exists
            if backup_table in existing_tables:
                # Move current (new) table to temp, backup to current
                rename_parts.append(f"{table_name} TO {temp_table}")
                rename_parts.append(f"{backup_table} TO {table_name}")
        
        if rename_parts:
            rename_sql = "RENAME TABLE " + ", ".join(rename_parts)
            logger.info(f"Executing rollback: {rename_sql}")
            mysql_cursor.execute(rename_sql)
            logger.info("Successfully rolled back table swap")
        else:
            logger.warning("No backup tables found to rollback")
        
        return True
        
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False


def full_sync_zero_downtime(config: dict, logger: logging.Logger) -> bool:
    """Perform zero-downtime synchronization using temporary tables and atomic swap"""
    sqlite_conn = None
    mysql_conn = None
    tunnel = None
    temp_tables_created = []
    
    try:
        logger.info("Starting zero-downtime synchronization...")
        
        # Establish connections
        sqlite_conn = get_sqlite_connection()
        mysql_conn, tunnel = get_mysql_connection(config)
        
        sqlite_cursor = sqlite_conn.cursor()
        mysql_cursor = mysql_conn.cursor()
        
        # Disable autocommit for transaction control
        mysql_conn.autocommit(False)
        
        total_synced = 0
        
        # Phase 1: Create temporary tables
        logger.info("Phase 1: Creating temporary tables...")
        for table_name in SYNC_TABLES:
            if not create_temp_table(table_name, mysql_cursor, logger):
                raise Exception(f"Failed to create temp table for {table_name}")
            temp_tables_created.append(table_name)
        
        mysql_conn.commit()
        logger.info("All temporary tables created successfully")
        
        # Phase 2: Sync data to temporary tables
        logger.info("Phase 2: Syncing data to temporary tables...")
        for table_name in SYNC_TABLES:
            logger.info(f"Syncing table: {table_name}")
            
            synced_count = sync_table_to_temp(table_name, sqlite_cursor, mysql_cursor, logger)
            total_synced += synced_count
            
            # Commit after each table
            mysql_conn.commit()
            logger.info(f"Table {table_name}: Committed {synced_count} records to temp table")
        
        logger.info("All data synced to temporary tables")
        
        # Phase 3: Verify data integrity
        logger.info("Phase 3: Verifying data integrity...")
        for table_name in SYNC_TABLES:
            # Count records in temp table
            mysql_cursor.execute(f"SELECT COUNT(*) FROM {table_name}_temp")
            temp_count = mysql_cursor.fetchone()[0]
            
            # Count records in SQLite
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = sqlite_cursor.fetchone()[0]
            
            if temp_count != sqlite_count:
                raise Exception(f"Data integrity check failed for {table_name}: temp={temp_count}, sqlite={sqlite_count}")
            
            logger.info(f"Table {table_name}: Verified {temp_count} records")
        
        # Phase 4: Atomic swap
        logger.info("Phase 4: Performing atomic table swap...")
        if not atomic_table_swap(SYNC_TABLES, mysql_cursor, logger):
            raise Exception("Atomic table swap failed")
        
        mysql_conn.commit()
        
        # Phase 5: Update sync timestamp
        logger.info("Phase 5: Updating sync timestamp...")
        update_mysql_sync_timestamp(mysql_cursor, logger)
        mysql_conn.commit()
        
        # Phase 6: Cleanup backup tables
        logger.info("Phase 6: Cleaning up backup tables...")
        cleanup_backup_tables(SYNC_TABLES, mysql_cursor, logger)
        mysql_conn.commit()
        
        logger.info(f"Zero-downtime synchronization completed: {total_synced} total records synced")
        return True
        
    except Exception as e:
        logger.error(f"Zero-downtime sync failed: {e}")
        
        # Attempt rollback if swap was attempted
        if mysql_conn:
            try:
                mysql_conn.rollback()
                
                # Check if we need to rollback a swap
                backup_exists = False
                for table_name in temp_tables_created:
                    mysql_cursor.execute(f"SHOW TABLES LIKE '{table_name}_backup'")
                    if mysql_cursor.fetchone():
                        backup_exists = True
                        break
                
                if backup_exists:
                    logger.info("Attempting to rollback table swap...")
                    if rollback_table_swap(temp_tables_created, mysql_cursor, logger):
                        mysql_conn.commit()
                        logger.info("Rollback successful")
                    else:
                        logger.error("Rollback failed - manual intervention may be required")
                        
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
        
        return False
        
    finally:
        # Cleanup any remaining temp tables
        if mysql_conn and temp_tables_created:
            try:
                for table_name in temp_tables_created:
                    mysql_cursor.execute(f"DROP TABLE IF EXISTS {table_name}_temp")
                mysql_conn.commit()
            except Exception as cleanup_error:
                logger.warning(f"Cleanup failed: {cleanup_error}")
        
        if sqlite_conn:
            sqlite_conn.close()
        if mysql_conn:
            mysql_conn.close()
        if tunnel:
            tunnel.stop()


def update_mysql_sync_timestamp(mysql_cursor: pymysql.cursors.Cursor, logger: logging.Logger) -> None:
    """Update the mysql_synced timestamp in last_update table"""
    now = datetime.now()
    timestamp = now.timestamp()
    formatted_time = now.strftime("%d-%m-%Y %H:%M:%S")  # Fixed format to match other entries
    
    try:
        mysql_cursor.execute("""
            INSERT INTO last_update (table_name, updated, timestamp) 
            VALUES ('mysql_synced', %s, %s)
            ON DUPLICATE KEY UPDATE updated = VALUES(updated), timestamp = VALUES(timestamp)
        """, (formatted_time, timestamp))
        
        logger.info(f"Updated mysql_synced timestamp: {formatted_time} ({timestamp})")
        
    except Exception as e:
        logger.error(f"Failed to update mysql_synced timestamp: {e}")
        raise


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='MySQL synchronization for core prediction league tables'
    )
    parser.add_argument('--test', action='store_true',
                       help='Test MySQL connection and show table status')
    parser.add_argument('--full-sync', action='store_true',
                       help='Perform zero-downtime synchronization using atomic table swaps')
    parser.add_argument('--incremental', action='store_true',
                       help='Sync only changed data since last MySQL sync')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be synced without making changes')
    
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()
    
    try:
        logger = setup_logging(args.test)
        config = load_config()
        
        logger.info("═" * 60)
        logger.info("MYSQL SYNCHRONIZATION")
        logger.info("═" * 60)
        
        if args.test:
            success = test_connection(config, logger)
            sys.exit(0 if success else 1)
        
        elif args.full_sync:
            success = full_sync_zero_downtime(config, logger)
            sys.exit(0 if success else 1)
        
        elif args.incremental:
            logger.info("Incremental sync not yet implemented")
            sys.exit(1)
        
        else:
            logger.info("No action specified. Use --test, --full-sync, or --incremental")
            sys.exit(1)
            
    except Exception as e:
        if 'logger' in locals():
            logger.error(f"Fatal error: {e}")
        else:
            print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()