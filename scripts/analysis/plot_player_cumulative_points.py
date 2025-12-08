#!/usr/bin/env python3
"""
Player Cumulative Points Analysis

Plots cumulative prediction points per gameweek comparing seasons for a given player.
Shows how a player's points accumulate throughout each season, allowing comparison
of performance across different years.
"""

import logging
import sqlite3
from pathlib import Path
import argparse
from datetime import datetime
from collections import defaultdict
import csv

import matplotlib.pyplot as plt


def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Plot cumulative prediction points per gameweek for a player'
    )
    parser.add_argument(
        '--player',
        type=str,
        required=True,
        help='Player name (required, e.g., "Tom Levin")'
    )
    parser.add_argument(
        '--season',
        type=str,
        help='Filter for specific season (optional, e.g., "2025/2026")'
    )
    parser.add_argument(
        '--no-chart',
        action='store_true',
        help='Skip chart generation (CSV only)'
    )
    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip CSV generation (chart only)'
    )
    return parser.parse_args()


def season_sort_key(season):
    """
    Convert season string to sortable integer for chronological ordering.

    Seasons like '93/94' -> 1993, '00/01' -> 2000, '25/26' -> 2025
    Assumes seasons >= 93 are 1900s, seasons < 93 are 2000s
    """
    year_start = int(season.split('/')[0])

    if year_start >= 93:
        return 1900 + year_start
    else:
        return 2000 + year_start


def verify_player_exists(cursor, player_name):
    """
    Verify player exists in database.

    Returns: (player_id, actual_player_name) or None if not found
    """
    cursor.execute(
        'SELECT player_id, player_name FROM players WHERE LOWER(player_name) = LOWER(?)',
        (player_name,)
    )
    result = cursor.fetchone()

    if result:
        return result[0], result[1]
    return None


def get_player_predictions_with_results(cursor, player_id, season_filter=None):
    """
    Get all predictions with results for a player.

    Returns: List of dictionaries with prediction and result data
    """
    query = """
        SELECT
            f.season,
            f.gameweek,
            pr.home_goals as pred_home,
            pr.away_goals as pred_away,
            pr.predicted_result,
            r.home_goals as actual_home,
            r.away_goals as actual_away,
            r.result as actual_result
        FROM predictions pr
        JOIN players p ON pr.player_id = p.player_id
        JOIN fixtures f ON pr.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.player_id = ?
            AND f.finished = 1
            AND r.home_goals IS NOT NULL
            AND r.away_goals IS NOT NULL
    """

    params = [player_id]

    if season_filter:
        query += " AND f.season = ?"
        params.append(season_filter)

    query += " ORDER BY f.season, f.gameweek"

    cursor.execute(query, params)

    predictions = []
    for row in cursor.fetchall():
        predictions.append({
            'season': row[0],
            'gameweek': row[1],
            'pred_home': row[2],
            'pred_away': row[3],
            'pred_result': row[4],
            'actual_home': row[5],
            'actual_away': row[6],
            'actual_result': row[7]
        })

    return predictions


def calculate_points(pred_home, pred_away, pred_result, actual_home, actual_away, actual_result):
    """
    Calculate points for a single prediction.

    Returns: int (0, 1, or 2)
    - 2 points: exact score match
    - 1 point: correct result only
    - 0 points: incorrect
    """
    # Check for exact score (2 points)
    if pred_home == actual_home and pred_away == actual_away:
        return 2

    # Normalize result formats (handle both 'H'/'HW', 'A'/'AW', 'D' formats)
    pred_normalized = pred_result[0] if pred_result else 'D'
    actual_normalized = actual_result[0] if actual_result else 'D'

    # Check for correct result (1 point)
    if pred_normalized == actual_normalized:
        return 1

    # Incorrect (0 points)
    return 0


def calculate_cumulative_points_by_season(predictions):
    """
    Calculate cumulative points per gameweek for each season.

    Returns: (season_data, max_gameweeks)
        season_data: dict of {season: {gameweek: cumulative_points}}
        max_gameweeks: dict of {season: max_gameweek_with_data}
    """
    # Step 1: Calculate points per gameweek (not cumulative yet)
    gameweek_points = defaultdict(lambda: defaultdict(int))
    max_gameweeks = defaultdict(int)

    for pred in predictions:
        season = pred['season']
        gameweek = pred['gameweek']

        points = calculate_points(
            pred['pred_home'],
            pred['pred_away'],
            pred['pred_result'],
            pred['actual_home'],
            pred['actual_away'],
            pred['actual_result']
        )

        # Accumulate points for this gameweek (multiple fixtures per gameweek)
        gameweek_points[season][gameweek] += points

        # Track maximum gameweek with actual data
        max_gameweeks[season] = max(max_gameweeks[season], gameweek)

    # Step 2: Calculate cumulative totals
    season_data = defaultdict(lambda: defaultdict(int))

    for season in gameweek_points:
        cumulative = 0
        for gameweek in range(1, max_gameweeks[season] + 1):
            # Add this gameweek's points to cumulative total
            cumulative += gameweek_points[season].get(gameweek, 0)
            season_data[season][gameweek] = cumulative

    return dict(season_data), dict(max_gameweeks)


