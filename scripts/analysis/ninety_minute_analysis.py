#!/usr/bin/env python3
"""
90-Minute Predictions Analysis

Analyzes player predictions against 90-minute match results (excluding injury time goals).
Uses match_events data from Pulse API to calculate scores at the 90-minute mark.
"""

import logging
import sqlite3
from pathlib import Path
import argparse
from typing import Dict, List, Tuple


def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def get_ninety_minute_results(cursor, season='2025/2026', gameweek=None):
    """
    Calculate 90-minute results from match_events data.

    Returns list of dicts with fixture_id, gameweek, home_team, away_team,
    home_90min, away_90min, result_90min
    """
    gameweek_filter = f"AND f.gameweek = {gameweek}" if gameweek else ""

    query = f"""
    SELECT
        f.fixture_id,
        f.gameweek,
        t_home.team_name as home_team,
        t_away.team_name as away_team,
        COALESCE(SUM(CASE
            WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
            AND CAST(me.event_time AS INTEGER) <= 5400
            THEN 1 ELSE 0
        END), 0) as home_90min,
        COALESCE(SUM(CASE
            WHEN (me.team_id = t_away.team_id OR me.team_id = t_away.pulse_id)
            AND CAST(me.event_time AS INTEGER) <= 5400
            THEN 1 ELSE 0
        END), 0) as away_90min,
        r.home_goals as ft_home,
        r.away_goals as ft_away,
        r.result as ft_result
    FROM fixtures f
    JOIN teams t_home ON f.home_teamid = t_home.team_id
    JOIN teams t_away ON f.away_teamid = t_away.team_id
    LEFT JOIN results r ON f.fixture_id = r.fixture_id
    LEFT JOIN match_events me ON f.pulse_id = me.pulseid AND me.event_type IN ('G', 'P', 'O')
    WHERE f.season = ? AND f.pulse_id IS NOT NULL {gameweek_filter}
    GROUP BY f.fixture_id
    ORDER BY f.gameweek, f.fixture_id
    """

    cursor.execute(query, (season,))

    results = []
    for row in cursor.fetchall():
        fixture_id, gameweek, home_team, away_team, home_90min, away_90min, ft_home, ft_away, ft_result = row

        # Calculate result at 90 minutes
        if home_90min > away_90min:
            result_90min = 'H'
        elif away_90min > home_90min:
            result_90min = 'A'
        else:
            result_90min = 'D'

        results.append({
            'fixture_id': fixture_id,
            'gameweek': gameweek,
            'home_team': home_team,
            'away_team': away_team,
            'home_90min': home_90min,
            'away_90min': away_90min,
            'result_90min': result_90min,
            'ft_home': ft_home or 0,
            'ft_away': ft_away or 0,
            'ft_result': ft_result or 'D'
        })

    return results


def get_player_predictions(cursor, fixture_ids):
    """Get all player predictions for given fixture IDs"""
    placeholders = ','.join('?' * len(fixture_ids))

    query = f"""
    SELECT
        pr.fixture_id,
        pr.player_id,
        p.player_name,
        pr.home_goals,
        pr.away_goals,
        pr.predicted_result
    FROM predictions pr
    JOIN players p ON pr.player_id = p.player_id
    WHERE pr.fixture_id IN ({placeholders})
    ORDER BY pr.player_id, pr.fixture_id
    """

    cursor.execute(query, fixture_ids)

    predictions = []
    for row in cursor.fetchall():
        fixture_id, player_id, player_name, home_goals, away_goals, predicted_result = row
        predictions.append({
            'fixture_id': fixture_id,
            'player_id': player_id,
            'player_name': player_name,
            'home_goals': home_goals,
            'away_goals': away_goals,
            'predicted_result': predicted_result
        })

    return predictions


def calculate_points(prediction, actual_result):
    """
    Calculate points for a single prediction.

    Returns: (points, is_exact_score, is_correct_result)
    """
    pred_home = prediction['home_goals']
    pred_away = prediction['away_goals']
    actual_home = actual_result['home_90min']
    actual_away = actual_result['away_90min']

    # Check for exact score (2 points)
    if pred_home == actual_home and pred_away == actual_away:
        return 2, True, True

    # Normalize result formats (database has both 'H' and 'HW' formats)
    pred_result = prediction['predicted_result'][0] if prediction['predicted_result'] else 'D'
    actual_res = actual_result['result_90min'][0] if actual_result['result_90min'] else 'D'

    # Check for correct result (1 point)
    if pred_result == actual_res:
        return 1, False, True

    # Incorrect prediction (0 points)
    return 0, False, False


