#!/usr/bin/env python3
"""
Normalize duplicate team entries in the database.

This script merges duplicate team entries for Tottenham (6→25) and Wolves (23→20),
ensuring a single canonical team_id for each team across all tables.

Usage:
    python normalize_team_ids.py --dry-run  # Preview changes
    python normalize_team_ids.py            # Execute migration
"""

import sqlite3 as sql
import logging
import shutil
from pathlib import Path
from datetime import datetime
import argparse


def setup_logging():
    """Setup logging configuration"""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_filename = log_dir / f"normalize_team_ids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def create_backup(db_path, logger):
    """Create a backup of the database before migration"""
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f"database_before_team_normalization_{timestamp}.db"

    logger.info(f"Creating backup at {backup_path}")
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ Backup created successfully")

    return backup_path


def analyze_current_state(cursor, logger):
    """Analyze current state of duplicate team entries"""
    logger.info("\n" + "="*80)
    logger.info("CURRENT STATE ANALYSIS")
    logger.info("="*80)

    teams_to_merge = [
        (6, 25, "Tottenham"),
        (23, 20, "Wolves")
    ]

    analysis = {}

    for old_id, new_id, team_name in teams_to_merge:
        logger.info(f"\n{team_name} - Merging team_id {old_id} → {new_id}")
        logger.info("-" * 40)

        # Get team names
        cursor.execute("SELECT team_name, football_data_name FROM teams WHERE team_id = ?", (old_id,))
        old_data = cursor.fetchone()
        cursor.execute("SELECT team_name, football_data_name FROM teams WHERE team_id = ?", (new_id,))
        new_data = cursor.fetchone()

        logger.info(f"  OLD (id {old_id}): {old_data[0]} (fd_name: {old_data[1]})")
        logger.info(f"  NEW (id {new_id}): {new_data[0]} (fd_name: {new_data[1]})")

        # Count fixtures
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures
            WHERE home_teamid = ? OR away_teamid = ?
        """, (old_id, old_id))
        old_fixtures = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM fixtures
            WHERE home_teamid = ? OR away_teamid = ?
        """, (new_id, new_id))
        new_fixtures = cursor.fetchone()[0]

        logger.info(f"  Fixtures: {old_fixtures} (old) + {new_fixtures} (new) = {old_fixtures + new_fixtures} (total)")

        # Count football_stats
        cursor.execute("""
            SELECT COUNT(*) FROM football_stats
            WHERE home_team_id = ? OR away_team_id = ?
        """, (old_id, old_id))
        old_stats = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM football_stats
            WHERE home_team_id = ? OR away_team_id = ?
        """, (new_id, new_id))
        new_stats = cursor.fetchone()[0]

        logger.info(f"  Football_stats: {old_stats} (old) + {new_stats} (new) = {old_stats + new_stats} (total)")

        # Count predictions (via fixtures)
        cursor.execute("""
            SELECT COUNT(*) FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.fixture_id
            WHERE f.home_teamid = ? OR f.away_teamid = ?
        """, (old_id, old_id))
        old_predictions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.fixture_id
            WHERE f.home_teamid = ? OR f.away_teamid = ?
        """, (new_id, new_id))
        new_predictions = cursor.fetchone()[0]

        logger.info(f"  Predictions: {old_predictions} (old) + {new_predictions} (new) = {old_predictions + new_predictions} (total)")

        analysis[team_name] = {
            'old_id': old_id,
            'new_id': new_id,
            'old_fixtures': old_fixtures,
            'new_fixtures': new_fixtures,
            'old_stats': old_stats,
            'new_stats': new_stats
        }

    return analysis


