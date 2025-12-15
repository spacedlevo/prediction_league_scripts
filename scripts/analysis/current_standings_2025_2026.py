#!/usr/bin/env python3
"""
Get current standings for 2025/2026 season
"""

import sqlite3
import logging
from pathlib import Path

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_current_standings(cursor, logger):
    """Get current standings for 2025/2026"""

    season = '2025/2026'

    # First, check how many gameweeks are completed
    cursor.execute("""
        SELECT MAX(f.gameweek) as max_gw, COUNT(DISTINCT f.fixture_id) as completed_fixtures
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
        AND f.finished = 1
        AND r.home_goals IS NOT NULL
    """, (season,))

    max_gw, completed = cursor.fetchone()
    logger.info(f"Season {season}: Through GW{max_gw}, {completed} completed fixtures\n")

    # Get current standings
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
        WHERE f.season = ?
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY pl.player_name
        ORDER BY total_points DESC, exact_scores DESC, player_name ASC
    """, (season,))

    standings = cursor.fetchall()

    logger.info(f"🏆 CURRENT STANDINGS - {season} (Through GW{max_gw})")
    logger.info("="*100)
    logger.info(f"{'Pos':<5} {'Player':<25} {'Predictions':<12} {'Points':<8} {'Exact':<8} {'PPG':<8}")
    logger.info("-"*100)

    for i, (name, preds, points, exact, ppg) in enumerate(standings, 1):
        logger.info(f"{i:<5} {name.title():<25} {preds:<12} {points:<8} {exact:<8} {ppg:<8.2f}")

    # Also check GW15 standings for comparison
    cursor.execute("""
        SELECT
            pl.player_name,
            SUM(CASE
                WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                     OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                     OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                ELSE 0
            END) as gw15_points,
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as gw15_exact
        FROM players pl
        JOIN predictions pred ON pl.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
        AND f.gameweek <= 15
        AND f.finished = 1
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY pl.player_name
        ORDER BY gw15_points DESC, gw15_exact DESC, player_name ASC
        LIMIT 5
    """, (season,))

    gw15_standings = cursor.fetchall()

    logger.info(f"\n📊 COMPARISON: Through GW15 vs. Current (GW{max_gw})")
    logger.info("="*100)
    logger.info(f"{'Player':<25} {'GW15 Points':<15} {'Current Points':<15} {'Gain':<10}")
    logger.info("-"*100)

    standings_dict = {name.lower(): points for name, preds, points, exact, ppg in standings}

    for name, gw15_pts, gw15_exact in gw15_standings:
        current_pts = standings_dict.get(name.lower(), 0)
        gain = current_pts - gw15_pts
        logger.info(f"{name.title():<25} {gw15_pts:<15} {current_pts:<15} {gain:<10}")

def main():
    """Main execution"""
    logger = setup_logging()

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Checking current 2025/2026 standings...")
    logger.info(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        get_current_standings(cursor, logger)
        logger.info("\n✅ Analysis completed!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
