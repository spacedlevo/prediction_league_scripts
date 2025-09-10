#!/usr/bin/env python3
"""
Database migration script to add totals market support to odds table.
Run this before using --include-totals flag in fetch_odds.py
"""

import sqlite3 as sql
import logging
from pathlib import Path

# Database path
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def migrate_database():
    """Apply database migration for totals support"""
    logger = setup_logging()
    logger.info("Starting database migration for totals market support...")
    
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(odds)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'total_line' in columns and 'outcome_type' in columns:
            logger.info("Totals columns already exist, no migration needed")
            return
        
        # Add new columns for totals support
        logger.info("Adding total_line column...")
        cursor.execute("ALTER TABLE odds ADD COLUMN total_line REAL DEFAULT NULL")
        
        logger.info("Adding outcome_type column...")
        cursor.execute("ALTER TABLE odds ADD COLUMN outcome_type TEXT DEFAULT NULL")
        
        # Create index for efficient totals queries
        logger.info("Creating index for totals queries...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_totals ON odds(bet_type, total_line, outcome_type)")
        
        conn.commit()
        logger.info("Database migration completed successfully")
        
        # Verify migration
        cursor.execute("PRAGMA table_info(odds)")
        columns_after = [row[1] for row in cursor.fetchall()]
        logger.info(f"Columns after migration: {', '.join(columns_after)}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()