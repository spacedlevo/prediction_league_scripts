#!/usr/bin/env python3
"""
Prediction League Web Application

Simple Flask-based web interface for managing the prediction league database.
Built following hobbyist development philosophy: simple, readable, maintainable.

Features:
- Dashboard with database overview
- Admin panel for player management  
- Script execution interface
- FPL insights and statistics

Single-file architecture for easy maintenance.
"""

import os
import json
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time
import pytz
import requests as http_requests
import pandas as pd
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, PULP_CBC_CMD

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

# Initialize Flask app
app = Flask(__name__)

# Global variables for configuration and state
config = {}
script_status = {}  # Track running scripts

# FPL Optimizer constants (from fpl_optimizer.py)
FPL_POSITION_REQUIREMENTS = {"1": 2, "2": 5, "3": 5, "4": 3}
FPL_MAX_PER_TEAM = 3
FPL_POSITION_NAMES = {"1": "GK", "2": "DEF", "3": "MID", "4": "FWD"}
FPL_FORM_WEIGHT = 0.4
FPL_FORM_GWS = 5

# Simple cache for FPL API responses (key -> (timestamp, data))
_fpl_api_cache = {}


def convert_to_uk_time(timestamp_or_dt, format_str='%d/%m/%Y %H:%M'):
    """Convert timestamp or datetime to UK timezone and format"""
    try:
        if isinstance(timestamp_or_dt, (int, float)):
            # Unix timestamp
            utc_dt = datetime.fromtimestamp(timestamp_or_dt, tz=timezone.utc)
        elif isinstance(timestamp_or_dt, str):
            # ISO datetime string
            utc_dt = datetime.fromisoformat(timestamp_or_dt.replace('Z', '+00:00'))
        else:
            # Assume it's already a datetime object
            utc_dt = timestamp_or_dt
            if utc_dt.tzinfo is None:
                # Assume UTC if no timezone info
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        
        uk_tz = pytz.timezone(config.get('timezone', 'Europe/London'))
        uk_dt = utc_dt.astimezone(uk_tz)
        return uk_dt.strftime(format_str)
    except (ValueError, OSError, AttributeError):
        return 'Unknown'


def load_config():
    """Load configuration from config.json file"""
    global config
    
    # Try local config first, then production path
    local_config_path = Path(__file__).parent / "config.json"
    production_config_path = Path("/opt/prediction-league/config.json")
    
    if local_config_path.exists():
        config_path = local_config_path
        print(f"Using local config: {config_path}")
    elif production_config_path.exists():
        config_path = production_config_path
        print(f"Using production config: {config_path}")
    else:
        # Create default config from example
        config_path = local_config_path
        example_path = Path(__file__).parent / "config.json.example"
        if example_path.exists():
            import shutil
            shutil.copy(example_path, config_path)
            print(f"Created config.json from example. Please edit {config_path} with your settings.")
        else:
            raise FileNotFoundError("No config.json or config.json.example found")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Set Flask configuration
    app.config['SECRET_KEY'] = config['secret_key']
    app.config['DEBUG'] = config.get('debug', False)
    
    # Setup logging for debugging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def get_db_connection():
    """Get SQLite database connection"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle absolute vs relative paths properly
    if Path(config['database_path']).is_absolute():
        db_path = Path(config['database_path'])
    else:
        db_path = Path(__file__).parent / config['database_path']
    logger.info(f"Database path requested: {db_path}")
    logger.info(f"Database path exists: {db_path.exists()}")
    logger.info(f"Current working directory: {Path.cwd()}")
    logger.info(f"Webapp parent directory: {Path(__file__).parent}")
    logger.info(f"Config database_path: {config['database_path']}")
    
    if not db_path.exists():
        # Try to find the database in common locations for debugging
        alternative_paths = [
            Path(__file__).parent.parent / "data" / "database.db",  # Up one level
            Path.cwd() / "data" / "database.db",  # Current working directory
            Path(__file__).parent / "data" / "database.db"  # Same level as webapp
        ]
        
        logger.info("Database not found at expected location. Checking alternatives:")
        for alt_path in alternative_paths:
            logger.info(f"  {alt_path}: {'EXISTS' if alt_path.exists() else 'NOT FOUND'}")
        
        raise FileNotFoundError(f"Database not found at {db_path}")
    
    logger.info(f"Successfully connecting to database at: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def require_auth(f):
    """Decorator to require authentication for routes"""
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Simple password-based authentication"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == config['admin_password']:
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            flash('Login successful', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Clear session and redirect to login"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))


# Main Application Routes
@app.route('/')
def index():
    """Redirect to dashboard"""
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@require_auth
def dashboard():
    """Main dashboard with database overview"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get basic statistics
        stats = get_dashboard_stats(cursor)
        
        # Get recent activity
        recent_updates = get_recent_updates(cursor)
        
        # Get players missing predictions for current and next gameweeks
        missing_predictions = get_players_missing_predictions(cursor)
        
        # Get predictions progress for current and next gameweeks
        predictions_progress = get_predictions_progress(cursor)
        
        # Get players with identical predictions for current and next gameweeks
        identical_predictions = get_players_with_identical_predictions(cursor)

        # Get verification mismatches
        verification_mismatches = get_verification_mismatches(cursor)

        # Get future gameweek deadlines
        future_deadlines = get_future_gameweek_deadlines(cursor)

        conn.close()

        return render_template('dashboard.html',
                             stats=stats,
                             recent_updates=recent_updates,
                             missing_predictions=missing_predictions,
                             predictions_progress=predictions_progress,
                             identical_predictions=identical_predictions,
                             verification_mismatches=verification_mismatches,
                             future_deadlines=future_deadlines,
                             page_title='Dashboard')
    
    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'error')
        return render_template('dashboard.html',
                             stats={},
                             recent_updates=[],
                             missing_predictions={'current': {}, 'next': {}},
                             predictions_progress={'current': {}, 'next': {}},
                             identical_predictions={'current': {}, 'next': {}},
                             verification_mismatches={},
                             future_deadlines=[],
                             page_title='Dashboard')


@app.route('/admin')
@require_auth 
def admin():
    """Player management page"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all players
        cursor.execute("""
            SELECT player_id, player_name, web_name, active, paid, 
                   mini_league, mini_league_paid, pundit 
            FROM players 
            ORDER BY player_name
        """)
        players = cursor.fetchall()
        
        conn.close()
        
        return render_template('admin.html', 
                             players=players,
                             page_title='Player Management')
    
    except Exception as e:
        flash(f'Error loading players: {e}', 'error')
        return render_template('admin.html', 
                             players=[],
                             page_title='Player Management')


@app.route('/admin/player/add', methods=['POST'])
@require_auth
def add_player():
    """Add new player to the database"""
    try:
        player_name = request.form.get('player_name', '').strip()
        web_name = request.form.get('web_name', '').strip()
        
        if not player_name:
            flash('Player name is required', 'error')
            return redirect(url_for('admin'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if player already exists
        cursor.execute("SELECT player_id FROM players WHERE LOWER(player_name) = LOWER(?)", (player_name,))
        if cursor.fetchone():
            flash(f'Player "{player_name}" already exists', 'error')
            conn.close()
            return redirect(url_for('admin'))
        
        # Insert new player
        cursor.execute("""
            INSERT INTO players (player_name, web_name, active, paid, mini_league, mini_league_paid, pundit)
            VALUES (?, ?, 1, 0, 0, 0, 0)
        """, (player_name, web_name))
        
        conn.commit()
        conn.close()
        
        flash(f'Player "{player_name}" added successfully', 'success')
        
    except Exception as e:
        flash(f'Error adding player: {e}', 'error')
    
    return redirect(url_for('admin'))


@app.route('/admin/player/<int:player_id>/toggle/<field>')
@require_auth
def toggle_player_field(player_id, field):
    """Toggle boolean fields for a player"""
    allowed_fields = ['active', 'paid', 'mini_league', 'mini_league_paid', 'pundit']
    
    if field not in allowed_fields:
        flash(f'Invalid field: {field}', 'error')
        return redirect(url_for('admin'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current value
        cursor.execute(f"SELECT {field}, player_name FROM players WHERE player_id = ?", (player_id,))
        result = cursor.fetchone()
        
        if not result:
            flash('Player not found', 'error')
            conn.close()
            return redirect(url_for('admin'))
        
        current_value = result[0]
        player_name = result[1]
        new_value = 1 - current_value  # Toggle 0/1
        
        # Update the field
        cursor.execute(f"UPDATE players SET {field} = ? WHERE player_id = ?", (new_value, player_id))
        conn.commit()
        conn.close()
        
        status = "enabled" if new_value else "disabled"
        flash(f'{field.replace("_", " ").title()} {status} for {player_name}', 'success')
        
    except Exception as e:
        flash(f'Error updating player: {e}', 'error')
    
    return redirect(url_for('admin'))


@app.route('/scripts')
@require_auth
def scripts():
    """Script management page"""
    available_scripts = config.get('available_scripts', {})
    return render_template('scripts.html', 
                         scripts=available_scripts,
                         script_status=script_status,
                         page_title='Scripts Management')


@app.route('/scripts/run/<script_key>')
@require_auth
def run_script(script_key):
    """Execute a script and return status"""
    available_scripts = config.get('available_scripts', {})
    
    if script_key not in available_scripts:
        flash(f'Unknown script: {script_key}', 'error')
        return redirect(url_for('scripts'))
    
    script_info = available_scripts[script_key]
    
    # Check if script is already running
    if script_key in script_status and script_status[script_key].get('running'):
        flash(f'Script "{script_info["name"]}" is already running', 'warning')
        return redirect(url_for('scripts'))
    
    # Start script in background thread
    thread = threading.Thread(target=execute_script, args=(script_key, script_info))
    thread.daemon = True
    thread.start()
    
    flash(f'Started script: {script_info["name"]}', 'success')
    return redirect(url_for('scripts'))


@app.route('/scripts/status/<script_key>')
@require_auth
def script_status_api(script_key):
    """Get script execution status via API"""
    status = script_status.get(script_key, {})
    return jsonify(status)


@app.route('/api/fpl/players')
@require_auth
def api_fpl_players():
    """API endpoint for FPL player search with comprehensive statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get query parameters
        player_name = request.args.get('playerName', '').strip()
        position = request.args.get('position', '')
        min_points = request.args.get('minPoints', '')
        max_value = request.args.get('maxValue', '')
        min_minutes = request.args.get('minMinutes', '0')
        min_form = request.args.get('minForm', '')
        max_ownership = request.args.get('maxOwnership', '')
        
        # Build base query
        query = """
            SELECT 
                player_name, position, total_points, value, minutes, starts,
                expected_goals, expected_assists, expected_goal_involvements,
                goals_scored, assists, clean_sheets, saves, bonus, bps,
                form, points_per_game, selected_by_percent, transfers_in,
                defensive_contribution, yellow_cards, red_cards, team_id
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026'
        """
        
        params = []
        
        # Add filters
        if player_name:
            query += " AND LOWER(player_name) LIKE LOWER(?)"
            params.append(f'%{player_name}%')
        
        if position:
            query += " AND position = ?"
            params.append(position)
        
        if min_points:
            query += " AND total_points >= ?"
            params.append(int(min_points))
        
        if max_value:
            query += " AND value <= ?"
            params.append(int(float(max_value) * 10))  # Convert to internal format
        
        if min_minutes:
            query += " AND minutes >= ?"
            params.append(int(min_minutes))
        
        if min_form:
            query += " AND form >= ?"
            params.append(float(min_form))
        
        if max_ownership:
            query += " AND selected_by_percent <= ?"
            params.append(float(max_ownership))
        
        # Default order by total points descending
        query += " ORDER BY total_points DESC, player_name ASC"
        
        # Limit results for performance
        query += " LIMIT 100"
        
        cursor.execute(query, params)
        raw_results = cursor.fetchall()
        
        # Process results to add calculated fields
        results = []
        for row in raw_results:
            player_data = {
                'player_name': row[0],
                'position': row[1],
                'total_points': row[2],
                'value': row[3],
                'minutes': row[4],
                'starts': row[5],
                'expected_goals': float(row[6] or 0),
                'expected_assists': float(row[7] or 0),
                'expected_goal_involvements': float(row[8] or 0),
                'goals_scored': row[9] or 0,
                'assists': row[10] or 0,
                'clean_sheets': row[11] or 0,
                'saves': row[12] or 0,
                'bonus': row[13] or 0,
                'bps': row[14] or 0,
                'form': float(row[15] or 0),
                'points_per_game': float(row[16] or 0),
                'selected_by_percent': float(row[17] or 0),
                'transfers_in': row[18] or 0,
                'defensive_contribution': row[19] or 0,
                'yellow_cards': row[20] or 0,
                'red_cards': row[21] or 0,
                'team_id': row[22] or 0,
                
                # Calculated fields
                'value_millions': round(row[3] / 10, 1),
                'value_per_million': round(row[2] / (row[3] / 10), 2) if row[3] > 0 else 0,
                'goal_contributions': (row[9] or 0) + (row[10] or 0),
                'minutes_per_start': round(row[4] / row[5], 1) if row[5] > 0 else 0,
                'saves_per_90': round((row[12] or 0) * 90 / row[4], 1) if row[4] > 0 else 0,
                'bps_per_90': round((row[14] or 0) * 90 / row[4], 1) if row[4] > 0 else 0,
            }
            
            # Position-specific enhancements
            if row[1] == '1':  # Goalkeeper
                player_data['position_type'] = 'goalkeeper'
                player_data['clean_sheet_rate'] = round(row[11] / row[5] * 100, 1) if row[5] > 0 else 0
            elif row[1] == '2':  # Defender
                player_data['position_type'] = 'defender'
                player_data['attacking_threat'] = player_data['expected_goals'] + player_data['expected_assists']
            elif row[1] == '3':  # Midfielder
                player_data['position_type'] = 'midfielder'
                player_data['creativity_vs_threat'] = 'creative' if player_data['expected_assists'] > player_data['expected_goals'] else 'goal_threat'
            elif row[1] == '4':  # Forward
                player_data['position_type'] = 'forward'
                player_data['shot_conversion'] = round((row[9] or 0) / max(player_data['expected_goals'], 0.1), 2)
            
            results.append(player_data)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'players': results,
            'count': len(results),
            'filters_applied': {
                'player_name': player_name,
                'position': position,
                'min_points': min_points,
                'max_value': max_value,
                'min_minutes': min_minutes,
                'min_form': min_form,
                'max_ownership': max_ownership
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'players': [],
            'count': 0
        })


