#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script

Migrates data from SQLite database to PostgreSQL database.
Handles schema creation and data transfer for all tables.
"""

import sqlite3
import psycopg2
import json
import argparse
import logging
import os
import sys
from pathlib import Path
from contextlib import contextmanager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_postgres_connection():
    """Get PostgreSQL connection using environment variables"""
    try:
        return psycopg2.connect(
            host=os.environ.get('POSTGRES_HOST', 'localhost'),
            port=os.environ.get('POSTGRES_PORT', '5432'),
            database=os.environ.get('POSTGRES_DB', 'prediction_league'),
            user=os.environ.get('POSTGRES_USER', 'postgres'),
            password=os.environ.get('POSTGRES_PASSWORD')
        )
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

@contextmanager
def database_connections(sqlite_path):
    """Context manager for database connections"""
    sqlite_conn = None
    postgres_conn = None
    
    try:
        # SQLite connection
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        
        # PostgreSQL connection
        postgres_conn = get_postgres_connection()
        postgres_conn.autocommit = False
        
        yield sqlite_conn, postgres_conn
        
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        if postgres_conn:
            postgres_conn.close()

def create_postgres_schema(pg_cursor):
    """Create PostgreSQL schema matching SQLite structure"""
    logger.info("Creating PostgreSQL schema...")
    
    schema_sql = """
    -- Create tables in dependency order
    
    CREATE TABLE IF NOT EXISTS teams (
        team_id SERIAL PRIMARY KEY,
        fpl_id INTEGER,
        team_name TEXT,
        available BOOLEAN DEFAULT FALSE,
        strength INTEGER,
        strength_overall_home INTEGER,
        strength_overall_away INTEGER,
        strength_attack_home INTEGER,
        strength_attack_away INTEGER,
        strength_defence_home INTEGER,
        strength_defence_away INTEGER,
        pulse_id INTEGER,
        football_data_name TEXT,
        odds_api_name TEXT
    );

    CREATE TABLE IF NOT EXISTS bookmakers (
        bookmaker_id SERIAL PRIMARY KEY,
        bookmaker_name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS gameweeks (
        gameweek INTEGER PRIMARY KEY,
        deadline_dttm TIMESTAMP,
        deadline_date DATE,
        deadline_time TIME,
        current_gameweek BOOLEAN,
        next_gameweek BOOLEAN,
        finished BOOLEAN
    );

    CREATE TABLE IF NOT EXISTS fixtures (
        fpl_fixture_id INTEGER NOT NULL,
        fixture_id SERIAL PRIMARY KEY,
        kickoff_dttm TIMESTAMP,
        home_teamid INTEGER NOT NULL,
        away_teamid INTEGER NOT NULL,
        finished BOOLEAN DEFAULT TRUE,
        season TEXT,
        home_win_odds REAL,
        draw_odds REAL,
        away_win_odds REAL,
        pulse_id INTEGER,
        gameweek INTEGER,
        started BOOLEAN DEFAULT FALSE,
        provisional_finished BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
        FOREIGN KEY (away_teamid) REFERENCES teams(team_id)
    );

    CREATE TABLE IF NOT EXISTS odds (
        odd_id SERIAL PRIMARY KEY,
        match_id TEXT NOT NULL,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        bet_type TEXT NOT NULL,
        fixture_id INTEGER,
        bookmaker_id INTEGER NOT NULL,
        price REAL,
        total_line REAL,
        outcome_type TEXT,
        FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
        FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
        FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
    );

    CREATE TABLE IF NOT EXISTS fixture_odds_summary (
        fixture_id INTEGER PRIMARY KEY,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        avg_home_win_odds REAL,
        avg_draw_odds REAL,
        avg_away_win_odds REAL,
        bookmaker_count INTEGER,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        avg_over_2_5_odds REAL,
        avg_under_2_5_odds REAL,
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
        FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
        FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
    );

    CREATE TABLE IF NOT EXISTS fantasy_pl_scores (
        player_name TEXT,
        gameweek INTEGER,
        player_id INTEGER,
        total_points INTEGER,
        fixture_id INTEGER,
        team_id INTEGER,
        was_home BOOLEAN,
        minutes INTEGER,
        goals_scored INTEGER,
        assists INTEGER,
        clean_sheets INTEGER,
        goals_conceded INTEGER,
        own_goals INTEGER,
        penalties_saved INTEGER,
        penalties_missed INTEGER,
        yellow_cards INTEGER,
        red_cards INTEGER,
        saves INTEGER,
        bonus INTEGER,
        bps INTEGER,
        influence REAL,
        creativity REAL,
        threat REAL,
        ict_index REAL,
        starts INTEGER,
        expected_goals REAL,
        expected_assists REAL,
        expected_goal_involvements REAL,
        expected_goals_conceded REAL,
        value INTEGER,
        transfers_balance INTEGER,
        selected INTEGER,
        transfers_in INTEGER,
        transfers_out INTEGER,
        loaned_in INTEGER,
        loaned_out INTEGER,
        season TEXT DEFAULT '2025/2026',
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );

    CREATE TABLE IF NOT EXISTS fpl_players_bootstrap (
        player_id INTEGER PRIMARY KEY,
        player_name TEXT NOT NULL,
        team_id INTEGER,
        db_team_id INTEGER,
        position TEXT,
        minutes INTEGER,
        total_points INTEGER,
        ict_index REAL,
        goals_scored INTEGER,
        assists INTEGER,
        clean_sheets INTEGER,
        saves INTEGER,
        yellow_cards INTEGER,
        red_cards INTEGER,
        bonus INTEGER,
        bps INTEGER,
        influence REAL,
        creativity REAL,
        threat REAL,
        starts INTEGER,
        expected_goals REAL,
        expected_assists REAL,
        value INTEGER,
        transfers_in INTEGER,
        transfers_out INTEGER,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        season TEXT DEFAULT '2025/2026',
        FOREIGN KEY (db_team_id) REFERENCES teams(team_id)
    );

    CREATE TABLE IF NOT EXISTS fpl_team_picks (
        season TEXT NOT NULL,
        gameweek INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        is_captain BOOLEAN DEFAULT FALSE,
        is_vice_captain BOOLEAN DEFAULT FALSE,
        multiplier INTEGER DEFAULT 1,
        PRIMARY KEY (season, gameweek, player_id)
    );

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
    );

    CREATE TABLE IF NOT EXISTS players (
        player_id INTEGER PRIMARY KEY,
        player_name TEXT,
        paid INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 0,
        mini_league INTEGER NOT NULL DEFAULT 0,
        mini_league_paid INTEGER NOT NULL DEFAULT 0,
        pundit INTEGER NOT NULL DEFAULT 0,
        web_name TEXT
    );

    CREATE TABLE IF NOT EXISTS results (
        result_id SERIAL PRIMARY KEY,
        fpl_fixture_id INTEGER NOT NULL,
        fixture_id INTEGER,
        home_goals INTEGER,
        away_goals INTEGER,
        result TEXT,
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    );

    CREATE TABLE IF NOT EXISTS predictions (
        prediction_id SERIAL PRIMARY KEY,
        player_id INTEGER NOT NULL,
        fixture_id INTEGER NOT NULL,
        fpl_fixture_id INTEGER,
        home_goals INTEGER NOT NULL,
        away_goals INTEGER NOT NULL,
        predicted_result TEXT NOT NULL,
        FOREIGN KEY (player_id) REFERENCES players(player_id),
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    );

    CREATE TABLE IF NOT EXISTS gameweek_cache (
        current_gw INTEGER PRIMARY KEY,
        next_gw_deadline_time TEXT
    );

    CREATE TABLE IF NOT EXISTS last_update (
        table_name TEXT PRIMARY KEY,
        updated TEXT,
        timestamp NUMERIC
    );

    CREATE TABLE IF NOT EXISTS file_metadata (
        filename TEXT PRIMARY KEY,
        last_modified TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS match_officials (
        id SERIAL PRIMARY KEY,
        matchOfficialID INTEGER NOT NULL,
        pulseid INTEGER NOT NULL,
        name TEXT NOT NULL,
        role TEXT
    );

    CREATE TABLE IF NOT EXISTS team_list (
        id SERIAL PRIMARY KEY,
        pulseid INTEGER NOT NULL,
        team_id INTEGER,
        person_id INTEGER,
        player_name TEXT NOT NULL,
        match_shirt_number INTEGER,
        is_captain BOOLEAN,
        position TEXT NOT NULL,
        is_starting BOOLEAN,
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );

    CREATE TABLE IF NOT EXISTS match_events (
        id SERIAL PRIMARY KEY,
        pulseid INTEGER NOT NULL,
        person_id INTEGER,
        team_id INTEGER,
        assist_id INTEGER,
        event_type TEXT NOT NULL,
        event_time TEXT NOT NULL
    );
    """
    
    try:
        pg_cursor.execute(schema_sql)
        logger.info("PostgreSQL schema created successfully")
    except psycopg2.Error as e:
        logger.error(f"Error creating PostgreSQL schema: {e}")
        raise

def get_table_names(sqlite_cursor):
    """Get list of tables from SQLite database"""
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in sqlite_cursor.fetchall()]

def inspect_sqlite_table(sqlite_cursor, table_name):
    """Get actual column information from SQLite table"""
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns = sqlite_cursor.fetchall()
    return [(col[1], col[2]) for col in columns]  # (name, type)

def get_boolean_columns(table_name):
    """Get list of boolean columns that need conversion from integer"""
    boolean_columns = {
        'teams': ['available'],
        'gameweeks': ['current_gameweek', 'next_gameweek', 'finished'],
        'fixtures': ['finished', 'started', 'provisional_finished'],
        'fantasy_pl_scores': ['was_home'],
        'fpl_team_picks': ['is_captain', 'is_vice_captain'],
        'players': ['paid', 'active', 'mini_league', 'mini_league_paid', 'pundit'],
        'team_list': ['is_captain', 'is_starting'],
    }
    return boolean_columns.get(table_name, [])

def convert_boolean_value(value, target_is_boolean=True):
    """Convert SQLite integer boolean to PostgreSQL boolean or keep as integer"""
    if value is None:
        return None
    if target_is_boolean:
        return bool(value)
    else:
        # Keep as integer (0/1) if target column is INTEGER
        return int(value) if value is not None else None

def sqlite_to_postgres_type(sqlite_type):
    """Convert SQLite data type to PostgreSQL type"""
    type_mapping = {
        'INTEGER': 'INTEGER',
        'TEXT': 'TEXT',
        'REAL': 'REAL',
        'BOOLEAN': 'BOOLEAN',
        'DATETIME': 'TIMESTAMP',
        'DATE': 'DATE',
        'TIME': 'TIME',
        'TIMESTAMP': 'TIMESTAMP',
        'NUMERIC': 'NUMERIC',
        '': 'INTEGER'  # SQLite empty type defaults to INTEGER
    }
    return type_mapping.get(sqlite_type.upper(), 'TEXT')

def escape_column_name(col_name):
    """Escape PostgreSQL reserved keywords and special characters"""
    reserved_keywords = {
        'as', 'order', 'group', 'having', 'where', 'select', 'from', 'join',
        'inner', 'outer', 'left', 'right', 'on', 'using', 'union', 'intersect',
        'except', 'all', 'distinct', 'case', 'when', 'then', 'else', 'end',
        'and', 'or', 'not', 'in', 'between', 'like', 'exists', 'null', 'true', 'false'
    }
    
    # Always quote column names with special characters, starting with numbers, or Unicode
    if (col_name.lower() in reserved_keywords or 
        any(char in col_name for char in ['>', '<', '.', ' ', '-', '+', '*', '/', '(', ')', '[', ']', '?', '!', '&', '|', '^', '%', '$', '#', '@', '`', '~', ':', ';', ',', '{', '}', '=', "'", '"']) or
        col_name[0].isdigit() or
        any(ord(char) > 127 for char in col_name)):  # Unicode characters
        return f'"{col_name}"'
    return col_name

def identify_primary_key(table_name, columns):
    """Identify the primary key column for a table"""
    
    # Table-specific primary key rules
    pk_rules = {
        'teams': 'team_id',
        'fixtures': 'fixture_id', 
        'odds': 'odd_id',
        'results': 'result_id',
        'predictions': 'prediction_id',
        'bookmakers': 'bookmaker_id',
        'players': 'player_id',
        'gameweeks': 'gameweek',
        'gameweek_cache': 'current_gw',
        'last_update': 'table_name',
        'file_metadata': 'filename'
    }
    
    # Use table-specific rule if available
    if table_name in pk_rules:
        return pk_rules[table_name]
    
    # Default: look for 'id' column or first column ending in '_id'
    col_names = [col[0] for col in columns]
    if 'id' in col_names:
        return 'id'
    
    for col_name, _ in columns:
        if col_name.endswith('_id'):
            return col_name
    
    return None

def create_table_from_sqlite_schema(table_name, sqlite_cursor, pg_cursor):
    """Create PostgreSQL table dynamically based on SQLite schema"""
    
    # Skip system tables
    if table_name in ['sqlite_sequence', 'sqlite_stat1']:
        return False
        
    # Get SQLite column info
    columns = inspect_sqlite_table(sqlite_cursor, table_name)
    if not columns:
        return False
    
    # Identify primary key
    pk_column = identify_primary_key(table_name, columns)
    logger.info(f"Creating table {table_name}: primary key = {pk_column}")
    
    # Build CREATE TABLE statement
    col_definitions = []
    for col_name, col_type in columns:
        pg_type = sqlite_to_postgres_type(col_type)
        escaped_name = escape_column_name(col_name)
        
        # Handle primary key
        if col_name == pk_column and pg_type == 'INTEGER':
            col_definitions.append(f"{escaped_name} SERIAL PRIMARY KEY")
        else:
            col_definitions.append(f"{escaped_name} {pg_type}")
    
    logger.info(f"CREATE TABLE SQL: {col_definitions[:3]}...")  # Show first 3 columns
    
    create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_definitions)})"
    
    try:
        pg_cursor.execute(create_sql)
        logger.info(f"Created table {table_name} with {len(columns)} columns")
        return True
    except psycopg2.Error as e:
        logger.error(f"Error creating table {table_name}: {e}")
        return False

def get_postgres_column_types(pg_cursor, table_name):
    """Get PostgreSQL column types for a table"""
    pg_cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = %s
    """, (table_name,))
    return {row[0]: row[1] for row in pg_cursor.fetchall()}