def migrate_team_ids(cursor, logger, dry_run=False):
    """Migrate duplicate team IDs to canonical IDs"""

    logger.info("\n" + "="*80)
    logger.info("MIGRATION STEPS")
    logger.info("="*80)

    migrations = [
        (6, 25, "Tottenham"),
        (23, 20, "Wolves")
    ]

    for old_id, new_id, team_name in migrations:
        logger.info(f"\n📝 Migrating {team_name}: team_id {old_id} → {new_id}")
        logger.info("-" * 40)

        # Update fixtures - home_teamid
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures WHERE home_teamid = ?
        """, (old_id,))
        home_count = cursor.fetchone()[0]

        if home_count > 0:
            logger.info(f"  Updating {home_count} fixtures where home_teamid = {old_id}")
            if not dry_run:
                cursor.execute("""
                    UPDATE fixtures SET home_teamid = ? WHERE home_teamid = ?
                """, (new_id, old_id))

        # Update fixtures - away_teamid
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures WHERE away_teamid = ?
        """, (old_id,))
        away_count = cursor.fetchone()[0]

        if away_count > 0:
            logger.info(f"  Updating {away_count} fixtures where away_teamid = {old_id}")
            if not dry_run:
                cursor.execute("""
                    UPDATE fixtures SET away_teamid = ? WHERE away_teamid = ?
                """, (new_id, old_id))

        # Update football_stats - home_team_id
        cursor.execute("""
            SELECT COUNT(*) FROM football_stats WHERE home_team_id = ?
        """, (old_id,))
        home_stats_count = cursor.fetchone()[0]

        if home_stats_count > 0:
            logger.info(f"  Updating {home_stats_count} football_stats where home_team_id = {old_id}")
            if not dry_run:
                cursor.execute("""
                    UPDATE football_stats SET home_team_id = ? WHERE home_team_id = ?
                """, (new_id, old_id))

        # Update football_stats - away_team_id
        cursor.execute("""
            SELECT COUNT(*) FROM football_stats WHERE away_team_id = ?
        """, (old_id,))
        away_stats_count = cursor.fetchone()[0]

        if away_stats_count > 0:
            logger.info(f"  Updating {away_stats_count} football_stats where away_team_id = {old_id}")
            if not dry_run:
                cursor.execute("""
                    UPDATE football_stats SET away_team_id = ? WHERE away_team_id = ?
                """, (new_id, old_id))

        # Update teams table metadata for canonical entry
        canonical_name = "tottenham" if team_name == "Tottenham" else "wolves"
        canonical_fd_name = "Tottenham" if team_name == "Tottenham" else "Wolves"

        logger.info(f"  Updating teams table for canonical entry (team_id {new_id})")
        if not dry_run:
            cursor.execute("""
                UPDATE teams
                SET team_name = ?,
                    football_data_name = ?
                WHERE team_id = ?
            """, (canonical_name, canonical_fd_name, new_id))

        # Delete duplicate entry
        logger.info(f"  Deleting duplicate team entry (team_id {old_id})")
        if not dry_run:
            cursor.execute("DELETE FROM teams WHERE team_id = ?", (old_id,))

        logger.info(f"  ✅ {team_name} migration {'would be' if dry_run else 'completed'}")


