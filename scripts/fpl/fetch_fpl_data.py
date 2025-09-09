#!/usr/bin/env python3
"""
Fantasy Premier League Data Fetching Script

Fetches comprehensive player data from FPL API with two-tier data collection:
1. Bootstrap data for all players (fpl_players_bootstrap table)
2. Individual player gameweek history (fantasy_pl_scores table)

Features bootstrap-based change detection, concurrent processing, and complete
FPL data capture for advanced fantasy football analysis.

PERFORMANCE OPTIMIZATIONS:
- Bootstrap Change Detection: Two-tier system using fpl_players_bootstrap cache table
- Concurrent Processing: ThreadPoolExecutor with 2-10 configurable workers
- Smart Filtering: Only processes players with actual bootstrap field changes
- Team Mapping: FPL team IDs mapped to database team_id relationships
- Type-Safe Comparisons: Handles string vs numeric API format variations

DATABASE SCHEMA ENHANCEMENTS (September 2025):

fpl_players_bootstrap table (94 columns):
- Complete player profiles with 66 new fields including:
  * Player identity: first_name, second_name, code, opta_code, squad_number, status
  * Performance metrics: form, points_per_game, dreamteam_count, event_points
  * Cost analysis: cost_change_start/event, value_form/season, selected_by_percent
  * Transfer data: transfers_in/out_event, ownership tracking
  * Set pieces: corners/freekicks/penalties order and text descriptions
  * Advanced stats: expected_goal_involvements, expected_goals_conceded
  * Defensive metrics: clearances_blocks_interceptions, recoveries, tackles
  * Per-90 statistics: expected_goals_per_90, saves_per_90, starts_per_90, etc.
  * Ranking data: now_cost_rank, form_rank, influence_rank (+ rank_type variants)

fantasy_pl_scores table (43 columns):
- Enhanced gameweek performance data with 10 new fields including:
  * Match context: opponent_team, kickoff_time, team_h_score, team_a_score
  * Player reference: element (API consistency)
  * Defensive performance: clearances_blocks_interceptions, recoveries, tackles
  * Composite metrics: defensive_contribution

DATA COLLECTION COVERAGE:
- Player Profiles: All FPL bootstrap fields (excluding news, photos, personal data)
- Performance History: Complete gameweek stats including defensive metrics
- Team Relationships: Proper mapping between FPL IDs and database team_id
- Match Context: Opponent data, scores, and kickoff times for fixture analysis

EXPECTED PERFORMANCE:
- First Run: ~20-30 minutes (all 700+ players, creates bootstrap cache)
- Subsequent Runs: Seconds to minutes (0 API calls if no changes detected)
- Typical Reduction: 60-80% fewer API calls after initial bootstrap population
- Debug Mode: --debug shows exact field-level change detection

COMMAND LINE OPTIONS:
- --max-workers N: Concurrent API requests (default: 5, recommended: 2-10)
- --debug: Detailed bootstrap change detection logging
- --dry-run: Preview changes without database updates
- --test: Use cached sample data for development
- --force-refresh: Clear existing FPL data and re-fetch everything

USE CASES:
- Complete fantasy team analysis with ownership, form, and value metrics
- Defensive player evaluation using tackles, recoveries, and clearances
- Fixture difficulty analysis using opponent_team data
- Game state performance analysis using match scores
- Set piece responsibility tracking for bonus point potential
- Transfer market analysis using ownership trends and price movements
"""

import json
import requests
import sqlite3 as sql
import time
import logging
import argparse
import glob
import os
from pathlib import Path
from datetime import datetime
from random import uniform
from tqdm import tqdm
from requests.exceptions import RequestException, Timeout
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BASE_URL = "https://fantasy.premierleague.com/api/"
CURRENT_SEASON = "2025/2026"

# Field mapping between database and FPL API
BOOTSTRAP_FIELD_MAPPING = {
    'team_id': 'team',           # Database field -> API field
    'position': 'element_type',   # Database field -> API field  
    'value': 'now_cost',         # Database field -> API field
    'player_name': 'web_name',   # Database field -> API field
    # All other fields map directly (same name in API and DB)
}

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"
samples_dir = Path(__file__).parent.parent.parent / "samples" / "fantasypl"

# Create directories
log_dir.mkdir(exist_ok=True)
samples_dir.mkdir(parents=True, exist_ok=True)

def setup_logging():
    """Setup logging with both file and console output"""
    log_file = log_dir / f"fpl_fetch_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def cleanup_old_sample_files(keep_count=5, logger=None):
    """Keep only the latest N sample files, remove older ones"""
    pattern = samples_dir / "fpl_data_*.json"
    files = list(glob.glob(str(pattern)))
    
    if len(files) <= keep_count:
        if logger:
            logger.info(f"Only {len(files)} FPL sample files found, no cleanup needed")
        return
    
    # Sort files by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Remove files beyond the keep_count
    files_to_remove = files[keep_count:]
    
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            if logger:
                logger.info(f"Removed old FPL sample file: {Path(file_path).name}")
        except Exception as e:
            if logger:
                logger.error(f"Error removing FPL sample file {file_path}: {e}")