def analyze_predictions(ninety_min_results, predictions):
    """
    Analyze all predictions against 90-minute results.

    Returns player stats dictionary
    """
    # Create lookup for 90-minute results
    results_lookup = {r['fixture_id']: r for r in ninety_min_results}

    # Initialize player stats
    player_stats = {}

    for pred in predictions:
        fixture_id = pred['fixture_id']
        player_id = pred['player_id']
        player_name = pred['player_name']

        # Skip if no 90-minute result available for this fixture
        if fixture_id not in results_lookup:
            continue

        # Initialize player stats if needed
        if player_id not in player_stats:
            player_stats[player_id] = {
                'player_name': player_name,
                'total_points': 0,
                'games_analyzed': 0,
                'exact_scores': 0,
                'correct_results': 0
            }

        # Calculate points for this prediction
        actual_result = results_lookup[fixture_id]
        points, is_exact, is_correct = calculate_points(pred, actual_result)

        # Update stats
        player_stats[player_id]['total_points'] += points
        player_stats[player_id]['games_analyzed'] += 1
        if is_exact:
            player_stats[player_id]['exact_scores'] += 1
        if is_correct:
            player_stats[player_id]['correct_results'] += 1

    return player_stats


def print_rankings(player_stats, logger):
    """Print player rankings table"""
    if not player_stats:
        logger.warning("No player stats to display")
        return

    # Sort by total points (descending), then by correct results
    sorted_players = sorted(
        player_stats.values(),
        key=lambda x: (x['total_points'], x['correct_results']),
        reverse=True
    )

    # Print header
    logger.info("\n" + "="*80)
    logger.info("90-MINUTE PREDICTIONS ANALYSIS - PLAYER RANKINGS")
    logger.info("="*80)

    # Print table header
    header = f"{'Rank':<6} {'Player':<20} {'Points':<8} {'Games':<8} {'Exact':<8} {'Correct':<10} {'Accuracy':<10}"
    logger.info(header)
    logger.info("-"*80)

    # Print player rows
    for rank, stats in enumerate(sorted_players, 1):
        accuracy = (stats['correct_results'] / stats['games_analyzed'] * 100) if stats['games_analyzed'] > 0 else 0

        row = (f"{rank:<6} "
               f"{stats['player_name']:<20} "
               f"{stats['total_points']:<8} "
               f"{stats['games_analyzed']:<8} "
               f"{stats['exact_scores']:<8} "
               f"{stats['correct_results']:<10} "
               f"{accuracy:.1f}%")

        logger.info(row)

    logger.info("="*80)


def compare_full_time_vs_ninety_min(cursor, season='2025/2026'):
    """Compare full-time results vs 90-minute results"""
    query = """
    SELECT
        f.fixture_id,
        f.gameweek,
        r.home_goals as ft_home,
        r.away_goals as ft_away,
        r.result as ft_result,
        COALESCE(SUM(CASE
            WHEN t_me.pulse_id = t_home.pulse_id
            AND CAST(me.event_time AS INTEGER) <= 5400
            THEN 1 ELSE 0
        END), 0) as home_90min,
        COALESCE(SUM(CASE
            WHEN t_me.pulse_id = t_away.pulse_id
            AND CAST(me.event_time AS INTEGER) <= 5400
            THEN 1 ELSE 0
        END), 0) as away_90min
    FROM fixtures f
    JOIN teams t_home ON f.home_teamid = t_home.team_id
    JOIN teams t_away ON f.away_teamid = t_away.team_id
    JOIN results r ON f.fixture_id = r.fixture_id
    LEFT JOIN match_events me ON f.pulse_id = me.pulseid AND me.event_type IN ('G', 'P', 'O')
    LEFT JOIN teams t_me ON me.team_id = t_me.pulse_id
    WHERE f.season = ? AND f.pulse_id IS NOT NULL
    GROUP BY f.fixture_id
    """

    cursor.execute(query, (season,))

    total_games = 0
    different_scores = 0
    different_results = 0

    for row in cursor.fetchall():
        fixture_id, gameweek, ft_home, ft_away, ft_result, min90_home, min90_away = row
        total_games += 1

        # Calculate 90-min result
        if min90_home > min90_away:
            min90_result = 'H'
        elif min90_away > min90_home:
            min90_result = 'A'
        else:
            min90_result = 'D'

        # Check differences
        if ft_home != min90_home or ft_away != min90_away:
            different_scores += 1

        if ft_result != min90_result:
            different_results += 1

    return total_games, different_scores, different_results


