#!/usr/bin/env python3
"""
Player Gameweek Points vs Average Analysis

Plots for each gameweek in a season the amount of points a player got in that 
predictions competition for that week. Also plots the average score of all 
players in each gameweek for comparison.
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
        description='Plot player gameweek points vs average for a season'
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
        required=True,
        help='Season to analyze (required, e.g., "2025/2026")'
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


def verify_season_exists(cursor, season):
    """
    Verify season exists in database.
    
    Returns: True if season exists, False otherwise
    """
    cursor.execute(
        'SELECT COUNT(*) FROM fixtures WHERE season = ?',
        (season,)
    )
    result = cursor.fetchone()
    return result[0] > 0 if result else False


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


def get_player_gameweek_points(cursor, player_id, season):
    """
    Get player's points for each gameweek in a season.
    
    Returns: dict of {gameweek: points}
    """
    query = """
        SELECT
            f.gameweek,
            pr.home_goals as pred_home,
            pr.away_goals as pred_away,
            pr.predicted_result,
            r.home_goals as actual_home,
            r.away_goals as actual_away,
            r.result as actual_result
        FROM predictions pr
        JOIN fixtures f ON pr.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE pr.player_id = ?
            AND f.season = ?
            AND f.finished = 1
            AND r.home_goals IS NOT NULL
            AND r.away_goals IS NOT NULL
        ORDER BY f.gameweek
    """
    
    cursor.execute(query, (player_id, season))
    
    # Calculate points per gameweek (sum across all fixtures in gameweek)
    gameweek_points = defaultdict(int)
    
    for row in cursor.fetchall():
        gameweek = row[0]
        pred_home, pred_away, pred_result = row[1], row[2], row[3]
        actual_home, actual_away, actual_result = row[4], row[5], row[6]
        
        points = calculate_points(
            pred_home, pred_away, pred_result,
            actual_home, actual_away, actual_result
        )
        
        gameweek_points[gameweek] += points
    
    return dict(gameweek_points)


def get_average_gameweek_points(cursor, season):
    """
    Get average points for each gameweek across all players.
    
    Returns: dict of {gameweek: average_points}
    """
    query = """
        SELECT
            f.gameweek,
            pr.player_id,
            pr.home_goals as pred_home,
            pr.away_goals as pred_away,
            pr.predicted_result,
            r.home_goals as actual_home,
            r.away_goals as actual_away,
            r.result as actual_result
        FROM predictions pr
        JOIN fixtures f ON pr.fixture_id = f.fixture_id
        JOIN results r ON f.fixture_id = r.fixture_id
        JOIN players p ON pr.player_id = p.player_id
        WHERE f.season = ?
            AND f.finished = 1
            AND r.home_goals IS NOT NULL
            AND r.away_goals IS NOT NULL
            AND p.active = 1
        ORDER BY f.gameweek, pr.player_id
    """
    
    cursor.execute(query, (season,))
    
    # Calculate points per player per gameweek
    player_gameweek_points = defaultdict(lambda: defaultdict(int))
    
    for row in cursor.fetchall():
        gameweek = row[0]
        player_id = row[1]
        pred_home, pred_away, pred_result = row[2], row[3], row[4]
        actual_home, actual_away, actual_result = row[5], row[6], row[7]
        
        points = calculate_points(
            pred_home, pred_away, pred_result,
            actual_home, actual_away, actual_result
        )
        
        player_gameweek_points[gameweek][player_id] += points
    
    # Calculate average for each gameweek
    gameweek_averages = {}
    
    for gameweek, player_points in player_gameweek_points.items():
        if player_points:
            total_points = sum(player_points.values())
            num_players = len(player_points)
            gameweek_averages[gameweek] = total_points / num_players
    
    return gameweek_averages


def print_summary_table(player_points, average_points, player_name, season, logger):
    """Print formatted summary table to console"""
    logger.info(f"\n{'='*80}")
    logger.info(f"GAMEWEEK POINTS ANALYSIS - {player_name} - {season}")
    logger.info(f"{'='*80}")
    logger.info(f"{'Gameweek':<12} {'Player Points':<15} {'Average Points':<15} {'Difference':<15}")
    logger.info(f"{'-'*80}")
    
    all_gameweeks = sorted(set(list(player_points.keys()) + list(average_points.keys())))
    
    total_player_points = 0
    total_average_points = 0
    gameweeks_played = 0
    
    for gameweek in all_gameweeks:
        player_gw_points = player_points.get(gameweek, 0)
        avg_gw_points = average_points.get(gameweek, 0)
        difference = player_gw_points - avg_gw_points
        
        logger.info(f"{gameweek:<12} {player_gw_points:<15} {avg_gw_points:<15.2f} {difference:<15.2f}")
        
        if gameweek in player_points:
            total_player_points += player_gw_points
            gameweeks_played += 1
        if gameweek in average_points:
            total_average_points += avg_gw_points
    
    logger.info(f"{'-'*80}")
    logger.info(f"{'TOTALS':<12} {total_player_points:<15} {total_average_points:<15.2f} {total_player_points - total_average_points:<15.2f}")
    
    if gameweeks_played > 0:
        player_avg = total_player_points / gameweeks_played
        overall_avg = total_average_points / len(average_points) if average_points else 0
        logger.info(f"{'AVG/GAME':<12} {player_avg:<15.2f} {overall_avg:<15.2f} {player_avg - overall_avg:<15.2f}")
    
    logger.info(f"{'='*80}")


def generate_csv_output(player_points, average_points, player_name, season, output_dir):
    """Generate CSV file with gameweek points data"""
    safe_player_name = player_name.lower().replace(' ', '_')
    safe_season = season.replace('/', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"{safe_player_name}_{safe_season}_gameweek_points_{timestamp}.csv"
    
    all_gameweeks = sorted(set(list(player_points.keys()) + list(average_points.keys())))
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['gameweek', 'player_points', 'average_points', 'difference'])
        
        for gameweek in all_gameweeks:
            player_gw_points = player_points.get(gameweek, 0)
            avg_gw_points = average_points.get(gameweek, 0)
            difference = player_gw_points - avg_gw_points
            writer.writerow([gameweek, player_gw_points, avg_gw_points, difference])
    
    return filename


def create_comparison_chart(player_points, average_points, player_name, season, output_dir):
    """Generate matplotlib comparison chart"""
    safe_player_name = player_name.lower().replace(' ', '_')
    safe_season = season.replace('/', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"{safe_player_name}_{safe_season}_gameweek_points_{timestamp}.png"
    
    all_gameweeks = sorted(set(list(player_points.keys()) + list(average_points.keys())))
    
    # Prepare data for plotting
    gameweeks_list = []
    player_points_list = []
    average_points_list = []
    
    for gameweek in all_gameweeks:
        gameweeks_list.append(gameweek)
        player_points_list.append(player_points.get(gameweek, 0))
        average_points_list.append(average_points.get(gameweek, 0))
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # Plot player points as bars
    bars = ax.bar(gameweeks_list, player_points_list, 
                  width=0.6, alpha=0.7,
                  label=f'{player_name}', color='#12436D')  # Dark blue
    
    # Plot average as a line
    ax.plot(gameweeks_list, average_points_list, 
            marker='o', markersize=4, linewidth=2.5, 
            label='Average (All Players)', color='#E52E36')  # Red for contrast
    
    # Styling
    ax.set_xlabel('Gameweek', fontsize=12, fontweight='bold')
    ax.set_ylabel('Points', fontsize=12, fontweight='bold')
    ax.set_title(f'{player_name} vs Average Points per Gameweek - {season}',
                 fontsize=14, fontweight='bold')
    
    # Set x-axis ticks and limits based on actual data
    if gameweeks_list:
        ax.set_xticks(range(min(gameweeks_list), max(gameweeks_list) + 1, 2))  # Every 2 gameweeks for readability
        ax.set_xlim(min(gameweeks_list) - 0.7, max(gameweeks_list) + 0.7)
    
    # Set y-axis to start from 0 with some padding at top
    if player_points_list and average_points_list:
        max_points = max(max(player_points_list), max(average_points_list))
        ax.set_ylim(0, max_points + 1)
    
    ax.legend(loc='upper left', fontsize=11)
    ax.grid(axis='y', alpha=0.3, linestyle='--')  # Only horizontal grid lines for cleaner look
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    
    return filename


def main(args, logger):
    """Main execution function"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "gameweek_points_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Analyzing gameweek points for player: {args.player} in season: {args.season}")
    
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
        
        # Verify season exists
        if not verify_season_exists(cursor, args.season):
            logger.error(f"Season '{args.season}' not found in database")
            logger.info("\nAvailable seasons:")
            cursor.execute('SELECT DISTINCT season FROM fixtures ORDER BY season DESC')
            for row in cursor.fetchall():
                logger.info(f"  - {row[0]}")
            return
        
        logger.info(f"Found season: {args.season}")
        
        # Get player gameweek points
        player_points = get_player_gameweek_points(cursor, player_id, args.season)
        
        if not player_points:
            logger.warning(f"No finished predictions found for {actual_player_name} in {args.season}")
            return
        
        # Get average gameweek points
        average_points = get_average_gameweek_points(cursor, args.season)
        
        if not average_points:
            logger.warning(f"No finished predictions found for any players in {args.season}")
            return
        
        logger.info(f"Found data for {len(player_points)} gameweeks for {actual_player_name}")
        logger.info(f"Found average data for {len(average_points)} gameweeks")
        
        # Print summary table
        print_summary_table(player_points, average_points, actual_player_name, args.season, logger)
        
        # Generate CSV output
        if not args.no_csv:
            csv_file = generate_csv_output(player_points, average_points, actual_player_name, args.season, output_dir)
            logger.info(f"\nCSV saved to: {csv_file}")
        
        # Generate chart
        if not args.no_chart:
            chart_file = create_comparison_chart(player_points, average_points, actual_player_name, args.season, output_dir)
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