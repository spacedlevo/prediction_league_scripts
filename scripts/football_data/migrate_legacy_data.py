#!/usr/bin/env python3
"""
Football-Data.co.uk Legacy Data Migration

Migrates historical match data from legacy/football_data/data/football_data.db
to the main database, including team name mapping and proper indexing.

FUNCTIONALITY:
- Migrates 12,324+ historical Premier League matches (1993-2025)
- Maps football-data team names to existing database teams
- Creates football_stats table with comprehensive match data
- Updates teams.football_data_name column for future reference
- Adds proper indexes for query performance
- Maintains transaction integrity with rollback on errors

DATA INCLUDES:
- Match results, half-time scores, referees
- Team statistics (shots, corners, cards, fouls)
- Comprehensive betting odds from multiple bookmakers
- Asian handicap and over/under markets
- 32 seasons of Premier League history
"""

import sqlite3 as sql
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Configuration
CURRENT_SEASON = "2025/2026"

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
football_data_path = Path(__file__).parent.parent.parent / "legacy" / "football_data" / "data" / "football_data.db"
log_dir = Path(__file__).parent.parent.parent / "logs"

# Create directories
log_dir.mkdir(exist_ok=True)

def setup_logging():
    """Setup logging configuration"""
    log_filename = log_dir / f"migrate_football_data_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def create_team_name_mapping():
    """Create mapping from football-data team names to database team names"""
    return {
        # Current Premier League teams
        "Arsenal": "arsenal",
        "Aston Villa": "aston villa", 
        "Bournemouth": "bournemouth",
        "Brentford": "brentford",
        "Brighton": "brighton",
        "Burnley": "burnley",
        "Chelsea": "chelsea",
        "Crystal Palace": "crystal palace",
        "Everton": "everton",
        "Fulham": "fulham",
        "Ipswich": "ipswich",
        "Leicester": "leicester",
        "Liverpool": "liverpool",
        "Luton": "luton",
        "Man City": "man city",
        "Man United": "man utd",
        "Newcastle": "newcastle",
        "Nott'm Forest": "nott'm forest",
        "Southampton": "southampton",
        "Tottenham": "spurs",  # Database has both spurs and tottenham entries
        "West Ham": "west ham",
        "Wolves": "wolves",
        
        # Teams that were in database already
        "Leeds": "leeds",
        "Norwich": "norwich", 
        "Sheffield United": "sheffield utd",
        "Sunderland": "sunderland",
        "Watford": "watford",
        
        # Historical Premier League teams (1993-2025) - Added to database
        "Barnsley": "barnsley",
        "Birmingham": "birmingham city",
        "Blackburn": "blackburn rovers",
        "Blackpool": "blackpool", 
        "Bolton": "bolton wanderers",
        "Bradford": "bradford city",
        "Cardiff": "cardiff city",
        "Charlton": "charlton athletic",
        "Coventry": "coventry city",
        "Derby": "derby county",
        "Huddersfield": "huddersfield town",
        "Hull": "hull city",
        "Middlesbrough": "middlesbrough",
        "Oldham": "oldham athletic",
        "Portsmouth": "portsmouth",
        "QPR": "queens park rangers", 
        "Reading": "reading",
        "Sheffield Weds": "sheffield wednesday",
        "Stoke": "stoke city",
        "Swansea": "swansea city",
        "Swindon": "swindon town",
        "West Brom": "west bromwich albion",
        "Wigan": "wigan athletic",
        "Wimbledon": "wimbledon"
    }

def update_teams_mapping(cursor, team_mapping, logger):
    """Update teams table with football_data_name mappings"""
    logger.info("Updating teams table with football-data name mappings...")
    
    updated_count = 0
    for fd_name, db_name in team_mapping.items():
        # Find matching team in database
        cursor.execute("SELECT team_id FROM teams WHERE LOWER(team_name) = LOWER(?)", (db_name,))
        result = cursor.fetchone()
        
        if result:
            team_id = result[0]
            cursor.execute(
                "UPDATE teams SET football_data_name = ? WHERE team_id = ?",
                (fd_name, team_id)
            )
            updated_count += 1
            logger.info(f"Mapped '{fd_name}' → '{db_name}' (team_id: {team_id})")
        else:
            logger.warning(f"No database team found for football-data team: '{fd_name}' → '{db_name}'")
    
    logger.info(f"Updated football_data_name for {updated_count} teams")

def create_football_stats_table(cursor, source_cursor, logger):
    """Create football_stats table in main database with same structure as source"""
    logger.info("Creating football_stats table...")
    
    cursor.execute("DROP TABLE IF EXISTS football_stats")
    
    # Get source table structure and recreate it
    source_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='football_stats'")
    source_schema = source_cursor.fetchone()[0]
    
    # Modify schema to add our additional columns
    modified_schema = source_schema.replace(
        '"BFECAHA" REAL',
        '"BFECAHA" REAL, home_team_id INTEGER, away_team_id INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP'
    )
    
    # Add foreign key constraints
    modified_schema = modified_schema.rstrip(')')
    modified_schema += """,
        FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
        FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
    )"""
    
    cursor.execute(modified_schema)
    logger.info("Football_stats table created successfully")

