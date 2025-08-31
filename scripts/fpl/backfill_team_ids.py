#!/usr/bin/env python3
"""
Backfill Team ID Script for Fantasy PL Scores

Populates missing team_id values in fantasy_pl_scores table by:
1. Using FPL team mappings from teams table
2. Matching players to fixtures to determine correct team
3. Handling team transfers that occurred mid-season

This script fixes the 1,533 records missing team_id values out of 2,364 total records.
"""

import sqlite3 as sql
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"backfill_team_ids_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def analyze_missing_team_ids(cursor, logger):
    """Analyze the current state of missing team_id values"""
    
    # Get overall statistics
    cursor.execute("""
        SELECT COUNT(*) as total_records, 
               COUNT(team_id) as records_with_team_id, 
               (COUNT(*) - COUNT(team_id)) as missing_team_id 
        FROM fantasy_pl_scores
    """)
    
    total, with_team_id, missing = cursor.fetchone()
    logger.info(f"Fantasy PL Scores Analysis:")
    logger.info(f"  Total records: {total:,}")
    logger.info(f"  Records with team_id: {with_team_id:,}")
    logger.info(f"  Records missing team_id: {missing:,} ({missing/total*100:.1f}%)")
    
    # Check available team mappings
    cursor.execute("""
        SELECT COUNT(*) FROM teams WHERE fpl_id IS NOT NULL
    """)
    
    team_mappings = cursor.fetchone()[0]
    logger.info(f"  Available FPL team mappings: {team_mappings}")
    
    # Check which gameweeks are affected
    cursor.execute("""
        SELECT gameweek, COUNT(*) as missing_count
        FROM fantasy_pl_scores 
        WHERE team_id IS NULL
        GROUP BY gameweek
        ORDER BY gameweek
    """)
    
    missing_by_gameweek = cursor.fetchall()
    logger.info(f"  Missing team_ids by gameweek:")
    for gw, count in missing_by_gameweek:
        logger.info(f"    GW{gw}: {count:,} records")
    
    return total, missing

def load_team_mappings(cursor, logger):
    """Load FPL team ID to database team_id mappings"""
    cursor.execute("""
        SELECT fpl_id, team_id, team_name 
        FROM teams 
        WHERE fpl_id IS NOT NULL
        ORDER BY fpl_id
    """)
    
    mappings = {}
    for fpl_id, team_id, team_name in cursor.fetchall():
        mappings[fpl_id] = {'team_id': team_id, 'name': team_name}
    
    logger.info(f"Loaded {len(mappings)} FPL team mappings:")
    for fpl_id, info in sorted(mappings.items()):
        logger.info(f"  FPL ID {fpl_id}: {info['name']} (DB team_id: {info['team_id']})")
    
    return mappings

def get_player_team_from_fixtures(cursor, player_id, gameweek, fixture_id, team_mappings, logger):
    """Determine player's team by matching fixture participants"""
    
    # Get fixture details
    cursor.execute("""
        SELECT home_teamid, away_teamid 
        FROM fixtures 
        WHERE fixture_id = ?
    """, (fixture_id,))
    
    fixture_result = cursor.fetchone()
    if not fixture_result:
        logger.warning(f"No fixture found for fixture_id {fixture_id}")
        return None
    
    home_team_id, away_team_id = fixture_result
    
    # Get FPL team IDs for these database team_ids
    reverse_team_mapping = {info['team_id']: fpl_id for fpl_id, info in team_mappings.items()}
    
    home_fpl_id = reverse_team_mapping.get(home_team_id)
    away_fpl_id = reverse_team_mapping.get(away_team_id)
    
    if not home_fpl_id or not away_fpl_id:
        logger.warning(f"Missing FPL mappings for fixture {fixture_id} teams: home={home_team_id}, away={away_team_id}")
        return None
    
    # Try to determine which team the player belongs to by checking bootstrap data
    cursor.execute("""
        SELECT team_id FROM fpl_players_bootstrap 
        WHERE player_id = ?
        ORDER BY last_updated DESC
        LIMIT 1
    """, (player_id,))
    
    bootstrap_result = cursor.fetchone()
    if bootstrap_result:
        player_fpl_team = bootstrap_result[0]
        
        # Check if player's current team matches one of the fixture teams
        if player_fpl_team == home_fpl_id:
            return home_team_id
        elif player_fpl_team == away_fpl_id:
            return away_team_id
    
    # If we can't determine from bootstrap, log the ambiguity
    logger.debug(f"Cannot determine team for player {player_id} in fixture {fixture_id} (home: {home_fpl_id}, away: {away_fpl_id})")
    return None

