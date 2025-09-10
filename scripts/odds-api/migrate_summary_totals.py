#!/usr/bin/env python3
"""
Migration script to add Over/Under 2.5 odds columns to fixture_odds_summary table.
Run this to enable enhanced predictions analysis with totals data.
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

def migrate_summary_totals():
    """Apply database migration for totals in summary table"""
    logger = setup_logging()
    logger.info("Starting fixture_odds_summary migration for totals support...")
    
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(fixture_odds_summary)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'avg_over_2_5_odds' in columns and 'avg_under_2_5_odds' in columns:
            logger.info("Totals columns already exist, checking for data updates...")
        else:
            # Add new columns for totals support
            logger.info("Adding avg_over_2_5_odds column...")
            cursor.execute("ALTER TABLE fixture_odds_summary ADD COLUMN avg_over_2_5_odds REAL DEFAULT NULL")
            
            logger.info("Adding avg_under_2_5_odds column...")
            cursor.execute("ALTER TABLE fixture_odds_summary ADD COLUMN avg_under_2_5_odds REAL DEFAULT NULL")
            
            # Create index for efficient queries
            logger.info("Creating index for totals queries...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fixture_odds_totals ON fixture_odds_summary(avg_over_2_5_odds, avg_under_2_5_odds)")
        
        # Update existing records with totals data
        logger.info("Updating fixture_odds_summary with totals data from odds table...")
        
        # Update Over 2.5 odds
        cursor.execute("""
            UPDATE fixture_odds_summary 
            SET avg_over_2_5_odds = (
                SELECT AVG(price) 
                FROM odds o 
                WHERE o.fixture_id = fixture_odds_summary.fixture_id 
                AND o.bet_type = 'over' 
                AND o.total_line = 2.5
                AND o.price IS NOT NULL
            )
            WHERE fixture_id IN (
                SELECT DISTINCT fixture_id 
                FROM odds 
                WHERE bet_type = 'over' AND total_line = 2.5
            )
        """)
        over_updated = cursor.rowcount
        logger.info(f"Updated Over 2.5 odds for {over_updated} fixtures")
        
        # Update Under 2.5 odds  
        cursor.execute("""
            UPDATE fixture_odds_summary 
            SET avg_under_2_5_odds = (
                SELECT AVG(price) 
                FROM odds o 
                WHERE o.fixture_id = fixture_odds_summary.fixture_id 
                AND o.bet_type = 'under' 
                AND o.total_line = 2.5  
                AND o.price IS NOT NULL
            )
            WHERE fixture_id IN (
                SELECT DISTINCT fixture_id 
                FROM odds 
                WHERE bet_type = 'under' AND total_line = 2.5
            )
        """)
        under_updated = cursor.rowcount
        logger.info(f"Updated Under 2.5 odds for {under_updated} fixtures")
        
        conn.commit()
        logger.info("Migration completed successfully")
        
        # Verify migration
        cursor.execute("SELECT COUNT(*) FROM fixture_odds_summary WHERE avg_over_2_5_odds IS NOT NULL")
        over_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM fixture_odds_summary WHERE avg_under_2_5_odds IS NOT NULL") 
        under_count = cursor.fetchone()[0]
        logger.info(f"Verification: {over_count} fixtures with Over 2.5 odds, {under_count} fixtures with Under 2.5 odds")
        
        # Show sample data
        cursor.execute("""
            SELECT fixture_id, avg_home_win_odds, avg_away_win_odds, avg_over_2_5_odds, avg_under_2_5_odds 
            FROM fixture_odds_summary 
            WHERE avg_over_2_5_odds IS NOT NULL 
            LIMIT 5
        """)
        samples = cursor.fetchall()
        logger.info("Sample data after migration:")
        for sample in samples:
            logger.info(f"  Fixture {sample[0]}: H{sample[1]:.2f} A{sample[2]:.2f} O2.5:{sample[3]:.2f} U2.5:{sample[4]:.2f}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_summary_totals()