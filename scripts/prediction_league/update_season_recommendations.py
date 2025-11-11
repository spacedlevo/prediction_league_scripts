#!/usr/bin/env python3
"""
Update Season Recommendations

Analyzes current season patterns and updates strategy recommendations.
Sends notifications when strategy switches are recommended.
Part of the automated scheduler system.
"""

import sqlite3
import json
import logging
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import centralized configuration
from scripts.config import CURRENT_SEASON

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def load_config():
    """Load configuration from keys.json file"""
    keys_file = Path(__file__).parent.parent.parent / "keys.json"
    try:
        with open(keys_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def get_db_connection():
    """Get database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)

def analyze_current_season(cursor, season, logger):
    """Analyze current season and generate updated recommendation"""
    logger.info(f"Analyzing season: {season}")

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
        return None

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

    return {
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
        'expected_points_improvement': expected_improvement
    }

def check_for_strategy_change(cursor, new_recommendation, logger):
    """Check if recommendation has changed from previous week"""
    season = new_recommendation['season']

    # Get previous recommendation
    cursor.execute('''
        SELECT recommended_strategy, confidence_level, low_scoring_percentage
        FROM season_recommendations
        WHERE season = ?
        ORDER BY last_updated DESC
        LIMIT 1
    ''', (season,))

    previous = cursor.fetchone()

    if not previous:
        logger.info("No previous recommendation found - this is the first analysis")
        return {
            'strategy_changed': True,
            'confidence_changed': False,
            'significant_change': True,
            'previous_strategy': None,
            'change_reason': 'Initial recommendation'
        }

    prev_strategy, prev_confidence, prev_percentage = previous

    strategy_changed = prev_strategy != new_recommendation['recommended_strategy']
    confidence_changed = prev_confidence != new_recommendation['confidence_level']

    # Significant change if strategy changes or percentage moves >3%
    percentage_change = abs(prev_percentage - new_recommendation['low_scoring_percentage'])
    significant_change = strategy_changed or percentage_change > 3.0

    change_reason = ""
    if strategy_changed:
        change_reason = f"Strategy changed from {prev_strategy} to {new_recommendation['recommended_strategy']}"
    elif confidence_changed:
        change_reason = f"Confidence changed from {prev_confidence} to {new_recommendation['confidence_level']}"
    elif percentage_change > 3.0:
        change_reason = f"Low-scoring percentage changed by {percentage_change:.1f}% (now {new_recommendation['low_scoring_percentage']:.1f}%)"
    else:
        change_reason = "Minor update to existing recommendation"

    logger.info(f"Change analysis: {change_reason}")

    return {
        'strategy_changed': strategy_changed,
        'confidence_changed': confidence_changed,
        'significant_change': significant_change,
        'previous_strategy': prev_strategy,
        'change_reason': change_reason,
        'percentage_change': percentage_change
    }

def send_notification(recommendation, change_info, config, logger):
    """Send Pushover notification for strategy recommendations"""
    if not config or 'pushover_user_key' not in config or 'pushover_app_token' not in config:
        logger.warning("Pushover configuration not found - skipping notification")
        return

    try:
        import requests

        season = recommendation['season']
        strategy = recommendation['recommended_strategy']
        confidence = recommendation['confidence_level']
        percentage = recommendation['low_scoring_percentage']
        matches = recommendation['total_matches']

        # Determine notification priority and message
        if change_info['strategy_changed'] and confidence in ['moderate', 'high']:
            priority = 1  # High priority for strategy changes with good confidence
            title = f"🔄 Strategy Switch Recommended: {strategy.upper()}"
        elif change_info['strategy_changed']:
            priority = 0  # Normal priority for early confidence strategy changes
            title = f"📊 Early Strategy Indication: {strategy.upper()}"
        elif change_info['significant_change']:
            priority = 0  # Normal priority for significant updates
            title = f"📈 Season Analysis Update: {strategy.upper()}"
        else:
            # Minor updates - only send if weekly summary is enabled
            logger.info("Minor update - skipping notification")
            return

        # Build detailed message
        message_parts = []
        message_parts.append(f"Season {season} Analysis ({matches} matches)")
        message_parts.append(f"Low-scoring matches: {percentage:.1f}%")
        message_parts.append(f"Recommended strategy: {strategy.upper()}")
        message_parts.append(f"Confidence: {confidence}")

        if change_info['change_reason']:
            message_parts.append(f"\n📋 {change_info['change_reason']}")

        if recommendation['expected_points_improvement'] > 0:
            message_parts.append(f"💡 Expected improvement: +{recommendation['expected_points_improvement']:.2f} pts/game")

        # Add historical context
        if recommendation['historical_precedents']:
            similar = recommendation['historical_precedents'][0]
            message_parts.append(f"📊 Similar to {similar['season']} ({similar['percentage']:.1f}% low-scoring)")

        # Send notification
        payload = {
            'token': config['pushover_app_token'],
            'user': config['pushover_user_key'],
            'title': title,
            'message': '\n'.join(message_parts),
            'priority': priority,
            'url': 'http://prediction-league.com/predictions',
            'url_title': 'View Predictions'
        }

        response = requests.post('https://api.pushover.net/1/messages.json', data=payload, timeout=10)

        if response.status_code == 200:
            logger.info(f"Notification sent successfully: {title}")
        else:
            logger.error(f"Failed to send notification: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error sending notification: {e}")

def update_recommendation_database(cursor, recommendation, logger):
    """Update the database with new recommendation"""
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO season_recommendations
            (season, current_gameweek, total_matches, low_scoring_matches,
             low_scoring_percentage, goals_per_game_avg, recommended_strategy,
             confidence_level, recommendation_reason, historical_precedents,
             expected_points_improvement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            recommendation['season'],
            recommendation['current_gameweek'],
            recommendation['total_matches'],
            recommendation['low_scoring_matches'],
            recommendation['low_scoring_percentage'],
            recommendation['goals_per_game_avg'],
            recommendation['recommended_strategy'],
            recommendation['confidence_level'],
            recommendation['recommendation_reason'],
            json.dumps(recommendation['historical_precedents']),
            recommendation['expected_points_improvement']
        ))

        cursor.connection.commit()
        logger.info("Database updated with new recommendation")
        return True

    except Exception as e:
        logger.error(f"Failed to update database: {e}")
        return False

def update_last_update_table(cursor, logger):
    """Update the last_update table to trigger automated uploads"""
    try:
        current_time = datetime.now()
        formatted_time = current_time.strftime("%d-%m-%Y %H:%M:%S")
        cursor.execute('''
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES ('season_recommendations', ?, ?)
        ''', (formatted_time, current_time.timestamp()))

        cursor.connection.commit()
        logger.info("Updated last_update table for automated upload")

    except Exception as e:
        logger.error(f"Failed to update last_update table: {e}")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Update season strategy recommendations')
    parser.add_argument('--season', default=CURRENT_SEASON, help=f'Season to analyze (default: {CURRENT_SEASON})')
    parser.add_argument('--dry-run', action='store_true', help='Show analysis without updating database')
    parser.add_argument('--force-notification', action='store_true', help='Send notification even for minor changes')
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("Starting season recommendation update...")

    # Load configuration
    config = load_config()

    # Database connection
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Analyze current season
        recommendation = analyze_current_season(cursor, args.season, logger)

        if not recommendation:
            logger.warning("No season data available for analysis")
            return

        # Check for changes
        change_info = check_for_strategy_change(cursor, recommendation, logger)

        # Log recommendation summary
        logger.info(f"=== Season Recommendation Summary ===")
        logger.info(f"Season: {recommendation['season']}")
        logger.info(f"Matches analyzed: {recommendation['total_matches']}")
        logger.info(f"Low-scoring percentage: {recommendation['low_scoring_percentage']:.1f}%")
        logger.info(f"Recommended strategy: {recommendation['recommended_strategy']}")
        logger.info(f"Confidence level: {recommendation['confidence_level']}")
        logger.info(f"Expected improvement: +{recommendation['expected_points_improvement']:.2f} pts/game")

        if not args.dry_run:
            # Update database
            if update_recommendation_database(cursor, recommendation, logger):
                update_last_update_table(cursor, logger)

            # Send notification if significant change or forced
            if change_info['significant_change'] or args.force_notification:
                send_notification(recommendation, change_info, config, logger)
        else:
            logger.info("Dry run mode - no database updates or notifications sent")

        logger.info("Season recommendation update completed successfully")

    except Exception as e:
        logger.error(f"Error updating season recommendations: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()