def backfill_team_ids_from_bootstrap(cursor, team_mappings, logger, dry_run=False):
    """Backfill team_id using current bootstrap data where available"""
    
    updated_count = 0
    
    # Get records missing team_id that have bootstrap data
    cursor.execute("""
        SELECT fps.rowid, fps.player_id, fps.gameweek, fps.player_name, fps.fixture_id,
               fpb.team_id as bootstrap_fpl_team_id
        FROM fantasy_pl_scores fps
        JOIN fpl_players_bootstrap fpb ON fps.player_id = fpb.player_id
        WHERE fps.team_id IS NULL
        ORDER BY fps.player_id, fps.gameweek
    """)
    
    records_to_update = cursor.fetchall()
    logger.info(f"Found {len(records_to_update)} records that can be updated from bootstrap data")
    
    for rowid, player_id, gameweek, player_name, fixture_id, bootstrap_fpl_team in records_to_update:
        # Map FPL team ID to database team_id
        team_info = team_mappings.get(bootstrap_fpl_team)
        
        if not team_info:
            logger.warning(f"No team mapping found for player {player_name} (ID: {player_id}) FPL team {bootstrap_fpl_team}")
            continue
        
        db_team_id = team_info['team_id']
        team_name = team_info['name']
        
        logger.debug(f"Updating player {player_name} (ID: {player_id}) GW{gameweek} -> team_id: {db_team_id} ({team_name})")
        
        if not dry_run:
            cursor.execute("""
                UPDATE fantasy_pl_scores 
                SET team_id = ? 
                WHERE rowid = ?
            """, (db_team_id, rowid))
        
        updated_count += 1
    
    logger.info(f"{'Would update' if dry_run else 'Updated'} {updated_count} records using bootstrap team data")
    return updated_count

def backfill_team_ids_from_fixtures(cursor, team_mappings, logger, dry_run=False):
    """Backfill remaining team_id values using fixture analysis"""
    
    updated_count = 0
    failed_count = 0
    
    # Get remaining records missing team_id
    cursor.execute("""
        SELECT rowid, player_id, gameweek, player_name, fixture_id
        FROM fantasy_pl_scores 
        WHERE team_id IS NULL
        ORDER BY player_id, gameweek
    """)
    
    records_to_analyze = cursor.fetchall()
    logger.info(f"Analyzing {len(records_to_analyze)} remaining records using fixture data")
    
    for rowid, player_id, gameweek, player_name, fixture_id in records_to_analyze:
        
        team_id = get_player_team_from_fixtures(cursor, player_id, gameweek, fixture_id, 
                                               team_mappings, logger)
        
        if team_id:
            team_name = next((info['name'] for info in team_mappings.values() 
                            if info['team_id'] == team_id), 'Unknown')
            
            logger.debug(f"Fixture analysis: player {player_name} (ID: {player_id}) GW{gameweek} -> team_id: {team_id} ({team_name})")
            
            if not dry_run:
                cursor.execute("""
                    UPDATE fantasy_pl_scores 
                    SET team_id = ? 
                    WHERE rowid = ?
                """, (team_id, rowid))
            
            updated_count += 1
        else:
            failed_count += 1
    
    logger.info(f"{'Would update' if dry_run else 'Updated'} {updated_count} records using fixture analysis")
    if failed_count > 0:
        logger.warning(f"Could not determine team for {failed_count} records")
    
    return updated_count

def update_last_update_table(cursor, logger):
    """Update last_update table to trigger database upload"""
    cursor.execute("""
        INSERT OR REPLACE INTO last_update (table_name, timestamp) 
        VALUES ('fantasy_pl_scores', CURRENT_TIMESTAMP)
    """)
    logger.info("Updated last_update table to trigger database upload")

def main_backfill(dry_run=False):
    """Main backfill execution function"""
    logger = setup_logging()
    logger.info("Starting FPL team_id backfill process...")
    
    if dry_run:
        logger.info("DRY RUN MODE - No database changes will be made")
    
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Analyze current state
        total_records, missing_count = analyze_missing_team_ids(cursor, logger)
        
        if missing_count == 0:
            logger.info("No missing team_id values found - backfill not needed")
            return
        
        # Load team mappings
        team_mappings = load_team_mappings(cursor, logger)
        
        if not team_mappings:
            logger.error("No FPL team mappings found - cannot proceed")
            return
        
        # Backfill using bootstrap data first (most reliable)
        logger.info("\n=== Phase 1: Backfill using bootstrap data ===")
        bootstrap_updated = backfill_team_ids_from_bootstrap(cursor, team_mappings, logger, dry_run)
        
        # Commit phase 1 updates before phase 2 (unless dry run)
        if not dry_run and bootstrap_updated > 0:
            conn.commit()
            logger.info(f"Committed {bootstrap_updated} bootstrap-based updates")
        
        # Backfill remaining using fixture analysis
        logger.info("\n=== Phase 2: Backfill using fixture analysis ===")
        fixture_updated = backfill_team_ids_from_fixtures(cursor, team_mappings, logger, dry_run)
        
        total_updated = bootstrap_updated + fixture_updated
        
        if not dry_run:
            # Update timestamp to trigger upload
            update_last_update_table(cursor, logger)
            
            # Commit changes
            conn.commit()
            logger.info("Database transaction committed successfully")
        else:
            conn.rollback()
            logger.info("DRY RUN - Transaction rolled back")
        
        # Final summary
        logger.info(f"\n=== Backfill Summary ===")
        logger.info(f"Total records processed: {missing_count:,}")
        logger.info(f"Records {'that would be ' if dry_run else ''}updated: {total_updated:,}")
        logger.info(f"Success rate: {total_updated/missing_count*100:.1f}%" if missing_count > 0 else "N/A")
        
        # Verify final state (only if not dry run)
        if not dry_run:
            final_total, final_missing = analyze_missing_team_ids(cursor, logger)
            logger.info(f"After backfill: {final_missing:,} records still missing team_id ({final_missing/final_total*100:.1f}%)")
        
        logger.info("FPL team_id backfill process completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error during backfill process: {e}")
        raise
    finally:
        conn.close()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Backfill missing team_id values in fantasy_pl_scores table')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without making database changes (shows what would happen)')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main_backfill(dry_run=args.dry_run)