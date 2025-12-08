#!/usr/bin/env python3
"""
Create stacked column charts for:
1. Football stats FTR (Full Time Result) by season
2. Player predictions for current season (2025/2026)
3. Player predictions by gameweek for a specific season (with --player and --season arguments)
4. All player predictions for a specific gameweek (with --gameweek and --season arguments)
"""

import sqlite3
import matplotlib.pyplot as plt
import numpy as np
import argparse
from pathlib import Path
from collections import defaultdict

def setup_database_connection():
    """Setup database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)

def get_ftr_by_season(conn):
    """Get FTR counts by season from football_stats table"""
    cursor = conn.cursor()
    cursor.execute('''
    SELECT
        Season,
        FTR,
        COUNT(*) as count
    FROM football_stats
    WHERE FTR IS NOT NULL
    GROUP BY Season, FTR
    ORDER BY Season, FTR
    ''')

    # Organize data for stacked chart
    # Map football_stats values (H, D, A) to standard format (HW, D, AW)
    ftr_mapping = {'H': 'HW', 'D': 'D', 'A': 'AW'}
    seasons = []
    data = defaultdict(lambda: {'HW': 0, 'D': 0, 'AW': 0})

    for season, ftr, count in cursor.fetchall():
        if season not in seasons:
            seasons.append(season)
        # Map H->HW, A->AW, D stays D
        mapped_ftr = ftr_mapping.get(ftr, ftr)
        data[season][mapped_ftr] = count

    # Sort seasons chronologically (93/94 to 25/26)
    def season_sort_key(season):
        """Convert season string to sortable year value"""
        first_year = int(season.split('/')[0])
        # Assume years 93-99 are 1900s, 00-99 could be 2000s
        # For proper sorting: 93-99 -> 1993-1999, 00-26 -> 2000-2026
        if first_year >= 93:
            return 1900 + first_year
        else:
            return 2000 + first_year

    seasons.sort(key=season_sort_key)

    return seasons, data

def get_predictions_by_player(conn):
    """Get prediction counts by player for current season"""
    cursor = conn.cursor()
    cursor.execute('''
    SELECT
        p.player_name,
        pr.predicted_result,
        COUNT(*) as count
    FROM predictions pr
    JOIN players p ON pr.player_id = p.player_id
    JOIN fixtures f ON pr.fixture_id = f.fixture_id
    WHERE f.season = '2025/2026'
    AND pr.predicted_result IS NOT NULL
    GROUP BY p.player_name, pr.predicted_result
    ORDER BY p.player_name, pr.predicted_result
    ''')

    # Organize data for stacked chart
    # Map both old format (H, D, A) and new format (HW, D, AW) to standard format
    result_mapping = {'H': 'HW', 'HW': 'HW', 'D': 'D', 'A': 'AW', 'AW': 'AW'}
    players = []
    data = defaultdict(lambda: {'HW': 0, 'D': 0, 'AW': 0})

    for player, result, count in cursor.fetchall():
        if player not in players:
            players.append(player)
        # Map old and new format to standard format
        mapped_result = result_mapping.get(result, result)
        data[player][mapped_result] += count

    return players, data

def create_ftr_season_chart(seasons, data):
    """Create stacked column chart for FTR by season (percentage-based)"""
    # Prepare data arrays and calculate percentages
    hw_percentages = []
    d_percentages = []
    aw_percentages = []

    for season in seasons:
        total = data[season]['HW'] + data[season]['D'] + data[season]['AW']
        hw_percentages.append((data[season]['HW'] / total) * 100 if total > 0 else 0)
        d_percentages.append((data[season]['D'] / total) * 100 if total > 0 else 0)
        aw_percentages.append((data[season]['AW'] / total) * 100 if total > 0 else 0)

    # Create figure
    fig, ax = plt.subplots(figsize=(20, 8))

    # Create stacked bar chart
    x = np.arange(len(seasons))
    width = 0.8

    p1 = ax.bar(x, hw_percentages, width, label='Home Win (HW)', color='#2E7D32')
    p2 = ax.bar(x, d_percentages, width, bottom=hw_percentages, label='Draw (D)', color='#FFA726')
    p3 = ax.bar(x, aw_percentages, width, bottom=np.array(hw_percentages) + np.array(d_percentages),
                label='Away Win (AW)', color='#1976D2')

    # Customize chart
    ax.set_xlabel('Season', fontsize=12, fontweight='bold')
    ax.set_ylabel('Percentage (%)', fontsize=12, fontweight='bold')
    ax.set_title('Full Time Results by Season - Percentage Distribution', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(seasons, rotation=45, ha='right')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    # Save figure
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "result_distribution"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ftr_by_season.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved chart: {output_path}")

    return output_path

def create_player_predictions_chart(players, data):
    """Create stacked column chart for player predictions (percentage-based)"""
    # Prepare data arrays and calculate percentages
    hw_percentages = []
    d_percentages = []
    aw_percentages = []

    for player in players:
        total = data[player]['HW'] + data[player]['D'] + data[player]['AW']
        hw_percentages.append((data[player]['HW'] / total) * 100 if total > 0 else 0)
        d_percentages.append((data[player]['D'] / total) * 100 if total > 0 else 0)
        aw_percentages.append((data[player]['AW'] / total) * 100 if total > 0 else 0)

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    # Create stacked bar chart
    x = np.arange(len(players))
    width = 0.8

    p1 = ax.bar(x, hw_percentages, width, label='Home Win (HW)', color='#2E7D32')
    p2 = ax.bar(x, d_percentages, width, bottom=hw_percentages, label='Draw (D)', color='#FFA726')
    p3 = ax.bar(x, aw_percentages, width, bottom=np.array(hw_percentages) + np.array(d_percentages),
                label='Away Win (AW)', color='#1976D2')

    # Customize chart
    ax.set_xlabel('Player', fontsize=12, fontweight='bold')
    ax.set_ylabel('Percentage (%)', fontsize=12, fontweight='bold')
    ax.set_title('Player Predictions by Result Type - Percentage Distribution (Season 2025/2026)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(players, rotation=45, ha='right')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    # Save figure
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "result_distribution"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "player_predictions_2025_2026.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved chart: {output_path}")

    return output_path

def get_player_predictions_by_gameweek(conn, player_name, season):
    """Get prediction counts by gameweek for a specific player and season"""
    cursor = conn.cursor()

    # First verify player exists
    cursor.execute('SELECT player_id, player_name FROM players WHERE LOWER(player_name) = LOWER(?)', (player_name,))
    player_result = cursor.fetchone()

    if not player_result:
        return None, None, None

    player_id, actual_player_name = player_result

    cursor.execute('''
    SELECT
        f.gameweek,
        pr.predicted_result,
        COUNT(*) as count
    FROM predictions pr
    JOIN players p ON pr.player_id = p.player_id
    JOIN fixtures f ON pr.fixture_id = f.fixture_id
    WHERE p.player_id = ?
    AND f.season = ?
    AND pr.predicted_result IS NOT NULL
    GROUP BY f.gameweek, pr.predicted_result
    ORDER BY f.gameweek, pr.predicted_result
    ''', (player_id, season))

    # Organize data for stacked chart
    # Map both old format (H, D, A) and new format (HW, D, AW) to standard format
    result_mapping = {'H': 'HW', 'HW': 'HW', 'D': 'D', 'A': 'AW', 'AW': 'AW'}
    gameweeks = []
    data = defaultdict(lambda: {'HW': 0, 'D': 0, 'AW': 0})

    for gameweek, result, count in cursor.fetchall():
        if gameweek not in gameweeks:
            gameweeks.append(gameweek)
        # Map old and new format to standard format
        mapped_result = result_mapping.get(result, result)
        data[gameweek][mapped_result] += count

    # Sort gameweeks numerically
    gameweeks.sort()

    return gameweeks, data, actual_player_name

def create_player_gameweek_chart(gameweeks, data, player_name, season):
    """Create stacked column chart for player predictions by gameweek (percentage-based)"""
    # Prepare data arrays and calculate percentages
    hw_percentages = []
    d_percentages = []
    aw_percentages = []

    for gameweek in gameweeks:
        total = data[gameweek]['HW'] + data[gameweek]['D'] + data[gameweek]['AW']
        hw_percentages.append((data[gameweek]['HW'] / total) * 100 if total > 0 else 0)
        d_percentages.append((data[gameweek]['D'] / total) * 100 if total > 0 else 0)
        aw_percentages.append((data[gameweek]['AW'] / total) * 100 if total > 0 else 0)

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    # Create stacked bar chart
    x = np.arange(len(gameweeks))
    width = 0.8

    p1 = ax.bar(x, hw_percentages, width, label='Home Win (HW)', color='#2E7D32')
    p2 = ax.bar(x, d_percentages, width, bottom=hw_percentages, label='Draw (D)', color='#FFA726')
    p3 = ax.bar(x, aw_percentages, width, bottom=np.array(hw_percentages) + np.array(d_percentages),
                label='Away Win (AW)', color='#1976D2')

    # Customize chart
    ax.set_xlabel('Gameweek', fontsize=12, fontweight='bold')
    ax.set_ylabel('Percentage (%)', fontsize=12, fontweight='bold')
    ax.set_title(f'{player_name} - Prediction Distribution by Gameweek ({season})', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'GW{gw}' for gw in gameweeks], rotation=45, ha='right')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    # Save figure
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "result_distribution"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create safe filename from player name
    safe_player_name = player_name.lower().replace(' ', '_')
    safe_season = season.replace('/', '_')
    output_path = output_dir / f"{safe_player_name}_gameweek_{safe_season}.png"

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved chart: {output_path}")

    return output_path

def get_all_players_for_gameweek(conn, gameweek, season):
    """Get prediction counts for all players for a specific gameweek"""
    cursor = conn.cursor()
    cursor.execute('''
    SELECT
        p.player_name,
        pr.predicted_result,
        COUNT(*) as count
    FROM predictions pr
    JOIN players p ON pr.player_id = p.player_id
    JOIN fixtures f ON pr.fixture_id = f.fixture_id
    WHERE f.gameweek = ?
    AND f.season = ?
    AND pr.predicted_result IS NOT NULL
    GROUP BY p.player_name, pr.predicted_result
    ORDER BY p.player_name, pr.predicted_result
    ''', (gameweek, season))

    # Organize data for stacked chart
    # Map both old format (H, D, A) and new format (HW, D, AW) to standard format
    result_mapping = {'H': 'HW', 'HW': 'HW', 'D': 'D', 'A': 'AW', 'AW': 'AW'}
    players = []
    data = defaultdict(lambda: {'HW': 0, 'D': 0, 'AW': 0})

    for player, result, count in cursor.fetchall():
        if player not in players:
            players.append(player)
        # Map old and new format to standard format
        mapped_result = result_mapping.get(result, result)
        data[player][mapped_result] += count

    return players, data

def create_gameweek_all_players_chart(players, data, gameweek, season):
    """Create stacked column chart for all players' predictions for a specific gameweek (percentage-based)"""
    # Prepare data arrays and calculate percentages
    hw_percentages = []
    d_percentages = []
    aw_percentages = []

    for player in players:
        total = data[player]['HW'] + data[player]['D'] + data[player]['AW']
        hw_percentages.append((data[player]['HW'] / total) * 100 if total > 0 else 0)
        d_percentages.append((data[player]['D'] / total) * 100 if total > 0 else 0)
        aw_percentages.append((data[player]['AW'] / total) * 100 if total > 0 else 0)

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    # Create stacked bar chart
    x = np.arange(len(players))
    width = 0.8

    p1 = ax.bar(x, hw_percentages, width, label='Home Win (HW)', color='#2E7D32')
    p2 = ax.bar(x, d_percentages, width, bottom=hw_percentages, label='Draw (D)', color='#FFA726')
    p3 = ax.bar(x, aw_percentages, width, bottom=np.array(hw_percentages) + np.array(d_percentages),
                label='Away Win (AW)', color='#1976D2')

    # Customize chart
    ax.set_xlabel('Player', fontsize=12, fontweight='bold')
    ax.set_ylabel('Percentage (%)', fontsize=12, fontweight='bold')
    ax.set_title(f'Player Predictions by Result Type - Gameweek {gameweek} ({season})', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(players, rotation=45, ha='right')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    # Save figure
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "result_distribution"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_season = season.replace('/', '_')
    output_path = output_dir / f"gameweek_{gameweek}_{safe_season}.png"

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved chart: {output_path}")

    return output_path

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Create stacked column charts for result distribution analysis'
    )
    parser.add_argument('--player', type=str,
                       help='Player name for gameweek analysis (e.g., "Tom Levin")')
    parser.add_argument('--gameweek', type=int,
                       help='Gameweek number to show all players\' predictions (e.g., 15)')
    parser.add_argument('--season', type=str,
                       help='Season for analysis (e.g., "2025/2026")')
    return parser.parse_args()

