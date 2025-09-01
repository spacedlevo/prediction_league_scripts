#!/usr/bin/env python3
"""
Database Change Monitor & PythonAnywhere Upload System

This script monitors the database for changes and uploads to PythonAnywhere when:
1. Any database changes are detected (immediate upload)
2. No upload has occurred in the last 30 minutes (health check upload)

CHANGE DETECTION:
- Monitors last_update table for timestamp changes from various scripts
- Scripts must update their timestamps after making database changes
- Fixed Aug 2025: Several scripts had transaction bugs preventing timestamp updates

UPLOAD BEHAVIOR:
- Triggers on any database table modification since last upload
- Uploads entire database.db file via SFTP to PythonAnywhere
- Updates "uploaded" timestamp after successful uploads
- Includes fallback health check uploads every 30 minutes

SCHEDULER INTEGRATION:
- Designed to run every minute via remote cron (master_scheduler.sh)
- Uses file locking to prevent multiple concurrent executions
- Logs all activity for debugging upload issues

Designed to run every minute via cron for responsive uploads and system monitoring.
"""

import sys
import json
import sqlite3 as sql
import logging
import paramiko
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Optional
import os
import fcntl
import tempfile

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
KEYS_PATH = PROJECT_ROOT / "keys.json"
LOG_DIR = PROJECT_ROOT / "logs"


def setup_logging(test_mode: bool = False) -> logging.Logger:
    """Setup daily logging configuration"""
    LOG_DIR.mkdir(exist_ok=True)
    
    log_filename = f"database_monitor_{datetime.now().strftime('%Y%m%d')}.log"
    if test_mode:
        log_filename = f"database_monitor_test_{datetime.now().strftime('%Y%m%d')}.log"
    
    log_path = LOG_DIR / log_filename
    
    # Always show console output for manual runs (when stdin is a tty)
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


def acquire_lock() -> Optional[int]:
    """Prevent multiple instances from running simultaneously"""
    lock_file = tempfile.gettempdir() + "/database_monitor.lock"
    
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_TRUNC | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        # Check if it's a stale lock (older than 10 minutes)
        try:
            import stat
            if os.path.exists(lock_file):
                file_stat = os.stat(lock_file)
                age_seconds = time.time() - file_stat.st_mtime
                if age_seconds > 600:  # 10 minutes
                    os.remove(lock_file)
                    # Try again after removing stale lock
                    try:
                        fd = os.open(lock_file, os.O_CREAT | os.O_TRUNC | os.O_RDWR)
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return fd
                    except (OSError, IOError):
                        pass
        except Exception:
            pass
        return None


def load_config() -> dict:
    """Load configuration from keys.json"""
    try:
        with open(KEYS_PATH, 'r') as f:
            config = json.load(f)
        
        required_keys = ['pythonanywhere_username', 'pythonanywhere_password']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required key: {key}")
        
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {KEYS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")


def parse_timestamp(timestamp_value) -> float:
    """Convert timestamp to Unix timestamp, handling both string and numeric formats"""
    if isinstance(timestamp_value, (int, float)):
        return float(timestamp_value)
    
    if isinstance(timestamp_value, str):
        # Try to parse various string formats
        try:
            # Try common formats used in the database
            for fmt in ['%Y-%m-%d %H:%M:%S', '%d-%m-%Y. %H:%M:%S', '%d-%m-%Y %H:%M:%S']:
                try:
                    dt = datetime.strptime(timestamp_value, fmt)
                    return dt.timestamp()
                except ValueError:
                    continue
            # If no format works, try direct float conversion
            return float(timestamp_value)
        except ValueError:
            # If all else fails, return 0 (epoch) so comparison works
            return 0.0
    
    return 0.0


def has_database_changes(cursor: sql.Cursor, logger: logging.Logger) -> bool:
    """Check if any database changes occurred since last upload"""
    try:
        # Get last upload timestamp
        cursor.execute("""
            SELECT timestamp FROM last_update 
            WHERE table_name = 'uploaded' 
            ORDER BY timestamp DESC LIMIT 1
        """)
        
        last_upload = cursor.fetchone()
        if not last_upload:
            logger.info("No previous upload found - upload needed")
            return True
        
        last_upload_timestamp = parse_timestamp(last_upload[0])
        logger.debug(f"Last upload timestamp: {last_upload_timestamp}")
        
        # Get all non-uploaded table updates
        cursor.execute("""
            SELECT table_name, timestamp FROM last_update 
            WHERE table_name != 'uploaded'
            ORDER BY timestamp DESC
        """)
        
        all_changes = cursor.fetchall()
        changes = []
        
        for table_name, timestamp_value in all_changes:
            parsed_timestamp = parse_timestamp(timestamp_value)
            if parsed_timestamp > last_upload_timestamp:
                changes.append((table_name, parsed_timestamp))
        
        if changes:
            change_list = [f"{change[0]} ({datetime.fromtimestamp(change[1]).strftime('%H:%M:%S')})" for change in changes]
            logger.info(f"Database changes detected: {', '.join(change_list)}")
            return True
        
        logger.debug("No database changes detected")
        return False
        
    except Exception as e:
        logger.error(f"Error checking database changes: {e}")
        return False


def last_upload_older_than_30_minutes(cursor: sql.Cursor, logger: logging.Logger) -> bool:
    """Check if last upload was more than 30 minutes ago"""
    try:
        cursor.execute("""
            SELECT timestamp FROM last_update 
            WHERE table_name = 'uploaded' 
            ORDER BY timestamp DESC LIMIT 1
        """)
        
        last_upload = cursor.fetchone()
        if not last_upload:
            logger.info("No previous upload found - health check upload needed")
            return True
        
        last_upload_timestamp = parse_timestamp(last_upload[0])
        current_timestamp = datetime.now().timestamp()
        time_diff_minutes = (current_timestamp - last_upload_timestamp) / 60
        
        if time_diff_minutes > 30:
            logger.info(f"Last upload was {time_diff_minutes:.1f} minutes ago - health check upload needed")
            return True
        
        logger.debug(f"Last upload was {time_diff_minutes:.1f} minutes ago - no health check needed")
        return False
        
    except Exception as e:
        logger.error(f"Error checking upload timestamp: {e}")
        return True  # Default to upload if we can't check


def should_upload(cursor: sql.Cursor, logger: logging.Logger) -> Tuple[bool, str]:
    """Determine if upload is needed and why"""
    if has_database_changes(cursor, logger):
        return (True, "database_changes")
    
    if last_upload_older_than_30_minutes(cursor, logger):
        return (True, "health_check")
    
    return (False, "no_upload_needed")


def upload_to_pythonanywhere(config: dict, logger: logging.Logger, dry_run: bool = False) -> bool:
    """Upload database to PythonAnywhere via SSH/SFTP"""
    if dry_run:
        logger.info("DRY RUN: Would upload database to PythonAnywhere")
        return True
    
    ssh = None
    sftp = None
    
    try:
        logger.info("Connecting to PythonAnywhere...")
        
        # Create SSH connection
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname="ssh.pythonanywhere.com",
            username=config["pythonanywhere_username"],
            password=config["pythonanywhere_password"],
            timeout=30
        )
        
        # Create SFTP connection
        sftp = ssh.open_sftp()
        
        # Upload database file
        local_db_path = str(DB_PATH)
        remote_db_path = "/home/spacedlevo/predictions_league/site/datadatabase.db"  # Upload to home directory
        
        logger.info(f"Uploading database ({DB_PATH.stat().st_size} bytes)...")
        sftp.put(local_db_path, remote_db_path)
        
        logger.info("Database upload successful")
        return True
        
    except paramiko.AuthenticationException:
        logger.error("Authentication failed - check PythonAnywhere credentials")
        return False
    except paramiko.SSHException as e:
        logger.error(f"SSH connection failed: {e}")
        return False
    except FileNotFoundError:
        logger.error(f"Database file not found: {DB_PATH}")
        return False
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return False
    finally:
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()


