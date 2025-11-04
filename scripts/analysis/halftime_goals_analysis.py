#!/usr/bin/env python3
"""
Analyze goals scored in 1st half vs 2nd half by season.

This script analyzes the football_stats table to compare goals scored in
the first half versus the second half for each Premier League season.
"""

import sqlite3
import argparse
from pathlib import Path
from typing import List, Tuple
import matplotlib.pyplot as plt
import numpy as np


def setup_database_connection():
    """Setup database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)


def get_seasonal_goal_analysis(cursor) -> List[Tuple]:
    """
    Get goal statistics by season.

    Returns list of tuples: (season, matches, 1st_half_goals, 2nd_half_goals, total_goals)
    """
    query = """
        SELECT
            Season,
            COUNT(*) as matches,
            SUM(HTHG + HTAG) as first_half_goals,
            SUM((FTHG - HTHG) + (FTAG - HTAG)) as second_half_goals,
            SUM(FTHG + FTAG) as total_goals
        FROM football_stats
        WHERE HTHG IS NOT NULL
        AND HTAG IS NOT NULL
        AND FTHG IS NOT NULL
        AND FTAG IS NOT NULL
        GROUP BY Season
        ORDER BY Season
    """

    cursor.execute(query)
    return cursor.fetchall()


def print_seasonal_analysis(data: List[Tuple], detailed: bool = False):
    """Print seasonal goal analysis"""
    print("\n" + "=" * 100)
    print("PREMIER LEAGUE SEASONAL GOALS ANALYSIS: 1ST HALF vs 2ND HALF")
    print("=" * 100)

    if detailed:
        print(f"\n{'Season':<10} {'Matches':<8} {'1st Half':<10} {'2nd Half':<10} {'Total':<8} "
              f"{'1H %':<7} {'2H %':<7} {'1H/Game':<9} {'2H/Game':<9}")
        print("-" * 100)
    else:
        print(f"\n{'Season':<10} {'Matches':<8} {'1st Half':<10} {'2nd Half':<10} "
              f"{'Difference':<12} {'2nd Half %':<12}")
        print("-" * 100)

    total_matches = 0
    total_first_half = 0
    total_second_half = 0

    for season, matches, first_half, second_half, total_goals in data:
        total_matches += matches
        total_first_half += first_half
        total_second_half += second_half

        first_half_pct = (first_half / total_goals * 100) if total_goals > 0 else 0
        second_half_pct = (second_half / total_goals * 100) if total_goals > 0 else 0
        difference = second_half - first_half
        difference_str = f"+{difference}" if difference >= 0 else str(difference)

        if detailed:
            first_half_per_game = first_half / matches if matches > 0 else 0
            second_half_per_game = second_half / matches if matches > 0 else 0
            print(f"{season:<10} {matches:<8} {first_half:<10} {second_half:<10} {total_goals:<8} "
                  f"{first_half_pct:>6.1f}% {second_half_pct:>6.1f}% {first_half_per_game:>8.2f} {second_half_per_game:>8.2f}")
        else:
            print(f"{season:<10} {matches:<8} {first_half:<10} {second_half:<10} "
                  f"{difference_str:<12} {second_half_pct:>11.1f}%")

    print("-" * 100)

    # Overall statistics
    total_goals = total_first_half + total_second_half
    overall_first_pct = (total_first_half / total_goals * 100) if total_goals > 0 else 0
    overall_second_pct = (total_second_half / total_goals * 100) if total_goals > 0 else 0
    overall_difference = total_second_half - total_first_half

    print(f"\n{'OVERALL':<10} {total_matches:<8} {total_first_half:<10} {total_second_half:<10} ", end="")

    if detailed:
        first_avg = total_first_half / total_matches if total_matches > 0 else 0
        second_avg = total_second_half / total_matches if total_matches > 0 else 0
        print(f"{total_goals:<8} {overall_first_pct:>6.1f}% {overall_second_pct:>6.1f}% "
              f"{first_avg:>8.2f} {second_avg:>8.2f}")
    else:
        print(f"+{overall_difference:<11} {overall_second_pct:>11.1f}%")

    print("\n" + "=" * 100)

    # Summary insights
    print("\nKEY INSIGHTS:")
    print("-" * 100)
    print(f"• Total matches analyzed: {total_matches:,}")
    print(f"• Total goals scored: {total_goals:,}")
    print(f"• 1st half goals: {total_first_half:,} ({overall_first_pct:.1f}%)")
    print(f"• 2nd half goals: {total_second_half:,} ({overall_second_pct:.1f}%)")
    print(f"• More goals in 2nd half: +{overall_difference:,} goals ({overall_second_pct - overall_first_pct:.1f}% more)")
    print(f"• Average goals per game: {total_goals/total_matches:.2f}")
    print(f"  - 1st half: {total_first_half/total_matches:.2f} per game")
    print(f"  - 2nd half: {total_second_half/total_matches:.2f} per game")

    # Find extremes
    max_second_half_pct = max(data, key=lambda x: (x[3] / (x[2] + x[3]) * 100) if (x[2] + x[3]) > 0 else 0)
    min_second_half_pct = min(data, key=lambda x: (x[3] / (x[2] + x[3]) * 100) if (x[2] + x[3]) > 0 else 0)

    max_second_pct_value = (max_second_half_pct[3] / (max_second_half_pct[2] + max_second_half_pct[3]) * 100)
    min_second_pct_value = (min_second_half_pct[3] / (min_second_half_pct[2] + min_second_half_pct[3]) * 100)

    print(f"\n• Highest 2nd half %: {max_second_half_pct[0]} ({max_second_pct_value:.1f}%)")
    print(f"• Lowest 2nd half %: {min_second_half_pct[0]} ({min_second_pct_value:.1f}%)")

    print("=" * 100)


def print_trend_analysis(data: List[Tuple]):
    """Print trend analysis comparing different eras"""
    print("\n" + "=" * 100)
    print("TREND ANALYSIS BY ERA")
    print("=" * 100)

    # Define eras
    eras = [
        ("1990s (93/94-99/00)", lambda s: s.startswith('9')),
        ("2000s (00/01-09/10)", lambda s: s.startswith('0')),
        ("2010s (10/11-19/20)", lambda s: s.startswith('1')),
        ("2020s (20/21-25/26)", lambda s: s.startswith('2')),
    ]

    print(f"\n{'Era':<25} {'Matches':<10} {'1st Half':<12} {'2nd Half':<12} "
          f"{'1H %':<8} {'2H %':<8} {'Diff':<10}")
    print("-" * 100)

    for era_name, era_filter in eras:
        era_data = [row for row in data if era_filter(row[0])]

        if not era_data:
            continue

        era_matches = sum(row[1] for row in era_data)
        era_first_half = sum(row[2] for row in era_data)
        era_second_half = sum(row[3] for row in era_data)
        era_total = era_first_half + era_second_half

        first_pct = (era_first_half / era_total * 100) if era_total > 0 else 0
        second_pct = (era_second_half / era_total * 100) if era_total > 0 else 0
        difference = era_second_half - era_first_half

        print(f"{era_name:<25} {era_matches:<10} {era_first_half:<12} {era_second_half:<12} "
              f"{first_pct:>7.1f}% {second_pct:>7.1f}% +{difference:<9}")

    print("=" * 100)


def season_to_year(season: str) -> int:
    """Convert season string to starting year for sorting"""
    year_start = int(season.split('/')[0])
    # Assume seasons >= 93 are 1900s, seasons < 93 are 2000s
    if year_start >= 93:
        return 1900 + year_start
    else:
        return 2000 + year_start


def plot_halftime_goals(data: List[Tuple], output_path: Path = None):
    """Create column graph comparing 1st half vs 2nd half goals by season"""
    # Filter out 93/94 and 94/95 due to data quality issues, keep 95/96 onwards
    filtered_data = [row for row in data if season_to_year(row[0]) >= 1995]

    # Sort chronologically by season
    filtered_data.sort(key=lambda x: season_to_year(x[0]))

    seasons = [row[0] for row in filtered_data]
    first_half_goals = [row[2] for row in filtered_data]
    second_half_goals = [row[3] for row in filtered_data]

    # Set up the bar positions
    x = np.arange(len(seasons))
    width = 0.35

    # Create figure with good size
    fig, ax = plt.subplots(figsize=(20, 8))

    # Create bars
    bars1 = ax.bar(x - width/2, first_half_goals, width, label='1st Half',
                   color='steelblue', edgecolor='navy', linewidth=0.5)
    bars2 = ax.bar(x + width/2, second_half_goals, width, label='2nd Half',
                   color='coral', edgecolor='darkred', linewidth=0.5)

    # Customize the plot
    ax.set_xlabel('Season', fontsize=12, fontweight='bold')
    ax.set_ylabel('Goals', fontsize=12, fontweight='bold')
    ax.set_title('Premier League Goals: 1st Half vs 2nd Half by Season',
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(seasons, rotation=45, ha='right', fontsize=9)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Add value labels on bars (only show every 3rd season to avoid clutter)
    for i, (s, fh, sh) in enumerate(zip(seasons, first_half_goals, second_half_goals)):
        if i % 3 == 0:  # Show every 3rd label
            ax.text(i - width/2, fh + 10, str(fh), ha='center', va='bottom',
                   fontsize=7, fontweight='bold')
            ax.text(i + width/2, sh + 10, str(sh), ha='center', va='bottom',
                   fontsize=7, fontweight='bold')

    plt.tight_layout()

    # Save or show
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nChart saved to: {output_path}")
    else:
        plt.show()

    plt.close()


def plot_goals_per_game(data: List[Tuple], output_path: Path = None):
    """Create column graph showing goals per game for 1st half vs 2nd half by season"""
    # Filter out 93/94 and 94/95 due to data quality issues, keep 95/96 onwards
    filtered_data = [row for row in data if season_to_year(row[0]) >= 1995]

    # Sort chronologically by season
    filtered_data.sort(key=lambda x: season_to_year(x[0]))

    seasons = [row[0] for row in filtered_data]
    matches = [row[1] for row in filtered_data]
    first_half_goals = [row[2] for row in filtered_data]
    second_half_goals = [row[3] for row in filtered_data]

    # Calculate goals per game
    first_half_per_game = [fh / m if m > 0 else 0 for fh, m in zip(first_half_goals, matches)]
    second_half_per_game = [sh / m if m > 0 else 0 for sh, m in zip(second_half_goals, matches)]

    # Set up the bar positions
    x = np.arange(len(seasons))
    width = 0.35

    # Create figure with good size
    fig, ax = plt.subplots(figsize=(20, 8))

    # Create bars
    bars1 = ax.bar(x - width/2, first_half_per_game, width, label='1st Half',
                   color='steelblue', edgecolor='navy', linewidth=0.5)
    bars2 = ax.bar(x + width/2, second_half_per_game, width, label='2nd Half',
                   color='coral', edgecolor='darkred', linewidth=0.5)

    # Customize the plot
    ax.set_xlabel('Season', fontsize=12, fontweight='bold')
    ax.set_ylabel('Goals per Game', fontsize=12, fontweight='bold')
    ax.set_title('Premier League Goals per Game: 1st Half vs 2nd Half by Season',
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(seasons, rotation=45, ha='right', fontsize=9)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Add average lines
    overall_first_avg = sum(first_half_per_game) / len(first_half_per_game) if first_half_per_game else 0
    overall_second_avg = sum(second_half_per_game) / len(second_half_per_game) if second_half_per_game else 0
    ax.axhline(y=overall_first_avg, color='steelblue', linestyle='--', linewidth=1.5, alpha=0.7,
               label=f'1st Half Avg: {overall_first_avg:.2f}')
    ax.axhline(y=overall_second_avg, color='coral', linestyle='--', linewidth=1.5, alpha=0.7,
               label=f'2nd Half Avg: {overall_second_avg:.2f}')

    # Update legend to include average lines
    ax.legend(fontsize=11, loc='upper left')

    # Add value labels on bars (only show every 5th season to avoid clutter)
    for i, (s, fh, sh) in enumerate(zip(seasons, first_half_per_game, second_half_per_game)):
        if i % 5 == 0:  # Show every 5th label
            ax.text(i - width/2, fh + 0.02, f'{fh:.2f}', ha='center', va='bottom',
                   fontsize=7, fontweight='bold')
            ax.text(i + width/2, sh + 0.02, f'{sh:.2f}', ha='center', va='bottom',
                   fontsize=7, fontweight='bold')

    plt.tight_layout()

    # Save or show
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nGoals per game chart saved to: {output_path}")
    else:
        plt.show()

    plt.close()


def save_to_report(data: List[Tuple], output_path: Path):
    """Save analysis to markdown file"""
    with open(output_path, 'w') as f:
        f.write("# Premier League Seasonal Goals Analysis: 1st Half vs 2nd Half\n\n")
        f.write(f"Generated from football_stats table data\n\n")

        f.write("## Season by Season Comparison\n\n")
        f.write("| Season | Matches | 1st Half Goals | 2nd Half Goals | Total | 1H % | 2H % | Difference |\n")
        f.write("|--------|---------|----------------|----------------|-------|------|------|------------|\n")

        total_matches = 0
        total_first_half = 0
        total_second_half = 0

        for season, matches, first_half, second_half, total_goals in data:
            total_matches += matches
            total_first_half += first_half
            total_second_half += second_half

            first_half_pct = (first_half / total_goals * 100) if total_goals > 0 else 0
            second_half_pct = (second_half / total_goals * 100) if total_goals > 0 else 0
            difference = second_half - first_half
            difference_str = f"+{difference}" if difference >= 0 else str(difference)

            f.write(f"| {season} | {matches} | {first_half} | {second_half} | {total_goals} | "
                   f"{first_half_pct:.1f}% | {second_half_pct:.1f}% | {difference_str} |\n")

        # Overall row
        total_goals = total_first_half + total_second_half
        overall_first_pct = (total_first_half / total_goals * 100) if total_goals > 0 else 0
        overall_second_pct = (total_second_half / total_goals * 100) if total_goals > 0 else 0
        overall_difference = total_second_half - total_first_half

        f.write(f"| **OVERALL** | **{total_matches}** | **{total_first_half}** | **{total_second_half}** | "
               f"**{total_goals}** | **{overall_first_pct:.1f}%** | **{overall_second_pct:.1f}%** | "
               f"**+{overall_difference}** |\n")

        f.write("\n## Key Findings\n\n")
        f.write(f"- **Total matches analyzed**: {total_matches:,}\n")
        f.write(f"- **Total goals**: {total_goals:,}\n")
        f.write(f"- **1st half goals**: {total_first_half:,} ({overall_first_pct:.1f}%)\n")
        f.write(f"- **2nd half goals**: {total_second_half:,} ({overall_second_pct:.1f}%)\n")
        f.write(f"- **Difference**: {overall_difference:,} more goals in 2nd half\n")
        f.write(f"- **Average per game**: {total_goals/total_matches:.2f} goals\n")
        f.write(f"  - 1st half: {total_first_half/total_matches:.2f} per game\n")
        f.write(f"  - 2nd half: {total_second_half/total_matches:.2f} per game\n")

    print(f"\nReport saved to: {output_path}")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze goals scored in 1st half vs 2nd half by season'
    )
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed statistics including per-game averages')
    parser.add_argument('--trends', action='store_true',
                       help='Show trend analysis by era')
    parser.add_argument('--save', action='store_true',
                       help='Save analysis to markdown report')
    parser.add_argument('--plot', action='store_true',
                       help='Generate column graph comparing 1st half vs 2nd half goals')
    parser.add_argument('--plot-per-game', action='store_true',
                       help='Generate column graph showing goals per game for 1st and 2nd half')
    parser.add_argument('--output', type=str,
                       default='analysis_reports/halftime_goals/halftime_goals_analysis.md',
                       help='Output file path for report')
    parser.add_argument('--chart-output', type=str,
                       default='analysis_reports/halftime_goals/halftime_goals_chart.png',
                       help='Output file path for total goals chart')
    parser.add_argument('--per-game-output', type=str,
                       default='analysis_reports/halftime_goals/halftime_goals_per_game_chart.png',
                       help='Output file path for per-game chart')
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_arguments()

    conn = setup_database_connection()
    cursor = conn.cursor()

    try:
        data = get_seasonal_goal_analysis(cursor)

        if not data:
            print("No data found in football_stats table")
            return

        print_seasonal_analysis(data, detailed=args.detailed)

        if args.trends:
            print_trend_analysis(data)

        if args.save:
            output_path = Path(__file__).parent.parent.parent / args.output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_to_report(data, output_path)

        if args.plot:
            chart_path = Path(__file__).parent.parent.parent / args.chart_output
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            plot_halftime_goals(data, chart_path)

        if args.plot_per_game:
            per_game_path = Path(__file__).parent.parent.parent / args.per_game_output
            per_game_path.parent.mkdir(parents=True, exist_ok=True)
            plot_goals_per_game(data, per_game_path)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