@app.route('/api/fpl/my-team')
@require_auth
def fpl_my_team():
    """API endpoint: fetch user's FPL team and recommend transfers"""
    try:
        team_id = config.get('fpl_team_id', 273788)
        db_path = config.get('database_path', '')

        conn = get_db_connection()
        cursor = conn.cursor()
        current_gw = get_current_fpl_gameweek(cursor)
        conn.close()

        # Fetch data from FPL API
        entry_data = fetch_fpl_entry(team_id)
        picks_data = fetch_fpl_picks(team_id, current_gw)
        history_data = fetch_fpl_history(team_id)

        # Extract key info
        team_name = entry_data.get('name', 'Unknown')
        overall_points = entry_data.get('summary_overall_points', 0)
        overall_rank = entry_data.get('summary_overall_rank', 0)

        entry_history = picks_data.get('entry_history', {})
        bank = entry_history.get('bank', 0)
        squad_value = entry_history.get('value', 0)

        free_transfers = calculate_free_transfers(history_data)

        # Get current squad player IDs from picks
        picks = picks_data.get('picks', [])
        current_player_ids = [p['element'] for p in picks]
        captain_id = next((p['element'] for p in picks if p.get('is_captain')), None)
        vice_captain_id = next((p['element'] for p in picks if p.get('is_vice_captain')), None)
        starter_positions = {p['element'] for p in picks if p.get('multiplier', 0) > 0}

        # Load all player data with blended scores
        all_players_df, total_gws = load_fpl_optimizer_data(db_path)

        # Build current squad details
        current_squad_df = all_players_df[all_players_df.player_id.isin(current_player_ids)]
        current_squad = []
        for _, p in current_squad_df.iterrows():
            current_squad.append({
                'player_id': int(p.player_id),
                'player_name': p.player_name,
                'position': FPL_POSITION_NAMES.get(str(p.position), str(p.position)),
                'position_raw': str(p.position),
                'team_name': p.team_name or 'Unknown',
                'total_points': int(p.total_points),
                'value': float(p.value),
                'blended': round(float(p.blended), 1),
                'form': str(p.form),
                'avg_pts_last5': round(float(p.avg_pts_last5), 1),
                'is_captain': p.player_id == captain_id,
                'is_vice_captain': p.player_id == vice_captain_id,
                'is_starter': p.player_id in starter_positions,
                'status': p.status,
            })

        # Sort by position then points
        pos_order = {'1': 0, '2': 1, '3': 2, '4': 3}
        current_squad.sort(key=lambda x: (pos_order.get(x['position_raw'], 9), -x['total_points']))

        # Run optimizer to get ideal squad
        optimal_squad_df = optimize_fpl_squad(all_players_df, score_col="blended")
        optimal_squad = []
        for _, p in optimal_squad_df.iterrows():
            optimal_squad.append({
                'player_id': int(p.player_id),
                'player_name': p.player_name,
                'position': FPL_POSITION_NAMES.get(str(p.position), str(p.position)),
                'position_raw': str(p.position),
                'team_name': p.team_name or 'Unknown',
                'total_points': int(p.total_points),
                'value': float(p.value),
                'blended': round(float(p.blended), 1),
                'form': str(p.form),
                'avg_pts_last5': round(float(p.avg_pts_last5), 1),
                'status': p.status,
            })
        optimal_squad.sort(key=lambda x: (pos_order.get(x['position_raw'], 9), -x['total_points']))

        # Recommend transfers
        recommended_transfers = recommend_transfers(
            current_player_ids, optimal_squad_df, all_players_df, bank, free_transfers
        )

        # Build recommended squad (current with transfers applied)
        out_ids = {t['out']['player_id'] for t in recommended_transfers}
        in_ids = {t['in']['player_id'] for t in recommended_transfers}
        recommended_squad = [p for p in current_squad if p['player_id'] not in out_ids]
        for _, p in all_players_df[all_players_df.player_id.isin(in_ids)].iterrows():
            recommended_squad.append({
                'player_id': int(p.player_id),
                'player_name': p.player_name,
                'position': FPL_POSITION_NAMES.get(str(p.position), str(p.position)),
                'position_raw': str(p.position),
                'team_name': p.team_name or 'Unknown',
                'total_points': int(p.total_points),
                'value': float(p.value),
                'blended': round(float(p.blended), 1),
                'form': str(p.form),
                'avg_pts_last5': round(float(p.avg_pts_last5), 1),
                'is_captain': False,
                'is_vice_captain': False,
                'is_starter': True,
                'status': p.status,
                'is_new': True,
            })
        recommended_squad.sort(key=lambda x: (pos_order.get(x['position_raw'], 9), -x['total_points']))

        # Chips used
        chips_used = [
            {'name': c.get('name', ''), 'event': c.get('event', 0)}
            for c in history_data.get('chips', [])
        ]

        return jsonify({
            'success': True,
            'gameweek': current_gw,
            'team_name': team_name,
            'free_transfers': free_transfers,
            'bank': bank,
            'squad_value': squad_value,
            'overall_points': overall_points,
            'overall_rank': overall_rank,
            'current_squad': current_squad,
            'optimal_squad': optimal_squad,
            'recommended_transfers': recommended_transfers,
            'recommended_squad': recommended_squad,
            'chips_used': chips_used,
        })

    except Exception as e:
        print(f"Error in fpl_my_team: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
        })


@app.route('/fpl')
@require_auth
def fpl_insights():
    """FPL insights and analytics page"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get basic FPL stats
        fpl_stats = get_fpl_stats(cursor)
        
        # Get top players by different metrics
        top_players = get_top_fpl_players(cursor)
        
        conn.close()
        
        return render_template('fpl.html',
                             fpl_stats=fpl_stats,
                             top_players=top_players,
                             page_title='FPL Insights')
    
    except Exception as e:
        flash(f'Error loading FPL data: {e}', 'error')
        return render_template('fpl.html',
                             fpl_stats={},
                             top_players={},
                             page_title='FPL Insights')


@app.route('/debug')
def debug_info():
    """Debug endpoint to test API without authentication"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current gameweek
        cursor.execute("""
            SELECT gameweek 
            FROM gameweeks 
            WHERE current_gameweek = 1 OR next_gameweek = 1
            ORDER BY gameweek ASC
            LIMIT 1
        """)
        current_gw = cursor.fetchone()
        gameweek = current_gw[0] if current_gw else 1
        
        # Test API data
        cursor.execute("""
            SELECT COUNT(*) FROM fixtures f
            LEFT JOIN fixture_odds_summary s ON f.fixture_id = s.fixture_id
            WHERE f.gameweek = ? AND f.season = '2025/2026'
        """, (gameweek,))
        fixture_count = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'status': 'ok',
            'current_gameweek': gameweek,
            'fixtures_found': fixture_count,
            'message': 'Debug endpoint working'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.route('/predictions')
@require_auth
def predictions_analysis():
    """Predictions analysis page showing odds-based predictions"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current gameweek
        cursor.execute("""
            SELECT gameweek 
            FROM gameweeks 
            WHERE current_gameweek = 1 OR next_gameweek = 1
            ORDER BY gameweek ASC
            LIMIT 1
        """)
        current_gw = cursor.fetchone()
        gameweek = current_gw[0] if current_gw else 1
        
        # Get available gameweeks for dropdown
        cursor.execute("""
            SELECT DISTINCT gameweek 
            FROM fixtures 
            WHERE season = '2025/2026'
            ORDER BY gameweek
        """)
        available_gameweeks = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template('predictions.html',
                             current_gameweek=gameweek,
                             available_gameweeks=available_gameweeks,
                             page_title='Predictions Analysis')
    
    except Exception as e:
        flash(f'Error loading predictions data: {e}', 'error')
        return render_template('predictions.html',
                             current_gameweek=1,
                             available_gameweeks=[],
                             page_title='Predictions Analysis')


@app.route('/api/predictions/gameweek/<int:gameweek>')
def get_gameweek_predictions(gameweek):
    """API endpoint to get fixtures and odds for a specific gameweek"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get fixtures with odds for the gameweek (including Over/Under 2.5 odds)
        cursor.execute("""
            SELECT 
                f.fixture_id,
                ht.team_name as home_team,
                at.team_name as away_team,
                f.kickoff_dttm,
                s.avg_home_win_odds as home_odds,
                s.avg_draw_odds as draw_odds,
                s.avg_away_win_odds as away_odds,
                s.avg_over_2_5_odds as over_2_5_odds,
                s.avg_under_2_5_odds as under_2_5_odds,
                r.home_goals as actual_home_goals,
                r.away_goals as actual_away_goals
            FROM fixtures f
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            LEFT JOIN fixture_odds_summary s ON f.fixture_id = s.fixture_id
            LEFT JOIN results r ON f.fixture_id = r.fixture_id
            WHERE f.gameweek = ? AND f.season = '2025/2026'
            ORDER BY f.kickoff_dttm
        """, (gameweek,))
        
        fixtures = []
        for row in cursor.fetchall():
            fixture = {
                'fixture_id': row[0],
                'home_team': row[1],
                'away_team': row[2],
                'kickoff_time': convert_to_uk_time(row[3], '%d/%m/%Y %H:%M %Z') if row[3] else None,
                'kickoff_time_raw': row[3],  # Keep original for any JavaScript processing
                'home_odds': row[4],
                'draw_odds': row[5],
                'away_odds': row[6],
                'over_2_5_odds': row[7],
                'under_2_5_odds': row[8],
                'actual_home_goals': row[9],
                'actual_away_goals': row[10]
            }
            fixtures.append(fixture)
        
        conn.close()
        
        return jsonify({
            'gameweek': gameweek,
            'fixtures': fixtures,
            'count': len(fixtures)
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'gameweek': gameweek,
            'fixtures': [],
            'count': 0
        }), 500


