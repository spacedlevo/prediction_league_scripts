#!/usr/bin/env python3
"""
Analyze Top Performers in 2025/2026 Season
Examines prediction patterns and strategies of Dan Barrell, Dean Charles, and Michael Green
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

def get_player_stats(cursor, player_name, season='2025/2026'):
    """Get comprehensive stats for a specific player"""

    # Get total points (calculate points on the fly)
    cursor.execute("""
        SELECT
            p.player_id,
            p.player_name,
            COUNT(DISTINCT pred.fixture_id) as predictions_made,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1
                ELSE 0
            END) as exact_scores,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as correct_results,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 0
                ELSE 1
            END) as wrong,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as total_points,
            AVG(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as avg_ppg
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
    """, (player_name, season))

    return cursor.fetchone()

def get_scoreline_preferences(cursor, player_name, season='2025/2026'):
    """Get scoreline prediction preferences for a player"""

    cursor.execute("""
        SELECT
            pred.home_goals,
            pred.away_goals,
            COUNT(*) as frequency,
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as correct_results,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 0
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 0
                ELSE 1
            END) as wrong,
            AVG(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as avg_points
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY pred.home_goals, pred.away_goals
        ORDER BY frequency DESC
    """, (player_name, season))

    return cursor.fetchall()

def get_result_type_preferences(cursor, player_name, season='2025/2026'):
    """Analyze home win/draw/away win prediction patterns"""

    cursor.execute("""
        SELECT
            CASE
                WHEN pred.home_goals > pred.away_goals THEN 'Home Win'
                WHEN pred.home_goals < pred.away_goals THEN 'Away Win'
                ELSE 'Draw'
            END as predicted_result,
            COUNT(*) as frequency,
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1
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
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY predicted_result
        ORDER BY frequency DESC
    """, (player_name, season))

    return cursor.fetchall()

def get_odds_based_analysis(cursor, player_name, season='2025/2026'):
    """Analyze how well the player follows odds vs. goes against them"""

    cursor.execute("""
        SELECT
            CASE
                WHEN fos.avg_home_win_odds < fos.avg_away_win_odds
                     AND fos.avg_home_win_odds < fos.avg_draw_odds THEN 'Home Favorite'
                WHEN fos.avg_away_win_odds < fos.avg_home_win_odds
                     AND fos.avg_away_win_odds < fos.avg_draw_odds THEN 'Away Favorite'
                WHEN fos.avg_draw_odds < fos.avg_home_win_odds
                     AND fos.avg_draw_odds < fos.avg_away_win_odds THEN 'Draw Favorite'
                ELSE 'Balanced'
            END as match_type,
            CASE
                WHEN pred.home_goals > pred.away_goals THEN 'Home Win'
                WHEN pred.home_goals < pred.away_goals THEN 'Away Win'
                ELSE 'Draw'
            END as prediction,
            COUNT(*) as frequency,
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1
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
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        LEFT JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
        WHERE p.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        AND fos.avg_home_win_odds IS NOT NULL
        GROUP BY match_type, prediction
        ORDER BY match_type, frequency DESC
    """, (player_name, season))

    return cursor.fetchall()

def analyze_gameweek_consistency(cursor, player_name, season='2025/2026'):
    """Check performance by gameweek"""

    cursor.execute("""
        SELECT
            f.gameweek,
            COUNT(*) as predictions,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as points,
            AVG(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as avg_ppg,
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores
        FROM players p
        JOIN predictions pred ON p.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY f.gameweek
        ORDER BY f.gameweek
    """, (player_name, season))

    return cursor.fetchall()

def compare_to_user(cursor, player_name, user_name="Tom Levin", season='2025/2026'):
    """Direct comparison of matches where both players made predictions"""

    cursor.execute("""
        SELECT
            f.gameweek,
            t1.team_name as home_team,
            t2.team_name as away_team,
            r.home_goals,
            r.away_goals,
            p1.home_goals as top_pred_home,
            p1.away_goals as top_pred_away,
            CASE
                WHEN p1.home_goals = r.home_goals AND p1.away_goals = r.away_goals THEN 2
                WHEN (p1.home_goals > p1.away_goals AND r.home_goals > r.away_goals)
                     OR (p1.home_goals < p1.away_goals AND r.home_goals < r.away_goals)
                     OR (p1.home_goals = p1.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END as top_points,
            p2.home_goals as user_pred_home,
            p2.away_goals as user_pred_away,
            CASE
                WHEN p2.home_goals = r.home_goals AND p2.away_goals = r.away_goals THEN 2
                WHEN (p2.home_goals > p2.away_goals AND r.home_goals > r.away_goals)
                     OR (p2.home_goals < p2.away_goals AND r.home_goals < r.away_goals)
                     OR (p2.home_goals = p2.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END as user_points
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN teams t1 ON f.home_teamid = t1.team_id
        JOIN teams t2 ON f.away_teamid = t2.team_id
        JOIN predictions p1 ON f.fixture_id = p1.fixture_id
        JOIN players pl1 ON p1.player_id = pl1.player_id
        LEFT JOIN predictions p2 ON f.fixture_id = p2.fixture_id
        LEFT JOIN players pl2 ON p2.player_id = pl2.player_id AND pl2.player_name = ?
        WHERE pl1.player_name = ?
        AND f.season = ?
        AND f.finished = 1
        AND p1.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        ORDER BY f.gameweek, f.fixture_id
    """, (user_name, player_name, season))

    return cursor.fetchall()

def analyze_player(cursor, player_name, logger):
    """Comprehensive analysis of a single player"""

    logger.info("="*80)
    logger.info(f"ANALYZING: {player_name}")
    logger.info("="*80)

    # Overall stats
    stats = get_player_stats(cursor, player_name)
    if stats and stats[2] and stats[2] > 0:  # Check if predictions > 0
        player_id, name, predictions, exact, correct, wrong, total, avg = stats
        logger.info(f"\n📊 OVERALL PERFORMANCE")
        logger.info(f"Total Predictions: {predictions}")
        logger.info(f"Total Points: {total if total is not None else 0}")
        logger.info(f"Points Per Game: {avg if avg is not None else 0:.2f}")
        logger.info(f"  - Exact Scores (2pts): {exact if exact else 0} ({exact/predictions*100 if exact and predictions else 0:.1f}%)")
        logger.info(f"  - Correct Results (1pt): {correct if correct else 0} ({correct/predictions*100 if correct and predictions else 0:.1f}%)")
        logger.info(f"  - Wrong (0pts): {wrong if wrong else 0} ({wrong/predictions*100 if wrong and predictions else 0:.1f}%)")
    else:
        logger.warning(f"No predictions found for {player_name}")
        return None

    # Scoreline preferences
    logger.info(f"\n🎯 SCORELINE PREFERENCES (Top 10)")
    logger.info(f"{'-'*80}")
    logger.info(f"{'Scoreline':<12} {'Count':<8} {'Exact':<8} {'Correct':<10} {'Wrong':<8} {'Avg Pts':<10}")
    logger.info(f"{'-'*80}")

    scorelines = get_scoreline_preferences(cursor, player_name)
    for i, scoreline in enumerate(scorelines[:10], 1):
        home, away, freq, exact, correct, wrong, avg_pts = scoreline
        logger.info(f"{home}-{away:<10} {freq:<8} {exact:<8} {correct:<10} {wrong:<8} {avg_pts:<10.2f}")

    # Result type preferences
    logger.info(f"\n📈 RESULT TYPE ANALYSIS")
    logger.info(f"{'-'*80}")
    logger.info(f"{'Type':<15} {'Count':<8} {'Exact':<8} {'Correct':<10} {'Avg Pts':<10}")
    logger.info(f"{'-'*80}")

    result_types = get_result_type_preferences(cursor, player_name)
    for result_type, freq, exact, correct, avg_pts in result_types:
        logger.info(f"{result_type:<15} {freq:<8} {exact:<8} {correct:<10} {avg_pts:<10.2f}")

    # Odds-based analysis
    logger.info(f"\n💰 ODDS-BASED STRATEGY ANALYSIS")
    logger.info(f"{'-'*80}")
    logger.info(f"{'Match Type':<18} {'Prediction':<12} {'Count':<8} {'Exact':<8} {'Correct':<10} {'Avg Pts':<10}")
    logger.info(f"{'-'*80}")

    odds_analysis = get_odds_based_analysis(cursor, player_name)
    for match_type, prediction, freq, exact, correct, avg_pts in odds_analysis:
        logger.info(f"{match_type:<18} {prediction:<12} {freq:<8} {exact:<8} {correct:<10} {avg_pts:<10.2f}")

    # Gameweek consistency
    logger.info(f"\n📅 GAMEWEEK-BY-GAMEWEEK PERFORMANCE")
    logger.info(f"{'-'*80}")
    logger.info(f"{'GW':<5} {'Predictions':<12} {'Points':<8} {'PPG':<8} {'Exact':<8}")
    logger.info(f"{'-'*80}")

    gw_stats = analyze_gameweek_consistency(cursor, player_name)
    for gw, preds, points, avg_ppg, exact in gw_stats:
        logger.info(f"{gw:<5} {preds:<12} {points:<8} {avg_ppg:<8.2f} {exact:<8}")

    return stats

def compare_top_performers(cursor, logger, top_players, user_name="Tom Levin"):
    """Compare strategies across top performers"""

    logger.info("\n" + "="*80)
    logger.info("🏆 COMPARATIVE ANALYSIS OF TOP PERFORMERS")
    logger.info("="*80)

    # Overall comparison
    logger.info(f"\n📊 OVERALL COMPARISON")
    logger.info(f"{'-'*80}")
    logger.info(f"{'Player':<20} {'Predictions':<12} {'Points':<8} {'PPG':<8} {'Exact %':<10} {'Correct %':<12}")
    logger.info(f"{'-'*80}")

    all_stats = []
    for player in top_players:
        stats = get_player_stats(cursor, player)
        if stats:
            all_stats.append(stats)
            player_id, name, predictions, exact, correct, wrong, total, avg = stats
            exact_pct = exact/predictions*100 if predictions > 0 else 0
            correct_pct = (exact+correct)/predictions*100 if predictions > 0 else 0
            logger.info(f"{name:<20} {predictions:<12} {total:<8} {avg:<8.2f} {exact_pct:<10.1f} {correct_pct:<12.1f}")

    # Add user for comparison
    user_stats = get_player_stats(cursor, user_name)
    if user_stats:
        player_id, name, predictions, exact, correct, wrong, total, avg = user_stats
        exact_pct = exact/predictions*100 if predictions > 0 else 0
        correct_pct = (exact+correct)/predictions*100 if predictions > 0 else 0
        logger.info(f"{'-'*80}")
        logger.info(f"{name:<20} {predictions:<12} {total:<8} {avg:<8.2f} {exact_pct:<10.1f} {correct_pct:<12.1f}")

    # Scoreline diversity analysis
    logger.info(f"\n🎨 SCORELINE DIVERSITY")
    logger.info(f"{'-'*80}")

    for player in top_players:
        scorelines = get_scoreline_preferences(cursor, player)
        total_preds = sum(s[2] for s in scorelines)
        unique_scorelines = len(scorelines)
        top_scoreline_usage = scorelines[0][2] / total_preds * 100 if scorelines and total_preds > 0 else 0

        logger.info(f"{player}:")
        logger.info(f"  Unique scorelines used: {unique_scorelines}")
        logger.info(f"  Most used scoreline: {scorelines[0][0]}-{scorelines[0][1]} ({top_scoreline_usage:.1f}% of predictions)")
        logger.info(f"  Top 3 scorelines:")
        for i, (home, away, freq, exact, correct, wrong, avg_pts) in enumerate(scorelines[:3], 1):
            logger.info(f"    {i}. {home}-{away}: {freq} times ({freq/total_preds*100:.1f}%), avg {avg_pts:.2f} pts")
        logger.info("")

def identify_key_differences(cursor, logger, top_players):
    """Identify what makes top performers successful"""

    logger.info("\n" + "="*80)
    logger.info("🔍 KEY SUCCESS FACTORS")
    logger.info("="*80)

    for player in top_players:
        logger.info(f"\n{player}:")

        # Check if they follow favorites
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE
                    WHEN (fos.avg_home_win_odds < fos.avg_away_win_odds
                          AND fos.avg_home_win_odds < fos.avg_draw_odds
                          AND pred.home_goals > pred.away_goals)
                    OR (fos.avg_away_win_odds < fos.avg_home_win_odds
                        AND fos.avg_away_win_odds < fos.avg_draw_odds
                        AND pred.home_goals < pred.away_goals)
                    THEN 1 ELSE 0
                END) as followed_favorite,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as avg_points
            FROM players p
            JOIN predictions pred ON p.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            LEFT JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
            WHERE p.player_name = ?
            AND f.season = '2025/2026'
            AND f.finished = 1
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
            AND fos.avg_home_win_odds IS NOT NULL
        """, (player,))

        result = cursor.fetchone()
        if result:
            total, followed, avg_pts = result
            follow_pct = followed/total*100 if total > 0 else 0
            logger.info(f"  ✓ Follows favorites: {follow_pct:.1f}% of the time")

        # Check draw prediction rate
        cursor.execute("""
            SELECT
                COUNT(*) as total_draws,
                SUM(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as total_points,
                AVG(CASE
                    WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                    WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                         OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                         OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                    ELSE 0
                END) as avg_points
            FROM players p
            JOIN predictions pred ON p.player_id = pred.player_id
            JOIN fixtures f ON pred.fixture_id = f.fixture_id
            JOIN results r ON f.fixture_id = r.fixture_id
            WHERE p.player_name = ?
            AND f.season = '2025/2026'
            AND f.finished = 1
            AND pred.home_goals = pred.away_goals
            AND pred.home_goals IS NOT NULL
            AND r.home_goals IS NOT NULL
        """, (player,))

        result = cursor.fetchone()
        if result:
            total_draws, total_pts, avg_pts = result
            cursor.execute("""
                SELECT COUNT(*) FROM players p
                JOIN predictions pred ON p.player_id = pred.player_id
                JOIN fixtures f ON pred.fixture_id = f.fixture_id
                WHERE p.player_name = ?
                AND f.season = '2025/2026'
                AND f.finished = 1
            """, (player,))
            total_preds = cursor.fetchone()[0]
            draw_pct = total_draws/total_preds*100 if total_preds > 0 else 0
            logger.info(f"  ✓ Draw predictions: {draw_pct:.1f}% ({total_draws} times, avg {avg_pts:.2f} pts per draw)")

def main():
    """Main analysis execution"""
    logger = setup_logging()

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Starting Top Performers Analysis...")
    logger.info(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Use lowercase names as they appear in the database
    top_players = ["dan barrell", "dean charles", "michael green"]

    try:
        # Analyze each player individually
        for player in top_players:
            analyze_player(cursor, player, logger)
            logger.info("\n")

        # Comparative analysis
        compare_top_performers(cursor, logger, top_players, user_name="tom levin")

        # Identify key differences
        identify_key_differences(cursor, logger, top_players)

        logger.info("\n✅ Analysis completed successfully!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
