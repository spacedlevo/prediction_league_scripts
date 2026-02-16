#!/usr/bin/env python3
"""
Migration: Add FPL team picks tables and season column to fantasy_pl_scores.

Creates:
- fpl_team_picks: Stores team squad picks per gameweek
- fpl_team_gameweek_summary: Stores gameweek-level manager stats (rank, points, transfers)

Modifies:
- fantasy_pl_scores: Adds season column, backfills existing rows with current season

Safe to run multiple times (idempotent).
"""

import sqlite3 as sql
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scripts.config import CURRENT_SEASON

db_path = Path(__file__).parent.parent.parent.parent / "data" / "database.db"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def run_migration(logger, dry_run=False):
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Create fpl_team_picks table
        logger.info("Creating fpl_team_picks table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fpl_team_picks (
                season TEXT NOT NULL,
                gameweek INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                is_captain BOOLEAN DEFAULT 0,
                is_vice_captain BOOLEAN DEFAULT 0,
                multiplier INTEGER DEFAULT 1,
                PRIMARY KEY (season, gameweek, player_id)
            )
        """)
        logger.info("fpl_team_picks table ready")

        # 2. Create fpl_team_gameweek_summary table
        logger.info("Creating fpl_team_gameweek_summary table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fpl_team_gameweek_summary (
                season TEXT NOT NULL,
                gameweek INTEGER NOT NULL,
                total_points INTEGER,
                gameweek_rank INTEGER,
                overall_rank INTEGER,
                bank INTEGER,
                squad_value INTEGER,
                points_on_bench INTEGER,
                transfers_made INTEGER,
                transfers_cost INTEGER,
                chip_used TEXT,
                PRIMARY KEY (season, gameweek)
            )
        """)
        logger.info("fpl_team_gameweek_summary table ready")

        # 3. Add season column to fantasy_pl_scores if it doesn't exist
        logger.info("Checking fantasy_pl_scores for season column...")
        cursor.execute("PRAGMA table_info(fantasy_pl_scores)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'season' not in columns:
            logger.info("Adding season column to fantasy_pl_scores...")
            cursor.execute(f"ALTER TABLE fantasy_pl_scores ADD COLUMN season TEXT DEFAULT '{CURRENT_SEASON}'")

            # Backfill existing rows
            cursor.execute("SELECT COUNT(*) FROM fantasy_pl_scores WHERE season IS NULL OR season = ''")
            null_count = cursor.fetchone()[0]
            if null_count > 0:
                logger.info(f"Backfilling {null_count} rows with season '{CURRENT_SEASON}'...")
                cursor.execute("UPDATE fantasy_pl_scores SET season = ? WHERE season IS NULL OR season = ''",
                               (CURRENT_SEASON,))
        else:
            logger.info("season column already exists on fantasy_pl_scores")

        # 4. Create index for season-aware queries
        logger.info("Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_player_scores_season_player_gw
            ON fantasy_pl_scores(season, player_id, gameweek)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fpl_picks_season_gw
            ON fpl_team_picks(season, gameweek)
        """)

        if dry_run:
            conn.rollback()
            logger.info("DRY RUN - rolled back all changes")
        else:
            conn.commit()
            logger.info("Migration completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Add FPL picks tables and season column')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    run_migration(logger, dry_run=args.dry_run)