def migrate_table_data(table_name, sqlite_cursor, pg_cursor):
    """Migrate data from SQLite table to PostgreSQL"""
    logger.info(f"Migrating table: {table_name}")
    
    # Get SQLite data
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    if not rows:
        logger.info(f"  No data in table {table_name}")
        return
    
    # Get column names
    column_names = [description[0] for description in sqlite_cursor.description]
    
    # Handle SERIAL columns (auto-increment in PostgreSQL)
    serial_columns = get_serial_columns(table_name)
    insert_columns = [col for col in column_names if col not in serial_columns]
    
    # Get boolean columns for this table
    boolean_columns = get_boolean_columns(table_name)
    
    # Get PostgreSQL column types
    pg_column_types = get_postgres_column_types(pg_cursor, table_name)
    
    # Prepare INSERT statement with escaped column names
    placeholders = ', '.join(['%s'] * len(insert_columns))
    escaped_columns = [escape_column_name(col) for col in insert_columns]
    columns_str = ', '.join(escaped_columns)
    
    insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    
    # Convert SQLite rows to PostgreSQL format
    pg_rows = []
    for row in rows:
        row_dict = dict(row)
        pg_row = []
        for col in insert_columns:
            value = row_dict[col]
            # Convert boolean columns based on PostgreSQL column type
            if col in boolean_columns:
                pg_col_type = pg_column_types.get(col, 'INTEGER')
                if pg_col_type == 'boolean':
                    value = bool(value) if value is not None else None
                else:
                    value = int(value) if value is not None else None
            
            # Convert Unix timestamps to PostgreSQL timestamps
            pg_col_type = pg_column_types.get(col, '')
            if pg_col_type in ['timestamp without time zone', 'timestamp with time zone'] and isinstance(value, (int, float)):
                # Convert Unix timestamp to datetime
                from datetime import datetime
                value = datetime.fromtimestamp(value) if value is not None else None
            # Handle foreign key constraints - set NULL for invalid fixture_id
            if table_name == 'odds' and col == 'fixture_id' and value is not None:
                # This will be checked during insertion - if FK fails, we'll set to NULL
                pass
            pg_row.append(value)
        pg_rows.append(tuple(pg_row))
    
    # Insert data
    if table_name == 'odds':
        # Handle odds table by filtering out invalid fixture_id references first
        logger.info(f"  Filtering {len(pg_rows)} odds rows for valid fixture references...")
        
        # Get list of valid fixture_ids from PostgreSQL
        pg_cursor.execute("SELECT fixture_id FROM fixtures")
        valid_fixture_ids = set(row[0] for row in pg_cursor.fetchall())
        valid_fixture_ids.add(None)  # Allow NULL fixture_id
        
        # Filter rows to only include those with valid fixture_id
        valid_rows = []
        invalid_count = 0
        fixture_id_col_index = None
        
        # Find the index of fixture_id column
        for i, col in enumerate(insert_columns):
            if col == 'fixture_id':
                fixture_id_col_index = i
                break
        
        for row in pg_rows:
            if fixture_id_col_index is not None:
                fixture_id_value = row[fixture_id_col_index]
                if fixture_id_value in valid_fixture_ids:
                    valid_rows.append(row)
                else:
                    invalid_count += 1
            else:
                valid_rows.append(row)
        
        # Insert valid rows
        if valid_rows:
            pg_cursor.executemany(insert_sql, valid_rows)
        
        logger.info(f"  Migrated {len(valid_rows)} rows from {table_name} ({invalid_count} skipped due to invalid fixture_id)")
    else:
        # Normal migration for other tables
        try:
            pg_cursor.executemany(insert_sql, pg_rows)
            logger.info(f"  Migrated {len(pg_rows)} rows from {table_name}")
        except psycopg2.Error as e:
            logger.error(f"Error migrating table {table_name}: {e}")
            raise

