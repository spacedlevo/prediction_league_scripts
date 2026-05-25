#!/usr/bin/env python3
"""
Plot cumulative points for top 10 prediction league players across gameweeks in a season.
"""

import sqlite3
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import argparse
import logging
from collections import defaultdict

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def setup_plot_style():
    """Setup matplotlib styling"""
    plt.style.use('default')
    plt.rcParams['figure.figsize'] = (14, 8)
    plt.rcParams['font.size'] = 10

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

def get_top_players_cumulative_points(db_path, season='2025/2026', top_n=10, logger=None):
    """
    Get cumulative points data for top N prediction league players across all gameweeks.
    
    Args:
        db_path: Path to SQLite database
        season: Season to analyze (default: 2025/2026)
        top_n: Number of top players to include (default: 10)
        logger: Logger instance
    
    Returns:
        tuple: (pivot_df, top_players_df)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if logger:
        logger.info(f"Getting top {top_n} players data for season {season}...")
    
    # Get all players with predictions in this season
    query = """
        SELECT
            p.player_id,
            p.player_name,
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
        JOIN players p ON pr.player_id = p.player_id
        WHERE f.season = ?
            AND f.finished = 1
            AND r.home_goals IS NOT NULL
            AND r.away_goals IS NOT NULL
            AND p.active = 1
        ORDER BY p.player_id, f.gameweek
    """
    
    cursor.execute(query, (season,))
    
    # Calculate points per player per gameweek
    player_gameweek_points = defaultdict(lambda: defaultdict(int))
    player_names = {}
    
    for row in cursor.fetchall():
        player_id, player_name, gameweek = row[0], row[1], row[2]
        pred_home, pred_away, pred_result = row[3], row[4], row[5]
        actual_home, actual_away, actual_result = row[6], row[7], row[8]
        
        player_names[player_id] = player_name
        
        points = calculate_points(
            pred_home, pred_away, pred_result,
            actual_home, actual_away, actual_result
        )
        
        player_gameweek_points[player_id][gameweek] += points
    
    conn.close()
    
    if not player_gameweek_points:
        if logger:
            logger.error(f"No player data found for season {season}")
        return None, None
    
    # Calculate total points for each player
    player_totals = {}
    for player_id, gameweeks in player_gameweek_points.items():
        player_totals[player_id] = sum(gameweeks.values())
    
    # Get top N players
    top_players = sorted(player_totals.items(), key=lambda x: x[1], reverse=True)[:top_n]
    
    if logger:
        logger.info(f"Found {len(player_totals)} players, selecting top {len(top_players)}")
    
    # Create DataFrames
    top_players_data = []
    cumulative_data = []
    
    for player_id, total_points in top_players:
        player_name = player_names[player_id]
        top_players_data.append({
            'player_id': player_id,
            'player_name': player_name,
            'total_season_points': total_points
        })
        
        # Calculate cumulative points for this player
        gameweeks = sorted(player_gameweek_points[player_id].keys())
        cumulative = 0
        
        for gameweek in gameweeks:
            cumulative += player_gameweek_points[player_id][gameweek]
            cumulative_data.append({
                'player_id': player_id,
                'player_name': player_name,
                'gameweek': gameweek,
                'cumulative_points': cumulative
            })
    
    top_players_df = pd.DataFrame(top_players_data)
    cumulative_df = pd.DataFrame(cumulative_data)
    
    # Create pivot table
    pivot_df = cumulative_df.pivot(index='gameweek', columns='player_name', values='cumulative_points')
    
    if logger:
        logger.info(f"Processed data for {len(pivot_df.columns)} players across {len(pivot_df)} gameweeks")
    
    return pivot_df, top_players_df

def create_cumulative_points_plot(pivot_df, top_players_df, season='2025/2026', output_dir=None, logger=None):
    """
    Create and save the cumulative points plot.
    
    Args:
        pivot_df: Pivoted DataFrame with cumulative points
        top_players_df: DataFrame with player names and total points
        season: Season being plotted
        output_dir: Directory to save the plot (optional)
        logger: Logger instance
    """
    setup_plot_style()
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    if logger:
        logger.info("Creating cumulative points plot...")
    
    # Plot lines for each player
    for player_name in pivot_df.columns:
        # Get total points for this player for the legend
        total_points = top_players_df[top_players_df['player_name'] == player_name]['total_season_points'].iloc[0]
        label = f"{player_name} ({total_points} pts)"
        
        # Plot the line
        pivot_df[player_name].plot(ax=ax, marker='o', markersize=3, linewidth=2, label=label)
    
    # Customize the plot
    ax.set_xlabel('Gameweek', fontsize=12)
    ax.set_ylabel('Cumulative Points', fontsize=12)
    ax.set_title(f'Cumulative Prediction League Points - Top 10 Players - {season}', fontsize=14, fontweight='bold')
    
    # Set x-axis to show all gameweeks
    max_gameweek = pivot_df.index.max()
    min_gameweek = pivot_df.index.min()
    ax.set_xlim(min_gameweek, max_gameweek)
    ax.set_xticks(range(min_gameweek, max_gameweek + 1, 2))  # Show every 2nd gameweek
    
    # Add grid for better readability
    ax.grid(True, alpha=0.3)
    
    # Position legend outside the plot area
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    # Tight layout to prevent legend cutoff
    plt.tight_layout()
    
    # Save the plot
    if output_dir:
        output_path = Path(output_dir) / f'top_10_prediction_league_cumulative_points_{season.replace("/", "_")}.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        if logger:
            logger.info(f"Plot saved to: {output_path}")
    
    plt.show()
    
    return fig

def print_summary_stats(top_players_df, pivot_df, logger=None):
    """Print summary statistics"""
    if logger:
        logger.info(f"\nTop 10 Prediction League Players Summary:")
        logger.info("=" * 60)
    else:
        print(f"\nTop 10 Prediction League Players Summary:")
        print("=" * 60)
    
    for idx, row in top_players_df.iterrows():
        player_name = row['player_name']
        total_points = row['total_season_points']
        
        if player_name in pivot_df.columns:
            # Get final gameweek data
            player_data = pivot_df[player_name].dropna()
            if not player_data.empty:
                final_cumulative_points = player_data.iloc[-1]
                gameweeks_played = len(player_data)
                avg_per_gw = total_points / gameweeks_played if gameweeks_played > 0 else 0
                
                summary_line = f"{idx+1:2d}. {player_name:<25} | {total_points:4d} pts | {avg_per_gw:5.1f} avg | {gameweeks_played:2d} GWs"
                
                if logger:
                    logger.info(summary_line)
                else:
                    print(summary_line)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Plot cumulative points for top 10 prediction league players')
    parser.add_argument('--season', default='2025/2026', help='Season to analyze (default: 2025/2026)')
    parser.add_argument('--top-n', type=int, default=10, help='Number of top players to plot (default: 10)')
    parser.add_argument('--output-dir', help='Directory to save the plot')
    parser.add_argument('--no-display', action='store_true', help='Don\'t display the plot (save only)')
    
    return parser.parse_args()

def main():
    logger = setup_logging()
    args = parse_arguments()
    
    # Setup paths
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "database.db"
    
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return
    
    # Set default output directory
    if not args.output_dir:
        args.output_dir = project_root / "analysis_reports"
        args.output_dir.mkdir(exist_ok=True)
    
    logger.info(f"Analyzing top {args.top_n} prediction league players for season {args.season}...")
    
    # Get data
    pivot_df, top_players_df = get_top_players_cumulative_points(
        db_path, args.season, args.top_n, logger
    )
    
    if pivot_df is None or pivot_df.empty:
        logger.error(f"No data found for season {args.season}")
        return
    
    # Create and display plot
    if args.no_display:
        # Modify matplotlib to not display
        import matplotlib
        matplotlib.use('Agg')
        plt.ioff()
    
    fig = create_cumulative_points_plot(
        pivot_df, top_players_df, args.season, args.output_dir, logger
    )
    
    # Print summary
    print_summary_stats(top_players_df, pivot_df, logger)
    
    logger.info("Analysis completed successfully!")

if __name__ == "__main__":
    main()