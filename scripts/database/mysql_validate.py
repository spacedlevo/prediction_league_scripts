#!/usr/bin/env python3
"""
MySQL Data Validation Script

Compares data between SQLite and MySQL databases to ensure sync accuracy.
Provides detailed reports on record counts, data differences, and integrity checks.

Usage:
    python mysql_validate.py --counts        # Compare record counts
    python mysql_validate.py --sample        # Sample data comparison
    python mysql_validate.py --integrity     # Check foreign key integrity
    python mysql_validate.py --all           # Run all validations
"""

import sys
import json
import sqlite3 as sql
import pymysql
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any
from sshtunnel import SSHTunnelForwarder

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
KEYS_PATH = PROJECT_ROOT / "keys.json"
LOG_DIR = PROJECT_ROOT / "logs"

# Core tables to validate
SYNC_TABLES = [
    'teams', 'gameweeks', 'players', 'fixtures', 
    'results', 'predictions', 'last_update'
]


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    LOG_DIR.mkdir(exist_ok=True)
    
    log_filename = f"mysql_validate_{datetime.now().strftime('%Y%m%d')}.log"
    log_path = LOG_DIR / log_filename
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def load_config() -> dict:
    """Load configuration from keys.json"""
    try:
        with open(KEYS_PATH, 'r') as f:
            config = json.load(f)
        
        required_keys = ['mysql_host', 'mysql_database', 'mysql_username', 'mysql_password']
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            raise ValueError(f"Missing required MySQL keys: {', '.join(missing_keys)}")
        
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {KEYS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")


def get_connections(config: dict) -> Tuple[sql.Connection, pymysql.Connection, SSHTunnelForwarder]:
    """Get both SQLite and MySQL connections via SSH tunnel"""
    # SQLite connection
    if not DB_PATH.exists():
        raise FileNotFoundError(f"SQLite database not found: {DB_PATH}")
    
    sqlite_conn = sql.connect(DB_PATH)
    sqlite_conn.row_factory = sql.Row
    
    # Create SSH tunnel
    tunnel = SSHTunnelForwarder(
        ('ssh.pythonanywhere.com', 22),
        ssh_username=config['pythonanywhere_username'],
        ssh_password=config['pythonanywhere_password'],
        remote_bind_address=(config['mysql_host'], 3306),
        local_bind_address=('127.0.0.1', 3306)
    )
    
    tunnel.start()
    
    # MySQL connection through tunnel
    mysql_conn = pymysql.connect(
        host='127.0.0.1',
        port=tunnel.local_bind_port,
        user=config['mysql_username'],
        password=config['mysql_password'],
        database=config['mysql_database'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    return sqlite_conn, mysql_conn, tunnel


def validate_record_counts(sqlite_conn: sql.Connection, mysql_conn: pymysql.Connection, 
                          logger: logging.Logger) -> Dict[str, Dict[str, int]]:
    """Compare record counts between databases"""
    logger.info("Validating record counts...")
    
    sqlite_cursor = sqlite_conn.cursor()
    mysql_cursor = mysql_conn.cursor()
    
    results = {}
    
    for table_name in SYNC_TABLES:
        try:
            # SQLite count
            sqlite_cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            sqlite_count = sqlite_cursor.fetchone()['count']
            
            # MySQL count
            mysql_cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            mysql_result = mysql_cursor.fetchone()
            mysql_count = mysql_result['count'] if mysql_result else 0
            
            results[table_name] = {
                'sqlite': sqlite_count,
                'mysql': mysql_count,
                'match': sqlite_count == mysql_count
            }
            
            status = "✓" if sqlite_count == mysql_count else "✗"
            logger.info(f"{status} {table_name}: SQLite={sqlite_count}, MySQL={mysql_count}")
            
        except Exception as e:
            logger.error(f"Error counting records in {table_name}: {e}")
            results[table_name] = {
                'sqlite': -1,
                'mysql': -1,
                'match': False,
                'error': str(e)
            }
    
    return results


def sample_data_comparison(sqlite_conn: sql.Connection, mysql_conn: pymysql.Connection,
                          logger: logging.Logger, sample_size: int = 5) -> Dict[str, bool]:
    """Compare sample records between databases"""
    logger.info(f"Comparing sample data (first {sample_size} records per table)...")
    
    sqlite_cursor = sqlite_conn.cursor()
    mysql_cursor = mysql_conn.cursor()
    
    results = {}
    
    for table_name in SYNC_TABLES:
        try:
            # Get primary key column
            sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
            pk_column = None
            for col in sqlite_cursor.fetchall():
                if col['pk'] == 1:
                    pk_column = col['name']
                    break
            
            if not pk_column:
                logger.warning(f"No primary key found for {table_name}")
                results[table_name] = False
                continue
            
            # Get sample from SQLite
            sqlite_cursor.execute(f"SELECT * FROM {table_name} ORDER BY {pk_column} LIMIT ?", (sample_size,))
            sqlite_rows = [dict(row) for row in sqlite_cursor.fetchall()]
            
            # Get sample from MySQL
            mysql_cursor.execute(f"SELECT * FROM {table_name} ORDER BY {pk_column} LIMIT %s", (sample_size,))
            mysql_rows = mysql_cursor.fetchall()
            
            # Compare data
            match = True
            if len(sqlite_rows) != len(mysql_rows):
                match = False
                logger.warning(f"{table_name}: Different sample sizes - SQLite={len(sqlite_rows)}, MySQL={len(mysql_rows)}")
            else:
                for i, (sqlite_row, mysql_row) in enumerate(zip(sqlite_rows, mysql_rows)):
                    # Convert types for comparison (SQLite uses different types)
                    for key, value in sqlite_row.items():
                        if isinstance(value, bool) and key in mysql_row:
                            mysql_row[key] = bool(mysql_row[key])
                        elif isinstance(value, (int, float)) and key in mysql_row and mysql_row[key] is not None:
                            if isinstance(value, int):
                                mysql_row[key] = int(mysql_row[key])
                            else:
                                mysql_row[key] = float(mysql_row[key])
                    
                    if sqlite_row != mysql_row:
                        match = False
                        logger.warning(f"{table_name} row {i+1}: Data mismatch")
                        logger.debug(f"SQLite: {sqlite_row}")
                        logger.debug(f"MySQL:  {mysql_row}")
                        break
            
            results[table_name] = match
            status = "✓" if match else "✗"
            logger.info(f"{status} {table_name}: Sample data {'matches' if match else 'differs'}")
            
        except Exception as e:
            logger.error(f"Error comparing sample data for {table_name}: {e}")
            results[table_name] = False
    
    return results


def check_foreign_key_integrity(mysql_conn: pymysql.Connection, logger: logging.Logger) -> Dict[str, bool]:
    """Check foreign key integrity in MySQL database"""
    logger.info("Checking foreign key integrity...")
    
    mysql_cursor = mysql_conn.cursor()
    results = {}
    
    # Define foreign key relationships to check
    foreign_keys = [
        ('fixtures', 'home_teamid', 'teams', 'team_id'),
        ('fixtures', 'away_teamid', 'teams', 'team_id'),
        ('results', 'fixture_id', 'fixtures', 'fixture_id'),
        ('predictions', 'player_id', 'players', 'player_id'),
        ('predictions', 'fixture_id', 'fixtures', 'fixture_id')
    ]
    
    for child_table, child_col, parent_table, parent_col in foreign_keys:
        try:
            # Check for orphaned records
            query = f"""
                SELECT COUNT(*) as orphaned_count
                FROM {child_table} c
                LEFT JOIN {parent_table} p ON c.{child_col} = p.{parent_col}
                WHERE c.{child_col} IS NOT NULL AND p.{parent_col} IS NULL
            """
            
            mysql_cursor.execute(query)
            result = mysql_cursor.fetchone()
            orphaned_count = result['orphaned_count'] if result else 0
            
            fk_name = f"{child_table}.{child_col} -> {parent_table}.{parent_col}"
            results[fk_name] = orphaned_count == 0
            
            status = "✓" if orphaned_count == 0 else "✗"
            logger.info(f"{status} {fk_name}: {orphaned_count} orphaned records")
            
        except Exception as e:
            logger.error(f"Error checking FK {fk_name}: {e}")
            results[fk_name] = False
    
    return results


def generate_summary_report(count_results: Dict, sample_results: Dict, 
                          integrity_results: Dict, logger: logging.Logger) -> None:
    """Generate a comprehensive validation summary"""
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY REPORT")
    logger.info("=" * 60)
    
    # Count validation summary
    count_pass = sum(1 for r in count_results.values() if r.get('match', False))
    count_total = len(count_results)
    logger.info(f"Record Count Validation: {count_pass}/{count_total} tables match")
    
    # Sample data summary
    sample_pass = sum(1 for match in sample_results.values() if match)
    sample_total = len(sample_results)
    logger.info(f"Sample Data Validation: {sample_pass}/{sample_total} tables match")
    
    # Foreign key summary
    integrity_pass = sum(1 for valid in integrity_results.values() if valid)
    integrity_total = len(integrity_results)
    logger.info(f"Foreign Key Integrity: {integrity_pass}/{integrity_total} constraints valid")
    
    # Overall status
    all_pass = count_pass == count_total and sample_pass == sample_total and integrity_pass == integrity_total
    overall_status = "PASS" if all_pass else "FAIL"
    logger.info(f"Overall Validation Status: {overall_status}")
    
    # Detailed failures
    if not all_pass:
        logger.info("\nFailed Validations:")
        
        for table, result in count_results.items():
            if not result.get('match', False):
                logger.info(f"  - Count mismatch in {table}: SQLite={result['sqlite']}, MySQL={result['mysql']}")
        
        for table, match in sample_results.items():
            if not match:
                logger.info(f"  - Sample data differs in {table}")
        
        for fk, valid in integrity_results.items():
            if not valid:
                logger.info(f"  - Foreign key violation: {fk}")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Validate data consistency between SQLite and MySQL'
    )
    parser.add_argument('--counts', action='store_true',
                       help='Compare record counts between databases')
    parser.add_argument('--sample', action='store_true',
                       help='Compare sample data between databases')
    parser.add_argument('--integrity', action='store_true',
                       help='Check foreign key integrity in MySQL')
    parser.add_argument('--all', action='store_true',
                       help='Run all validations')
    parser.add_argument('--sample-size', type=int, default=5,
                       help='Number of sample records to compare (default: 5)')
    
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()
    
    if not (args.counts or args.sample or args.integrity or args.all):
        print("Error: No validation type specified. Use --counts, --sample, --integrity, or --all")
        sys.exit(1)
    
    try:
        logger = setup_logging()
        config = load_config()
        
        logger.info("=" * 60)
        logger.info("MYSQL DATA VALIDATION")
        logger.info("=" * 60)
        
        sqlite_conn, mysql_conn, tunnel = get_connections(config)
        
        count_results = {}
        sample_results = {}
        integrity_results = {}
        
        try:
            if args.all or args.counts:
                count_results = validate_record_counts(sqlite_conn, mysql_conn, logger)
            
            if args.all or args.sample:
                sample_results = sample_data_comparison(sqlite_conn, mysql_conn, logger, args.sample_size)
            
            if args.all or args.integrity:
                integrity_results = check_foreign_key_integrity(mysql_conn, logger)
            
            if args.all:
                generate_summary_report(count_results, sample_results, integrity_results, logger)
            
            # Determine exit code based on results
            all_passed = True
            
            if count_results and not all(r.get('match', False) for r in count_results.values()):
                all_passed = False
            
            if sample_results and not all(sample_results.values()):
                all_passed = False
            
            if integrity_results and not all(integrity_results.values()):
                all_passed = False
            
            sys.exit(0 if all_passed else 1)
            
        finally:
            sqlite_conn.close()
            mysql_conn.close()
            tunnel.stop()
            
    except Exception as e:
        if 'logger' in locals():
            logger.error(f"Validation failed: {e}")
        else:
            print(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()