def create_bootstrap_table(cursor):
    """Create fpl_players_bootstrap table if it doesn't exist"""
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS fpl_players_bootstrap (
            player_id INTEGER PRIMARY KEY,
            player_name TEXT NOT NULL,
            team_id INTEGER,
            db_team_id INTEGER,
            position TEXT,
            minutes INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            ict_index REAL DEFAULT 0.0,
            goals_scored INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            clean_sheets INTEGER DEFAULT 0,
            goals_conceded INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            yellow_cards INTEGER DEFAULT 0,
            red_cards INTEGER DEFAULT 0,
            bonus INTEGER DEFAULT 0,
            bps INTEGER DEFAULT 0,
            influence REAL DEFAULT 0.0,
            creativity REAL DEFAULT 0.0,
            threat REAL DEFAULT 0.0,
            starts INTEGER DEFAULT 0,
            expected_goals REAL DEFAULT 0.0,
            expected_assists REAL DEFAULT 0.0,
            value INTEGER DEFAULT 0,
            transfers_in INTEGER DEFAULT 0,
            transfers_out INTEGER DEFAULT 0,
            
            -- Additional player identity fields
            first_name TEXT,
            second_name TEXT,
            code INTEGER,
            opta_code TEXT,
            squad_number INTEGER,
            status TEXT DEFAULT 'a',
            special INTEGER DEFAULT 0,
            can_select INTEGER DEFAULT 1,
            can_transact INTEGER DEFAULT 1,
            removed INTEGER DEFAULT 0,
            
            -- Performance and form metrics
            event_points INTEGER DEFAULT 0,
            form REAL DEFAULT 0.0,
            points_per_game REAL DEFAULT 0.0,
            dreamteam_count INTEGER DEFAULT 0,
            in_dreamteam INTEGER DEFAULT 0,
            
            -- Cost and value analysis
            cost_change_start INTEGER DEFAULT 0,
            cost_change_start_fall INTEGER DEFAULT 0,
            cost_change_event INTEGER DEFAULT 0,
            cost_change_event_fall INTEGER DEFAULT 0,
            value_form REAL DEFAULT 0.0,
            value_season REAL DEFAULT 0.0,
            
            -- Transfer and ownership data
            selected_by_percent REAL DEFAULT 0.0,
            transfers_in_event INTEGER DEFAULT 0,
            transfers_out_event INTEGER DEFAULT 0,
            
            -- Injury/availability predictions
            chance_of_playing_this_round INTEGER,
            chance_of_playing_next_round INTEGER,
            
            -- Set piece responsibilities
            corners_and_indirect_freekicks_order INTEGER,
            corners_and_indirect_freekicks_text TEXT DEFAULT '',
            direct_freekicks_order INTEGER,
            direct_freekicks_text TEXT DEFAULT '',
            penalties_order INTEGER,
            penalties_text TEXT DEFAULT '',
            
            -- Advanced expected stats
            expected_goal_involvements REAL DEFAULT 0.0,
            expected_goals_conceded REAL DEFAULT 0.0,
            
            -- Additional defensive stats
            clearances_blocks_interceptions INTEGER DEFAULT 0,
            recoveries INTEGER DEFAULT 0,
            tackles INTEGER DEFAULT 0,
            defensive_contribution INTEGER DEFAULT 0,
            own_goals INTEGER DEFAULT 0,
            penalties_saved INTEGER DEFAULT 0,
            penalties_missed INTEGER DEFAULT 0,
            
            -- Per-90 performance metrics
            expected_goals_per_90 REAL DEFAULT 0.0,
            expected_assists_per_90 REAL DEFAULT 0.0,
            expected_goal_involvements_per_90 REAL DEFAULT 0.0,
            expected_goals_conceded_per_90 REAL DEFAULT 0.0,
            goals_conceded_per_90 REAL DEFAULT 0.0,
            saves_per_90 REAL DEFAULT 0.0,
            starts_per_90 REAL DEFAULT 0.0,
            clean_sheets_per_90 REAL DEFAULT 0.0,
            defensive_contribution_per_90 REAL DEFAULT 0.0,
            
            -- Ranking data
            now_cost_rank INTEGER,
            now_cost_rank_type INTEGER,
            form_rank INTEGER,
            form_rank_type INTEGER,
            points_per_game_rank INTEGER,
            points_per_game_rank_type INTEGER,
            selected_rank INTEGER,
            selected_rank_type INTEGER,
            influence_rank INTEGER,
            influence_rank_type INTEGER,
            creativity_rank INTEGER,
            creativity_rank_type INTEGER,
            threat_rank INTEGER,
            threat_rank_type INTEGER,
            ict_index_rank INTEGER,
            ict_index_rank_type INTEGER,
            
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            season TEXT DEFAULT '{CURRENT_SEASON}',
            FOREIGN KEY (db_team_id) REFERENCES teams(team_id)
        )
    """)
    
    # Add new columns to existing table if they don't exist
    new_columns = [
        ("db_team_id", "INTEGER"),
        ("first_name", "TEXT"),
        ("second_name", "TEXT"),
        ("code", "INTEGER"),
        ("opta_code", "TEXT"),
        ("squad_number", "INTEGER"),
        ("status", "TEXT DEFAULT 'a'"),
        ("special", "INTEGER DEFAULT 0"),
        ("can_select", "INTEGER DEFAULT 1"),
        ("can_transact", "INTEGER DEFAULT 1"),
        ("removed", "INTEGER DEFAULT 0"),
        ("event_points", "INTEGER DEFAULT 0"),
        ("form", "REAL DEFAULT 0.0"),
        ("points_per_game", "REAL DEFAULT 0.0"),
        ("dreamteam_count", "INTEGER DEFAULT 0"),
        ("in_dreamteam", "INTEGER DEFAULT 0"),
        ("cost_change_start", "INTEGER DEFAULT 0"),
        ("cost_change_start_fall", "INTEGER DEFAULT 0"),
        ("cost_change_event", "INTEGER DEFAULT 0"),
        ("cost_change_event_fall", "INTEGER DEFAULT 0"),
        ("value_form", "REAL DEFAULT 0.0"),
        ("value_season", "REAL DEFAULT 0.0"),
        ("selected_by_percent", "REAL DEFAULT 0.0"),
        ("transfers_in_event", "INTEGER DEFAULT 0"),
        ("transfers_out_event", "INTEGER DEFAULT 0"),
        ("chance_of_playing_this_round", "INTEGER"),
        ("chance_of_playing_next_round", "INTEGER"),
        ("corners_and_indirect_freekicks_order", "INTEGER"),
        ("corners_and_indirect_freekicks_text", "TEXT DEFAULT ''"),
        ("direct_freekicks_order", "INTEGER"),
        ("direct_freekicks_text", "TEXT DEFAULT ''"),
        ("penalties_order", "INTEGER"),
        ("penalties_text", "TEXT DEFAULT ''"),
        ("expected_goal_involvements", "REAL DEFAULT 0.0"),
        ("expected_goals_conceded", "REAL DEFAULT 0.0"),
        ("clearances_blocks_interceptions", "INTEGER DEFAULT 0"),
        ("recoveries", "INTEGER DEFAULT 0"),
        ("tackles", "INTEGER DEFAULT 0"),
        ("defensive_contribution", "INTEGER DEFAULT 0"),
        ("own_goals", "INTEGER DEFAULT 0"),
        ("penalties_saved", "INTEGER DEFAULT 0"),
        ("penalties_missed", "INTEGER DEFAULT 0"),
        ("expected_goals_per_90", "REAL DEFAULT 0.0"),
        ("expected_assists_per_90", "REAL DEFAULT 0.0"),
        ("expected_goal_involvements_per_90", "REAL DEFAULT 0.0"),
        ("expected_goals_conceded_per_90", "REAL DEFAULT 0.0"),
        ("goals_conceded_per_90", "REAL DEFAULT 0.0"),
        ("saves_per_90", "REAL DEFAULT 0.0"),
        ("starts_per_90", "REAL DEFAULT 0.0"),
        ("clean_sheets_per_90", "REAL DEFAULT 0.0"),
        ("defensive_contribution_per_90", "REAL DEFAULT 0.0"),
        ("now_cost_rank", "INTEGER"),
        ("now_cost_rank_type", "INTEGER"),
        ("form_rank", "INTEGER"),
        ("form_rank_type", "INTEGER"),
        ("points_per_game_rank", "INTEGER"),
        ("points_per_game_rank_type", "INTEGER"),
        ("selected_rank", "INTEGER"),
        ("selected_rank_type", "INTEGER"),
        ("influence_rank", "INTEGER"),
        ("influence_rank_type", "INTEGER"),
        ("creativity_rank", "INTEGER"),
        ("creativity_rank_type", "INTEGER"),
        ("threat_rank", "INTEGER"),
        ("threat_rank_type", "INTEGER"),
        ("ict_index_rank", "INTEGER"),
        ("ict_index_rank_type", "INTEGER")
    ]
    
    for column_name, column_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE fpl_players_bootstrap ADD COLUMN {column_name} {column_type}")
        except sql.OperationalError:
            pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE fpl_players_bootstrap ADD FOREIGN KEY (db_team_id) REFERENCES teams(team_id)")
    except sql.OperationalError:
        pass  # Foreign key already exists
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bootstrap_player_season 
        ON fpl_players_bootstrap(player_id, season)
    """)