def main_analysis(args, logger):
    """Main analysis logic"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

    logger.info("Starting 90-minute predictions analysis...")
    logger.info(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get 90-minute results
        season = args.season
        gameweek = args.gameweek

        logger.info(f"Analyzing season: {season}")
        if gameweek:
            logger.info(f"Filtering for gameweek: {gameweek}")

        ninety_min_results = get_ninety_minute_results(cursor, season, gameweek)
        logger.info(f"Found {len(ninety_min_results)} fixtures with match events data")

        if not ninety_min_results:
            logger.warning("No fixtures with match events data found")
            return

        # Get player predictions
        fixture_ids = [r['fixture_id'] for r in ninety_min_results]
        predictions = get_player_predictions(cursor, fixture_ids)
        logger.info(f"Found {len(predictions)} predictions to analyze")

        # Analyze predictions
        player_stats = analyze_predictions(ninety_min_results, predictions)

        # Generate markdown report if requested
        if args.markdown:
            logger.info("Generating summary markdown report...")
            markdown_content = generate_markdown_report(
                ninety_min_results, predictions, player_stats, season, gameweek
            )
            output_path = save_markdown_report(markdown_content, season, gameweek, 'summary')
            logger.info(f"Summary report saved to: {output_path}")

        # Generate player detail report if requested
        if args.player_detail:
            logger.info("Generating player detail markdown report...")
            player_detail_content = generate_player_detail_report(
                ninety_min_results, predictions, player_stats, season, gameweek
            )
            output_path = save_markdown_report(player_detail_content, season, gameweek, 'player')
            logger.info(f"Player detail report saved to: {output_path}")

        # Console output if no markdown requested
        if not args.markdown and not args.player_detail:
            # Print rankings to console
            print_rankings(player_stats, logger)

            # Compare full-time vs 90-minute results
            if not gameweek:  # Only show comparison for full season
                total_games, diff_scores, diff_results = compare_full_time_vs_ninety_min(cursor, season)
                logger.info("\nFull-time vs 90-minute comparison:")
                logger.info(f"  Total games analyzed: {total_games}")
                logger.info(f"  Different scores: {diff_scores} ({diff_scores/total_games*100:.1f}%)")
                logger.info(f"  Different results: {diff_results} ({diff_results/total_games*100:.1f}%)")

        logger.info("\nAnalysis completed successfully")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()


def generate_markdown_report(ninety_min_results, predictions, player_stats, season, gameweek=None):
    """Generate markdown report with fixtures, predictions, and league table"""
    # Group predictions by fixture
    predictions_by_fixture = {}
    for pred in predictions:
        fixture_id = pred['fixture_id']
        if fixture_id not in predictions_by_fixture:
            predictions_by_fixture[fixture_id] = []
        predictions_by_fixture[fixture_id].append(pred)

    # Build markdown content
    md_lines = []

    # Title
    if gameweek:
        md_lines.append(f"# 90-Minute Analysis - Season {season} - Gameweek {gameweek}\n")
    else:
        md_lines.append(f"# 90-Minute Analysis - Season {season}\n")

    md_lines.append("*Predictions scored against 90-minute results (excluding injury time)*\n")
    md_lines.append("---\n")

    # Group fixtures by gameweek
    fixtures_by_gameweek = {}
    for result in ninety_min_results:
        gw = result['gameweek']
        if gw not in fixtures_by_gameweek:
            fixtures_by_gameweek[gw] = []
        fixtures_by_gameweek[gw].append(result)

    # Generate fixture sections
    for gw in sorted(fixtures_by_gameweek.keys()):
        md_lines.append(f"\n## Gameweek {gw}\n")

        for result in fixtures_by_gameweek[gw]:
            fixture_id = result['fixture_id']
            home_team = result['home_team'].title()
            away_team = result['away_team'].title()
            home_score = result['home_90min']
            away_score = result['away_90min']

            # Fixture header
            md_lines.append(f"\n### {home_team} {home_score} - {away_score} {away_team}\n")

            # Player predictions for this fixture
            if fixture_id in predictions_by_fixture:
                fixture_predictions = predictions_by_fixture[fixture_id]

                # Sort predictions by player name
                fixture_predictions.sort(key=lambda x: x['player_name'])

                md_lines.append("\n**Predictions:**\n")
                for pred in fixture_predictions:
                    player_name = pred['player_name'].title()
                    pred_score = f"{pred['home_goals']}-{pred['away_goals']}"

                    # Calculate points for this prediction
                    points, is_exact, is_correct = calculate_points(pred, result)

                    # Add indicator for points
                    if is_exact:
                        indicator = "✓✓ (2 pts)"
                    elif is_correct:
                        indicator = "✓ (1 pt)"
                    else:
                        indicator = "✗ (0 pts)"

                    md_lines.append(f"- {player_name}: {pred_score} {indicator}\n")

    # League table
    md_lines.append("\n---\n")
    md_lines.append("\n## League Table\n")

    # Sort by total points (descending), then by correct results
    sorted_players = sorted(
        player_stats.values(),
        key=lambda x: (x['total_points'], x['correct_results']),
        reverse=True
    )

    md_lines.append("\n| Rank | Player | Points | Games | Exact Scores | Correct Results | Accuracy |\n")
    md_lines.append("|------|--------|--------|-------|--------------|-----------------|----------|\n")

    for rank, stats in enumerate(sorted_players, 1):
        player_name = stats['player_name'].title()
        points = stats['total_points']
        games = stats['games_analyzed']
        exact = stats['exact_scores']
        correct = stats['correct_results']
        accuracy = (correct / games * 100) if games > 0 else 0

        md_lines.append(f"| {rank} | {player_name} | {points} | {games} | {exact} | {correct} | {accuracy:.1f}% |\n")

    return ''.join(md_lines)


def generate_player_detail_report(ninety_min_results, predictions, player_stats, season, gameweek=None):
    """Generate detailed player-by-player analysis with 90min vs FT comparison"""
    # Group predictions by player
    predictions_by_player = {}
    for pred in predictions:
        player_id = pred['player_id']
        if player_id not in predictions_by_player:
            predictions_by_player[player_id] = []
        predictions_by_player[player_id].append(pred)

    # Create lookup for 90-minute results
    results_lookup = {r['fixture_id']: r for r in ninety_min_results}

    # Build markdown content
    md_lines = []

    # Title
    if gameweek:
        md_lines.append(f"# Player Detail Analysis - Season {season} - Gameweek {gameweek}\n")
    else:
        md_lines.append(f"# Player Detail Analysis - Season {season}\n")

    md_lines.append("*Individual player breakdowns showing 90-minute vs Full-Time score impact*\n")
    md_lines.append("---\n")

    # Sort players by total points
    sorted_players = sorted(
        player_stats.values(),
        key=lambda x: (x['total_points'], x['correct_results']),
        reverse=True
    )

    # Generate player sections
    for rank, stats in enumerate(sorted_players, 1):
        player_name = stats['player_name'].title()
        player_id = [pid for pid, pstats in player_stats.items() if pstats['player_name'] == stats['player_name']][0]

        md_lines.append(f"\n## {rank}. {player_name}\n")
        md_lines.append(f"\n**Overall Stats:** {stats['total_points']} points | ")
        md_lines.append(f"{stats['correct_results']}/{stats['games_analyzed']} correct results | ")
        md_lines.append(f"{stats['exact_scores']} exact scores | ")
        accuracy = (stats['correct_results'] / stats['games_analyzed'] * 100) if stats['games_analyzed'] > 0 else 0
        md_lines.append(f"{accuracy:.1f}% accuracy\n")

        # Get player's predictions
        player_predictions = predictions_by_player.get(player_id, [])

        # Calculate points with full-time scores
        points_90min = 0
        points_ft = 0
        different_results = []

        for pred in player_predictions:
            fixture_id = pred['fixture_id']
            if fixture_id not in results_lookup:
                continue

            result = results_lookup[fixture_id]

            # Calculate points for 90-minute result
            pts_90, _, _ = calculate_points(pred, result)
            points_90min += pts_90

            # Calculate points for full-time result
            # Normalize result format (database has both 'H' and 'HW' formats)
            ft_result_normalized = result['ft_result'][0] if result['ft_result'] else 'D'
            ft_result_dict = {
                'home_90min': result['ft_home'],
                'away_90min': result['ft_away'],
                'result_90min': ft_result_normalized
            }
            pts_ft, _, _ = calculate_points(pred, ft_result_dict)
            points_ft += pts_ft

            # Track fixtures where 90min vs FT made a difference to points
            if pts_90 != pts_ft:
                different_results.append({
                    'fixture': result,
                    'prediction': pred,
                    'pts_90': pts_90,
                    'pts_ft': pts_ft
                })

        # Show points comparison (FT - 90min to show injury time impact)
        injury_time_impact = points_ft - points_90min
        if injury_time_impact > 0:
            md_lines.append(f"\n**Injury Time Impact:** +{injury_time_impact} points (benefited from late goals)\n")
        elif injury_time_impact < 0:
            md_lines.append(f"\n**Injury Time Impact:** {injury_time_impact} points (hurt by late goals)\n")
        else:
            md_lines.append(f"\n**Injury Time Impact:** No impact from injury time goals\n")

        # Show fixtures where injury time affected scoring
        if different_results:
            md_lines.append(f"\n### Fixtures Affected by Injury Time ({len(different_results)} games)\n")
            md_lines.append("\n| GW | Match | 90min | FT | Prediction | 90min Pts | FT Pts | Impact |\n")
            md_lines.append("|-----|-------|-------|-----|------------|-----------|---------|--------|\n")

            for item in sorted(different_results, key=lambda x: x['fixture']['gameweek']):
                fixture = item['fixture']
                pred = item['prediction']
                gw = fixture['gameweek']
                home = fixture['home_team'].title()
                away = fixture['away_team'].title()
                score_90 = f"{fixture['home_90min']}-{fixture['away_90min']}"
                score_ft = f"{fixture['ft_home']}-{fixture['ft_away']}"
                pred_score = f"{pred['home_goals']}-{pred['away_goals']}"
                pts_90 = item['pts_90']
                pts_ft = item['pts_ft']
                impact = pts_ft - pts_90  # FT - 90min to show injury time benefit/loss

                if impact > 0:
                    impact_str = f"+{impact}"
                elif impact < 0:
                    impact_str = f"{impact}"
                else:
                    impact_str = "="

                md_lines.append(f"| {gw} | {home} vs {away} | {score_90} | {score_ft} | {pred_score} | {pts_90} | {pts_ft} | {impact_str} |\n")

        md_lines.append("\n---\n")

    return ''.join(md_lines)


def save_markdown_report(content, season, gameweek=None, report_type='summary'):
    """Save markdown report to file"""
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "90min_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    season_slug = season.replace('/', '_')
    if gameweek:
        if report_type == 'player':
            filename = f"90min_player_detail_{season_slug}_gw{gameweek}.md"
        else:
            filename = f"90min_analysis_{season_slug}_gw{gameweek}.md"
    else:
        if report_type == 'player':
            filename = f"90min_player_detail_{season_slug}.md"
        else:
            filename = f"90min_analysis_{season_slug}.md"

    output_path = output_dir / filename

    with open(output_path, 'w') as f:
        f.write(content)

    return output_path


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze player predictions against 90-minute match results'
    )
    parser.add_argument(
        '--season',
        default='2025/2026',
        help='Season to analyze (default: 2025/2026)'
    )
    parser.add_argument(
        '--gameweek',
        type=int,
        help='Specific gameweek to analyze (optional)'
    )
    parser.add_argument(
        '--markdown',
        action='store_true',
        help='Generate summary markdown report'
    )
    parser.add_argument(
        '--player-detail',
        action='store_true',
        help='Generate player detail markdown report with 90min vs FT comparison'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    main_analysis(args, logger)
