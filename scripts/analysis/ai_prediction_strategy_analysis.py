#!/usr/bin/env python3
"""
AI-Driven Prediction Strategy Analysis
Analyzes historical data to identify optimal scoreline prediction strategies
based on bookmaker odds and actual results.
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

def examine_database_structure(cursor, logger):
    """Examine available tables and their structure"""
    logger.info("Examining database structure...")

    # Get fixtures structure
    cursor.execute("PRAGMA table_info(fixtures)")
    fixtures_columns = cursor.fetchall()
    logger.info(f"Fixtures table columns: {[col[1] for col in fixtures_columns]}")

    # Get results structure
    cursor.execute("PRAGMA table_info(results)")
    results_columns = cursor.fetchall()
    logger.info(f"Results table columns: {[col[1] for col in results_columns]}")

    # Get odds structure
    cursor.execute("PRAGMA table_info(odds)")
    odds_columns = cursor.fetchall()
    logger.info(f"Odds table columns: {[col[1] for col in odds_columns]}")

    # Get fixture_odds_summary structure
    cursor.execute("PRAGMA table_info(fixture_odds_summary)")
    summary_columns = cursor.fetchall()
    logger.info(f"Fixture odds summary columns: {[col[1] for col in summary_columns]}")

    # Check sample data
    cursor.execute("""
        SELECT f.fixture_id, f.home_teamid, f.away_teamid, f.season,
               r.home_goals, r.away_goals
        FROM fixtures f
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = '2024/2025'
        LIMIT 5
    """)
    sample = cursor.fetchall()
    logger.info(f"Sample fixtures with results: {len(sample)} records")

    # Check odds availability in fixtures
    cursor.execute("""
        SELECT COUNT(*) FROM fixtures WHERE home_win_odds IS NOT NULL
    """)
    fixtures_odds_count = cursor.fetchone()[0]
    logger.info(f"Fixtures with odds: {fixtures_odds_count}")

    # Check fixture_odds_summary
    cursor.execute("""
        SELECT fixture_id, avg_home_win_odds, avg_draw_odds, avg_away_win_odds, avg_over_2_5_odds
        FROM fixture_odds_summary
        WHERE avg_home_win_odds IS NOT NULL
        LIMIT 5
    """)
    odds_sample = cursor.fetchall()
    logger.info(f"Sample odds summary: {odds_sample}")

def analyze_clean_sheet_bankers(cursor, logger):
    """
    Analysis A: Clean Sheet Banker - Strong favorites (odds ≤1.50)
    Identifies optimal scoreline: 1-0, 2-0, or 3-0
    """
    logger.info("\n" + "="*80)
    logger.info("ANALYSIS A: CLEAN SHEET BANKER (Strong Favorites, Odds ≤1.50)")
    logger.info("="*80)

    # Query for matches where either home or away was strong favorite
    cursor.execute("""
        SELECT
            f.fixture_id,
            r.home_goals,
            r.away_goals,
            fos.avg_home_win_odds,
            fos.avg_away_win_odds,
            CASE
                WHEN fos.avg_home_win_odds <= 1.50 THEN 'home'
                WHEN fos.avg_away_win_odds <= 1.50 THEN 'away'
                ELSE 'neither'
            END as favorite_side
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
        WHERE (fos.avg_home_win_odds <= 1.50 OR fos.avg_away_win_odds <= 1.50)
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
    """)

    matches = cursor.fetchall()
    logger.info(f"Found {len(matches)} matches with strong favorite (odds ≤1.50)")

    scoreline_counts = defaultdict(int)
    total_favorite_wins = 0

    for match in matches:
        fixture_id, home_score, away_score, home_odds, away_odds, fav_side = match

        # Normalize to favorite's perspective
        if fav_side == 'home':
            fav_score = home_score
            opp_score = away_score
        elif fav_side == 'away':
            fav_score = away_score
            opp_score = home_score
        else:
            continue

        # Only count if favorite won
        if fav_score > opp_score:
            total_favorite_wins += 1
            scoreline = f"{fav_score}-{opp_score}"
            scoreline_counts[scoreline] += 1

    logger.info(f"Total matches where strong favorite won: {total_favorite_wins}")

    # Focus on clean sheet scorelines
    target_scorelines = ['1-0', '2-0', '3-0', '2-1', '3-1']
    logger.info("\nScoreline distribution for strong favorites:")
    for scoreline in target_scorelines:
        count = scoreline_counts[scoreline]
        percentage = (count / total_favorite_wins * 100) if total_favorite_wins > 0 else 0
        logger.info(f"  {scoreline}: {count} ({percentage:.1f}%)")

    # Find optimal scoreline
    clean_sheet_scorelines = ['1-0', '2-0', '3-0']
    best_scoreline = max(clean_sheet_scorelines, key=lambda s: scoreline_counts[s])
    best_count = scoreline_counts[best_scoreline]
    best_rate = (best_count / total_favorite_wins * 100) if total_favorite_wins > 0 else 0

    logger.info(f"\n✅ OPTIMAL CLEAN SHEET SCORELINE: {best_scoreline}")
    logger.info(f"   Hit Rate: {best_count}/{total_favorite_wins} ({best_rate:.1f}%)")
    logger.info(f"   2-Point Value: Expect {best_rate:.1f}% correct score rate for strong favorites")

    return {
        'scoreline': best_scoreline,
        'hit_rate': best_rate,
        'sample_size': total_favorite_wins
    }

def analyze_draw_hunters(cursor, logger):
    """
    Analysis B: Draw Hunter - Balanced matches (draw odds 3.00-3.50)
    Identifies optimal draw scoreline: 1-1 or 0-0
    """
    logger.info("\n" + "="*80)
    logger.info("ANALYSIS B: DRAW HUNTER (Balanced Contests, Draw Odds 3.00-3.50)")
    logger.info("="*80)

    cursor.execute("""
        SELECT
            f.fixture_id,
            r.home_goals,
            r.away_goals,
            fos.avg_draw_odds
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
        WHERE fos.avg_draw_odds BETWEEN 3.00 AND 3.50
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
    """)

    matches = cursor.fetchall()
    logger.info(f"Found {len(matches)} matches with draw odds 3.00-3.50")

    draw_scorelines = defaultdict(int)
    total_draws = 0

    for match in matches:
        fixture_id, home_score, away_score, draw_odds = match

        if home_score == away_score:
            total_draws += 1
            scoreline = f"{home_score}-{away_score}"
            draw_scorelines[scoreline] += 1

    logger.info(f"Total draws in this odds range: {total_draws}")
    draw_rate = (total_draws / len(matches) * 100) if len(matches) > 0 else 0
    logger.info(f"Draw occurrence rate: {draw_rate:.1f}%")

    # Focus on common draw scorelines
    target_draws = ['0-0', '1-1', '2-2']
    logger.info("\nDraw scoreline distribution:")
    for scoreline in target_draws:
        count = draw_scorelines[scoreline]
        percentage = (count / total_draws * 100) if total_draws > 0 else 0
        logger.info(f"  {scoreline}: {count} ({percentage:.1f}% of all draws)")

    # Find optimal draw scoreline
    best_draw = max(['0-0', '1-1'], key=lambda s: draw_scorelines[s])
    best_count = draw_scorelines[best_draw]
    best_rate = (best_count / len(matches) * 100) if len(matches) > 0 else 0

    logger.info(f"\n✅ OPTIMAL DRAW SCORELINE: {best_draw}")
    logger.info(f"   Hit Rate: {best_count}/{len(matches)} ({best_rate:.1f}%)")
    logger.info(f"   2-Point Value: Expect {best_rate:.1f}% correct score rate for balanced matches")

    return {
        'scoreline': best_draw,
        'hit_rate': best_rate,
        'sample_size': len(matches),
        'draw_rate': draw_rate
    }

def analyze_chaos_favorites(cursor, logger):
    """
    Analysis C: Chaos Favorite - Moderate favorites (odds 1.60-2.20) in high-scoring games
    Identifies optimal winning scoreline: 2-1, 3-1, or 3-2
    """
    logger.info("\n" + "="*80)
    logger.info("ANALYSIS C: CHAOS FAVORITE (Moderate Favorites 1.60-2.20)")
    logger.info("="*80)

    # Use Over 2.5 odds to identify high-scoring games
    cursor.execute("""
        SELECT
            f.fixture_id,
            r.home_goals,
            r.away_goals,
            fos.avg_home_win_odds,
            fos.avg_away_win_odds,
            fos.avg_over_2_5_odds,
            CASE
                WHEN fos.avg_home_win_odds BETWEEN 1.60 AND 2.20 THEN 'home'
                WHEN fos.avg_away_win_odds BETWEEN 1.60 AND 2.20 THEN 'away'
                ELSE 'neither'
            END as favorite_side
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN fixture_odds_summary fos ON f.fixture_id = fos.fixture_id
        WHERE (fos.avg_home_win_odds BETWEEN 1.60 AND 2.20
               OR fos.avg_away_win_odds BETWEEN 1.60 AND 2.20)
        AND r.home_goals IS NOT NULL
        AND r.away_goals IS NOT NULL
        AND fos.avg_over_2_5_odds IS NOT NULL
        AND fos.avg_over_2_5_odds <= 1.80
    """)

    matches = cursor.fetchall()
    logger.info(f"Found {len(matches)} matches with moderate favorite (odds 1.60-2.20)")

    scoreline_counts = defaultdict(int)
    total_favorite_wins = 0
    high_scoring_wins = 0

    for match in matches:
        fixture_id, home_goals, away_goals, home_odds, away_odds, over_2_5_odds, fav_side = match

        # Normalize to favorite's perspective
        if fav_side == 'home':
            fav_score = home_goals
            opp_score = away_goals
        elif fav_side == 'away':
            fav_score = away_goals
            opp_score = home_goals
        else:
            continue

        # Only count if favorite won
        if fav_score > opp_score:
            total_favorite_wins += 1
            scoreline = f"{fav_score}-{opp_score}"
            scoreline_counts[scoreline] += 1

            # Track high-scoring games (total goals > 2)
            if fav_score + opp_score > 2:
                high_scoring_wins += 1

    logger.info(f"Total matches where moderate favorite won: {total_favorite_wins}")
    logger.info(f"High-scoring wins (>2 total goals): {high_scoring_wins}")

    # Focus on chaos scorelines (favorite wins but concedes)
    target_scorelines = ['2-1', '3-1', '3-2', '2-0', '3-0']
    logger.info("\nScoreline distribution for moderate favorites:")
    for scoreline in target_scorelines:
        count = scoreline_counts[scoreline]
        percentage = (count / total_favorite_wins * 100) if total_favorite_wins > 0 else 0
        logger.info(f"  {scoreline}: {count} ({percentage:.1f}%)")

    # Find optimal chaos scoreline (favorite wins but concedes)
    chaos_scorelines = ['2-1', '3-1', '3-2']
    best_chaos = max(chaos_scorelines, key=lambda s: scoreline_counts[s])
    best_count = scoreline_counts[best_chaos]
    best_rate = (best_count / total_favorite_wins * 100) if total_favorite_wins > 0 else 0

    logger.info(f"\n✅ OPTIMAL CHAOS SCORELINE: {best_chaos}")
    logger.info(f"   Hit Rate: {best_count}/{total_favorite_wins} ({best_rate:.1f}%)")
    logger.info(f"   2-Point Value: Expect {best_rate:.1f}% correct score rate for moderate favorites")

    return {
        'scoreline': best_chaos,
        'hit_rate': best_rate,
        'sample_size': total_favorite_wins
    }

def generate_strategy_manifesto(clean_sheet_results, draw_results, chaos_results, logger):
    """Generate the final strategy table and recommendations"""
    logger.info("\n" + "="*80)
    logger.info("🎯 FINAL PREDICTION STRATEGY MANIFESTO")
    logger.info("="*80)

    logger.info("\n| Match Scenario | Odds Criteria | Optimal Scoreline | Historical 2-Point Hit Rate |")
    logger.info("|:---------------|:--------------|:------------------|:----------------------------|")
    logger.info(f"| **Strong Favorite Clean Sheet** | Favorite odds ≤1.50 | **{clean_sheet_results['scoreline']}** | {clean_sheet_results['hit_rate']:.1f}% (n={clean_sheet_results['sample_size']}) |")
    logger.info(f"| **Balanced Mid-Table Draw** | Draw odds 3.00-3.50 | **{draw_results['scoreline']}** | {draw_results['hit_rate']:.1f}% (n={draw_results['sample_size']}) |")
    logger.info(f"| **Moderate Favorite (Chaos)** | Favorite odds 1.60-2.20 | **{chaos_results['scoreline']}** | {chaos_results['hit_rate']:.1f}% (n={chaos_results['sample_size']}) |")

    # Calculate overall strategy confidence
    avg_hit_rate = (clean_sheet_results['hit_rate'] + draw_results['hit_rate'] + chaos_results['hit_rate']) / 3

    logger.info("\n" + "="*80)
    logger.info("📊 STRATEGY CONFIDENCE ASSESSMENT")
    logger.info("="*80)
    logger.info(f"Average 2-Point Hit Rate: {avg_hit_rate:.1f}%")
    logger.info(f"Target: 7 points per week (0.7 PPG) from 10 games")

    # Calculate expected performance
    # Assume equal distribution of match types for simplicity
    expected_ppg = avg_hit_rate / 100 * 2  # If we always get the scoreline right

    confidence = min(10, int(expected_ppg / 0.7 * 10))
    logger.info(f"\n🎯 CONFIDENCE LEVEL: {confidence}/10")

    if confidence >= 7:
        logger.info("✅ HIGH CONFIDENCE - Strategy should exceed 0.7 PPG target")
    elif confidence >= 5:
        logger.info("⚠️  MODERATE CONFIDENCE - Strategy may approach 0.7 PPG target")
    else:
        logger.info("❌ LOW CONFIDENCE - Strategy unlikely to reach 0.7 PPG target alone")

    logger.info("\n" + "="*80)
    logger.info("💡 KEY RECOMMENDATIONS")
    logger.info("="*80)
    logger.info("1. PRIORITIZE Strong Favorite matches (≤1.50 odds) with clean sheet prediction")
    logger.info(f"2. Use {draw_results['scoreline']} for balanced matches (draw odds 3.00-3.50)")
    logger.info(f"3. Apply {chaos_results['scoreline']} for moderate favorites (odds 1.60-2.20)")
    logger.info("4. Avoid guessing on highly uncertain matches (all odds >3.0)")
    logger.info("5. Track actual performance weekly and adjust thresholds if needed")

def main():
    """Main analysis execution"""
    logger = setup_logging()

    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Starting AI-Driven Prediction Strategy Analysis...")
    logger.info(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Examine database structure
        examine_database_structure(cursor, logger)

        # Step 2: Run the three core analyses
        clean_sheet_results = analyze_clean_sheet_bankers(cursor, logger)
        draw_results = analyze_draw_hunters(cursor, logger)
        chaos_results = analyze_chaos_favorites(cursor, logger)

        # Step 3: Generate final strategy
        generate_strategy_manifesto(clean_sheet_results, draw_results, chaos_results, logger)

        logger.info("\n✅ Analysis completed successfully!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