def get_serial_columns(table_name):
    """Get list of SERIAL columns that should be excluded from INSERT"""
    serial_columns = {
        'teams': ['team_id'],
        'bookmakers': ['bookmaker_id'],
        'fixtures': ['fixture_id'],
        'odds': ['odd_id'],
        'results': ['result_id'],
        'predictions': ['prediction_id'],
        'match_officials': ['id'],
        'team_list': ['id'],
        'match_events': ['id']
    }
    return serial_columns.get(table_name, [])

def create_indexes(pg_cursor):
    """Create PostgreSQL indexes for performance"""
    logger.info("Creating PostgreSQL indexes...")
    
    indexes_sql = """
    -- Core indexes
    CREATE INDEX IF NOT EXISTS idx_odds_match_id ON odds(match_id);
    CREATE INDEX IF NOT EXISTS idx_teams_odds_api_name ON teams(odds_api_name);
    CREATE INDEX IF NOT EXISTS idx_fixtures_teams_kickoff ON fixtures(home_teamid, away_teamid, kickoff_dttm);
    CREATE INDEX IF NOT EXISTS idx_fixtures_season ON fixtures(season);
    CREATE INDEX IF NOT EXISTS idx_fixtures_gameweek ON fixtures(gameweek);
    CREATE INDEX IF NOT EXISTS idx_fixtures_fpl_id ON fixtures(fpl_fixture_id);

    -- FPL indexes
    CREATE INDEX IF NOT EXISTS idx_player_scores_fixture_id ON fantasy_pl_scores(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_player_scores_player_id ON fantasy_pl_scores(player_id);
    CREATE INDEX IF NOT EXISTS idx_player_scores_gameweek ON fantasy_pl_scores(gameweek);
    CREATE INDEX IF NOT EXISTS idx_player_scores_team_id ON fantasy_pl_scores(team_id);
    CREATE INDEX IF NOT EXISTS idx_bootstrap_player_season ON fpl_players_bootstrap(player_id, season);
    CREATE INDEX IF NOT EXISTS idx_player_scores_season_player_gw ON fantasy_pl_scores(season, player_id, gameweek);
    CREATE INDEX IF NOT EXISTS idx_fpl_picks_season_gw ON fpl_team_picks(season, gameweek);

    -- Gameweek indexes
    CREATE INDEX IF NOT EXISTS idx_gameweeks_current ON gameweeks(current_gameweek);
    CREATE INDEX IF NOT EXISTS idx_gameweeks_finished ON gameweeks(finished);

    -- Prediction indexes
    CREATE INDEX IF NOT EXISTS idx_predictions_player_fixture ON predictions(player_id, fixture_id);
    CREATE INDEX IF NOT EXISTS idx_predictions_fixture_id ON predictions(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_predictions_player_id ON predictions(player_id);
    CREATE INDEX IF NOT EXISTS idx_file_metadata_filename ON file_metadata(filename);

    -- Pulse API indexes
    CREATE INDEX IF NOT EXISTS idx_match_officials_pulseid ON match_officials(pulseid);
    CREATE INDEX IF NOT EXISTS idx_team_list_pulseid ON team_list(pulseid);
    CREATE INDEX IF NOT EXISTS idx_team_list_team_id ON team_list(team_id);
    CREATE INDEX IF NOT EXISTS idx_match_events_pulseid ON match_events(pulseid);
    CREATE INDEX IF NOT EXISTS idx_match_events_event_type ON match_events(event_type);
    """
    
    try:
        pg_cursor.execute(indexes_sql)
        logger.info("PostgreSQL indexes created successfully")
    except psycopg2.Error as e:
        logger.error(f"Error creating indexes: {e}")
        raise