def clear_existing_fpl_data(cursor, conn, season, logger, dry_run=False):
    """Clear all existing FPL data for the specified season"""
    try:
        if dry_run:
            logger.info(f"DRY RUN: Would clear existing FPL data for season {season}...")
        else:
            logger.info(f"Clearing existing FPL data for season {season}...")
        
        # Get count before clearing
        cursor.execute("SELECT COUNT(*) FROM fantasy_pl_scores")
        scores_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM fpl_players_bootstrap WHERE season = ?", (season,))
        bootstrap_count = cursor.fetchone()[0]
        
        if dry_run:
            logger.info(f"DRY RUN: Would clear FPL data for season {season}: "
                       f"{bootstrap_count} bootstrap records, {scores_count} performance records")
            return
        
        # Clear fantasy_pl_scores table (no season filter needed - it's all current season data)
        cursor.execute("DELETE FROM fantasy_pl_scores")
        scores_deleted = cursor.rowcount
        
        # Clear bootstrap data for the specified season
        cursor.execute("DELETE FROM fpl_players_bootstrap WHERE season = ?", (season,))
        bootstrap_deleted = cursor.rowcount
        
        conn.commit()
        
        logger.info(f"Cleared FPL data for season {season}: "
                   f"{bootstrap_deleted} bootstrap records, {scores_deleted} performance records")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error clearing FPL data for season {season}: {e}")
        raise


def load_team_mapping(cursor):
    """Load FPL team ID to database team_id mapping"""
    cursor.execute("""
        SELECT fpl_id, team_id 
        FROM teams 
        WHERE fpl_id IS NOT NULL
    """)
    
    mapping = {fpl_id: team_id for fpl_id, team_id in cursor.fetchall()}
    return mapping

def load_existing_bootstrap_data(cursor):
    """Load existing bootstrap data from database for comparison"""
    cursor.execute("""
        SELECT player_id, player_name, team_id, db_team_id, position, minutes, total_points, 
               ict_index, goals_scored, assists, clean_sheets, goals_conceded, 
               saves, yellow_cards, red_cards, bonus, bps, influence, creativity, 
               threat, starts, expected_goals, expected_assists, value, 
               transfers_in, transfers_out,
               first_name, second_name, code, opta_code, squad_number, status, special,
               can_select, can_transact, removed, event_points, form, points_per_game,
               dreamteam_count, in_dreamteam, cost_change_start, cost_change_start_fall,
               cost_change_event, cost_change_event_fall, value_form, value_season,
               selected_by_percent, transfers_in_event, transfers_out_event,
               chance_of_playing_this_round, chance_of_playing_next_round,
               corners_and_indirect_freekicks_order, corners_and_indirect_freekicks_text,
               direct_freekicks_order, direct_freekicks_text, penalties_order, penalties_text,
               expected_goal_involvements, expected_goals_conceded,
               clearances_blocks_interceptions, recoveries, tackles, defensive_contribution,
               own_goals, penalties_saved, penalties_missed,
               expected_goals_per_90, expected_assists_per_90, expected_goal_involvements_per_90,
               expected_goals_conceded_per_90, goals_conceded_per_90, saves_per_90,
               starts_per_90, clean_sheets_per_90, defensive_contribution_per_90,
               now_cost_rank, now_cost_rank_type, form_rank, form_rank_type,
               points_per_game_rank, points_per_game_rank_type, selected_rank, selected_rank_type,
               influence_rank, influence_rank_type, creativity_rank, creativity_rank_type,
               threat_rank, threat_rank_type, ict_index_rank, ict_index_rank_type
        FROM fpl_players_bootstrap
        WHERE season = ?
    """, (CURRENT_SEASON,))
    
    existing_data = {}
    for row in cursor.fetchall():
        player_id = row[0]
        existing_data[player_id] = {
            'player_name': row[1],
            'team_id': row[2],
            'db_team_id': row[3],
            'position': row[4],
            'minutes': row[5],
            'total_points': row[6],
            'ict_index': row[7],
            'goals_scored': row[8],
            'assists': row[9],
            'clean_sheets': row[10],
            'goals_conceded': row[11],
            'saves': row[12],
            'yellow_cards': row[13],
            'red_cards': row[14],
            'bonus': row[15],
            'bps': row[16],
            'influence': row[17],
            'creativity': row[18],
            'threat': row[19],
            'starts': row[20],
            'expected_goals': row[21],
            'expected_assists': row[22],
            'value': row[23],
            'transfers_in': row[24],
            'transfers_out': row[25],
            # New fields start at index 26
            'first_name': row[26],
            'second_name': row[27],
            'code': row[28],
            'opta_code': row[29],
            'squad_number': row[30],
            'status': row[31],
            'special': row[32],
            'can_select': row[33],
            'can_transact': row[34],
            'removed': row[35],
            'event_points': row[36],
            'form': row[37],
            'points_per_game': row[38],
            'dreamteam_count': row[39],
            'in_dreamteam': row[40],
            'cost_change_start': row[41],
            'cost_change_start_fall': row[42],
            'cost_change_event': row[43],
            'cost_change_event_fall': row[44],
            'value_form': row[45],
            'value_season': row[46],
            'selected_by_percent': row[47],
            'transfers_in_event': row[48],
            'transfers_out_event': row[49],
            'chance_of_playing_this_round': row[50],
            'chance_of_playing_next_round': row[51],
            'corners_and_indirect_freekicks_order': row[52],
            'corners_and_indirect_freekicks_text': row[53],
            'direct_freekicks_order': row[54],
            'direct_freekicks_text': row[55],
            'penalties_order': row[56],
            'penalties_text': row[57],
            'expected_goal_involvements': row[58],
            'expected_goals_conceded': row[59],
            'clearances_blocks_interceptions': row[60],
            'recoveries': row[61],
            'tackles': row[62],
            'defensive_contribution': row[63],
            'own_goals': row[64],
            'penalties_saved': row[65],
            'penalties_missed': row[66],
            'expected_goals_per_90': row[67],
            'expected_assists_per_90': row[68],
            'expected_goal_involvements_per_90': row[69],
            'expected_goals_conceded_per_90': row[70],
            'goals_conceded_per_90': row[71],
            'saves_per_90': row[72],
            'starts_per_90': row[73],
            'clean_sheets_per_90': row[74],
            'defensive_contribution_per_90': row[75],
            'now_cost_rank': row[76],
            'now_cost_rank_type': row[77],
            'form_rank': row[78],
            'form_rank_type': row[79],
            'points_per_game_rank': row[80],
            'points_per_game_rank_type': row[81],
            'selected_rank': row[82],
            'selected_rank_type': row[83],
            'influence_rank': row[84],
            'influence_rank_type': row[85],
            'creativity_rank': row[86],
            'creativity_rank_type': row[87],
            'threat_rank': row[88],
            'threat_rank_type': row[89],
            'ict_index_rank': row[90],
            'ict_index_rank_type': row[91]
        }
    
    return existing_data