def print_summary_table(season_data, player_name, logger):
    """Print formatted summary table to console"""
    logger.info(f"\n{'='*70}")
    logger.info(f"CUMULATIVE POINTS SUMMARY - {player_name}")
    logger.info(f"{'='*70}")
    logger.info(f"{'Season':<12} {'Games':<8} {'Total Points':<15} {'Avg/Game':<12}")
    logger.info(f"{'-'*70}")

    for season in sorted(season_data.keys(), key=season_sort_key):
        # Count non-zero gameweeks (games played)
        games_played = len([gw for gw in season_data[season] if season_data[season][gw] > 0 or gw == 1])

        # Get final cumulative total
        total_points = max(season_data[season].values()) if season_data[season] else 0

        # Calculate average
        avg_per_game = total_points / games_played if games_played > 0 else 0

        logger.info(f"{season:<12} {games_played:<8} {total_points:<15} {avg_per_game:<12.2f}")

    logger.info(f"{'='*70}")


def generate_csv_output(season_data, player_name, output_dir):
    """Generate CSV file with cumulative points data"""
    safe_player_name = player_name.lower().replace(' ', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"{safe_player_name}_cumulative_{timestamp}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['season', 'gameweek', 'cumulative_points'])

        for season in sorted(season_data.keys(), key=season_sort_key):
            # Only write gameweeks that have data
            gameweeks_with_data = sorted(season_data[season].keys())
            for gameweek in gameweeks_with_data:
                points = season_data[season][gameweek]
                writer.writerow([season, gameweek, points])

    return filename


def create_line_chart(season_data, player_name, output_dir):
    """Generate matplotlib line chart"""
    safe_player_name = player_name.lower().replace(' ', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"{safe_player_name}_cumulative_{timestamp}.png"

    # Sort seasons chronologically
    sorted_seasons = sorted(season_data.keys(), key=season_sort_key)

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    # Color scheme: ONS color guidance
    # https://style.ons.gov.uk/category/data-visualisation/
    ons_colors = [
        '#12436D',  # Dark blue
        '#28A197',  # Teal
        '#801650',  # Purple
        '#F46A25',  # Orange
        '#3D3D3D',  # Dark grey
        '#A285D1',  # Light purple
        '#1D70B8',  # Bright blue
        '#912B88',  # Magenta
        '#6BACE6',  # Light blue
        '#E52E36',  # Red
        '#FFC726',  # Yellow
        '#85994B',  # Olive
    ]

    # Use ONS colors, cycling if more seasons than colors
    num_seasons = len(sorted_seasons)
    colors = [ons_colors[i % len(ons_colors)] for i in range(num_seasons)]

    # Determine overall max gameweek for x-axis limit
    max_gameweek_overall = 0

    # Plot each season as a line
    for idx, season in enumerate(sorted_seasons):
        # Only plot gameweeks that have data for this season
        gameweeks_with_data = sorted(season_data[season].keys())
        if gameweeks_with_data:
            max_gameweek_overall = max(max_gameweek_overall, max(gameweeks_with_data))
            cumulative_points = [season_data[season][gw] for gw in gameweeks_with_data]

            ax.plot(gameweeks_with_data, cumulative_points,
                    marker='o', markersize=4, linewidth=2,
                    label=season, color=colors[idx])

    # Styling
    ax.set_xlabel('Gameweek', fontsize=12, fontweight='bold')
    ax.set_ylabel('Cumulative Points', fontsize=12, fontweight='bold')
    ax.set_title(f'{player_name} - Cumulative Points by Gameweek',
                 fontsize=14, fontweight='bold')

    # Set x-axis ticks and limits based on actual data
    ax.set_xticks(range(0, max_gameweek_overall + 2, 2))
    ax.set_xlim(0.5, max_gameweek_overall + 0.5)

    ax.legend(loc='upper left', fontsize=10)
    ax.grid(axis='both', alpha=0.3, linestyle='--')

    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

    return filename


def main(args, logger):
    """Main execution function"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "player_cumulative_points"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Analyzing cumulative points for player: {args.player}")

    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verify player exists
        player_result = verify_player_exists(cursor, args.player)

        if not player_result:
            logger.error(f"Player '{args.player}' not found in database")
            logger.info("\nAvailable players:")
            cursor.execute('SELECT player_name FROM players ORDER BY player_name')
            for row in cursor.fetchall():
                logger.info(f"  - {row[0]}")
            return

        player_id, actual_player_name = player_result
        logger.info(f"Found player: {actual_player_name}")

        # Get predictions with results
        predictions = get_player_predictions_with_results(cursor, player_id, args.season)

        if not predictions:
            logger.warning(f"No finished predictions found for {actual_player_name}")
            if args.season:
                logger.info("Try without --season filter or check season format (e.g., '2025/2026')")
            return

        logger.info(f"Found {len(predictions)} finished predictions")

        # Calculate cumulative points by season
        season_data, _ = calculate_cumulative_points_by_season(predictions)

        logger.info(f"Processed {len(season_data)} season(s)")

        # Print summary table
        print_summary_table(season_data, actual_player_name, logger)

        # Generate CSV output
        if not args.no_csv:
            csv_file = generate_csv_output(season_data, actual_player_name, output_dir)
            logger.info(f"\nCSV saved to: {csv_file}")

        # Generate chart
        if not args.no_chart:
            chart_file = create_line_chart(season_data, actual_player_name, output_dir)
            logger.info(f"Chart saved to: {chart_file}")

        logger.info("\nAnalysis completed successfully")

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    main(args, logger)