def migrate_database(sqlite_path):
    """Main migration function"""
    logger.info(f"Starting migration from {sqlite_path}")
    
    with database_connections(sqlite_path) as (sqlite_conn, postgres_conn):
        sqlite_cursor = sqlite_conn.cursor()
        pg_cursor = postgres_conn.cursor()
        
        try:
            # Get table names from SQLite
            table_names = get_table_names(sqlite_cursor)
            logger.info(f"Found {len(table_names)} tables to migrate: {table_names}")
            
            # Create PostgreSQL tables dynamically based on SQLite schema
            logger.info("Creating PostgreSQL tables based on SQLite schema...")
            for table_name in table_names:
                if table_name not in ['sqlite_sequence', 'sqlite_stat1']:
                    create_table_from_sqlite_schema(table_name, sqlite_cursor, pg_cursor)
            postgres_conn.commit()
            
            # Define migration order (respecting likely foreign key dependencies)
            migration_order = [
                'teams', 'bookmakers', 'gameweeks', 'fixtures', 'odds', 'fixture_odds_summary',
                'fantasy_pl_scores', 'fpl_players_bootstrap', 'fpl_team_picks', 'fpl_team_gameweek_summary',
                'players', 'results', 'predictions', 'gameweek_cache', 'last_update', 'file_metadata',
                'match_officials', 'team_list', 'match_events'
            ]
            
            # Migrate tables in order
            for table_name in migration_order:
                if table_name in table_names:
                    migrate_table_data(table_name, sqlite_cursor, pg_cursor)
                    postgres_conn.commit()
            
            # Migrate any remaining tables not in the order list
            remaining_tables = set(table_names) - set(migration_order)
            for table_name in remaining_tables:
                migrate_table_data(table_name, sqlite_cursor, pg_cursor)
                postgres_conn.commit()
            
            # Create indexes
            create_indexes(pg_cursor)
            postgres_conn.commit()
            
            logger.info("Migration completed successfully!")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            postgres_conn.rollback()
            raise

