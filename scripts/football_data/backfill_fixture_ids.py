#!/usr/bin/env python3
"""
Backfill fixture_id column in football_stats table.

This script populates the fixture_id column for all existing records in football_stats
by matching them to the fixtures table based on season, home_team_id, and away_team_id.
"""

import sqlite3 as sql
import logging
from pathlib import Path
from datetime import datetime


def setup_logging():
    """Setup logging configuration"""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_filename = log_dir / f"backfill_fixture_ids_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def convert_season_format(short_season):
    """
    Convert short season format to full format
    Examples: "25/26" -> "2025/2026", "99/00" -> "1999/2000"
    """
    if not short_season or '/' not in short_season:
        return None

    try:
        year1_short, year2_short = short_season.split('/')

        # Determine century based on first year
        year1_int = int(year1_short)
        if year1_int >= 93:  # 1993 onwards
            century = 1900
        else:
            century = 2000

        year1 = century + year1_int
        year2 = year1 + 1

        return f"{year1}/{year2}"
    except:
        return None


def backfill_fixture_ids(logger, dry_run=False):
    """Backfill fixture_id for all records in football_stats"""

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get all records without fixture_id
        cursor.execute("""
            SELECT GameID, Season, home_team_id, away_team_id, HomeTeam, AwayTeam
            FROM football_stats
            WHERE fixture_id IS NULL
            AND home_team_id IS NOT NULL
            AND away_team_id IS NOT NULL
        """)

        records_to_update = cursor.fetchall()
        logger.info(f"Found {len(records_to_update)} records without fixture_id")

        if len(records_to_update) == 0:
            logger.info("All records already have fixture_id populated")
            return True

        updated_count = 0
        not_found_count = 0

        for game_id, season_short, home_team_id, away_team_id, home_team, away_team in records_to_update:
            # Convert season format
            season_full = convert_season_format(season_short)

            if not season_full:
                logger.warning(f"Could not convert season {season_short} for GameID {game_id}")
                not_found_count += 1
                continue

            # Lookup fixture_id
            cursor.execute("""
                SELECT fixture_id
                FROM fixtures
                WHERE season = ?
                AND home_teamid = ?
                AND away_teamid = ?
            """, (season_full, home_team_id, away_team_id))

            result = cursor.fetchone()

            if result:
                fixture_id = result[0]

                if not dry_run:
                    cursor.execute("""
                        UPDATE football_stats
                        SET fixture_id = ?
                        WHERE GameID = ?
                    """, (fixture_id, game_id))

                updated_count += 1
                logger.debug(f"Updated GameID {game_id} ({home_team} vs {away_team}) with fixture_id {fixture_id}")
            else:
                not_found_count += 1
                logger.debug(f"No fixture found for GameID {game_id}: {home_team} vs {away_team} (Season: {season_full})")

            # Log progress every 100 records
            if (updated_count + not_found_count) % 100 == 0:
                logger.info(f"Progress: {updated_count + not_found_count}/{len(records_to_update)} processed")

        if dry_run:
            logger.info(f"DRY RUN - Would update {updated_count} records")
            logger.info(f"DRY RUN - {not_found_count} records would not be matched")
        else:
            conn.commit()
            logger.info(f"✅ Successfully updated {updated_count} records with fixture_id")
            logger.info(f"⚠️  {not_found_count} records could not be matched to fixtures")

            # Update last_update table
            dt = datetime.now()
            now = dt.strftime("%d-%m-%Y %H:%M:%S")
            timestamp = dt.timestamp()
            cursor.execute(
                "INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) VALUES (?, ?, ?)",
                ("football_stats", now, timestamp)
            )
            conn.commit()
            logger.info("Updated last_update table for football_stats")

        # Show statistics
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(fixture_id) as with_fixture_id
            FROM football_stats
        """)
        total, with_id = cursor.fetchone()

        logger.info(f"\nFinal statistics:")
        logger.info(f"  Total records in football_stats: {total}")
        logger.info(f"  Records with fixture_id: {with_id}")
        logger.info(f"  Records without fixture_id: {total - with_id}")

        return True

    except Exception as e:
        conn.rollback()
        logger.error(f"Backfill failed: {e}")
        return False

    finally:
        conn.close()


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Backfill fixture_id column in football_stats table')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    args = parser.parse_args()

    logger = setup_logging()

    if args.dry_run:
        logger.info("Running in DRY-RUN mode - no database changes will be made")

    logger.info("Starting fixture_id backfill...")

    success = backfill_fixture_ids(logger, args.dry_run)

    if success:
        logger.info("Backfill completed successfully")
    else:
        logger.error("Backfill failed")
        exit(1)


if __name__ == "__main__":
    main()