def update_upload_timestamp(cursor: sql.Cursor, conn: sql.Connection, logger: logging.Logger) -> bool:
    """Update the uploaded timestamp in last_update table"""
    try:
        now = datetime.now()
        timestamp = now.timestamp()
        formatted_time = now.strftime("%d-%m-%Y. %H:%M:%S")
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES (?, ?, ?)
        """, ("uploaded", formatted_time, timestamp))
        
        conn.commit()
        logger.info(f"Updated upload timestamp: {formatted_time}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update upload timestamp: {e}")
        conn.rollback()
        return False


def main_process(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Main processing logic"""
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Connect to database
        conn = sql.connect(DB_PATH)
        cursor = conn.cursor()
        logger.debug("Database connection established")
        
        try:
            # Determine if upload is needed
            upload_needed, reason = should_upload(cursor, logger)
            
            if args.force:
                upload_needed = True
                reason = "forced"
                logger.info("Force mode enabled - uploading regardless of changes")
            
            if not upload_needed:
                logger.debug("No upload needed")
                return 0  # Success - no action required
            
            logger.info(f"Upload needed: {reason}")
            
            # Perform upload
            upload_success = upload_to_pythonanywhere(config, logger, args.dry_run)
            
            if upload_success and not args.dry_run:
                # Update timestamp only on successful upload
                timestamp_updated = update_upload_timestamp(cursor, conn, logger)
                if not timestamp_updated:
                    logger.warning("Upload succeeded but failed to update timestamp")
                    return 1  # Partial failure
                
                logger.info(f"Database upload completed successfully (reason: {reason})")
                return 0  # Success
            elif upload_success and args.dry_run:
                logger.info("Dry run completed successfully")
                return 0  # Success
            else:
                logger.error("Database upload failed")
                return 1  # Failure
                
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}")
        return 1  # Failure


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Monitor database changes and upload to PythonAnywhere'
    )
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be uploaded without uploading')
    parser.add_argument('--force', action='store_true',
                       help='Force upload regardless of changes or timing')
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode with console output')
    return parser.parse_args()


def main():
    """Main entry point with proper exit codes for cron"""
    args = parse_arguments()
    
    # Acquire lock to prevent multiple instances
    lock_fd = acquire_lock()
    if lock_fd is None:
        if args.test or sys.stdin.isatty():
            print("Another instance is already running or unable to acquire lock")
        sys.exit(0)  # Exit silently for cron
    
    try:
        logger = setup_logging(args.test)
        logger.info("Starting database monitor and upload process")
        
        exit_code = main_process(args, logger)
        
        logger.info(f"Database monitor process completed with exit code: {exit_code}")
        sys.exit(exit_code)
        
    except Exception as e:
        if args.test:
            print(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        if lock_fd:
            os.close(lock_fd)


if __name__ == "__main__":
    main()