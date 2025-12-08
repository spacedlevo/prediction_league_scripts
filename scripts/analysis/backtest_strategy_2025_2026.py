#!/usr/bin/env python3
"""
Backtest AI Prediction Strategy on 2025/2026 Season
Applies the strategy to completed fixtures and calculates what the score would have been.
"""

import sqlite3
import logging
from pathlib import Path
from collections import defaultdict

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def apply_strategy(home_odds, away_odds, draw_odds, over_2_5_odds=None):
    """
    Apply the AI strategy to determine the prediction

    Returns: (home_score, away_score, strategy_used, confidence)
    """

    # Strategy A: Strong Favorite Clean Sheet (odds ≤1.50)
    if home_odds and home_odds <= 1.50:
        return (1, 0, 'Strong Favorite Home', 'HIGH')

    if away_odds and away_odds <= 1.50:
        return (0, 1, 'Strong Favorite Away', 'HIGH')

    # Strategy B: Balanced Draw (draw odds 3.00-3.50)
    if draw_odds and 3.00 <= draw_odds <= 3.50:
        return (1, 1, 'Balanced Draw', 'MEDIUM')

    # Strategy C: Moderate Favorite with high scoring
    # Only if we have Over 2.5 odds
    if over_2_5_odds and over_2_5_odds <= 1.80:
        if home_odds and 1.60 <= home_odds <= 2.20:
            return (2, 1, 'Chaos Favorite Home', 'LOW')

        if away_odds and 1.60 <= away_odds <= 2.20:
            return (1, 2, 'Chaos Favorite Away', 'LOW')

    # Fallback: Use lowest odds to determine favorite
    # Default to 2-0 for moderate favorites
    if home_odds and away_odds:
        if home_odds < away_odds and home_odds < draw_odds:
            # Home is favorite
            if home_odds <= 2.00:
                return (2, 0, 'Fallback Home Favorite', 'LOW')
            else:
                return (1, 1, 'Fallback Uncertain', 'VERY_LOW')
        elif away_odds < home_odds and away_odds < draw_odds:
            # Away is favorite
            if away_odds <= 2.00:
                return (0, 2, 'Fallback Away Favorite', 'LOW')
            else:
                return (1, 1, 'Fallback Uncertain', 'VERY_LOW')
        else:
            # Draw is most likely
            return (1, 1, 'Fallback Draw', 'VERY_LOW')

    # Last resort: predict most common scoreline
    return (1, 1, 'No Strategy Match', 'VERY_LOW')

def score_prediction(predicted_home, predicted_away, actual_home, actual_away):
    """
    Score a prediction
    Returns: (points, outcome)
    """
    # Check for exact score
    if predicted_home == actual_home and predicted_away == actual_away:
        return (2, 'EXACT_SCORE')

    # Check for correct result
    predicted_result = 'D' if predicted_home == predicted_away else ('H' if predicted_home > predicted_away else 'A')
    actual_result = 'D' if actual_home == actual_away else ('H' if actual_home > actual_away else 'A')

    if predicted_result == actual_result:
        return (1, 'CORRECT_RESULT')

    return (0, 'WRONG')