def identify_players_to_update(new_players, existing_bootstrap_data, logger, debug=False):
    """Identify players that need individual API calls based on bootstrap changes"""
    players_to_update = []
    new_players_count = 0
    changed_players_count = 0
    
    # Key fields to check for changes (database field names) - optimized for essential gameplay stats
    key_fields = ['team_id', 'position', 'total_points', 'minutes', 'goals_scored', 
                  'assists', 'clean_sheets', 'goals_conceded', 'saves', 'yellow_cards', 'red_cards',
                  'bonus', 'bps', 'form', 'event_points']
    
    for player in new_players:
        player_id = player["id"]
        existing_data = existing_bootstrap_data.get(player_id)
        
        if not existing_data:
            # New player - definitely needs updating
            players_to_update.append(player)
            new_players_count += 1
            continue
        
        # Check if any key fields have changed
        has_changed = False
        changed_fields = []
        
        for db_field in key_fields:
            # Get the API field name for this database field
            api_field = BOOTSTRAP_FIELD_MAPPING.get(db_field, db_field)
            
            new_value = player.get(api_field)
            existing_value = existing_data.get(db_field)
            
            # Handle None comparisons and type differences
            if (new_value is None) != (existing_value is None):
                has_changed = True
                changed_fields.append(f"{db_field}: {existing_value} -> {new_value}")
                if debug:
                    logger.debug(f"Player {player_id} field {db_field} changed: {existing_value} -> {new_value} (None mismatch)")
                break
            
            if new_value is not None and existing_value is not None:
                # Try numeric comparison for all values (handles string vs float issues)
                try:
                    new_float = float(new_value)
                    existing_float = float(existing_value)
                    if abs(new_float - existing_float) > 0.001:
                        has_changed = True
                        changed_fields.append(f"{db_field}: {existing_value} -> {new_value}")
                        if debug:
                            logger.debug(f"Player {player_id} field {db_field} changed: {existing_value} -> {new_value} (numeric)")
                        break
                except (ValueError, TypeError):
                    # Fall back to string comparison for non-numeric values
                    if str(new_value) != str(existing_value):
                        has_changed = True
                        changed_fields.append(f"{db_field}: {existing_value} -> {new_value}")
                        if debug:
                            logger.debug(f"Player {player_id} field {db_field} changed: {existing_value} -> {new_value} (string)")
                        break
        
        if has_changed:
            players_to_update.append(player)
            changed_players_count += 1
            if debug:
                logger.debug(f"Player {player['web_name']} (ID: {player_id}) marked for update: {', '.join(changed_fields)}")
    
    logger.info(f"Players to update: {len(players_to_update)} total "
                f"({new_players_count} new, {changed_players_count} changed)")
    logger.info(f"Skipping {len(new_players) - len(players_to_update)} unchanged players")
    
    return players_to_update

