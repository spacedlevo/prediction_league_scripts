#!/usr/bin/env python3
"""
Setup Season Recommendations System

Creates the database tables and populates historical season patterns
based on the comprehensive analysis findings.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import logging

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def create_tables(cursor, logger):
    """Create the season recommendations tables"""
    logger.info("Creating season recommendations tables...")

    # Read and execute the SQL file
    sql_file = Path(__file__).parent / "create_season_recommendations_table.sql"
    with open(sql_file, 'r') as f:
        sql_commands = f.read()

    # Execute all commands
    cursor.executescript(sql_commands)
    logger.info("Tables created successfully")

def populate_historical_patterns(cursor, logger):
    """Populate historical season patterns based on comprehensive analysis"""
    logger.info("Populating historical season patterns...")

    # Data from the comprehensive analysis document
    historical_seasons = [
        # Based on analysis findings
        {
            'season': '2021/2022',
            'optimal_strategy': '1-0',
            'strategy_advantage': 0.029,
            'low_scoring_percentage': 44.8,
            'season_classification': 'low_scoring'
        },
        {
            'season': '2022/2023',
            'optimal_strategy': '1-0',
            'strategy_advantage': 0.024,
            'low_scoring_percentage': 47.4,
            'season_classification': 'low_scoring'
        },
        {
            'season': '2025/2026',
            'optimal_strategy': '1-0',
            'strategy_advantage': 0.125,
            'low_scoring_percentage': 52.5,
            'season_classification': 'low_scoring'
        },
        {
            'season': '2019/2020',
            'optimal_strategy': '2-1',
            'strategy_advantage': -0.023,  # 2-1 wins by this margin
            'low_scoring_percentage': 48.8,
            'season_classification': 'mixed'
        },
        {
            'season': '2023/2024',
            'optimal_strategy': '2-1',
            'strategy_advantage': -0.018,  # 2-1 wins by this margin
            'low_scoring_percentage': 35.3,
            'season_classification': 'high_scoring'
        },
        {
            'season': '2024/2025',
            'optimal_strategy': '2-1',
            'strategy_advantage': -0.013,  # 2-1 wins by this margin
            'low_scoring_percentage': 43.4,
            'season_classification': 'mixed'
        }
    ]

    for season_data in historical_seasons:
        # Calculate estimated values for missing data
        total_matches = 380  # Standard Premier League season
        low_scoring_matches = int(total_matches * (season_data['low_scoring_percentage'] / 100))

        # Estimate goals per game based on low-scoring percentage
        if season_data['season_classification'] == 'low_scoring':
            goals_per_game = 2.3
        elif season_data['season_classification'] == 'high_scoring':
            goals_per_game = 2.8
        else:
            goals_per_game = 2.55

        cursor.execute('''
            INSERT OR REPLACE INTO historical_season_patterns
            (season, total_matches, low_scoring_matches, low_scoring_percentage,
             goals_per_game_avg, optimal_strategy, strategy_advantage,
             season_classification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            season_data['season'],
            total_matches,
            low_scoring_matches,
            season_data['low_scoring_percentage'],
            goals_per_game,
            season_data['optimal_strategy'],
            abs(season_data['strategy_advantage']),  # Store as positive value
            season_data['season_classification']
        ))

    logger.info(f"Populated {len(historical_seasons)} historical season patterns")

def get_current_season_stats(cursor, logger):
    """Get current season statistics and create initial recommendation"""
    logger.info("Analyzing current season (2025/2026)...")

    # Get current season data from fixtures and results
    cursor.execute('''
        SELECT
            COUNT(*) as total_matches,
            SUM(CASE WHEN (r.home_goals + r.away_goals) <= 2 THEN 1 ELSE 0 END) as low_scoring,
            AVG(r.home_goals + r.away_goals) as avg_goals,
            MAX(f.gameweek) as current_gameweek
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = '2025/2026'
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
    ''')

    result = cursor.fetchone()
    if result and result[0] > 0:
        total_matches, low_scoring, avg_goals, current_gameweek = result
        low_scoring_percentage = (low_scoring / total_matches) * 100

        # Determine recommendation based on analysis
        if low_scoring_percentage > 47:
            recommended_strategy = '1-0'
            confidence = 'high' if total_matches > 80 else 'moderate' if total_matches > 40 else 'early'
            reason = f"Season shows {low_scoring_percentage:.1f}% low-scoring matches (>47% threshold for 1-0 strategy)"
            expected_improvement = 0.05  # Conservative estimate
        else:
            recommended_strategy = '2-1'
            confidence = 'high' if total_matches > 80 else 'moderate' if total_matches > 40 else 'early'
            reason = f"Season shows {low_scoring_percentage:.1f}% low-scoring matches (<47% threshold, continue 2-1 strategy)"
            expected_improvement = 0.0

        # Find similar historical seasons
        cursor.execute('''
            SELECT season, low_scoring_percentage, optimal_strategy, strategy_advantage
            FROM historical_season_patterns
            WHERE ABS(low_scoring_percentage - ?) < 5.0
            ORDER BY ABS(low_scoring_percentage - ?)
            LIMIT 3
        ''', (low_scoring_percentage, low_scoring_percentage))

        similar_seasons = cursor.fetchall()
        precedents = json.dumps([{
            'season': s[0],
            'percentage': s[1],
            'strategy': s[2],
            'advantage': s[3]
        } for s in similar_seasons])

        # Insert current season recommendation
        cursor.execute('''
            INSERT OR REPLACE INTO season_recommendations
            (season, current_gameweek, total_matches, low_scoring_matches,
             low_scoring_percentage, goals_per_game_avg, recommended_strategy,
             confidence_level, recommendation_reason, historical_precedents,
             expected_points_improvement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            '2025/2026',
            current_gameweek or 1,
            total_matches,
            low_scoring,
            low_scoring_percentage,
            avg_goals or 2.5,
            recommended_strategy,
            confidence,
            reason,
            precedents,
            expected_improvement
        ))

        logger.info(f"Current season analysis complete:")
        logger.info(f"  - {total_matches} matches analyzed")
        logger.info(f"  - {low_scoring_percentage:.1f}% low-scoring matches")
        logger.info(f"  - Recommended strategy: {recommended_strategy}")
        logger.info(f"  - Confidence level: {confidence}")
    else:
        logger.warning("No current season results found for analysis")

def main():
    """Main function"""
    logger = setup_logging()
    logger.info("Setting up season recommendations system...")

    # Database connection
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create tables
        create_tables(cursor, logger)

        # Populate historical patterns
        populate_historical_patterns(cursor, logger)

        # Analyze current season
        get_current_season_stats(cursor, logger)

        # Commit changes
        conn.commit()
        logger.info("Season recommendations system setup complete!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM historical_season_patterns")
        patterns_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM season_recommendations")
        recommendations_count = cursor.fetchone()[0]

        logger.info(f"Summary:")
        logger.info(f"  - {patterns_count} historical season patterns stored")
        logger.info(f"  - {recommendations_count} season recommendations created")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error setting up season recommendations: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()