def verify_migration(cursor, logger):
    """Verify migration was successful"""
    logger.info("\n" + "="*80)
    logger.info("VERIFICATION")
    logger.info("="*80)

    # Check duplicate IDs no longer exist
    cursor.execute("SELECT COUNT(*) FROM teams WHERE team_id IN (6, 23)")
    duplicate_count = cursor.fetchone()[0]

    if duplicate_count == 0:
        logger.info("✅ Duplicate team entries (6, 23) successfully removed")
    else:
        logger.error(f"❌ Found {duplicate_count} duplicate entries still in teams table!")
        return False

    # Check canonical IDs exist
    cursor.execute("SELECT COUNT(*) FROM teams WHERE team_id IN (20, 25)")
    canonical_count = cursor.fetchone()[0]

    if canonical_count == 2:
        logger.info("✅ Canonical team entries (20, 25) exist")
    else:
        logger.error(f"❌ Expected 2 canonical entries, found {canonical_count}!")
        return False

    # Check no fixtures reference old IDs
    cursor.execute("""
        SELECT COUNT(*) FROM fixtures
        WHERE home_teamid IN (6, 23) OR away_teamid IN (6, 23)
    """)
    old_fixture_refs = cursor.fetchone()[0]

    if old_fixture_refs == 0:
        logger.info("✅ No fixtures reference old team IDs")
    else:
        logger.error(f"❌ Found {old_fixture_refs} fixtures still referencing old team IDs!")
        return False

    # Check no football_stats reference old IDs
    cursor.execute("""
        SELECT COUNT(*) FROM football_stats
        WHERE home_team_id IN (6, 23) OR away_team_id IN (6, 23)
    """)
    old_stats_refs = cursor.fetchone()[0]

    if old_stats_refs == 0:
        logger.info("✅ No football_stats reference old team IDs")
    else:
        logger.error(f"❌ Found {old_stats_refs} football_stats still referencing old team IDs!")
        return False

    # Show final counts for canonical IDs
    logger.info("\n📊 Final counts for canonical team IDs:")

    for team_id, team_name in [(25, "Tottenham"), (20, "Wolves")]:
        cursor.execute("SELECT team_name, football_data_name FROM teams WHERE team_id = ?", (team_id,))
        db_name, fd_name = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) FROM fixtures
            WHERE home_teamid = ? OR away_teamid = ?
        """, (team_id, team_id))
        fixtures = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM football_stats
            WHERE home_team_id = ? OR away_team_id = ?
        """, (team_id, team_id))
        stats = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.fixture_id
            WHERE f.home_teamid = ? OR f.away_teamid = ?
        """, (team_id, team_id))
        predictions = cursor.fetchone()[0]

        logger.info(f"\n  team_id {team_id}: {db_name} (fd_name: {fd_name})")
        logger.info(f"    Fixtures: {fixtures}")
        logger.info(f"    Football_stats: {stats}")
        logger.info(f"    Predictions: {predictions}")

    return True


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Normalize duplicate team entries in database'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying database')
    args = parser.parse_args()

    logger = setup_logging()

    if args.dry_run:
        logger.info("🔍 DRY-RUN MODE - No changes will be made")
    else:
        logger.info("⚠️  LIVE MODE - Database will be modified")

    logger.info("\n" + "="*80)
    logger.info("DATABASE TEAM ID NORMALIZATION")
    logger.info("="*80)
    logger.info("This script will merge duplicate team entries:")
    logger.info("  • Tottenham: team_id 6 → 25")
    logger.info("  • Wolves: team_id 23 → 20")
    logger.info("="*80)

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return 1

    # Create backup (even for dry-run, good practice)
    if not args.dry_run:
        backup_path = create_backup(db_path, logger)
        logger.info(f"📦 Backup saved to: {backup_path}")

    # Connect to database
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Analyze current state
        analysis = analyze_current_state(cursor, logger)

        # Perform migration
        migrate_team_ids(cursor, logger, args.dry_run)

        if args.dry_run:
            logger.info("\n" + "="*80)
            logger.info("DRY-RUN COMPLETE")
            logger.info("="*80)
            logger.info("Run without --dry-run to execute migration")
        else:
            # Verify migration
            if verify_migration(cursor, logger):
                # Update last_update table
                dt = datetime.now()
                now = dt.strftime("%d-%m-%Y %H:%M:%S")
                timestamp = dt.timestamp()
                cursor.execute(
                    "INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) VALUES (?, ?, ?)",
                    ("teams", now, timestamp)
                )

                conn.commit()
                logger.info("\n" + "="*80)
                logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
                logger.info("="*80)
                logger.info("Database has been normalized:")
                logger.info("  • All fixtures now use canonical team IDs")
                logger.info("  • Duplicate team entries removed")
                logger.info("  • Teams table updated with canonical names")
                logger.info(f"  • Backup available at: {backup_path}")
            else:
                conn.rollback()
                logger.error("\n❌ MIGRATION FAILED - Rolling back changes")
                return 1

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed with error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
