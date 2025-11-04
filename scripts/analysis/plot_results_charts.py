#!/usr/bin/env python3
"""
Create stacked column charts for:
1. Football stats FTR (Full Time Result) by season
2. Player predictions for current season (2025/2026)
"""

import sqlite3
import matplotlib.pyplot as plt
import numpy as np
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
    players = []
    data = defaultdict(lambda: {'HW': 0, 'D': 0, 'AW': 0})

    for player, result, count in cursor.fetchall():
        if player not in players:
            players.append(player)
        data[player][result] = count

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

def main():
    """Main execution"""
    print("Creating stacked column charts...")
    print("=" * 60)

    # Connect to database
    conn = setup_database_connection()

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