def main():
    """Main execution"""
    args = parse_arguments()

    # Connect to database
    conn = setup_database_connection()

    # Check if gameweek chart for all players requested
    if args.gameweek and args.season:
        print(f"Creating gameweek distribution chart for all players (GW{args.gameweek}, {args.season})...")
        print("=" * 60)

        players, gw_data = get_all_players_for_gameweek(conn, args.gameweek, args.season)

        if not players:
            print(f"\nError: No predictions found for gameweek {args.gameweek} in season {args.season}")
            conn.close()
            return

        print(f"\nFound predictions from {len(players)} players for gameweek {args.gameweek}")

        # Create chart
        print("\nCreating gameweek distribution chart...")
        gw_chart = create_gameweek_all_players_chart(players, gw_data, args.gameweek, args.season)

        conn.close()

        print("\n" + "=" * 60)
        print("Chart created successfully!")
        print(f"\nChart: {gw_chart}")

    # Check if player-specific gameweek chart requested
    elif args.player and args.season:
        print(f"Creating gameweek distribution chart for {args.player} ({args.season})...")
        print("=" * 60)

        gameweeks, gw_data, actual_player_name = get_player_predictions_by_gameweek(
            conn, args.player, args.season
        )

        if gameweeks is None:
            print(f"\nError: Player '{args.player}' not found in database")
            conn.close()
            return

        if not gameweeks:
            print(f"\nError: No predictions found for {actual_player_name} in season {args.season}")
            conn.close()
            return

        print(f"\nFound {len(gameweeks)} gameweeks with predictions for {actual_player_name}")
        print(f"Gameweeks: {min(gameweeks)} to {max(gameweeks)}")

        # Create chart
        print("\nCreating gameweek distribution chart...")
        gw_chart = create_player_gameweek_chart(gameweeks, gw_data, actual_player_name, args.season)

        conn.close()

        print("\n" + "=" * 60)
        print("Chart created successfully!")
        print(f"\nChart: {gw_chart}")

    elif args.player and not args.season:
        print("Error: --season must be provided with --player")
        conn.close()
        return

    elif args.gameweek and not args.season:
        print("Error: --season must be provided with --gameweek")
        conn.close()
        return

    elif args.season and not (args.player or args.gameweek):
        print("Error: --season must be used with either --player or --gameweek")
        conn.close()
        return

    else:
        # Default behavior: create all standard charts
        print("Creating stacked column charts...")
        print("=" * 60)

        # Get data
        print("\n1. Fetching FTR data by season...")
        seasons, ftr_data = get_ftr_by_season(conn)
        print(f"   Found {len(seasons)} seasons")

        print("\n2. Fetching player predictions for 2025/2026...")
        players, pred_data = get_predictions_by_player(conn)
        print(f"   Found {len(players)} players")

        # Close database
        conn.close()

        # Create charts
        print("\n3. Creating FTR by season chart...")
        ftr_chart = create_ftr_season_chart(seasons, ftr_data)

        print("\n4. Creating player predictions chart...")
        pred_chart = create_player_predictions_chart(players, pred_data)

        print("\n" + "=" * 60)
        print("Charts created successfully!")
        print(f"\nChart 1: {ftr_chart}")
        print(f"Chart 2: {pred_chart}")

if __name__ == "__main__":
    main()