@app.route('/api/predictions/calculate-points', methods=['POST'])
@require_auth
def calculate_custom_points():
    """Calculate points for custom predictions"""
    try:
        data = request.get_json()
        predictions = data.get('predictions', [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        total_points = 0
        results = []
        
        for pred in predictions:
            fixture_id = pred['fixture_id']
            pred_home = int(pred['home_score'])
            pred_away = int(pred['away_score'])
            
            # Get actual result
            cursor.execute("""
                SELECT home_goals, away_goals 
                FROM results 
                WHERE fixture_id = ?
            """, (fixture_id,))
            
            result = cursor.fetchone()
            if result:
                actual_home, actual_away = result
                
                points = 0
                # Exact score (2 points)
                if actual_home == pred_home and actual_away == pred_away:
                    points = 2
                # Correct result (1 point)  
                elif ((actual_home > actual_away and pred_home > pred_away) or
                      (actual_home < actual_away and pred_home < pred_away) or
                      (actual_home == actual_away and pred_home == pred_away)):
                    points = 1
                
                total_points += points
                results.append({
                    'fixture_id': fixture_id,
                    'points': points,
                    'actual_home': actual_home,
                    'actual_away': actual_away
                })
        
        conn.close()
        
        return jsonify({
            'total_points': total_points,
            'results': results
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/verification/acknowledge', methods=['POST'])
@require_auth
def acknowledge_verification_issues():
    """Acknowledge verification issues to clear them from the dashboard"""
    try:
        data = request.get_json()
        gameweek = data.get('gameweek')  # Optional: specific gameweek to acknowledge

        conn = get_db_connection()
        cursor = conn.cursor()

        if gameweek:
            # Acknowledge issues for a specific gameweek
            cursor.execute("""
                UPDATE prediction_verification
                SET acknowledged = 1
                WHERE verification_id IN (
                    SELECT pv.verification_id
                    FROM prediction_verification pv
                    JOIN fixtures f ON pv.fixture_id = f.fixture_id
                    WHERE pv.category = 'Score Mismatch'
                    AND f.gameweek = ?
                    AND f.season = '2025/2026'
                )
            """, (gameweek,))
            message = f"Acknowledged all issues for Gameweek {gameweek}"
        else:
            # Acknowledge all issues
            cursor.execute("""
                UPDATE prediction_verification
                SET acknowledged = 1
                WHERE category = 'Score Mismatch'
            """)
            message = "Acknowledged all verification issues"

        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': message,
            'acknowledged_count': affected_rows
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_fixtures_with_odds_multi_season(cursor, season_filter='2025/2026', logger=None):
    """Get fixtures with odds data from both fixture_odds_summary and football_stats fallback"""
    
    # Primary query - use fixture_odds_summary when available
    primary_query = """
        SELECT 
            f.fixture_id,
            ht.team_name as home_team,
            at.team_name as away_team,
            s.avg_home_win_odds as home_odds,
            s.avg_draw_odds as draw_odds,
            s.avg_away_win_odds as away_odds,
            s.avg_over_2_5_odds as over_2_5_odds,
            s.avg_under_2_5_odds as under_2_5_odds,
            r.home_goals as actual_home_goals,
            r.away_goals as actual_away_goals,
            f.season,
            'fixture_odds_summary' as data_source
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        LEFT JOIN fixture_odds_summary s ON f.fixture_id = s.fixture_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE {season_filter}
        AND r.home_goals IS NOT NULL 
        AND r.away_goals IS NOT NULL
        AND s.avg_home_win_odds IS NOT NULL
        AND s.avg_away_win_odds IS NOT NULL
    """
    
    # Fallback query - use football_stats for historical data
    fallback_query = """
        SELECT 
            f.fixture_id,
            ht.team_name as home_team,
            at.team_name as away_team,
            fs.AvgH as home_odds,
            fs.AvgD as draw_odds,
            fs.AvgA as away_odds,
            fs."Avg>2.5" as over_2_5_odds,
            fs."Avg<2.5" as under_2_5_odds,
            r.home_goals as actual_home_goals,
            r.away_goals as actual_away_goals,
            f.season,
            'football_stats' as data_source
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        LEFT JOIN football_stats fs ON (
            f.home_teamid = fs.home_team_id 
            AND f.away_teamid = fs.away_team_id 
            AND DATE(f.kickoff_dttm) = DATE(fs.Date)
        )
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE {season_filter}
        AND r.home_goals IS NOT NULL 
        AND r.away_goals IS NOT NULL
        AND fs.AvgH IS NOT NULL
        AND fs.AvgA IS NOT NULL
        AND f.fixture_id NOT IN (
            SELECT DISTINCT f2.fixture_id 
            FROM fixtures f2 
            LEFT JOIN fixture_odds_summary s2 ON f2.fixture_id = s2.fixture_id
            WHERE s2.avg_home_win_odds IS NOT NULL
        )
    """
    
    # Build season filter
    if season_filter == 'all':
        season_condition = "f.season IS NOT NULL"
    elif isinstance(season_filter, list):
        seasons_list = "', '".join(season_filter) 
        season_condition = f"f.season IN ('{seasons_list}')"
    else:
        season_condition = f"f.season = '{season_filter}'"
    
    primary_query = primary_query.format(season_filter=season_condition)
    fallback_query = fallback_query.format(season_filter=season_condition)
    
    # Execute both queries and combine results
    if logger:
        logger.info(f"Executing primary query for seasons: {season_filter}")
    cursor.execute(primary_query)
    primary_results = cursor.fetchall()
    
    if logger:
        logger.info(f"Found {len(primary_results)} fixtures from fixture_odds_summary")
        logger.info(f"Executing fallback query for historical data")
    cursor.execute(fallback_query)
    fallback_results = cursor.fetchall()
    
    if logger:
        logger.info(f"Found {len(fallback_results)} additional fixtures from football_stats")
    
    # Combine and format results
    all_fixtures = []
    
    # Process primary results
    for row in primary_results:
        fixture = {
            'fixture_id': row[0],
            'home_team': row[1],
            'away_team': row[2],
            'home_odds': row[3],
            'draw_odds': row[4],
            'away_odds': row[5],
            'over_2_5_odds': row[6],
            'under_2_5_odds': row[7],
            'actual_home_goals': row[8],
            'actual_away_goals': row[9],
            'season': row[10],
            'data_source': row[11]
        }
        all_fixtures.append(fixture)
    
    # Process fallback results
    for row in fallback_results:
        fixture = {
            'fixture_id': row[0],
            'home_team': row[1],
            'away_team': row[2],
            'home_odds': row[3],
            'draw_odds': row[4],
            'away_odds': row[5],
            'over_2_5_odds': row[6],
            'under_2_5_odds': row[7],
            'actual_home_goals': row[8],
            'actual_away_goals': row[9],
            'season': row[10],
            'data_source': row[11]
        }
        all_fixtures.append(fixture)
    
    return all_fixtures


@app.route('/api/predictions/season-performance')
def get_season_performance():
    """Get performance comparison for all prediction strategies this season"""
    import logging
    
    # Setup logging for debugging
    logger = logging.getLogger(__name__)
    logger.info("=== Season Performance API Called ===")
    
    try:
        # Get season parameter from query string (default to current season)
        season = request.args.get('season', '2025/2026')
        logger.info(f"Season performance analysis requested for: {season}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get fixtures with multi-season fallback support
        if season == 'all':
            logger.info("Analyzing performance across all available seasons")
            fixtures_data = get_fixtures_with_odds_multi_season(cursor, 'all', logger)
        elif season == 'historical':
            # Historical seasons (excluding current)
            historical_seasons = ['2020/2021', '2021/2022', '2022/2023', '2023/2024', '2024/2025']
            logger.info(f"Analyzing historical seasons: {historical_seasons}")
            fixtures_data = get_fixtures_with_odds_multi_season(cursor, historical_seasons, logger)
        else:
            logger.info(f"Analyzing single season: {season}")
            fixtures_data = get_fixtures_with_odds_multi_season(cursor, season, logger)
        
        conn.close()
        
        # Count data sources
        data_sources = {}
        seasons_analyzed = set()
        for fixture in fixtures_data:
            source = fixture.get('data_source', 'unknown')
            data_sources[source] = data_sources.get(source, 0) + 1
            if fixture.get('season'):
                seasons_analyzed.add(fixture['season'])
        
        logger.info(f"Data sources: {data_sources}")
        logger.info(f"Seasons analyzed: {sorted(list(seasons_analyzed))}")
        logger.info(f"Total fixtures for analysis: {len(fixtures_data)}")
        
        # Log first few fixtures for debugging
        for i, fixture in enumerate(fixtures_data[:3]):
            logger.info(f"Sample fixture {i+1}: {fixture['home_team']} {fixture['actual_home_goals']}-{fixture['actual_away_goals']} {fixture['away_team']} (odds: {fixture['home_odds']:.2f}/{fixture['away_odds']:.2f})")
        
        conn.close()
        
        if not fixtures_data:
            logger.warning(f"No fixtures found for season filter: {season}")
            return jsonify({
                'strategies': [],
                'message': f'No completed fixtures with odds data available for {season}',
                'debug': {
                    'season_filter': season,
                    'complete_fixtures': 0,
                    'data_sources_used': list(data_sources.keys())
                }
            })
        
        # Calculate performance for each strategy
        strategies = ['adaptive', 'fixed', 'fixed-2-0', 'fixed-1-0', 'calibrated', 'home-away', 'poisson', 'smart-goals']
        strategy_performance = []
        
        logger.info("Calculating performance for each strategy...")
        for strategy in strategies:
            logger.info(f"Calculating performance for {strategy} strategy...")
            performance = calculate_strategy_performance(fixtures_data, strategy)
            performance['strategy_name'] = get_strategy_display_name(strategy)
            strategy_performance.append(performance)
            logger.info(f"{strategy} strategy: {performance['total_points']} points, {performance['accuracy_rate']:.1f}% accuracy")
        
        logger.info("=== Season Performance API Completed Successfully ===")
        
        return jsonify({
            'strategies': strategy_performance,
            'total_games': len(fixtures_data),
            'season': season,
            'seasons_analyzed': sorted(list(seasons_analyzed)),
            'debug': {
                'season_filter': season,
                'data_sources_used': data_sources,
                'seasons_covered': sorted(list(seasons_analyzed)),
                'complete_fixtures': len(fixtures_data)
            }
        })
    
    except Exception as e:
        logger.error(f"Error in season performance API: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({
            'error': str(e), 
            'strategies': [],
            'debug': {
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
        }), 500


@app.route('/api/season-recommendation')
def get_season_recommendation():
    """Get current season strategy recommendation based on real-time analysis"""
    import logging

    # Setup logging for debugging
    logger = logging.getLogger(__name__)
    logger.info("=== Season Recommendation API Called ===")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get season parameter (default to current season)
        season = request.args.get('season', '2025/2026')
        logger.info(f"Season recommendation requested for: {season}")

        # Get latest recommendation for the season
        cursor.execute('''
            SELECT
                season, current_gameweek, total_matches, low_scoring_matches,
                low_scoring_percentage, goals_per_game_avg, recommended_strategy,
                confidence_level, recommendation_reason, historical_precedents,
                expected_points_improvement, last_updated
            FROM season_recommendations
            WHERE season = ?
            ORDER BY last_updated DESC
            LIMIT 1
        ''', (season,))

        recommendation = cursor.fetchone()

        if not recommendation:
            # Generate new recommendation for the season
            logger.info(f"No existing recommendation found for {season}, generating new one...")
            recommendation_data = generate_season_recommendation(cursor, season, logger)
        else:
            # Convert to dict for easier handling
            recommendation_data = {
                'season': recommendation[0],
                'current_gameweek': recommendation[1],
                'total_matches': recommendation[2],
                'low_scoring_matches': recommendation[3],
                'low_scoring_percentage': recommendation[4],
                'goals_per_game_avg': recommendation[5],
                'recommended_strategy': recommendation[6],
                'confidence_level': recommendation[7],
                'recommendation_reason': recommendation[8],
                'historical_precedents': json.loads(recommendation[9]) if recommendation[9] else [],
                'expected_points_improvement': recommendation[10],
                'last_updated': recommendation[11]
            }
            logger.info(f"Retrieved existing recommendation: {recommendation_data['recommended_strategy']} ({recommendation_data['confidence_level']})")

        # Get switch timing guidance
        switch_guidance = get_switch_timing_guidance(recommendation_data, logger)

        # Get historical context
        historical_context = get_historical_context(cursor, recommendation_data['low_scoring_percentage'], logger)

        conn.close()

        response_data = {
            'recommendation': recommendation_data,
            'switch_guidance': switch_guidance,
            'historical_context': historical_context,
            'success': True
        }

        logger.info("=== Season Recommendation API Completed Successfully ===")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error in season recommendation API: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({
            'error': str(e),
            'success': False,
            'recommendation': None
        }), 500


def generate_season_recommendation(cursor, season, logger):
    """Generate a new season recommendation based on current data"""
    logger.info(f"Generating new recommendation for season: {season}")

    # Get current season stats
    cursor.execute('''
        SELECT
            COUNT(*) as total_matches,
            SUM(CASE WHEN (r.home_goals + r.away_goals) <= 2 THEN 1 ELSE 0 END) as low_scoring,
            AVG(r.home_goals + r.away_goals) as avg_goals,
            MAX(f.gameweek) as current_gameweek
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
    ''', (season,))

    result = cursor.fetchone()

    if not result or result[0] == 0:
        logger.warning(f"No completed matches found for season {season}")
        return {
            'season': season,
            'current_gameweek': 1,
            'total_matches': 0,
            'low_scoring_matches': 0,
            'low_scoring_percentage': 0.0,
            'goals_per_game_avg': 2.5,
            'recommended_strategy': '2-1',
            'confidence_level': 'early',
            'recommendation_reason': 'No completed matches yet - using default 2-1 strategy',
            'historical_precedents': [],
            'expected_points_improvement': 0.0,
            'last_updated': datetime.now().isoformat()
        }

    total_matches, low_scoring, avg_goals, current_gameweek = result
    low_scoring_percentage = (low_scoring / total_matches) * 100

    logger.info(f"Season stats: {total_matches} matches, {low_scoring_percentage:.1f}% low-scoring")

    # Determine recommendation based on analysis thresholds
    if low_scoring_percentage > 47:
        recommended_strategy = '1-0'
        expected_improvement = 0.05 if low_scoring_percentage > 50 else 0.025
        reason = f"Season shows {low_scoring_percentage:.1f}% low-scoring matches (above 47% threshold for 1-0 strategy)"
    else:
        recommended_strategy = '2-1'
        expected_improvement = 0.0
        reason = f"Season shows {low_scoring_percentage:.1f}% low-scoring matches (below 47% threshold, continue 2-1 strategy)"

    # Determine confidence level
    if total_matches >= 80:
        confidence = 'high'
    elif total_matches >= 40:
        confidence = 'moderate'
    else:
        confidence = 'early'

    # Find similar historical seasons
    cursor.execute('''
        SELECT season, low_scoring_percentage, optimal_strategy, strategy_advantage
        FROM historical_season_patterns
        WHERE ABS(low_scoring_percentage - ?) < 5.0
        ORDER BY ABS(low_scoring_percentage - ?)
        LIMIT 3
    ''', (low_scoring_percentage, low_scoring_percentage))

    similar_seasons = cursor.fetchall()
    historical_precedents = [{
        'season': s[0],
        'percentage': s[1],
        'strategy': s[2],
        'advantage': s[3]
    } for s in similar_seasons]

    # Save to database
    recommendation_data = {
        'season': season,
        'current_gameweek': current_gameweek or 1,
        'total_matches': total_matches,
        'low_scoring_matches': low_scoring,
        'low_scoring_percentage': low_scoring_percentage,
        'goals_per_game_avg': avg_goals or 2.5,
        'recommended_strategy': recommended_strategy,
        'confidence_level': confidence,
        'recommendation_reason': reason,
        'historical_precedents': historical_precedents,
        'expected_points_improvement': expected_improvement,
        'last_updated': datetime.now().isoformat()
    }

    cursor.execute('''
        INSERT OR REPLACE INTO season_recommendations
        (season, current_gameweek, total_matches, low_scoring_matches,
         low_scoring_percentage, goals_per_game_avg, recommended_strategy,
         confidence_level, recommendation_reason, historical_precedents,
         expected_points_improvement)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        season, current_gameweek or 1, total_matches, low_scoring,
        low_scoring_percentage, avg_goals or 2.5, recommended_strategy,
        confidence, reason, json.dumps(historical_precedents),
        expected_improvement
    ))

    cursor.connection.commit()
    logger.info(f"Saved new recommendation: {recommended_strategy} ({confidence})")

    return recommendation_data


def get_switch_timing_guidance(recommendation_data, logger):
    """Generate switch timing guidance based on current season progress"""
    current_gw = recommendation_data['current_gameweek']
    total_matches = recommendation_data['total_matches']
    confidence = recommendation_data['confidence_level']
    strategy = recommendation_data['recommended_strategy']

    guidance = {
        'current_week': current_gw,
        'assessment_stage': '',
        'next_review_week': 0,
        'action_recommended': '',
        'timing_message': ''
    }

    if total_matches < 40:  # Early season (weeks 1-4)
        guidance.update({
            'assessment_stage': 'early_monitoring',
            'next_review_week': max(5, current_gw + 2),
            'action_recommended': 'monitor',
            'timing_message': f'Early season assessment - monitor for {40 - total_matches} more matches before confident recommendation'
        })
    elif total_matches < 80:  # Mid early season (weeks 5-8)
        if strategy == '1-0':
            guidance.update({
                'assessment_stage': 'moderate_confidence',
                'next_review_week': current_gw + 4,
                'action_recommended': 'consider_switch',
                'timing_message': f'Moderate confidence in 1-0 strategy. Consider switching now, full confidence after week 8.'
            })
        else:
            guidance.update({
                'assessment_stage': 'moderate_confidence',
                'next_review_week': current_gw + 4,
                'action_recommended': 'continue_monitoring',
                'timing_message': f'Continue with 2-1 strategy. Re-assess after week 8.'
            })
    else:  # High confidence (week 8+)
        if strategy == '1-0':
            guidance.update({
                'assessment_stage': 'high_confidence',
                'next_review_week': 15,  # Mid-season review
                'action_recommended': 'switch_now',
                'timing_message': f'High confidence: Switch to 1-0 strategy now. Expected season benefit: +{recommendation_data["expected_points_improvement"]:.2f} pts/game'
            })
        else:
            guidance.update({
                'assessment_stage': 'high_confidence',
                'next_review_week': 15,
                'action_recommended': 'continue_current',
                'timing_message': f'High confidence: Continue 2-1 strategy. Mid-season review at week 15.'
            })

    return guidance


def get_historical_context(cursor, current_percentage, logger):
    """Get historical context for current season's scoring pattern"""
    # Get similar seasons
    cursor.execute('''
        SELECT
            season, low_scoring_percentage, optimal_strategy, strategy_advantage,
            season_classification
        FROM historical_season_patterns
        ORDER BY ABS(low_scoring_percentage - ?)
        LIMIT 5
    ''', (current_percentage,))

    similar_seasons = cursor.fetchall()

    # Get overall distribution
    cursor.execute('''
        SELECT
            COUNT(*) as total_seasons,
            AVG(low_scoring_percentage) as avg_percentage,
            COUNT(CASE WHEN optimal_strategy = '1-0' THEN 1 END) as seasons_favoring_1_0,
            COUNT(CASE WHEN optimal_strategy = '2-1' THEN 1 END) as seasons_favoring_2_1
        FROM historical_season_patterns
    ''')

    distribution = cursor.fetchone()

    context = {
        'similar_seasons': [{
            'season': s[0],
            'percentage': s[1],
            'optimal_strategy': s[2],
            'advantage': s[3],
            'classification': s[4]
        } for s in similar_seasons],
        'historical_average': distribution[1] if distribution[1] else 45.0,
        'seasons_1_0_optimal': distribution[2] if distribution[2] else 0,
        'seasons_2_1_optimal': distribution[3] if distribution[3] else 0,
        'current_vs_average': current_percentage - (distribution[1] if distribution[1] else 45.0),
        'percentile_rank': calculate_percentile_rank(cursor, current_percentage, logger)
    }

    return context


def calculate_percentile_rank(cursor, current_percentage, logger):
    """Calculate what percentile the current season's low-scoring percentage is"""
    cursor.execute('''
        SELECT COUNT(*)
        FROM historical_season_patterns
        WHERE low_scoring_percentage <= ?
    ''', (current_percentage,))

    lower_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM historical_season_patterns')
    total_count = cursor.fetchone()[0]

    if total_count > 0:
        percentile = (lower_count / total_count) * 100
        return round(percentile, 1)
    else:
        return 50.0  # Default middle percentile


def get_strategy_display_name(strategy):
    """Get display name for strategy"""
    names = {
        'fixed': 'Fixed (2-1 Favourite)',
        'adaptive': 'Adaptive (Season-Based Recommendation)',
        'fixed-2-0': 'Fixed (2-0 Favourite)',
        'fixed-1-0': 'Fixed (1-0 Favourite)',
        'calibrated': 'Calibrated Scorelines',
        'home-away': 'Home/Away Bias',
        'poisson': 'Poisson Model',
        'smart-goals': 'Smart Goals (1X2 + Over/Under)'
    }
    return names.get(strategy, strategy.title())


def get_current_season_recommendation(season='2025/2026'):
    """Get the current recommended strategy for a season"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get latest recommendation for the season
        cursor.execute('''
            SELECT recommended_strategy
            FROM season_recommendations
            WHERE season = ?
            ORDER BY last_updated DESC
            LIMIT 1
        ''', (season,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0]
        else:
            # If no recommendation exists, return default
            return '2-1'

    except Exception as e:
        # If there's any error, return default strategy
        return '2-1'


def calculate_strategy_performance(fixtures_data, strategy):
    """Calculate performance metrics for a specific strategy"""
    total_points = 0
    correct_results = 0
    exact_scores = 0
    games_analyzed = len(fixtures_data)
    
    for fixture in fixtures_data:
        # Generate prediction using the same logic as frontend
        prediction = generate_prediction_for_fixture(fixture, strategy)
        
        actual_home = fixture['actual_home_goals']
        actual_away = fixture['actual_away_goals']
        pred_home = prediction['homeScore']
        pred_away = prediction['awayScore']
        
        # Calculate points
        points = 0
        
        # Exact score (2 points)
        if actual_home == pred_home and actual_away == pred_away:
            points = 2
            exact_scores += 1
            correct_results += 1
        # Correct result (1 point)
        elif ((actual_home > actual_away and pred_home > pred_away) or
              (actual_home < actual_away and pred_home < pred_away) or
              (actual_home == actual_away and pred_home == pred_away)):
            points = 1
            correct_results += 1
        
        total_points += points
    
    accuracy_rate = (correct_results / games_analyzed * 100) if games_analyzed > 0 else 0
    avg_points_per_game = total_points / games_analyzed if games_analyzed > 0 else 0
    
    return {
        'total_points': total_points,
        'correct_results': correct_results,
        'exact_scores': exact_scores,
        'games_analyzed': games_analyzed,
        'accuracy_rate': accuracy_rate,
        'avg_points_per_game': avg_points_per_game
    }


def generate_prediction_for_fixture(fixture, strategy):
    """Generate prediction for a fixture using specified strategy (backend version of frontend logic)"""
    home_odds = float(fixture['home_odds']) if fixture['home_odds'] else 999
    away_odds = float(fixture['away_odds']) if fixture['away_odds'] else 999
    
    home_score = 1
    away_score = 1
    
    if strategy == 'fixed':
        if home_odds <= away_odds:
            home_score = 2
            away_score = 1
        else:
            home_score = 1
            away_score = 2

    elif strategy == 'adaptive':
        # Get current season recommendation to determine which strategy to use
        season = fixture.get('season', '2025/2026')
        recommended_strategy = get_current_season_recommendation(season)

        if recommended_strategy == '1-0':
            # Use 1-0 strategy
            if home_odds <= away_odds:
                home_score = 1
                away_score = 0
            else:
                home_score = 0
                away_score = 1
        else:
            # Default to 2-1 strategy
            if home_odds <= away_odds:
                home_score = 2
                away_score = 1
            else:
                home_score = 1
                away_score = 2

    elif strategy == 'fixed-2-0':
        if home_odds <= away_odds:
            home_score = 2
            away_score = 0
        else:
            home_score = 0
            away_score = 2
            
    elif strategy == 'fixed-1-0':
        if home_odds <= away_odds:
            home_score = 1
            away_score = 0
        else:
            home_score = 0
            away_score = 1
            
    elif strategy == 'calibrated':
        favourite_odds = min(home_odds, away_odds)
        is_home_fav = home_odds <= away_odds
        
        if favourite_odds <= 1.50:
            home_score, away_score = (3, 0) if is_home_fav else (0, 3)
        elif favourite_odds <= 2.00:
            home_score, away_score = (2, 1) if is_home_fav else (1, 2)
        elif favourite_odds <= 2.50:
            home_score, away_score = (1, 0) if is_home_fav else (0, 1)
        else:
            home_score, away_score = 1, 1
            
    elif strategy == 'home-away':
        if home_odds <= away_odds:
            home_score = 2
            away_score = 0  # Home favourite
        else:
            home_score = 1
            away_score = 2  # Away favourite
            
    elif strategy == 'poisson':
        # Placeholder - using calibrated logic for now
        favourite_odds = min(home_odds, away_odds)
        is_home_fav = home_odds <= away_odds
        
        if favourite_odds <= 1.50:
            home_score, away_score = (2, 0) if is_home_fav else (0, 2)
        elif favourite_odds <= 2.00:
            home_score, away_score = (2, 1) if is_home_fav else (1, 2)
        else:
            home_score, away_score = (1, 0) if is_home_fav else (0, 1)
            
    elif strategy == 'smart-goals':
        # Combined 1X2 + Over/Under strategy
        favourite_odds = min(home_odds, away_odds)
        is_home_fav = home_odds <= away_odds
        
        # Get Over/Under odds (fallback to defaults if missing or None)
        over_2_5_odds = float(fixture.get('over_2_5_odds') or 1.90)
        under_2_5_odds = float(fixture.get('under_2_5_odds') or 1.90)
        
        # Determine if Over 2.5 is favoured (lower odds = more likely)
        goals_favoured_high = over_2_5_odds < under_2_5_odds
        
        if favourite_odds <= 1.60:  # Short favourite
            if goals_favoured_high:
                # Over 2.5 is favoured - predict higher scoring
                if over_2_5_odds <= 1.50:  # Very heavy over 2.5
                    home_score, away_score = (3, 1) if is_home_fav else (1, 3)
                else:
                    home_score, away_score = (2, 1) if is_home_fav else (1, 2)
            else:
                # Under 2.5 favoured - predict low scoring
                home_score, away_score = (1, 0) if is_home_fav else (0, 1)
        elif favourite_odds <= 2.20:  # Moderate favourite
            if goals_favoured_high:
                home_score, away_score = (2, 1) if is_home_fav else (1, 2)
            else:
                home_score, away_score = (1, 0) if is_home_fav else (0, 1)
        else:
            # Close match - use totals market as main indicator
            if goals_favoured_high:
                home_score, away_score = (2, 1) if is_home_fav else (1, 2)
            else:
                home_score, away_score = 1, 1  # Conservative draw prediction
    
    return {'homeScore': home_score, 'awayScore': away_score}


# Helper Functions
def get_predictions_progress(cursor) -> Dict:
    """Get predictions submission progress for upcoming gameweeks"""
    progress_data = {'current': {}, 'next': {}}
    
    try:
        # Get current gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE current_gameweek = 1")
        current_gw_result = cursor.fetchone()
        current_gameweek = current_gw_result[0] if current_gw_result else None
        
        # Get next gameweek  
        cursor.execute("SELECT gameweek FROM gameweeks WHERE next_gameweek = 1")
        next_gw_result = cursor.fetchone()
        next_gameweek = next_gw_result[0] if next_gw_result else None
        
        # Get total active players
        cursor.execute("SELECT COUNT(*) FROM players WHERE active = 1")
        total_active_players = cursor.fetchone()[0]
        
        # Process current gameweek
        if current_gameweek:
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (current_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            # Count players with complete valid predictions
            cursor.execute("""
                SELECT COUNT(*) as players_with_complete_predictions
                FROM (
                    SELECT p.player_id
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    JOIN players pl ON p.player_id = pl.player_id
                    WHERE f.gameweek = ? AND f.season = '2025/2026' AND pl.active = 1
                    GROUP BY p.player_id
                    HAVING COUNT(*) = ? AND SUM(CASE WHEN p.home_goals != 9 OR p.away_goals != 9 THEN 1 ELSE 0 END) = ?
                )
            """, (current_gameweek, total_fixtures, total_fixtures))
            
            complete_players_result = cursor.fetchone()
            players_with_complete = complete_players_result[0] if complete_players_result else 0
            
            progress_data['current'] = {
                'gameweek': current_gameweek,
                'total_players': total_active_players,
                'players_completed': players_with_complete,
                'completion_rate': round((players_with_complete / total_active_players * 100) if total_active_players > 0 else 0, 1)
            }
        
        # Process next gameweek
        if next_gameweek:
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (next_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            # Count players with complete valid predictions
            cursor.execute("""
                SELECT COUNT(*) as players_with_complete_predictions
                FROM (
                    SELECT p.player_id
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    JOIN players pl ON p.player_id = pl.player_id
                    WHERE f.gameweek = ? AND f.season = '2025/2026' AND pl.active = 1
                    GROUP BY p.player_id
                    HAVING COUNT(*) = ? AND SUM(CASE WHEN p.home_goals != 9 OR p.away_goals != 9 THEN 1 ELSE 0 END) = ?
                )
            """, (next_gameweek, total_fixtures, total_fixtures))
            
            complete_players_result = cursor.fetchone()
            players_with_complete = complete_players_result[0] if complete_players_result else 0
            
            progress_data['next'] = {
                'gameweek': next_gameweek,
                'total_players': total_active_players,
                'players_completed': players_with_complete,
                'completion_rate': round((players_with_complete / total_active_players * 100) if total_active_players > 0 else 0, 1)
            }
            
    except Exception as e:
        print(f"Error getting predictions progress: {e}")
        
    return progress_data

def get_players_missing_predictions(cursor) -> Dict:
    """Get players missing predictions for current and next gameweeks"""
    missing_data = {'current': {}, 'next': {}}
    
    try:
        # Get current gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE current_gameweek = 1")
        current_gw_result = cursor.fetchone()
        current_gameweek = current_gw_result[0] if current_gw_result else None
        
        # Get next gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE next_gameweek = 1")
        next_gw_result = cursor.fetchone()
        next_gameweek = next_gw_result[0] if next_gw_result else None
        
        # Process current gameweek
        if current_gameweek:
            missing_data['current']['gameweek'] = current_gameweek
            
            # Get total fixtures for current gameweek in current season
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (current_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            # Get all active players
            cursor.execute("SELECT player_id, player_name FROM players WHERE active = 1 ORDER BY player_name")
            active_players = cursor.fetchall()
            
            players_missing = []
            players_with_invalid = []
            
            for player_id, player_name in active_players:
                # Check predictions for this player in current gameweek
                cursor.execute("""
                    SELECT COUNT(*) as total_predictions,
                           SUM(CASE WHEN home_goals != 9 OR away_goals != 9 THEN 1 ELSE 0 END) as valid_predictions
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    WHERE p.player_id = ? AND f.gameweek = ? AND f.season = '2025/2026'
                """, (player_id, current_gameweek))
                
                result = cursor.fetchone()
                total_predictions = result[0] if result else 0
                valid_predictions = result[1] if result else 0
                
                if total_predictions < total_fixtures:
                    players_missing.append({
                        'player_name': player_name,
                        'predictions_count': total_predictions,
                        'total_fixtures': total_fixtures,
                        'missing_count': total_fixtures - total_predictions
                    })
                elif valid_predictions < total_fixtures and total_predictions == total_fixtures:
                    # Player has all predictions but some are still 9-9 (incomplete)
                    players_with_invalid.append({
                        'player_name': player_name,
                        'valid_count': valid_predictions,
                        'total_fixtures': total_fixtures,
                        'invalid_count': total_fixtures - valid_predictions
                    })
            
            missing_data['current']['players_missing'] = players_missing
            missing_data['current']['players_with_invalid'] = players_with_invalid
        
        # Process next gameweek
        if next_gameweek:
            missing_data['next']['gameweek'] = next_gameweek
            
            # Get total fixtures for next gameweek
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (next_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            # Get all active players
            cursor.execute("SELECT player_id, player_name FROM players WHERE active = 1 ORDER BY player_name")
            active_players = cursor.fetchall()
            
            players_missing = []
            players_with_invalid = []
            
            for player_id, player_name in active_players:
                # Check predictions for this player in next gameweek
                cursor.execute("""
                    SELECT COUNT(*) as total_predictions,
                           SUM(CASE WHEN home_goals != 9 OR away_goals != 9 THEN 1 ELSE 0 END) as valid_predictions
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    WHERE p.player_id = ? AND f.gameweek = ? AND f.season = '2025/2026'
                """, (player_id, next_gameweek))
                
                result = cursor.fetchone()
                total_predictions = result[0] if result else 0
                valid_predictions = result[1] if result else 0
                
                if total_predictions < total_fixtures:
                    players_missing.append({
                        'player_name': player_name,
                        'predictions_count': total_predictions,
                        'total_fixtures': total_fixtures,
                        'missing_count': total_fixtures - total_predictions
                    })
                elif valid_predictions < total_fixtures and total_predictions == total_fixtures:
                    # Player has all predictions but some are still 9-9 (incomplete)
                    players_with_invalid.append({
                        'player_name': player_name,
                        'valid_count': valid_predictions,
                        'total_fixtures': total_fixtures,
                        'invalid_count': total_fixtures - valid_predictions
                    })
            
            missing_data['next']['players_missing'] = players_missing
            missing_data['next']['players_with_invalid'] = players_with_invalid
    
    except Exception as e:
        print(f"Error getting missing predictions: {e}")
        missing_data = {'current': {}, 'next': {}}
    
    return missing_data


def get_players_with_identical_predictions(cursor) -> Dict:
    """Get players with identical predictions across all fixtures in current and next gameweeks"""
    identical_data = {'current': {}, 'next': {}}
    
    try:
        # Get current gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE current_gameweek = 1")
        current_gw_result = cursor.fetchone()
        current_gameweek = current_gw_result[0] if current_gw_result else None
        
        # Get next gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE next_gameweek = 1")
        next_gw_result = cursor.fetchone()
        next_gameweek = next_gw_result[0] if next_gw_result else None
        
        # Process current gameweek
        if current_gameweek:
            identical_data['current']['gameweek'] = current_gameweek
            identical_data['current']['players_with_identical'] = []
            
            # Get players with identical predictions (excluding 9-9)
            cursor.execute("""
                SELECT 
                    pl.player_name,
                    p.home_goals,
                    p.away_goals,
                    COUNT(*) as prediction_count,
                    GROUP_CONCAT(t_home.short_name || ' vs ' || t_away.short_name) as fixtures
                FROM predictions p
                JOIN fixtures f ON p.fixture_id = f.fixture_id
                JOIN players pl ON p.player_id = pl.player_id
                JOIN teams t_home ON f.home_teamid = t_home.team_id
                JOIN teams t_away ON f.away_teamid = t_away.team_id
                WHERE f.gameweek = ? AND f.season = '2025/2026'
                  AND NOT (p.home_goals = 9 AND p.away_goals = 9)
                  AND pl.active = 1
                GROUP BY p.player_id, p.home_goals, p.away_goals
                HAVING COUNT(*) > 1
                ORDER BY pl.player_name, COUNT(*) DESC
            """, (current_gameweek,))
            
            current_results = cursor.fetchall()
            
            # Group by player to check if ALL their predictions are identical
            current_player_data = {}
            for row in current_results:
                player_name = row[0]
                if player_name not in current_player_data:
                    current_player_data[player_name] = []
                current_player_data[player_name].append({
                    'home_goals': row[1],
                    'away_goals': row[2],
                    'count': row[3],
                    'fixtures': row[4].split(',') if row[4] else []
                })
            
            # Check total fixtures for current gameweek
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (current_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            for player_name, predictions in current_player_data.items():
                # Check if player has only one prediction pattern covering all fixtures
                if len(predictions) == 1 and predictions[0]['count'] == total_fixtures:
                    identical_data['current']['players_with_identical'].append({
                        'player_name': player_name,
                        'prediction': f"{predictions[0]['home_goals']}-{predictions[0]['away_goals']}",
                        'fixture_count': predictions[0]['count'],
                        'total_fixtures': total_fixtures
                    })
        
        # Process next gameweek
        if next_gameweek:
            identical_data['next']['gameweek'] = next_gameweek
            identical_data['next']['players_with_identical'] = []
            
            # Get players with identical predictions (excluding 9-9)
            cursor.execute("""
                SELECT 
                    pl.player_name,
                    p.home_goals,
                    p.away_goals,
                    COUNT(*) as prediction_count,
                    GROUP_CONCAT(t_home.short_name || ' vs ' || t_away.short_name) as fixtures
                FROM predictions p
                JOIN fixtures f ON p.fixture_id = f.fixture_id
                JOIN players pl ON p.player_id = pl.player_id
                JOIN teams t_home ON f.home_teamid = t_home.team_id
                JOIN teams t_away ON f.away_teamid = t_away.team_id
                WHERE f.gameweek = ? AND f.season = '2025/2026'
                  AND NOT (p.home_goals = 9 AND p.away_goals = 9)
                  AND pl.active = 1
                GROUP BY p.player_id, p.home_goals, p.away_goals
                HAVING COUNT(*) > 1
                ORDER BY pl.player_name, COUNT(*) DESC
            """, (next_gameweek,))
            
            next_results = cursor.fetchall()
            
            # Group by player to check if ALL their predictions are identical
            next_player_data = {}
            for row in next_results:
                player_name = row[0]
                if player_name not in next_player_data:
                    next_player_data[player_name] = []
                next_player_data[player_name].append({
                    'home_goals': row[1],
                    'away_goals': row[2],
                    'count': row[3],
                    'fixtures': row[4].split(',') if row[4] else []
                })
            
            # Check total fixtures for next gameweek
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ? AND season = '2025/2026'", (next_gameweek,))
            total_fixtures = cursor.fetchone()[0]
            
            for player_name, predictions in next_player_data.items():
                # Check if player has only one prediction pattern covering all fixtures
                if len(predictions) == 1 and predictions[0]['count'] == total_fixtures:
                    identical_data['next']['players_with_identical'].append({
                        'player_name': player_name,
                        'prediction': f"{predictions[0]['home_goals']}-{predictions[0]['away_goals']}",
                        'fixture_count': predictions[0]['count'],
                        'total_fixtures': total_fixtures
                    })
    
    except Exception as e:
        print(f"Error getting identical predictions: {e}")
        identical_data = {'current': {}, 'next': {}}

    return identical_data


def get_verification_mismatches(cursor) -> Dict:
    """Get prediction verification mismatches grouped by gameweek"""
    mismatches = {}

    try:
        # Get score mismatches from verification table
        cursor.execute("""
            SELECT
                f.gameweek,
                p.player_name,
                ht.team_name || ' vs ' || at.team_name as fixture,
                pv.db_home_goals || '-' || pv.db_away_goals as db_score,
                pv.message_home_goals || '-' || pv.message_away_goals as message_score,
                pv.verified_at
            FROM prediction_verification pv
            JOIN players p ON pv.player_id = p.player_id
            JOIN fixtures f ON pv.fixture_id = f.fixture_id
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            WHERE pv.category = 'Score Mismatch'
            AND f.season = '2025/2026'
            AND (pv.acknowledged IS NULL OR pv.acknowledged = 0)
            ORDER BY f.gameweek DESC, p.player_name
        """)

        results = cursor.fetchall()

        for row in results:
            gameweek = row[0]
            if gameweek not in mismatches:
                mismatches[gameweek] = []

            mismatches[gameweek].append({
                'player_name': row[1],
                'fixture': row[2],
                'db_score': row[3],
                'message_score': row[4],
                'verified_at': row[5]
            })

    except Exception as e:
        print(f"Error getting verification mismatches: {e}")
        mismatches = {}

    return mismatches


def get_dashboard_stats(cursor) -> Dict:
    """Get dashboard statistics from database"""
    stats = {}
    
    try:
        # Player counts
        cursor.execute("SELECT COUNT(*) FROM players")
        stats['total_players'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM players WHERE active = 1")
        stats['active_players'] = cursor.fetchone()[0]
        
        # Fixture counts
        cursor.execute("SELECT COUNT(*) FROM fixtures WHERE season = '2025/2026'")
        stats['total_fixtures'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM fixtures WHERE season = '2025/2026' AND finished = 1")
        stats['completed_fixtures'] = cursor.fetchone()[0]
        
        # Current gameweek
        cursor.execute("SELECT gameweek FROM gameweeks WHERE current_gameweek = 1")
        result = cursor.fetchone()
        stats['current_gameweek'] = result[0] if result else None
        
        # Prediction counts
        cursor.execute("""
            SELECT COUNT(*) FROM predictions p 
            JOIN fixtures f ON p.fixture_id = f.fixture_id 
            WHERE f.season = '2025/2026'
        """)
        stats['total_predictions'] = cursor.fetchone()[0]
        
        # Recent predictions by gameweek
        cursor.execute("""
            SELECT f.gameweek, COUNT(*) as prediction_count
            FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.fixture_id
            WHERE f.season = '2025/2026'
            GROUP BY f.gameweek
            ORDER BY f.gameweek DESC
            LIMIT 5
        """)
        stats['recent_predictions'] = cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        stats = {}
    
    return stats


def get_recent_updates(cursor) -> List:
    """Get recent database updates with formatted timestamps"""
    try:
        cursor.execute("""
            SELECT table_name, updated, timestamp 
            FROM last_update 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        raw_updates = cursor.fetchall()
        
        # Convert to list of dictionaries with formatted timestamps
        formatted_updates = []
        for update in raw_updates:
            update_dict = {
                'table_name': update[0],
                'updated': update[1],
                'timestamp': update[2],
                'formatted_timestamp': 'Unknown'
            }
            
            # Format timestamp if available
            if update[2]:
                update_dict['formatted_timestamp'] = convert_to_uk_time(update[2], '%d/%m/%Y %H:%M %Z')
            
            formatted_updates.append(update_dict)
        
        return formatted_updates
    except Exception:
        return []


def get_future_gameweek_deadlines(cursor) -> List:
    """Get future gameweek deadlines (unfinished gameweeks)"""
    try:
        cursor.execute("""
            SELECT gameweek, deadline_dttm, current_gameweek, next_gameweek, finished
            FROM gameweeks
            WHERE finished = 0 OR finished IS NULL
            ORDER BY gameweek ASC
            LIMIT 10
        """)
        raw_deadlines = cursor.fetchall()

        formatted_deadlines = []
        for deadline in raw_deadlines:
            deadline_dict = {
                'gameweek': deadline[0],
                'deadline_dttm': deadline[1],
                'current_gameweek': deadline[2],
                'next_gameweek': deadline[3],
                'finished': deadline[4],
                'formatted_deadline': 'Unknown'
            }

            if deadline[1]:
                deadline_dict['formatted_deadline'] = convert_to_uk_time(deadline[1], '%a %d %b %Y, %H:%M')

            formatted_deadlines.append(deadline_dict)

        return formatted_deadlines
    except Exception:
        return []


def get_fpl_stats(cursor) -> Dict:
    """Get FPL statistics"""
    stats = {}
    
    try:
        # Total players in bootstrap
        cursor.execute("SELECT COUNT(*) FROM fpl_players_bootstrap WHERE season = '2025/2026'")
        stats['total_fpl_players'] = cursor.fetchone()[0]
        
        # Players by position
        cursor.execute("""
            SELECT position, COUNT(*) as count
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026'
            GROUP BY position
            ORDER BY 
                CASE position 
                    WHEN '1' THEN 1 -- GK
                    WHEN '2' THEN 2 -- DEF  
                    WHEN '3' THEN 3 -- MID
                    WHEN '4' THEN 4 -- FWD
                END
        """)
        stats['players_by_position'] = cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting FPL stats: {e}")
        stats = {}
    
    return stats


def get_top_fpl_players(cursor) -> Dict:
    """Get top FPL players by various metrics"""
    top_players = {}
    
    try:
        # Top scorers
        cursor.execute("""
            SELECT player_name, total_points, value, team_id
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND total_points > 0
            ORDER BY total_points DESC 
            LIMIT 10
        """)
        top_players['top_scorers'] = cursor.fetchall()
        
        # Most transferred in
        cursor.execute("""
            SELECT player_name, transfers_in, total_points, value
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND transfers_in > 0
            ORDER BY transfers_in DESC 
            LIMIT 10
        """)
        top_players['most_transferred'] = cursor.fetchall()
        
        # Top defensive contributions
        cursor.execute("""
            SELECT player_name, defensive_contribution, total_points, position
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND defensive_contribution > 0
            ORDER BY defensive_contribution DESC 
            LIMIT 10
        """)
        top_players['top_defensive'] = cursor.fetchall()
        
        # Top goal contributions (goals + assists)
        cursor.execute("""
            SELECT player_name, (goals_scored + assists) as goal_contributions, 
                   goals_scored, assists, total_points
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND (goals_scored + assists) > 0
            ORDER BY (goals_scored + assists) DESC 
            LIMIT 10
        """)
        top_players['top_goal_contributions'] = cursor.fetchall()
        
        # Top Expected Goal Involvements - higher is better for attacking players
        cursor.execute("""
            SELECT player_name, expected_goal_involvements, total_points, position, minutes
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND expected_goal_involvements > 0 AND minutes > 0
            ORDER BY expected_goal_involvements DESC 
            LIMIT 10
        """)
        top_players['top_xgi'] = cursor.fetchall()
        
        # Most selected by percent
        cursor.execute("""
            SELECT player_name, selected_by_percent, total_points, value
            FROM fpl_players_bootstrap 
            WHERE season = '2025/2026' AND selected_by_percent > 0
            ORDER BY selected_by_percent DESC 
            LIMIT 10
        """)
        top_players['most_selected'] = cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting top FPL players: {e}")
        top_players = {}
    
    return top_players


# ─── FPL My Team & Transfer Recommendation Helpers ───────────────────────────

def _fpl_cache_get(key, max_age=1800):
    """Get cached FPL API response if still fresh (default 30 min)"""
    if key in _fpl_api_cache:
        ts, data = _fpl_api_cache[key]
        if time.time() - ts < max_age:
            return data
    return None


def _fpl_cache_set(key, data):
    """Cache an FPL API response"""
    _fpl_api_cache[key] = (time.time(), data)


def get_current_fpl_gameweek(cursor):
    """Get the current/most recent finished gameweek number"""
    cursor.execute("""
        SELECT gameweek FROM gameweeks
        WHERE current_gameweek = 1
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        return row[0]
    # Fallback: highest finished gameweek
    cursor.execute("""
        SELECT MAX(gameweek) FROM gameweeks WHERE finished = 1
    """)
    row = cursor.fetchone()
    return row[0] if row else 1


def fetch_fpl_entry(team_id):
    """Fetch manager profile from FPL API"""
    cache_key = f"entry_{team_id}"
    cached = _fpl_cache_get(cache_key)
    if cached:
        return cached

    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/"
    response = http_requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    _fpl_cache_set(cache_key, data)
    return data


def fetch_fpl_picks(team_id, gameweek):
    """Fetch team picks for a specific gameweek from FPL API"""
    cache_key = f"picks_{team_id}_{gameweek}"
    cached = _fpl_cache_get(cache_key)
    if cached:
        return cached

    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
    response = http_requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    _fpl_cache_set(cache_key, data)
    return data


def fetch_fpl_history(team_id):
    """Fetch manager's season history from FPL API"""
    cache_key = f"history_{team_id}"
    cached = _fpl_cache_get(cache_key)
    if cached:
        return cached

    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/history/"
    response = http_requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    _fpl_cache_set(cache_key, data)
    return data


def calculate_free_transfers(history_data):
    """Calculate free transfers available based on gameweek history and chips used"""
    chip_reset_events = set()
    for chip in history_data.get('chips', []):
        if chip.get('name') in ('wildcard', 'freehit'):
            chip_reset_events.add(chip['event'])

    free_transfers = 1
    for gw in history_data.get('current', []):
        event = gw['event']
        if event in chip_reset_events:
            free_transfers = 1
            continue
        transfers_made = gw.get('event_transfers', 0)
        free_transfers = max(1, min(free_transfers - transfers_made + 1, 5))

    return free_transfers


def load_fpl_optimizer_data(db_path):
    """Load all eligible players with blended scores (ported from fpl_optimizer.py)"""
    conn = sqlite3.connect(db_path)

    df = pd.read_sql_query("""
        SELECT p.player_id, p.player_name, p.position, p.total_points, p.value,
               p.team_id, p.db_team_id, p.minutes, p.status,
               p.saves, p.clean_sheets, p.goals_scored, p.assists,
               p.expected_goals, p.expected_assists, p.expected_goal_involvements,
               p.defensive_contribution, p.bonus, p.bps, p.form, p.points_per_game,
               t.team_name
        FROM fpl_players_bootstrap p
        LEFT JOIN teams t ON p.db_team_id = t.team_id
        WHERE p.can_select = 1 AND p.minutes > 0
    """, conn)

    # Get max gameweek for form calculation
    max_gw = pd.read_sql_query(
        "SELECT MAX(gameweek) as max_gw FROM fantasy_pl_scores", conn
    ).iloc[0]["max_gw"]
    total_gws = int(max_gw) if max_gw else 26
    min_gw = total_gws - FPL_FORM_GWS + 1

    # Load form data (last 5 gameweeks)
    gw_data = pd.read_sql_query(f"""
        SELECT player_id, AVG(total_points) as avg_pts_last5
        FROM fantasy_pl_scores
        WHERE gameweek BETWEEN {min_gw} AND {total_gws}
        GROUP BY player_id
    """, conn)

    conn.close()

    df = df.merge(gw_data, on="player_id", how="left")
    df["avg_pts_last5"] = df["avg_pts_last5"].fillna(0)

    # Blended score: 60% season + 40% recent form projected over full season
    df["blended"] = (
        (1 - FPL_FORM_WEIGHT) * df["total_points"]
        + FPL_FORM_WEIGHT * (df["avg_pts_last5"] * total_gws)
    )

    return df, total_gws


def optimize_fpl_squad(df, score_col="blended"):
    """Find optimal 15-player squad using LP solver (ported from fpl_optimizer.py)"""
    prob = LpProblem("FPL_Optimal", LpMaximize)

    player_vars = {
        row.player_id: LpVariable(f"x_{row.player_id}", cat="Binary")
        for _, row in df.iterrows()
    }

    # Objective: maximize the chosen score column
    prob += lpSum(
        player_vars[row.player_id] * getattr(row, score_col)
        for _, row in df.iterrows()
    )

    # Budget constraint: use max possible budget (1000 = £100m)
    budget = 1000
    prob += lpSum(
        player_vars[row.player_id] * row.value
        for _, row in df.iterrows()
    ) <= budget

    # Position constraints
    for pos, count in FPL_POSITION_REQUIREMENTS.items():
        prob += lpSum(
            player_vars[row.player_id]
            for _, row in df[df.position == pos].iterrows()
        ) == count

    # Max 3 players per team
    for team_id in df.team_id.unique():
        prob += lpSum(
            player_vars[row.player_id]
            for _, row in df[df.team_id == team_id].iterrows()
        ) <= FPL_MAX_PER_TEAM

    prob.solve(PULP_CBC_CMD(msg=0))

    selected_ids = [
        pid for pid, var in player_vars.items() if var.varValue == 1
    ]
    return df[df.player_id.isin(selected_ids)].copy()


def recommend_transfers(current_ids, optimal_squad_df, all_players_df, bank, free_transfers):
    """Recommend transfers by comparing current squad to optimal, limited by free transfers"""
    optimal_ids = set(optimal_squad_df.player_id)
    current_set = set(current_ids)

    # Players to potentially swap out (in current but not in optimal)
    potential_outs = current_set - optimal_ids
    # Players to potentially swap in (in optimal but not in current)
    potential_ins = optimal_ids - current_set

    if not potential_outs or not potential_ins:
        return []

    current_df = all_players_df[all_players_df.player_id.isin(current_set)]
    # Count players per team in current squad
    team_counts = current_df.groupby('team_id').size().to_dict()

    transfers = []
    out_players = all_players_df[all_players_df.player_id.isin(potential_outs)]
    in_players = all_players_df[all_players_df.player_id.isin(potential_ins)]

    # Generate all valid (out, in) pairs at the same position
    for _, out_p in out_players.iterrows():
        for _, in_p in in_players[in_players.position == out_p.position].iterrows():
            cost_change = in_p.value - out_p.value
            score_gain = in_p.blended - out_p.blended
            if score_gain <= 0:
                continue
            transfers.append({
                'out_id': out_p.player_id,
                'in_id': in_p.player_id,
                'out': {
                    'player_id': int(out_p.player_id),
                    'player_name': out_p.player_name,
                    'position': FPL_POSITION_NAMES.get(str(out_p.position), str(out_p.position)),
                    'team_name': out_p.team_name,
                    'total_points': int(out_p.total_points),
                    'value': float(out_p.value),
                    'blended': round(float(out_p.blended), 1),
                    'form': str(out_p.form),
                },
                'in': {
                    'player_id': int(in_p.player_id),
                    'player_name': in_p.player_name,
                    'position': FPL_POSITION_NAMES.get(str(in_p.position), str(in_p.position)),
                    'team_name': in_p.team_name,
                    'total_points': int(in_p.total_points),
                    'value': float(in_p.value),
                    'blended': round(float(in_p.blended), 1),
                    'form': str(in_p.form),
                },
                'score_gain': round(float(score_gain), 1),
                'cost_change': float(cost_change),
            })

    # Sort by score gain descending
    transfers.sort(key=lambda t: t['score_gain'], reverse=True)

    # Greedily pick top N transfers respecting constraints
    selected = []
    used_outs = set()
    used_ins = set()
    running_bank = bank

    for t in transfers:
        if len(selected) >= free_transfers:
            break
        if t['out_id'] in used_outs or t['in_id'] in used_ins:
            continue
        if t['cost_change'] > running_bank:
            continue

        # Check team limit: after removing out_player's team count and adding in_player's
        out_team = all_players_df[all_players_df.player_id == t['out_id']].iloc[0].team_id
        in_team = all_players_df[all_players_df.player_id == t['in_id']].iloc[0].team_id
        if out_team != in_team:
            current_in_team_count = team_counts.get(in_team, 0)
            if current_in_team_count >= FPL_MAX_PER_TEAM:
                continue

        selected.append(t)
        used_outs.add(t['out_id'])
        used_ins.add(t['in_id'])
        running_bank -= t['cost_change']

        # Update team counts for subsequent checks
        if out_team != in_team:
            team_counts[out_team] = team_counts.get(out_team, 1) - 1
            team_counts[in_team] = team_counts.get(in_team, 0) + 1

    # Clean up internal fields before returning
    for t in selected:
        del t['out_id']
        del t['in_id']

    return selected


def execute_script(script_key: str, script_info: Dict):
    """Execute a script in background and track status"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle absolute vs relative paths properly
    if Path(config['scripts_path']).is_absolute():
        script_path = Path(config['scripts_path']) / script_info['path']
    else:
        script_path = Path(__file__).parent / config['scripts_path'] / script_info['path']
    
    if Path(config['venv_path']).is_absolute():
        venv_python = Path(config['venv_path'])
    else:
        venv_python = Path(__file__).parent / config['venv_path']
    
    timeout = script_info.get('timeout', config.get('script_timeout', 300))
    
    # Debug logging
    logger.info(f"Executing script: {script_key}")
    logger.info(f"Script path: {script_path}")
    logger.info(f"Script exists: {script_path.exists()}")
    logger.info(f"Python venv: {venv_python}")
    logger.info(f"Python exists: {venv_python.exists()}")
    logger.info(f"Timeout: {timeout}s")
    
    # Initialize status
    script_status[script_key] = {
        'running': True,
        'start_time': datetime.now().isoformat(),
        'output': [],
        'error': None,
        'returncode': None
    }
    
    try:
        # Set working directory to project root (parent of scripts directory)
        if Path(config['scripts_path']).is_absolute():
            project_root = Path(config['scripts_path']).parent
        else:
            project_root = Path(__file__).parent / config['scripts_path']
            project_root = project_root.parent
        
        logger.info(f"Working directory: {project_root}")
        logger.info(f"Working directory exists: {project_root.exists()}")
        
        # Execute script
        cmd = [str(venv_python), str(script_path)]
        logger.info(f"Command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=str(project_root)
        )
        
        logger.info(f"Process started with PID: {process.pid}")
        
        # Read output in real-time
        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")
                script_status[script_key]['output'] = output_lines[-50:]  # Keep last 50 lines
        
        # Wait for completion
        returncode = process.wait(timeout=timeout)
        
        # Capture any remaining stderr
        stderr_output = process.stderr.read().strip()
        if stderr_output:
            output_lines.append(f"ERROR: {stderr_output}")
        
        script_status[script_key].update({
            'running': False,
            'end_time': datetime.now().isoformat(),
            'returncode': returncode,
            'output': output_lines[-50:],
            'success': returncode == 0
        })
        
    except subprocess.TimeoutExpired:
        process.kill()
        script_status[script_key].update({
            'running': False,
            'end_time': datetime.now().isoformat(),
            'error': f'Script timed out after {timeout} seconds',
            'returncode': -1,
            'success': False
        })
        
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        logger.exception("Full traceback:")
        script_status[script_key].update({
            'running': False,
            'end_time': datetime.now().isoformat(),
            'error': str(e),
            'returncode': -1,
            'success': False,
            'output': [f"ERROR: {str(e)}"]
        })


@app.route('/analysis')
def analysis():
    """Analysis dashboard with interactive cards"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get basic stats for overview
        cursor.execute("""
            SELECT COUNT(DISTINCT p.player_id) as players, 
                   COUNT(*) as total_predictions,
                   COUNT(DISTINCT f.season) as seasons
            FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.fixture_id
        """)
        stats = cursor.fetchone()
        
        # Get current season info
        current_season = '2025/2026'
        cursor.execute("""
            SELECT MAX(f.gameweek) as current_gameweek,
                   COUNT(DISTINCT f.fixture_id) as completed_fixtures
            FROM fixtures f 
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE f.season = ? AND f.finished = 1
        """, (current_season,))
        season_info = cursor.fetchone()
        
        conn.close()
        
        return render_template('analysis.html', 
                             stats=stats, 
                             season_info=season_info,
                             current_season=current_season,
                             page_title='Analysis Dashboard')
        
    except Exception as e:
        flash(f"Database error: {str(e)}", 'error')
        return render_template('analysis.html', 
                             stats=None, 
                             season_info=None,
                             current_season='2025/2026',
                             page_title='Analysis Dashboard')


@app.route('/api/analysis/standings')
def api_standings():
    """API endpoint for current season standings"""
    try:
        season = request.args.get('season', '2025/2026')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                pl.player_name,
                COUNT(DISTINCT pred.fixture_id) as predictions_made,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as total_points,
                SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as correct_results,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as ppg
            FROM players pl
            JOIN predictions pred ON pl.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE f.season = ?
            AND f.finished = 1
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
            GROUP BY pl.player_id, pl.player_name
            ORDER BY total_points DESC, exact_scores DESC, pl.player_name ASC
        """, (season,))
        
        standings = [
            {
                'rank': i + 1,
                'player_name': row[0],
                'predictions_made': row[1],
                'total_points': row[2] if row[2] else 0,
                'exact_scores': row[3] if row[3] else 0,
                'correct_results': row[4] if row[4] else 0,
                'ppg': round(row[5] if row[5] else 0, 2)
            }
            for i, row in enumerate(cursor.fetchall())
        ]
        
        conn.close()
        return jsonify({'standings': standings})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/scoreline-heatmap')
def api_scoreline_heatmap():
    """API endpoint for scoreline prediction heatmap"""
    try:
        season = request.args.get('season', '2025/2026')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get scoreline frequency and success rates
        cursor.execute("""
            SELECT 
                pred.home_goals,
                pred.away_goals,
                COUNT(*) as frequency,
                SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_hits,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as avg_points
            FROM predictions pred
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE f.season = ?
            AND f.finished = 1
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
            AND pred.home_goals <= 5 AND pred.away_goals <= 5  -- Limit to reasonable scores
            GROUP BY pred.home_goals, pred.away_goals
            ORDER BY frequency DESC
        """, (season,))
        
        heatmap_data = [
            {
                'home_goals': row[0],
                'away_goals': row[1],
                'frequency': row[2],
                'exact_hits': row[3],
                'success_rate': round((row[3] / row[2]) * 100, 1) if row[2] > 0 else 0,
                'avg_points': round(row[4] if row[4] else 0, 2)
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({'heatmap': heatmap_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/gameweek-trends')
def api_gameweek_trends():
    """API endpoint for gameweek performance trends"""
    try:
        season = request.args.get('season', '2025/2026')
        player = request.args.get('player', None)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if player:
            # Single player trends
            cursor.execute("""
                SELECT
                    f.gameweek,
                    SUM(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as points,
                    COUNT(*) as predictions,
                    AVG(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as ppg
                FROM players pl
                JOIN predictions pred ON pl.player_id = pred.player_id
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                JOIN results r ON f.fixture_id = r.fixture_id
                WHERE f.season = ? AND pl.player_name = ?
                AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
                GROUP BY f.gameweek
                ORDER BY f.gameweek
            """, (season, player))
        else:
            # League average trends
            cursor.execute("""
                SELECT
                    f.gameweek,
                    AVG(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as avg_ppg,
                    COUNT(DISTINCT pl.player_id) as players,
                    COUNT(*) as total_predictions
                FROM players pl
                JOIN predictions pred ON pl.player_id = pred.player_id
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                JOIN results r ON f.fixture_id = r.fixture_id
                WHERE f.season = ?
                AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
                GROUP BY f.gameweek
                ORDER BY f.gameweek
            """, (season,))
        
        trends = [
            {
                'gameweek': row[0],
                'points': row[1] if player else None,
                'predictions': row[2] if player else row[3],
                'ppg': round(row[3] if player else row[1], 2),
                'players': None if player else row[2]
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({'trends': trends, 'player': player})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/player-comparison')
def api_player_comparison():
    """API endpoint for player vs player comparison"""
    try:
        player1 = request.args.get('player1')
        player2 = request.args.get('player2')
        season = request.args.get('season', '2025/2026')
        
        if not player1 or not player2:
            return jsonify({'error': 'Both player1 and player2 parameters required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get head-to-head comparison for specific matches
        cursor.execute("""
            SELECT
                f.gameweek,
                t1.team_name as home_team,
                t2.team_name as away_team,
                r.home_goals,
                r.away_goals,
                p1.home_goals as p1_home_pred,
                p1.away_goals as p1_away_pred,
                CASE
                    WHEN p1.home_goals = r.home_goals AND p1.away_goals = r.away_goals THEN 2
                    WHEN (p1.home_goals > p1.away_goals AND r.home_goals > r.away_goals)
                         OR (p1.home_goals < p1.away_goals AND r.home_goals < r.away_goals)
                         OR (p1.home_goals = p1.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END as p1_points,
                p2.home_goals as p2_home_pred,
                p2.away_goals as p2_away_pred,
                CASE
                    WHEN p2.home_goals = r.home_goals AND p2.away_goals = r.away_goals THEN 2
                    WHEN (p2.home_goals > p2.away_goals AND r.home_goals > r.away_goals)
                         OR (p2.home_goals < p2.away_goals AND r.home_goals < r.away_goals)
                         OR (p2.home_goals = p2.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END as p2_points
            FROM fixtures f
            JOIN results r ON f.fixture_id = r.fixture_id
            JOIN teams t1 ON f.home_teamid = t1.team_id
            JOIN teams t2 ON f.away_teamid = t2.team_id
            JOIN predictions p1 ON f.fixture_id = p1.fixture_id
            JOIN players pl1 ON p1.player_id = pl1.player_id
            LEFT JOIN predictions p2 ON f.fixture_id = p2.fixture_id
            LEFT JOIN players pl2 ON p2.player_id = pl2.player_id
            WHERE pl1.player_name = ? AND pl2.player_name = ?
            AND f.season = ? AND f.finished = 1
            AND p1.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
            AND p2.home_goals IS NOT NULL
            ORDER BY f.gameweek, f.fixture_id
        """, (player1, player2, season))
        
        matches = [
            {
                'gameweek': row[0],
                'home_team': row[1],
                'away_team': row[2],
                'actual_score': f"{row[3]}-{row[4]}",
                'player1_prediction': f"{row[5]}-{row[6]}",
                'player1_points': row[7],
                'player2_prediction': f"{row[8]}-{row[9]}",
                'player2_points': row[10]
            }
            for row in cursor.fetchall()
        ]
        
        # Get overall comparison stats
        cursor.execute("""
            SELECT 
                pl.player_name,
                COUNT(DISTINCT pred.fixture_id) as predictions_made,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as total_points,
                SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as ppg
            FROM players pl
            JOIN predictions pred ON pl.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE pl.player_name IN (?, ?) AND f.season = ?
            AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
            GROUP BY pl.player_id, pl.player_name
            ORDER BY total_points DESC
        """, (player1, player2, season))
        
        stats = cursor.fetchall()
        
        comparison_stats = {}
        for row in stats:
            comparison_stats[row[0]] = {
                'predictions_made': row[1],
                'total_points': row[2] if row[2] else 0,
                'exact_scores': row[3] if row[3] else 0,
                'ppg': round(row[4] if row[4] else 0, 2)
            }
        
        conn.close()
        return jsonify({
            'matches': matches,
            'stats': comparison_stats,
            'player1': player1,
            'player2': player2
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/historical-performance')
def api_historical_performance():
    """API endpoint for historical performance comparison across seasons"""
    try:
        player = request.args.get('player')
        
        if not player:
            return jsonify({'error': 'Player parameter required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get performance by season for the specified player
        cursor.execute("""
            SELECT
                f.season,
                COUNT(DISTINCT pred.fixture_id) as predictions_made,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as total_points,
                SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as ppg,
                -- Calculate cumulative stats by gameweek for trend analysis
                MAX(f.gameweek) as max_gameweek
            FROM players pl
            JOIN predictions pred ON pl.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE pl.player_name = ?
            AND f.finished = 1
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
            GROUP BY f.season
            ORDER BY f.season
        """, (player,))
        
        performance_data = [
            {
                'season': row[0],
                'predictions_made': row[1],
                'total_points': row[2] if row[2] else 0,
                'exact_scores': row[3] if row[3] else 0,
                'ppg': round(row[4] if row[4] else 0, 2),
                'max_gameweek': row[5]
            }
            for row in cursor.fetchall()
        ]
        
        # Get cumulative points progression for each season (for chart)
        cumulative_data = {}
        for season_data in performance_data:
            season = season_data['season']
            
            cursor.execute("""
                SELECT
                    f.gameweek,
                    SUM(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as gameweek_points
                FROM players pl
                JOIN predictions pred ON pl.player_id = pred.player_id
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                JOIN results r ON f.fixture_id = r.fixture_id
                WHERE pl.player_name = ? AND f.season = ?
                AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
                GROUP BY f.gameweek
                ORDER BY f.gameweek
            """, (player, season))
            
            gameweek_data = cursor.fetchall()
            cumulative = 0
            cumulative_points = []
            
            for gw, points in gameweek_data:
                cumulative += points if points else 0
                cumulative_points.append({'gameweek': gw, 'cumulative_points': cumulative})
            
            cumulative_data[season] = cumulative_points
        
        conn.close()
        return jsonify({
            'performance': performance_data,
            'cumulative': cumulative_data,
            'player': player
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/seasons')
def api_seasons():
    """API endpoint to get all available seasons"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT season FROM fixtures ORDER BY season DESC")
        seasons = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return jsonify({'seasons': seasons})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/top-performers')
def api_top_performers():
    """API endpoint for top performers analysis"""
    try:
        season = request.args.get('season', '2025/2026')
        limit = int(request.args.get('limit', 5))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get top performers with detailed stats
        cursor.execute("""
            SELECT
                pl.player_name,
                COUNT(DISTINCT pred.fixture_id) as predictions_made,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as total_points,
                SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as correct_results,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as ppg,
                -- Most used scoreline
                (SELECT pred2.home_goals || '-' || pred2.away_goals 
                 FROM predictions pred2 
                 JOIN fixtures f2 ON pred2.fixture_id = f2.fixture_id
                 WHERE pred2.player_id = pl.player_id AND f2.season = ?
                 GROUP BY pred2.home_goals, pred2.away_goals 
                 ORDER BY COUNT(*) DESC LIMIT 1) as favorite_scoreline
            FROM players pl
            JOIN predictions pred ON pl.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE f.season = ?
            AND f.finished = 1
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
            GROUP BY pl.player_id, pl.player_name
            HAVING COUNT(DISTINCT pred.fixture_id) >= 5  -- Minimum 5 predictions
            ORDER BY total_points DESC, exact_scores DESC, ppg DESC
            LIMIT ?
        """, (season, season, limit))
        
        performers = [
            {
                'rank': i + 1,
                'player_name': row[0],
                'predictions_made': row[1],
                'total_points': row[2] if row[2] else 0,
                'exact_scores': row[3] if row[3] else 0,
                'correct_results': row[4] if row[4] else 0,
                'ppg': round(row[5] if row[5] else 0, 2),
                'favorite_scoreline': row[6] if row[6] else 'N/A'
            }
            for i, row in enumerate(cursor.fetchall())
        ]
        
        conn.close()
        return jsonify({'performers': performers, 'season': season})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis/result-types')
def api_result_types():
    """API endpoint for result type analysis (Home Win/Draw/Away Win)"""
    try:
        season = request.args.get('season', '2025/2026')
        player = request.args.get('player', None)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if player:
            # Individual player analysis
            cursor.execute("""
                SELECT
                    CASE
                        WHEN pred.home_goals > pred.away_goals THEN 'Home Win'
                        WHEN pred.home_goals < pred.away_goals THEN 'Away Win'
                        ELSE 'Draw'
                    END as predicted_result,
                    COUNT(*) as frequency,
                    SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_hits,
                    SUM(CASE
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as correct_results,
                    AVG(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as avg_points
                FROM players pl
                JOIN predictions pred ON pl.player_id = pred.player_id
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                JOIN results r ON f.fixture_id = r.fixture_id
                WHERE pl.player_name = ? AND f.season = ?
                AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
                GROUP BY predicted_result
                ORDER BY frequency DESC
            """, (player, season))
        else:
            # League-wide analysis
            cursor.execute("""
                SELECT
                    CASE
                        WHEN pred.home_goals > pred.away_goals THEN 'Home Win'
                        WHEN pred.home_goals < pred.away_goals THEN 'Away Win'
                        ELSE 'Draw'
                    END as predicted_result,
                    COUNT(*) as frequency,
                    SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_hits,
                    SUM(CASE
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as correct_results,
                    AVG(CASE
                        WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                        WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                             OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                             OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                        ELSE 0
                    END) as avg_points
                FROM predictions pred
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                JOIN results r ON f.fixture_id = r.fixture_id
                WHERE f.season = ?
                AND f.finished = 1 AND pred.home_goals IS NOT NULL AND r.home_goals IS NOT NULL
                GROUP BY predicted_result
                ORDER BY frequency DESC
            """, (season,))
        
        result_types = [
            {
                'result_type': row[0],
                'frequency': row[1],
                'exact_hits': row[2],
                'correct_results': row[3],
                'success_rate': round((row[3] / row[1]) * 100, 1) if row[1] > 0 else 0,
                'avg_points': round(row[4] if row[4] else 0, 2)
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return jsonify({
            'result_types': result_types,
            'season': season,
            'player': player
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Initialize application
if __name__ == '__main__':
    try:
        load_config()
        host = config.get('host', '127.0.0.1')
        port = config.get('port', 5000)
        debug = config.get('debug', False)

        print(f"Starting Prediction League Web App...")
        print(f"Access at: http://{host}:{port}")
        print(f"Admin password: {config['admin_password']}")

        app.run(host=host, port=port, debug=debug)

    except Exception as e:
        print(f"Failed to start application: {e}")
        print("Make sure config.json exists and database is accessible")

# Ensure config is loaded when running under gunicorn
if not config:
    load_config()
