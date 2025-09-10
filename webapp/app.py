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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

# Initialize Flask app
app = Flask(__name__)

# Global variables for configuration and state
config = {}
script_status = {}  # Track running scripts


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
        
        # Get players with identical predictions for current and next gameweeks
        identical_predictions = get_players_with_identical_predictions(cursor)
        
        conn.close()
        
        return render_template('dashboard.html', 
                             stats=stats, 
                             recent_updates=recent_updates,
                             missing_predictions=missing_predictions,
                             identical_predictions=identical_predictions,
                             page_title='Dashboard')
    
    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'error')
        return render_template('dashboard.html', 
                             stats={}, 
                             recent_updates=[],
                             missing_predictions={'current': {}, 'next': {}},
                             identical_predictions={'current': {}, 'next': {}},
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
                'kickoff_time': row[3],
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
@require_auth
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
        strategies = ['fixed', 'fixed-2-0', 'fixed-1-0', 'calibrated', 'home-away', 'poisson', 'smart-goals']
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


def get_strategy_display_name(strategy):
    """Get display name for strategy"""
    names = {
        'fixed': 'Fixed (2-1 Favourite)',
        'fixed-2-0': 'Fixed (2-0 Favourite)', 
        'fixed-1-0': 'Fixed (1-0 Favourite)',
        'calibrated': 'Calibrated Scorelines',
        'home-away': 'Home/Away Bias',
        'poisson': 'Poisson Model',
        'smart-goals': 'Smart Goals (1X2 + Over/Under)'
    }
    return names.get(strategy, strategy.title())


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
        
        # Get Over/Under odds (fallback to defaults if missing)
        over_2_5_odds = float(fixture.get('over_2_5_odds', 1.90))
        under_2_5_odds = float(fixture.get('under_2_5_odds', 1.90))
        
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
                           SUM(CASE WHEN home_goals = 9 AND away_goals = 9 THEN 1 ELSE 0 END) as invalid_predictions
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    WHERE p.player_id = ? AND f.gameweek = ? AND f.season = '2025/2026'
                """, (player_id, current_gameweek))
                
                result = cursor.fetchone()
                total_predictions = result[0] if result else 0
                invalid_predictions = result[1] if result else 0
                
                if total_predictions < total_fixtures:
                    players_missing.append({
                        'player_name': player_name,
                        'predictions_count': total_predictions,
                        'total_fixtures': total_fixtures,
                        'missing_count': total_fixtures - total_predictions
                    })
                elif invalid_predictions > 0:
                    players_with_invalid.append({
                        'player_name': player_name,
                        'invalid_count': invalid_predictions
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
                           SUM(CASE WHEN home_goals = 9 AND away_goals = 9 THEN 1 ELSE 0 END) as invalid_predictions
                    FROM predictions p
                    JOIN fixtures f ON p.fixture_id = f.fixture_id
                    WHERE p.player_id = ? AND f.gameweek = ? AND f.season = '2025/2026'
                """, (player_id, next_gameweek))
                
                result = cursor.fetchone()
                total_predictions = result[0] if result else 0
                invalid_predictions = result[1] if result else 0
                
                if total_predictions < total_fixtures:
                    players_missing.append({
                        'player_name': player_name,
                        'predictions_count': total_predictions,
                        'total_fixtures': total_fixtures,
                        'missing_count': total_fixtures - total_predictions
                    })
                elif invalid_predictions > 0:
                    players_with_invalid.append({
                        'player_name': player_name,
                        'invalid_count': invalid_predictions
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
                try:
                    # Convert Unix timestamp to datetime and format
                    dt = datetime.fromtimestamp(update[2])
                    update_dict['formatted_timestamp'] = dt.strftime('%d/%m/%Y %H:%M')
                except (ValueError, OSError):
                    # Keep 'Unknown' as fallback for invalid timestamps
                    pass
            
            formatted_updates.append(update_dict)
        
        return formatted_updates
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


def execute_script(script_key: str, script_info: Dict):
    """Execute a script in background and track status"""
    script_path = Path(__file__).parent / config['scripts_path'] / script_info['path']
    venv_python = Path(__file__).parent / config['venv_path']
    timeout = script_info.get('timeout', config.get('script_timeout', 300))
    
    # Initialize status
    script_status[script_key] = {
        'running': True,
        'start_time': datetime.now().isoformat(),
        'output': [],
        'error': None,
        'returncode': None
    }
    
    try:
        # Execute script
        process = subprocess.Popen(
            [str(venv_python), str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
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
        script_status[script_key].update({
            'running': False,
            'end_time': datetime.now().isoformat(),
            'error': str(e),
            'returncode': -1,
            'success': False
        })


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
