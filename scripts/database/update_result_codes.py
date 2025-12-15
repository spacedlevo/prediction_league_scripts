#!/usr/bin/env python3
"""
Update Result Codes - Convert Old Format to New Format

Updates result codes in predictions and fixtures tables:
- HW (Home Win) -> H
- AW (Away Win) -> A
- D (Draw) -> D (unchanged)

FUNCTIONALITY:
- Scans predictions.predicted_result and fixtures.result columns
- Updates old format codes to new simplified format
- Provides dry-run mode to preview changes
- Transaction-safe with rollback on error
- Comprehensive logging of all changes

USAGE:
- Test mode: python update_result_codes.py --dry-run
- Live mode: python update_result_codes.py
- With logging: tail -f logs/update_result_codes_YYYYMMDD.log
"""

import sqlite3 as sql
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"update_result_codes_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_database_connection():
    """Get database connection and cursor"""
    conn = sql.connect(db_path)
    return conn, conn.cursor()

def analyze_current_values(cursor, logger):
    """Analyze current result values in both tables"""
    logger.info("Analyzing current result values...")

    # Check predictions table
    cursor.execute("""
        SELECT predicted_result, COUNT(*) as count
        FROM predictions
        WHERE predicted_result IN ('HW', 'AW', 'D', 'H', 'A')
        GROUP BY predicted_result
        ORDER BY predicted_result
    """)
    predictions_results = cursor.fetchall()

    logger.info("Current predictions.predicted_result values:")
    total_predictions_to_update = 0
    for result, count in predictions_results:
        logger.info(f"  {result}: {count} records")
        if result in ('HW', 'AW'):
            total_predictions_to_update += count

    # Check results table
    cursor.execute("""
        SELECT result, COUNT(*) as count
        FROM results
        WHERE result IN ('HW', 'AW', 'D', 'H', 'A')
        GROUP BY result
        ORDER BY result
    """)
    results_table_results = cursor.fetchall()

    logger.info("Current results.result values:")
    total_results_to_update = 0
    for result, count in results_table_results:
        logger.info(f"  {result}: {count} records")
        if result in ('HW', 'AW'):
            total_results_to_update += count

    return {
        'predictions': total_predictions_to_update,
        'results': total_results_to_update
    }

def update_predictions_table(cursor, logger, dry_run=False):
    """Update predicted_result column in predictions table"""
    updates_made = {'HW': 0, 'AW': 0}

    # Update HW -> H
    if dry_run:
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE predicted_result = 'HW'")
        hw_count = cursor.fetchone()[0]
        updates_made['HW'] = hw_count
        logger.info(f"DRY RUN: Would update {hw_count} predictions from 'HW' to 'H'")
    else:
        cursor.execute("UPDATE predictions SET predicted_result = 'H' WHERE predicted_result = 'HW'")
        updates_made['HW'] = cursor.rowcount
        if updates_made['HW'] > 0:
            logger.info(f"Updated {updates_made['HW']} predictions from 'HW' to 'H'")

    # Update AW -> A
    if dry_run:
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE predicted_result = 'AW'")
        aw_count = cursor.fetchone()[0]
        updates_made['AW'] = aw_count
        logger.info(f"DRY RUN: Would update {aw_count} predictions from 'AW' to 'A'")
    else:
        cursor.execute("UPDATE predictions SET predicted_result = 'A' WHERE predicted_result = 'AW'")
        updates_made['AW'] = cursor.rowcount
        if updates_made['AW'] > 0:
            logger.info(f"Updated {updates_made['AW']} predictions from 'AW' to 'A'")

    return updates_made


def update_results_table(cursor, logger, dry_run=False):
    """Update result column in results table"""
    updates_made = {'HW': 0, 'AW': 0}

    # Update HW -> H
    if dry_run:
        cursor.execute("SELECT COUNT(*) FROM results WHERE result = 'HW'")
        hw_count = cursor.fetchone()[0]
        updates_made['HW'] = hw_count
        logger.info(f"DRY RUN: Would update {hw_count} results from 'HW' to 'H'")
    else:
        cursor.execute("UPDATE results SET result = 'H' WHERE result = 'HW'")
        updates_made['HW'] = cursor.rowcount
        if updates_made['HW'] > 0:
            logger.info(f"Updated {updates_made['HW']} results from 'HW' to 'H'")

    # Update AW -> A
    if dry_run:
        cursor.execute("SELECT COUNT(*) FROM results WHERE result = 'AW'")
        aw_count = cursor.fetchone()[0]
        updates_made['AW'] = aw_count
        logger.info(f"DRY RUN: Would update {aw_count} results from 'AW' to 'A'")
    else:
        cursor.execute("UPDATE results SET result = 'A' WHERE result = 'AW'")
        updates_made['AW'] = cursor.rowcount
        if updates_made['AW'] > 0:
            logger.info(f"Updated {updates_made['AW']} results from 'AW' to 'A'")

    return updates_made

def update_last_update_table(cursor, logger):
    """Update the last_update table with current timestamp"""
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y %H:%M:%S")
        timestamp = dt.timestamp()

        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("predictions", now, timestamp))

        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, ("results", now, timestamp))

        logger.info("Updated last_update table for predictions and results")

    except Exception as e:
        logger.error(f"Error updating last_update table: {e}")

def main(dry_run=False):
    """Main execution function"""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Starting result code update process")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN MODE: No database changes will be made")

    try:
        # Setup database
        conn, cursor = get_database_connection()

        # Analyze current state
        analysis = analyze_current_values(cursor, logger)

        total_to_update = analysis['predictions'] + analysis['results']

        if total_to_update == 0:
            logger.info("No records found with old format codes (HW/AW)")
            logger.info("Database is already using new format (H/A/D)")
            return

        logger.info("=" * 60)
        logger.info(f"Total records to update: {total_to_update}")
        logger.info(f"  Predictions: {analysis['predictions']}")
        logger.info(f"  Results: {analysis['results']}")
        logger.info("=" * 60)

        # Update predictions table
        logger.info("Updating predictions table...")
        predictions_updates = update_predictions_table(cursor, logger, dry_run)

        # Update results table
        logger.info("Updating results table...")
        results_updates = update_results_table(cursor, logger, dry_run)

        # Calculate total updates
        total_hw_updates = predictions_updates['HW'] + results_updates['HW']
        total_aw_updates = predictions_updates['AW'] + results_updates['AW']
        total_updates = total_hw_updates + total_aw_updates

        # Commit or rollback
        if not dry_run and total_updates > 0:
            update_last_update_table(cursor, logger)
            conn.commit()
            logger.info("=" * 60)
            logger.info("Database changes committed successfully")
            logger.info(f"Total updates: {total_updates}")
            logger.info(f"  HW -> H: {total_hw_updates}")
            logger.info(f"  AW -> A: {total_aw_updates}")
            logger.info("=" * 60)
        elif dry_run:
            logger.info("=" * 60)
            logger.info("DRY RUN SUMMARY:")
            logger.info(f"Would update {total_updates} records total")
            logger.info(f"  HW -> H: {total_hw_updates}")
            logger.info(f"  AW -> A: {total_aw_updates}")
            logger.info("=" * 60)
        else:
            logger.info("No updates needed")

    except Exception as e:
        logger.error(f"Error during update process: {e}")
        if 'conn' in locals():
            conn.rollback()
            logger.error("Database changes rolled back")
        raise
    finally:
        if 'conn' in locals():
            conn.close()
        logger.info("Result code update process completed")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Update result codes from old format (HW/AW) to new format (H/A)'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main(dry_run=args.dry_run)