def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite database to PostgreSQL')
    parser.add_argument('sqlite_path', help='Path to SQLite database file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without doing it')
    parser.add_argument('--inspect', action='store_true', help='Inspect SQLite table schemas')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.sqlite_path):
        logger.error(f"SQLite database file not found: {args.sqlite_path}")
        sys.exit(1)
    
    if args.inspect:
        logger.info("INSPECT MODE - Showing SQLite table schemas")
        with sqlite3.connect(args.sqlite_path) as conn:
            cursor = conn.cursor()
            table_names = get_table_names(cursor)
            for table in table_names:
                if table not in ['sqlite_sequence', 'sqlite_stat1']:
                    columns = inspect_sqlite_table(cursor, table)
                    logger.info(f"Table {table}: {columns}")
        return
    
    # Check required environment variables
    if not os.environ.get('POSTGRES_PASSWORD'):
        logger.error("POSTGRES_PASSWORD environment variable is required")
        sys.exit(1)
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No actual migration will be performed")
        with sqlite3.connect(args.sqlite_path) as conn:
            cursor = conn.cursor()
            table_names = get_table_names(cursor)
            logger.info(f"Would migrate {len(table_names)} tables: {table_names}")
    else:
        migrate_database(args.sqlite_path)

if __name__ == "__main__":
    main()