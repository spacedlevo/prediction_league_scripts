#!/usr/bin/env python3
"""
Analyze who was leading at the end of Gameweek 15 in each season
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

def get_all_seasons(cursor):
    """Get all seasons with data"""
    cursor.execute("""
        SELECT DISTINCT season
        FROM fixtures
        ORDER BY season DESC
    """)
    return [row[0] for row in cursor.fetchall()]

def get_gw15_leader(cursor, season, logger):
    """Get the leader after gameweek 15 for a specific season"""

    # Get all predictions up to and including gameweek 15
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
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores
        FROM players pl
        JOIN predictions pred ON pl.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
        AND f.gameweek <= 15
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY pl.player_name
        ORDER BY total_points DESC, exact_scores DESC, player_name ASC
    """, (season,))

    results = cursor.fetchall()

    if not results:
        logger.warning(f"No data found for {season} gameweek 15")
        return None

    return results

def get_final_standings(cursor, season, logger):
    """Get the final standings for comparison"""

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
            SUM(CASE WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 1 ELSE 0 END) as exact_scores
        FROM players pl
        JOIN predictions pred ON pl.player_id = pred.player_id
        JOIN fixtures f ON pred.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
        AND pred.home_goals IS NOT NULL
        AND r.home_goals IS NOT NULL
        GROUP BY pl.player_name
        ORDER BY total_points DESC, exact_scores DESC, player_name ASC
        LIMIT 1
    """, (season,))

    result = cursor.fetchone()
    return result if result else None

def analyze_seasons(cursor, logger):
    """Analyze all seasons"""

    logger.info("="*80)
    logger.info("GAMEWEEK 15 LEADERS ANALYSIS - ALL SEASONS")
    logger.info("="*80)

    seasons = get_all_seasons(cursor)
    logger.info(f"\nFound {len(seasons)} seasons with data\n")

    season_summary = []

    for season in seasons:
        logger.info(f"{'='*80}")
        logger.info(f"SEASON: {season}")
        logger.info(f"{'='*80}")

        # Get GW15 standings
        gw15_results = get_gw15_leader(cursor, season, logger)

        if not gw15_results:
            logger.info(f"No gameweek 15 data available for {season}\n")
            continue

        # Get final standings
        final_result = get_final_standings(cursor, season, logger)

        # Display GW15 leader
        leader_name, leader_preds, leader_points, leader_exact = gw15_results[0]
        logger.info(f"\n🏆 LEADER AFTER GAMEWEEK 15:")
        logger.info(f"   {leader_name.title()}: {leader_points} points ({leader_exact} exact scores from {leader_preds} predictions)")

        # Display top 10
        logger.info(f"\n📊 TOP 10 AFTER GAMEWEEK 15:")
        logger.info(f"{'Pos':<5} {'Player':<25} {'Predictions':<12} {'Points':<8} {'Exact':<8} {'PPG':<8}")
        logger.info(f"{'-'*80}")

        tom_levin_pos = None
        for i, (name, preds, points, exact) in enumerate(gw15_results, 1):
            if i <= 10:
                ppg = points / preds if preds > 0 else 0
                marker = " ← YOU" if "tom levin" in name.lower() else ""
                logger.info(f"{i:<5} {name.title():<25} {preds:<12} {points:<8} {exact:<8} {ppg:<8.2f}{marker}")
            if "tom levin" in name.lower():
                tom_levin_pos = i
                tom_levin_points = points
                tom_levin_gap = leader_points - points

        # Show Tom Levin if not in top 10
        if tom_levin_pos and tom_levin_pos > 10:
            logger.info(f"...")
            name, preds, points, exact = gw15_results[tom_levin_pos - 1]
            ppg = points / preds if preds > 0 else 0
            logger.info(f"{tom_levin_pos:<5} {name.title():<25} {preds:<12} {points:<8} {exact:<8} {ppg:<8.2f} ← YOU")

        # Show your position and gap for current season
        if season == '2025/2026' and tom_levin_pos:
            logger.info(f"\n📍 YOUR POSITION:")
            logger.info(f"   Position: {tom_levin_pos} of {len(gw15_results)}")
            logger.info(f"   Points: {tom_levin_points}")
            logger.info(f"   Behind leader: {tom_levin_gap} points")
            logger.info(f"   Games remaining: ~230")
            logger.info(f"   Points to make up per game: {tom_levin_gap/230:.3f} PPG")

        # Compare to final winner
        if final_result:
            final_name, final_preds, final_points, final_exact = final_result
            logger.info(f"\n🎯 FINAL WINNER:")
            logger.info(f"   {final_name.title()}: {final_points} points ({final_exact} exact scores from {final_preds} predictions)")

            # Check if GW15 leader won
            if leader_name.lower() == final_name.lower():
                logger.info(f"   ✅ GW15 leader {leader_name.title()} went on to WIN the season!")
            else:
                logger.info(f"   ❌ GW15 leader {leader_name.title()} did NOT win (winner: {final_name.title()})")

                # Find where GW15 leader finished
                cursor.execute("""
                    SELECT
                        pl.player_name,
                        SUM(CASE
                            WHEN pred.home_goals = r.home_goals AND pred.away_goals = r.away_goals THEN 2
                            WHEN (pred.home_goals > pred.away_goals AND r.home_goals > r.away_goals)
                                 OR (pred.home_goals < pred.away_goals AND r.home_goals < r.away_goals)
                                 OR (pred.home_goals = pred.away_goals AND r.home_goals = r.away_goals) THEN 1
                            ELSE 0
                        END) as total_points
                    FROM players pl
                    JOIN predictions pred ON pl.player_id = pred.player_id
                    JOIN fixtures f ON pred.fixture_id = f.fixture_id
                    JOIN results r ON f.fixture_id = r.fixture_id
                    WHERE f.season = ?
                    AND pred.home_goals IS NOT NULL
                    AND r.home_goals IS NOT NULL
                    GROUP BY pl.player_name
                    ORDER BY total_points DESC
                """, (season,))

                final_standings = cursor.fetchall()
                for pos, (name, pts) in enumerate(final_standings, 1):
                    if name.lower() == leader_name.lower():
                        logger.info(f"   {leader_name.title()} finished position {pos} with {pts} points")
                        break

        # Store summary
        season_summary.append({
            'season': season,
            'gw15_leader': leader_name.title(),
            'gw15_points': leader_points,
            'gw15_exact': leader_exact,
            'final_winner': final_name.title() if final_result else 'Unknown',
            'final_points': final_points if final_result else 0,
            'leader_won': leader_name.lower() == final_name.lower() if final_result else False
        })

        logger.info("")

    # Summary table
    logger.info("\n" + "="*80)
    logger.info("📋 SUMMARY: GW15 LEADERS ACROSS ALL SEASONS")
    logger.info("="*80)
    logger.info(f"{'Season':<15} {'GW15 Leader':<25} {'GW15 Pts':<10} {'Final Winner':<25} {'Won?':<8}")
    logger.info(f"{'-'*80}")

    wins = 0
    for s in season_summary:
        won_marker = "✅ YES" if s['leader_won'] else "❌ NO"
        if s['leader_won']:
            wins += 1
        logger.info(f"{s['season']:<15} {s['gw15_leader']:<25} {s['gw15_points']:<10} {s['final_winner']:<25} {won_marker:<8}")

    logger.info(f"\n{'='*80}")
    logger.info(f"GW15 leaders who went on to win: {wins}/{len(season_summary)} ({wins/len(season_summary)*100:.1f}%)")
    logger.info(f"{'='*80}")

    # Current season analysis
    current_season = '2025/2026'
    if current_season in [s['season'] for s in season_summary]:
        logger.info(f"\n🔍 CURRENT SEASON ({current_season}) IMPLICATIONS:")
        current_data = [s for s in season_summary if s['season'] == current_season][0]
        logger.info(f"   Leader: {current_data['gw15_leader']}")
        logger.info(f"   Points: {current_data['gw15_points']}")
        logger.info(f"\n   Based on historical data:")
        logger.info(f"   - {wins}/{len(season_summary)} times ({wins/len(season_summary)*100:.1f}%), the GW15 leader went on to win")
        logger.info(f"   - There's still a {100-wins/len(season_summary)*100:.1f}% chance for a comeback!")

def main():
    """Main execution"""
    logger = setup_logging()

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Starting Gameweek 15 Leaders Analysis...")
    logger.info(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        analyze_seasons(cursor, logger)
        logger.info("\n✅ Analysis completed successfully!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