def backtest_season(cursor, logger):
    """
    Backtest the strategy on 2025/2026 season
    """
    logger.info("="*80)
    logger.info("BACKTESTING AI STRATEGY ON 2025/2026 SEASON")
    logger.info("="*80)

    # Get all completed fixtures from 2025/2026 with odds and results
    cursor.execute("""
        SELECT
            f.fixture_id,
            f.gameweek,
            f.home_teamid,
            f.away_teamid,
            t1.team_name as home_team,
            t2.team_name as away_team,
            r.home_goals,
            r.away_goals,
            fos.avg_home_win_odds,
            fos.avg_away_win_odds,
            fos.avg_draw_odds,
            fos.avg_over_2_5_odds
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        LEFT JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
        LEFT JOIN teams t1 ON f.home_teamid = t1.team_id
        LEFT JOIN teams t2 ON f.away_teamid = t2.team_id
        WHERE f.season = '2025/2026'
        AND f.finished = 1
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
        ORDER BY f.gameweek, f.fixture_id
    """)

    matches = cursor.fetchall()
    logger.info(f"Found {len(matches)} completed fixtures in 2025/2026 season\n")

    # Track results by strategy
    strategy_stats = defaultdict(lambda: {'count': 0, 'points': 0, 'exact': 0, 'correct_result': 0, 'wrong': 0})
    gameweek_stats = defaultdict(lambda: {'points': 0, 'matches': 0, 'exact': 0, 'correct_result': 0})

    total_points = 0
    total_matches = 0

    detailed_results = []

    for match in matches:
        (fixture_id, gameweek, home_teamid, away_teamid, home_team, away_team,
         actual_home, actual_away, home_odds, away_odds, draw_odds, over_2_5_odds) = match

        # Apply strategy to get prediction
        pred_home, pred_away, strategy, confidence = apply_strategy(
            home_odds, away_odds, draw_odds, over_2_5_odds
        )

        # Score the prediction
        points, outcome = score_prediction(pred_home, pred_away, actual_home, actual_away)

        # Update totals
        total_points += points
        total_matches += 1

        # Update strategy stats
        strategy_stats[strategy]['count'] += 1
        strategy_stats[strategy]['points'] += points
        if outcome == 'EXACT_SCORE':
            strategy_stats[strategy]['exact'] += 1
        elif outcome == 'CORRECT_RESULT':
            strategy_stats[strategy]['correct_result'] += 1
        else:
            strategy_stats[strategy]['wrong'] += 1

        # Update gameweek stats
        gameweek_stats[gameweek]['points'] += points
        gameweek_stats[gameweek]['matches'] += 1
        if outcome == 'EXACT_SCORE':
            gameweek_stats[gameweek]['exact'] += 1
        elif outcome == 'CORRECT_RESULT':
            gameweek_stats[gameweek]['correct_result'] += 1

        # Store detailed result
        detailed_results.append({
            'gameweek': gameweek,
            'home_team': home_team,
            'away_team': away_team,
            'actual': f"{actual_home}-{actual_away}",
            'predicted': f"{pred_home}-{pred_away}",
            'points': points,
            'outcome': outcome,
            'strategy': strategy,
            'confidence': confidence
        })

    # Print overall summary
    logger.info(f"📊 OVERALL BACKTEST RESULTS")
    logger.info(f"{'='*80}")
    logger.info(f"Total Matches: {total_matches}")
    logger.info(f"Total Points: {total_points}")
    logger.info(f"Points Per Game: {total_points/total_matches:.2f}")
    logger.info(f"")

    # Print gameweek breakdown
    logger.info(f"\n📅 GAMEWEEK BREAKDOWN")
    logger.info(f"{'='*80}")
    logger.info(f"{'GW':<4} {'Matches':<8} {'Points':<8} {'PPG':<8} {'Exact':<8} {'Correct':<10}")
    logger.info(f"{'-'*80}")

    for gw in sorted(gameweek_stats.keys()):
        stats = gameweek_stats[gw]
        ppg = stats['points'] / stats['matches'] if stats['matches'] > 0 else 0
        logger.info(f"{gw:<4} {stats['matches']:<8} {stats['points']:<8} {ppg:<8.2f} "
                   f"{stats['exact']:<8} {stats['correct_result']:<10}")

    # Print strategy performance
    logger.info(f"\n🎯 STRATEGY PERFORMANCE")
    logger.info(f"{'='*80}")
    logger.info(f"{'Strategy':<30} {'Count':<8} {'Points':<8} {'PPG':<8} {'Exact':<8} {'Correct':<10} {'Wrong':<8}")
    logger.info(f"{'-'*80}")

    for strategy in sorted(strategy_stats.keys(), key=lambda s: strategy_stats[s]['points'], reverse=True):
        stats = strategy_stats[strategy]
        ppg = stats['points'] / stats['count'] if stats['count'] > 0 else 0
        logger.info(f"{strategy:<30} {stats['count']:<8} {stats['points']:<8} {ppg:<8.2f} "
                   f"{stats['exact']:<8} {stats['correct_result']:<10} {stats['wrong']:<8}")

    # Print detailed results for high-confidence predictions
    logger.info(f"\n🔍 HIGH CONFIDENCE PREDICTIONS (Strategy A & B only)")
    logger.info(f"{'='*80}")
    logger.info(f"{'GW':<4} {'Match':<40} {'Predicted':<10} {'Actual':<10} {'Pts':<5} {'Strategy':<25}")
    logger.info(f"{'-'*80}")

    for result in detailed_results:
        if result['confidence'] in ['HIGH', 'MEDIUM']:
            match_str = f"{result['home_team']} vs {result['away_team']}"
            if len(match_str) > 40:
                match_str = match_str[:37] + "..."

            logger.info(f"{result['gameweek']:<4} {match_str:<40} {result['predicted']:<10} "
                       f"{result['actual']:<10} {result['points']:<5} {result['strategy']:<25}")

    # Calculate target comparison
    logger.info(f"\n🎯 TARGET COMPARISON")
    logger.info(f"{'='*80}")
    logger.info(f"Target PPG: 0.70 (7 points per 10-match week)")
    logger.info(f"Actual PPG: {total_points/total_matches:.2f}")

    if total_points/total_matches >= 0.70:
        logger.info(f"✅ EXCEEDS TARGET by {(total_points/total_matches - 0.70):.2f} PPG")
    else:
        logger.info(f"❌ BELOW TARGET by {(0.70 - total_points/total_matches):.2f} PPG")

    total_weeks = len(gameweek_stats)
    estimated_weekly_average = total_points / total_weeks if total_weeks > 0 else 0
    logger.info(f"\nEstimated Weekly Average: {estimated_weekly_average:.1f} points per week")
    logger.info(f"Target Weekly: 7.0 points per week")

    if estimated_weekly_average >= 7.0:
        logger.info(f"✅ ON TRACK to catch up!")
    else:
        logger.info(f"⚠️  Need {7.0 - estimated_weekly_average:.1f} more points per week")

def main():
    """Main backtest execution"""
    logger = setup_logging()

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Starting backtest on 2025/2026 season...")
    logger.info(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        backtest_season(cursor, logger)
        logger.info("\n✅ Backtest completed successfully!")

    except Exception as e:
        logger.error(f"Error during backtest: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