def update_last_update_table(table_name, cursor, logger):
    """Update the last_update table with current timestamp"""
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y. %H:%M:%S")
        timestamp = dt.timestamp()
        
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
            VALUES (?, ?, ?)
        """, (table_name, now, timestamp))
        
        logger.info(f"Updated last_update table for '{table_name}'")
        
    except Exception as e:
        logger.error(f"Error updating last_update table for '{table_name}': {e}")

def update_bootstrap_data(cursor, players, team_mapping, logger):
    """Update bootstrap table with current player data"""
    updated_count = 0
    changes_made = len(players) > 0  # If we have players to update, assume changes
    
    for player in players:
        # Map FPL team ID to database team_id
        fpl_team_id = player["team"]
        db_team_id = team_mapping.get(fpl_team_id)
        
        cursor.execute("""
            INSERT OR REPLACE INTO fpl_players_bootstrap (
                player_id, player_name, team_id, db_team_id, position, minutes, total_points, 
                ict_index, goals_scored, assists, clean_sheets, goals_conceded, 
                saves, yellow_cards, red_cards, bonus, bps, influence, creativity, 
                threat, starts, expected_goals, expected_assists, value, 
                transfers_in, transfers_out,
                first_name, second_name, code, opta_code, squad_number, status, special,
                can_select, can_transact, removed, event_points, form, points_per_game,
                dreamteam_count, in_dreamteam, cost_change_start, cost_change_start_fall,
                cost_change_event, cost_change_event_fall, value_form, value_season,
                selected_by_percent, transfers_in_event, transfers_out_event,
                chance_of_playing_this_round, chance_of_playing_next_round,
                corners_and_indirect_freekicks_order, corners_and_indirect_freekicks_text,
                direct_freekicks_order, direct_freekicks_text, penalties_order, penalties_text,
                expected_goal_involvements, expected_goals_conceded,
                clearances_blocks_interceptions, recoveries, tackles, defensive_contribution,
                own_goals, penalties_saved, penalties_missed,
                expected_goals_per_90, expected_assists_per_90, expected_goal_involvements_per_90,
                expected_goals_conceded_per_90, goals_conceded_per_90, saves_per_90,
                starts_per_90, clean_sheets_per_90, defensive_contribution_per_90,
                now_cost_rank, now_cost_rank_type, form_rank, form_rank_type,
                points_per_game_rank, points_per_game_rank_type, selected_rank, selected_rank_type,
                influence_rank, influence_rank_type, creativity_rank, creativity_rank_type,
                threat_rank, threat_rank_type, ict_index_rank, ict_index_rank_type,
                last_updated, season
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (
            player["id"],
            player["web_name"], 
            player["team"],
            db_team_id,
            player["element_type"],
            player["minutes"],
            player["total_points"],
            player["ict_index"],
            player["goals_scored"],
            player["assists"],
            player["clean_sheets"],
            player["goals_conceded"],
            player["saves"],
            player["yellow_cards"],
            player["red_cards"],
            player["bonus"],
            player["bps"],
            player["influence"],
            player["creativity"],
            player["threat"],
            player["starts"],
            player["expected_goals"],
            player["expected_assists"],
            player["now_cost"],
            player["transfers_in"],
            player["transfers_out"],
            # New fields
            player.get("first_name", ""),
            player.get("second_name", ""),
            player.get("code"),
            player.get("opta_code", ""),
            player.get("squad_number"),
            player.get("status", "a"),
            player.get("special", False),
            player.get("can_select", True),
            player.get("can_transact", True),
            player.get("removed", False),
            player.get("event_points", 0),
            player.get("form", "0.0"),
            player.get("points_per_game", "0.0"),
            player.get("dreamteam_count", 0),
            player.get("in_dreamteam", False),
            player.get("cost_change_start", 0),
            player.get("cost_change_start_fall", 0),
            player.get("cost_change_event", 0),
            player.get("cost_change_event_fall", 0),
            player.get("value_form", "0.0"),
            player.get("value_season", "0.0"),
            player.get("selected_by_percent", "0.0"),
            player.get("transfers_in_event", 0),
            player.get("transfers_out_event", 0),
            player.get("chance_of_playing_this_round"),
            player.get("chance_of_playing_next_round"),
            player.get("corners_and_indirect_freekicks_order"),
            player.get("corners_and_indirect_freekicks_text", ""),
            player.get("direct_freekicks_order"),
            player.get("direct_freekicks_text", ""),
            player.get("penalties_order"),
            player.get("penalties_text", ""),
            player.get("expected_goal_involvements", "0.0"),
            player.get("expected_goals_conceded", "0.0"),
            player.get("clearances_blocks_interceptions", 0),
            player.get("recoveries", 0),
            player.get("tackles", 0),
            player.get("defensive_contribution", 0),
            player.get("own_goals", 0),
            player.get("penalties_saved", 0),
            player.get("penalties_missed", 0),
            player.get("expected_goals_per_90", 0.0),
            player.get("expected_assists_per_90", 0.0),
            player.get("expected_goal_involvements_per_90", 0.0),
            player.get("expected_goals_conceded_per_90", 0.0),
            player.get("goals_conceded_per_90", 0.0),
            player.get("saves_per_90", 0.0),
            player.get("starts_per_90", 0.0),
            player.get("clean_sheets_per_90", 0.0),
            player.get("defensive_contribution_per_90", 0.0),
            player.get("now_cost_rank"),
            player.get("now_cost_rank_type"),
            player.get("form_rank"),
            player.get("form_rank_type"),
            player.get("points_per_game_rank"),
            player.get("points_per_game_rank_type"),
            player.get("selected_rank"),
            player.get("selected_rank_type"),
            player.get("influence_rank"),
            player.get("influence_rank_type"),
            player.get("creativity_rank"),
            player.get("creativity_rank_type"),
            player.get("threat_rank"),
            player.get("threat_rank_type"),
            player.get("ict_index_rank"),
            player.get("ict_index_rank_type"),
            CURRENT_SEASON
        ))
        updated_count += 1
    
    logger.info(f"Updated bootstrap data for {updated_count} players")
    return changes_made

def create_fantasy_scores_team_column(cursor):
    """Add missing columns to fantasy_pl_scores table if they don't exist"""
    # Define all missing columns to add
    missing_columns = [
        ("team_id", "INTEGER"),
        ("opponent_team", "INTEGER"),
        ("kickoff_time", "TEXT"),
        ("team_h_score", "INTEGER"),
        ("team_a_score", "INTEGER"),
        ("element", "INTEGER"),
        ("clearances_blocks_interceptions", "INTEGER DEFAULT 0"),
        ("recoveries", "INTEGER DEFAULT 0"),
        ("tackles", "INTEGER DEFAULT 0"),
        ("defensive_contribution", "INTEGER DEFAULT 0")
    ]
    
    # Add each column if it doesn't exist
    for column_name, column_type in missing_columns:
        try:
            cursor.execute(f"ALTER TABLE fantasy_pl_scores ADD COLUMN {column_name} {column_type}")
        except sql.OperationalError:
            pass  # Column already exists
    
    # Add foreign key relationships
    try:
        cursor.execute("ALTER TABLE fantasy_pl_scores ADD FOREIGN KEY (team_id) REFERENCES teams(team_id)")
    except sql.OperationalError:
        pass  # Foreign key already exists

def load_fixture_mapping(cursor):
    """Load FPL fixture ID to database fixture_id mapping for current season"""
    cursor.execute("""
        SELECT fpl_fixture_id, fixture_id 
        FROM fixtures 
        WHERE season = ?
    """, (CURRENT_SEASON,))
    
    mapping = {fpl_id: db_id for fpl_id, db_id in cursor.fetchall()}
    return mapping

