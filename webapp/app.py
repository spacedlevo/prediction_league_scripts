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
    config_path = Path( "/opt/prediction-league/config.json")
    
    if not config_path.exists():
        # Create default config from example
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


def get_db_connection():
    """Get SQLite database connection"""
    db_path = Path(__file__).parent / config['database_path']
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")
    
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
        
        conn.close()
        
        return render_template('dashboard.html', 
                             stats=stats, 
                             recent_updates=recent_updates,
                             missing_predictions=missing_predictions,
                             page_title='Dashboard')
    
    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'error')
        return render_template('dashboard.html', 
                             stats={}, 
                             recent_updates=[],
                             missing_predictions={'current': {}, 'next': {}},
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
            
            # Get total fixtures for current gameweek
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ?", (current_gameweek,))
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
                    WHERE p.player_id = ? AND f.gameweek = ?
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
            cursor.execute("SELECT COUNT(*) FROM fixtures WHERE gameweek = ?", (next_gameweek,))
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
                    WHERE p.player_id = ? AND f.gameweek = ?
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
    """Get recent database updates"""
    try:
        cursor.execute("""
            SELECT table_name, updated, timestamp 
            FROM last_update 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        return cursor.fetchall()
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