def migrate_data(cursor, source_cursor, team_mapping, logger):
    """Migrate data from source database to main database"""
    logger.info("Starting data migration...")
    
    source_cursor.execute("SELECT COUNT(*) FROM football_stats")
    total_rows = source_cursor.fetchone()[0]
    logger.info(f"Migrating {total_rows} matches...")
    
    # Get all team IDs for mapping
    cursor.execute("SELECT team_name, team_id FROM teams")
    team_id_map = {name.lower(): team_id for name, team_id in cursor.fetchall()}
    
    source_cursor.execute("SELECT * FROM football_stats ORDER BY GameID")
    
    migrated_count = 0
    skipped_count = 0
    
    for row in source_cursor.fetchall():
        game_id, date, home_team, away_team = row[:4]
        
        # Map team names to IDs
        home_team_mapped = team_mapping.get(home_team, home_team).lower()
        away_team_mapped = team_mapping.get(away_team, away_team).lower()
        
        home_team_id = team_id_map.get(home_team_mapped)
        away_team_id = team_id_map.get(away_team_mapped)
        
        if not home_team_id or not away_team_id:
            logger.warning(f"Skipping match {game_id}: {home_team} vs {away_team} - team mapping failed")
            skipped_count += 1
            continue
        
        # Insert with team IDs and timestamp
        row_with_ids = list(row) + [home_team_id, away_team_id, None]  # None for created_at (uses DEFAULT)
        
        placeholders = "?" + ",?" * (len(row_with_ids) - 1)
        cursor.execute(f"INSERT INTO football_stats VALUES ({placeholders})", row_with_ids)
        
        migrated_count += 1
        
        if migrated_count % 1000 == 0:
            logger.info(f"Migrated {migrated_count}/{total_rows} matches...")
    
    logger.info(f"Migration completed: {migrated_count} matches migrated, {skipped_count} skipped")

def create_indexes(cursor, logger):
    """Create indexes for optimal query performance"""
    logger.info("Creating indexes...")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_football_stats_season ON football_stats(Season)",
        "CREATE INDEX IF NOT EXISTS idx_football_stats_date ON football_stats(Date)",
        "CREATE INDEX IF NOT EXISTS idx_football_stats_home_team ON football_stats(home_team_id)",
        "CREATE INDEX IF NOT EXISTS idx_football_stats_away_team ON football_stats(away_team_id)",
        "CREATE INDEX IF NOT EXISTS idx_football_stats_teams ON football_stats(home_team_id, away_team_id)",
        "CREATE INDEX IF NOT EXISTS idx_football_stats_result ON football_stats(FTR)"
    ]
    
    for index_sql in indexes:
        cursor.execute(index_sql)
        logger.info(f"Created index: {index_sql.split('idx_')[1].split(' ')[0]}")

def update_last_update_table(cursor, logger):
    """Update last_update table to track this migration"""
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y %H:%M:%S")
    timestamp = dt.timestamp()
    cursor.execute(
        "INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) VALUES (?, ?, ?)",
        ("football_stats", now, timestamp)
    )
    logger.info("Updated last_update table")

def main_migration(args, logger):
    """Main migration logic"""
    logger.info("Starting football-data.co.uk legacy data migration...")
    
    if not football_data_path.exists():
        logger.error(f"Source database not found: {football_data_path}")
        return False
    
    # Connect to both databases
    main_conn = sql.connect(db_path)
    source_conn = sql.connect(football_data_path)
    
    try:
        main_cursor = main_conn.cursor()
        source_cursor = source_conn.cursor()
        
        # Check if football_stats already exists
        main_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='football_stats'")
        if main_cursor.fetchone() and not args.force:
            logger.error("football_stats table already exists. Use --force to recreate.")
            return False
        
        team_mapping = create_team_name_mapping()
        
        # Perform migration steps
        update_teams_mapping(main_cursor, team_mapping, logger)
        create_football_stats_table(main_cursor, source_cursor, logger)
        migrate_data(main_cursor, source_cursor, team_mapping, logger)
        create_indexes(main_cursor, logger)
        update_last_update_table(main_cursor, logger)
        
        # Commit all changes
        main_conn.commit()
        
        # Verify migration
        main_cursor.execute("SELECT COUNT(*) FROM football_stats")
        final_count = main_cursor.fetchone()[0]
        
        main_cursor.execute("SELECT COUNT(DISTINCT Season) FROM football_stats")
        season_count = main_cursor.fetchone()[0]
        
        logger.info(f"Migration completed successfully!")
        logger.info(f"Total matches: {final_count}")
        logger.info(f"Seasons covered: {season_count}")
        
        return True
        
    except Exception as e:
        main_conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False
        
    finally:
        main_conn.close()
        source_conn.close()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Migrate football-data.co.uk legacy data to main database')
    parser.add_argument('--force', action='store_true',
                       help='Force recreation of football_stats table if it exists')
    parser.add_argument('--test', action='store_true',
                       help='Run in test mode with detailed output')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    
    if args.test:
        logger.info("Running in test mode...")
        logger.setLevel(logging.DEBUG)
    
    success = main_migration(args, logger)
    
    if success:
        logger.info("Football-data migration completed successfully")
    else:
        logger.error("Football-data migration failed")
        exit(1)