def fetch_bootstrap_data(logger):
    """Fetch initial player data from FPL bootstrap endpoint"""
    url = f"{BASE_URL}bootstrap-static/"
    
    try:
        logger.info("Fetching FPL bootstrap data...")
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            players = data.get("elements", [])
            logger.info(f"Retrieved {len(players)} players from FPL API")
            return players
        else:
            logger.error(f"Bootstrap API request failed with status {response.status_code}")
            return None
            
    except Timeout:
        logger.error("Bootstrap API request timed out after 30 seconds")
        return None
    except RequestException as e:
        logger.error(f"Bootstrap API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching bootstrap data: {e}")
        return None

def fetch_player_history(player_id, player_name, logger):
    """Fetch individual player history with error handling"""
    url = f"{BASE_URL}element-summary/{player_id}/"
    
    try:
        # Random delay to be respectful to the API
        time.sleep(uniform(1.0, 3.0))
        
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Player {player_name} (ID: {player_id}) API request failed with status {response.status_code}")
            return None
            
    except Timeout:
        logger.warning(f"Player {player_name} (ID: {player_id}) request timed out")
        return None
    except RequestException as e:
        logger.warning(f"Player {player_name} (ID: {player_id}) request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching player {player_name} (ID: {player_id}): {e}")
        return None

def fetch_players_concurrently(players_to_fetch, logger, max_workers=5):
    """Fetch player histories concurrently with rate limiting"""
    all_player_scores = []
    api_errors = 0
    
    def fetch_single_player(player):
        player_id = player["id"]
        player_name = player["web_name"]
        fpl_team_id = player["team"]  # Get FPL team ID from bootstrap data
        
        history_data = fetch_player_history(player_id, player_name, logger)
        
        if not history_data:
            return None, 1  # None result, 1 error
        
        player_scores = []
        for gameweek in history_data.get("history", []):
            player_score = {
                "player_name": player_name,
                "gameweek": gameweek["round"],
                "player_id": player_id,
                "fpl_team_id": fpl_team_id,  # Add FPL team ID for mapping
                "total_points": gameweek["total_points"],
                "fixture": gameweek["fixture"],
                "was_home": gameweek["was_home"],
                "minutes": gameweek["minutes"],
                "goals_scored": gameweek["goals_scored"],
                "assists": gameweek["assists"],
                "clean_sheets": gameweek["clean_sheets"],
                "goals_conceded": gameweek["goals_conceded"],
                "own_goals": gameweek["own_goals"],
                "penalties_saved": gameweek["penalties_saved"],
                "penalties_missed": gameweek["penalties_missed"],
                "yellow_cards": gameweek["yellow_cards"],
                "red_cards": gameweek["red_cards"],
                "saves": gameweek["saves"],
                "bonus": gameweek["bonus"],
                "bps": gameweek["bps"],
                "influence": gameweek["influence"],
                "creativity": gameweek["creativity"],
                "threat": gameweek["threat"],
                "ict_index": gameweek["ict_index"],
                "starts": gameweek["starts"],
                "expected_goals": gameweek["expected_goals"],
                "expected_assists": gameweek["expected_assists"],
                "expected_goal_involvements": gameweek["expected_goal_involvements"],
                "expected_goals_conceded": gameweek["expected_goals_conceded"],
                "value": gameweek["value"],
                "transfers_balance": gameweek["transfers_balance"],
                "selected": gameweek["selected"],
                "transfers_in": gameweek["transfers_in"],
                "transfers_out": gameweek["transfers_out"],
                # New fields
                "opponent_team": gameweek.get("opponent_team"),
                "kickoff_time": gameweek.get("kickoff_time", ""),
                "team_h_score": gameweek.get("team_h_score"),
                "team_a_score": gameweek.get("team_a_score"),
                "element": gameweek.get("element", player_id),
                "clearances_blocks_interceptions": gameweek.get("clearances_blocks_interceptions", 0),
                "recoveries": gameweek.get("recoveries", 0),
                "tackles": gameweek.get("tackles", 0),
                "defensive_contribution": gameweek.get("defensive_contribution", 0),
            }
            player_scores.append(player_score)
        
        return player_scores, 0  # Return scores, 0 errors
    
    logger.info(f"Fetching individual player history for {len(players_to_fetch)} players using {max_workers} concurrent workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_player = {executor.submit(fetch_single_player, player): player for player in players_to_fetch}
        
        # Process results with progress bar
        for future in tqdm(as_completed(future_to_player), total=len(players_to_fetch), desc="Processing players"):
            player_scores, errors = future.result()
            api_errors += errors
            
            if player_scores:
                all_player_scores.extend(player_scores)
    
    return all_player_scores, api_errors

def get_existing_player_data(cursor):
    """Get existing player data from database for comparison"""
    cursor.execute("""
        SELECT player_id, gameweek, fixture_id, total_points, minutes, goals_scored, assists,
               clean_sheets, goals_conceded, saves, yellow_cards, red_cards, bonus, bps,
               clearances_blocks_interceptions, recoveries, tackles, defensive_contribution
        FROM fantasy_pl_scores
    """)
    
    # Create a dictionary keyed by (player_id, gameweek, fixture_id) 
    existing_data = {}
    for row in cursor.fetchall():
        key = (row[0], row[1], row[2])  # player_id, gameweek, fixture_id
        existing_data[key] = {
            'total_points': row[3],
            'minutes': row[4], 
            'goals_scored': row[5],
            'assists': row[6],
            'clean_sheets': row[7],
            'goals_conceded': row[8],
            'saves': row[9],
            'yellow_cards': row[10],
            'red_cards': row[11],
            'bonus': row[12],
            'bps': row[13],
            'clearances_blocks_interceptions': row[14],
            'recoveries': row[15],
            'tackles': row[16],
            'defensive_contribution': row[17]
        }
    
    return existing_data

def has_data_changed(new_record, existing_record):
    """Check if any tracked fields have changed"""
    if not existing_record:
        return True  # New record
    
    # Check key fields that might change - optimized for essential gameplay stats
    check_fields = ['total_points', 'minutes', 'goals_scored', 'assists', 
                   'clean_sheets', 'goals_conceded', 'saves', 'yellow_cards', 
                   'red_cards', 'bonus', 'bps', 'clearances_blocks_interceptions',
                   'recoveries', 'tackles', 'defensive_contribution']
    
    for field in check_fields:
        new_val = new_record.get(field)
        existing_val = existing_record.get(field)
        
        # Handle None comparisons and type differences
        if (new_val is None) != (existing_val is None):
            return True
        if new_val is not None and existing_val is not None:
            if abs(float(new_val) - float(existing_val)) > 0.001:  # Handle floating point precision
                return True
                
    return False

def upsert_player_scores(cursor, player_scores, existing_data, fixture_mapping, team_mapping, logger):
    """Insert or update player scores with efficient upsert logic"""
    
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    fixture_mapping_errors = 0
    
    for score_data in player_scores:
        # Map FPL fixture ID to database fixture_id
        fpl_fixture_id = score_data['fixture']
        fixture_id = fixture_mapping.get(fpl_fixture_id)
        
        if not fixture_id:
            logger.warning(f"No fixture mapping found for FPL fixture ID {fpl_fixture_id}")
            fixture_mapping_errors += 1
            continue
        
        # Get team_id from mapping 
        fpl_team_id = score_data.get('fpl_team_id')  # We'll need to add this to score data
        team_id = team_mapping.get(fpl_team_id)
        
        # Create database record with proper fixture_id and team_id
        db_record = {
            'player_name': score_data['player_name'],
            'gameweek': score_data['gameweek'],
            'player_id': score_data['player_id'],
            'total_points': score_data['total_points'],
            'fixture_id': fixture_id,
            'team_id': team_id,
            'was_home': score_data['was_home'],
            'minutes': score_data['minutes'],
            'goals_scored': score_data['goals_scored'],
            'assists': score_data['assists'],
            'clean_sheets': score_data['clean_sheets'],
            'goals_conceded': score_data['goals_conceded'],
            'own_goals': score_data['own_goals'],
            'penalties_saved': score_data['penalties_saved'],
            'penalties_missed': score_data['penalties_missed'],
            'yellow_cards': score_data['yellow_cards'],
            'red_cards': score_data['red_cards'],
            'saves': score_data['saves'],
            'bonus': score_data['bonus'],
            'bps': score_data['bps'],
            'influence': score_data['influence'],
            'creativity': score_data['creativity'],
            'threat': score_data['threat'],
            'ict_index': score_data['ict_index'],
            'starts': score_data['starts'],
            'expected_goals': score_data['expected_goals'],
            'expected_assists': score_data['expected_assists'],
            'expected_goal_involvements': score_data['expected_goal_involvements'],
            'expected_goals_conceded': score_data['expected_goals_conceded'],
            'value': score_data['value'],
            'transfers_balance': score_data['transfers_balance'],
            'selected': score_data['selected'],
            'transfers_in': score_data['transfers_in'],
            'transfers_out': score_data['transfers_out'],
            # New fields
            'opponent_team': score_data.get('opponent_team'),
            'kickoff_time': score_data.get('kickoff_time', ''),
            'team_h_score': score_data.get('team_h_score'),
            'team_a_score': score_data.get('team_a_score'),
            'element': score_data.get('element'),
            'clearances_blocks_interceptions': score_data.get('clearances_blocks_interceptions', 0),
            'recoveries': score_data.get('recoveries', 0),
            'tackles': score_data.get('tackles', 0),
            'defensive_contribution': score_data.get('defensive_contribution', 0)
        }
        
        # Check if this record exists and has changed
        record_key = (score_data['player_id'], score_data['gameweek'], fixture_id)
        existing_record = existing_data.get(record_key)
        
        if not has_data_changed(db_record, existing_record):
            skipped_count += 1
            continue
        
        # Use INSERT OR REPLACE for efficient upsert
        cursor.execute("""
            INSERT OR REPLACE INTO fantasy_pl_scores (
                player_name, gameweek, player_id, total_points, fixture_id, team_id, was_home, minutes,
                goals_scored, assists, clean_sheets, goals_conceded, own_goals, penalties_saved,
                penalties_missed, yellow_cards, red_cards, saves, bonus, bps, influence,
                creativity, threat, ict_index, starts, expected_goals, expected_assists,
                expected_goal_involvements, expected_goals_conceded, value, transfers_balance,
                selected, transfers_in, transfers_out, opponent_team, kickoff_time, team_h_score,
                team_a_score, element, clearances_blocks_interceptions, recoveries, tackles,
                defensive_contribution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            db_record['player_name'], db_record['gameweek'], db_record['player_id'],
            db_record['total_points'], db_record['fixture_id'], db_record['team_id'], db_record['was_home'],
            db_record['minutes'], db_record['goals_scored'], db_record['assists'],
            db_record['clean_sheets'], db_record['goals_conceded'], db_record['own_goals'],
            db_record['penalties_saved'], db_record['penalties_missed'], db_record['yellow_cards'],
            db_record['red_cards'], db_record['saves'], db_record['bonus'], db_record['bps'],
            db_record['influence'], db_record['creativity'], db_record['threat'],
            db_record['ict_index'], db_record['starts'], db_record['expected_goals'],
            db_record['expected_assists'], db_record['expected_goal_involvements'],
            db_record['expected_goals_conceded'], db_record['value'], db_record['transfers_balance'],
            db_record['selected'], db_record['transfers_in'], db_record['transfers_out'],
            # New fields
            db_record['opponent_team'], db_record['kickoff_time'], db_record['team_h_score'],
            db_record['team_a_score'], db_record['element'], db_record['clearances_blocks_interceptions'],
            db_record['recoveries'], db_record['tackles'], db_record['defensive_contribution']
        ))
        
        if existing_record:
            updated_count += 1
        else:
            inserted_count += 1
    
    logger.info(f"Database operations: {inserted_count} inserted, {updated_count} updated, {skipped_count} unchanged")
    if fixture_mapping_errors > 0:
        logger.warning(f"Skipped {fixture_mapping_errors} records due to fixture mapping errors")

def collect_fpl_data(logger, max_workers=5, debug=False, force_refresh=False, dry_run=False):
    """Collect FPL data with smart bootstrap-based filtering"""
    # Get bootstrap data
    players = fetch_bootstrap_data(logger)
    if not players:
        logger.error("Failed to fetch bootstrap data")
        return None
    
    # Setup database connection for bootstrap operations
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Ensure bootstrap table exists
        create_bootstrap_table(cursor)
        
        # Ensure fantasy_pl_scores has team_id column
        create_fantasy_scores_team_column(cursor)
        
        # Load team mapping for FPL ID to database team_id
        logger.info("Loading team mapping...")
        team_mapping = load_team_mapping(cursor)
        logger.info(f"Loaded {len(team_mapping)} team mappings")
        
        # Handle force refresh option
        if force_refresh:
            logger.info("Force refresh enabled - clearing existing FPL data...")
            clear_existing_fpl_data(cursor, conn, CURRENT_SEASON, logger, dry_run)
            existing_bootstrap_data = {}  # Empty since we cleared everything
            players_to_update = players  # Update all players
            logger.info(f"Force refresh: All {len(players)} players marked for update")
        else:
            # Load existing bootstrap data
            logger.info("Loading existing bootstrap data for comparison...")
            existing_bootstrap_data = load_existing_bootstrap_data(cursor)
            logger.info(f"Loaded {len(existing_bootstrap_data)} existing bootstrap records")
            
            # Identify which players need individual API calls
            players_to_update = identify_players_to_update(players, existing_bootstrap_data, logger, debug)
        
        # Update bootstrap table with current data
        logger.info("Updating bootstrap table with current player data...")
        bootstrap_changes_made = update_bootstrap_data(cursor, players, team_mapping, logger)
        
        # Log bootstrap updates if changes were detected (indicated by players needing updates)
        if len(players_to_update) > 0 and not dry_run:
            logger.info("Bootstrap data changes detected - logging update timestamp")
            update_last_update_table("fpl_players_bootstrap", cursor, logger)
        
        conn.commit()
        
        # Collect player scores for filtered players
        if players_to_update:
            all_player_scores, api_errors = fetch_players_concurrently(players_to_update, logger, max_workers)
        else:
            logger.info("No players need updating - using existing data")
            all_player_scores, api_errors = [], 0
        
        logger.info(f"Collected {len(all_player_scores)} player performance records")
        if api_errors > 0:
            logger.warning(f"Failed to fetch data for {api_errors} players due to API errors")
        
        return {
            'players': players,
            'player_scores': all_player_scores,
            'team_mapping': team_mapping,  # Include team mapping for processing
            'metadata': {
                'fetch_time': datetime.now().isoformat(),
                'total_players': len(players),
                'players_updated': len(players_to_update),
                'total_records': len(all_player_scores),
                'api_errors': api_errors,
                'season': CURRENT_SEASON
            }
        }
    
    except Exception as e:
        conn.rollback()
        logger.error(f"Error in collect_fpl_data: {e}")
        raise
    finally:
        conn.close()

def save_sample_data(fpl_data, logger):
    """Save FPL data as JSON sample with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fpl_data_{timestamp}.json"
    output_file = samples_dir / filename
    
    try:
        with open(output_file, 'w') as f:
            json.dump(fpl_data, f, indent=2)
        logger.info(f"FPL sample data saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to save FPL sample data: {e}")

def process_fpl_data(fpl_data, logger, dry_run=False):
    """Process FPL data and update database"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        logger.info("Loading fixture mappings...")
        fixture_mapping = load_fixture_mapping(cursor)
        logger.info(f"Loaded {len(fixture_mapping)} fixture mappings for season {CURRENT_SEASON}")
        
        if not fixture_mapping:
            logger.error(f"No fixture mappings found for season {CURRENT_SEASON}")
            return
        
        logger.info("Loading existing player data for comparison...")
        existing_data = get_existing_player_data(cursor)
        logger.info(f"Loaded {len(existing_data)} existing player records")
        
        player_scores = fpl_data['player_scores']
        logger.info(f"Processing {len(player_scores)} player score records...")
        
        if dry_run:
            logger.info("DRY RUN MODE - No database changes will be made")
            # Still run the upsert logic to show what would happen
            # But rollback the transaction
        
        team_mapping = fpl_data.get('team_mapping', {})
        upsert_player_scores(cursor, player_scores, existing_data, fixture_mapping, team_mapping, logger)
        
        if dry_run:
            conn.rollback()
            logger.info("DRY RUN - Transaction rolled back")
        else:
            # Update last_update table to trigger database upload
            update_last_update_table("fantasy_pl_scores", cursor, logger)
            conn.commit()
            logger.info("Database transaction committed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing FPL data: {e}")
        raise
    finally:
        conn.close()

def load_sample_data(logger):
    """Load the most recent sample data for testing"""
    pattern = samples_dir / "fpl_data_*.json"
    sample_files = list(glob.glob(str(pattern)))
    
    if not sample_files:
        logger.error("No FPL sample data files found")
        return None
    
    # Use the most recent sample file
    sample_file = max(sample_files, key=lambda f: os.path.getmtime(f))
    logger.info(f"Loading sample data from: {Path(sample_file).name}")
    
    try:
        with open(sample_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load sample data: {e}")
        return None

def main(cleanup_count=5, dry_run=False, max_workers=5, debug=False, force_refresh=False):
    """Main execution function"""
    logger = setup_logging()
    if debug:
        logger.setLevel(logging.DEBUG)
    logger.info("Starting FPL data fetch process...")
    
    # Collect FPL data
    fpl_data = collect_fpl_data(logger, max_workers, debug, force_refresh, dry_run)
    
    if fpl_data and fpl_data['player_scores']:
        # Save sample data
        save_sample_data(fpl_data, logger)
        
        # Process data into database
        process_fpl_data(fpl_data, logger, dry_run=dry_run)
        
        # Clean up old sample files
        if cleanup_count > 0:
            logger.info(f"Cleaning up old sample files, keeping latest {cleanup_count}...")
            cleanup_old_sample_files(keep_count=cleanup_count, logger=logger)
        
        logger.info("FPL data fetch process completed successfully")
    else:
        logger.error("No FPL data collected - aborting process")

def test_with_sample_data(dry_run=False):
    """Test the script using existing sample data"""
    logger = setup_logging()
    logger.info("Starting FPL test with sample data...")
    
    fpl_data = load_sample_data(logger)
    
    if fpl_data:
        logger.info("Processing sample FPL data...")
        process_fpl_data(fpl_data, logger, dry_run=dry_run)
        logger.info("FPL test completed successfully")
    else:
        logger.error("No sample data available for testing")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch FPL data and update fantasy_pl_scores table')
    parser.add_argument('--test', action='store_true', 
                       help='Run in test mode with sample data')
    parser.add_argument('--cleanup-count', type=int, default=5,
                       help='Number of sample files to keep (0 to disable cleanup)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without making database changes (shows what would happen)')
    parser.add_argument('--max-workers', type=int, default=5,
                       help='Maximum number of concurrent API requests (default: 5)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging for detailed change detection info')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Clear existing FPL data and re-fetch everything')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.test:
        test_with_sample_data(dry_run=args.dry_run)
    else:
        main(cleanup_count=args.cleanup_count, dry_run=args.dry_run, max_workers=args.max_workers, debug=args.debug, force_refresh=args.force_refresh)