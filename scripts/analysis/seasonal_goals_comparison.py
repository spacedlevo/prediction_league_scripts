#!/usr/bin/env python3
"""
Seasonal Goals Comparison Analysis

Compares goals scored across Premier League seasons up to the current date.
For each season, calculates total goals and average goals per game for matches
played on or before the equivalent date in the season.
"""

import logging
import sqlite3
import csv
from pathlib import Path
import argparse
from datetime import datetime
from typing import List, Dict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def season_sort_key(season: str) -> int:
    """
    Convert season string to sortable integer for chronological ordering.

    Seasons like '93/94' -> 1993, '00/01' -> 2000, '25/26' -> 2025
    Assumes seasons >= 93 are 1900s, seasons < 93 are 2000s
    """
    year_start = int(season.split('/')[0])

    # Convert 2-digit year to 4-digit year
    if year_start >= 93:
        return 1900 + year_start
    else:
        return 2000 + year_start


def get_seasonal_goals_data(cursor, target_date: datetime) -> List[Dict]:
    """
    Get goals data for all seasons up to the equivalent date.

    Args:
        cursor: Database cursor
        target_date: Date to compare against (e.g., today's date)

    Returns:
        List of dicts with season, matches, total_goals, avg_goals_per_game
    """
    # Extract month and day for comparison
    target_month = target_date.month
    target_day = target_date.day

    # Premier League seasons typically run from August to May
    # We need to compare dates properly within the season's year range
    query = """
    SELECT
        Season,
        COUNT(*) as matches,
        SUM(FTHG + FTAG) as total_goals
    FROM football_stats
    WHERE (
        -- For matches in Aug-Dec (start of season), use actual year
        (CAST(strftime('%m', Date) AS INTEGER) >= 8 AND
         CAST(strftime('%m', Date) AS INTEGER) <= 12 AND
         (CAST(strftime('%m', Date) AS INTEGER) < ? OR
          (CAST(strftime('%m', Date) AS INTEGER) = ? AND CAST(strftime('%d', Date) AS INTEGER) <= ?)))
        OR
        -- For matches in Jan-Jul (end of season), only include if target is in those months
        (CAST(strftime('%m', Date) AS INTEGER) >= 1 AND
         CAST(strftime('%m', Date) AS INTEGER) <= 7 AND
         ? <= 7 AND
         (CAST(strftime('%m', Date) AS INTEGER) < ? OR
          (CAST(strftime('%m', Date) AS INTEGER) = ? AND CAST(strftime('%d', Date) AS INTEGER) <= ?)))
    )
    GROUP BY Season
    ORDER BY Season
    """

    cursor.execute(query, (target_month, target_month, target_day, target_month, target_month, target_month, target_day))

    results = []
    for row in cursor.fetchall():
        season, matches, total_goals = row

        # Calculate average goals per game
        avg_goals = round(total_goals / matches, 2) if matches > 0 else 0.0

        results.append({
            'season': season,
            'matches': matches,
            'total_goals': total_goals,
            'avg_goals_per_game': avg_goals
        })

    # Sort chronologically by season (earliest to latest)
    results.sort(key=lambda x: season_sort_key(x['season']))

    return results


def generate_csv_report(data: List[Dict], output_dir: Path, target_date: datetime):
    """Generate CSV report with seasonal goals comparison"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"seasonal_goals_comparison_{timestamp}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['season', 'matches', 'total_goals', 'avg_goals_per_game'])
        writer.writeheader()
        writer.writerows(data)

    return filename


def generate_bar_chart(data: List[Dict], output_dir: Path, target_date: datetime):
    """Generate bar chart showing average goals per game by season"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f"seasonal_goals_chart_{timestamp}.png"

    # Extract data for plotting
    seasons = [row['season'] for row in data]
    avg_goals = [row['avg_goals_per_game'] for row in data]

    # Create figure with larger size for readability
    plt.figure(figsize=(16, 8))

    # Create bar chart
    bars = plt.bar(seasons, avg_goals, color='steelblue', edgecolor='navy', linewidth=0.5)

    # Highlight highest and lowest scoring seasons
    max_idx = avg_goals.index(max(avg_goals))
    min_idx = avg_goals.index(min(avg_goals))
    bars[max_idx].set_color('green')
    bars[min_idx].set_color('red')

    # Add overall average line
    overall_avg = sum(avg_goals) / len(avg_goals)
    plt.axhline(y=overall_avg, color='orange', linestyle='--', linewidth=2,
                label=f'Overall Average: {overall_avg:.2f}')

    # Customize chart
    plt.xlabel('Season', fontsize=12, fontweight='bold')
    plt.ylabel('Average Goals per Game', fontsize=12, fontweight='bold')
    plt.title(f'Premier League Goals per Game by Season (up to {target_date.strftime("%B %d")})',
              fontsize=14, fontweight='bold', pad=20)
    plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.yticks(fontsize=10)
    plt.grid(axis='y', alpha=0.3, linestyle='--')
    plt.legend(fontsize=10)

    # Add value labels on top of all bars
    for i, (season, value) in enumerate(zip(seasons, avg_goals)):
        plt.text(i, value + 0.05, f'{value:.2f}',
                ha='center', va='bottom', fontsize=7, fontweight='bold')

    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

    return filename


def print_summary_table(data: List[Dict], target_date: datetime, logger):
    """Print formatted summary table to console"""
    logger.info(f"\n{'='*70}")
    logger.info(f"SEASONAL GOALS COMPARISON - UP TO {target_date.strftime('%B %d')}")
    logger.info(f"{'='*70}")
    logger.info(f"{'Season':<10} {'Matches':<10} {'Total Goals':<15} {'Avg Goals/Game':<15}")
    logger.info(f"{'-'*70}")

    for row in data:
        logger.info(
            f"{row['season']:<10} {row['matches']:<10} {row['total_goals']:<15} {row['avg_goals_per_game']:<15.2f}"
        )

    logger.info(f"{'='*70}")

    # Summary statistics
    if data:
        total_matches = sum(row['matches'] for row in data)
        total_goals = sum(row['total_goals'] for row in data)
        overall_avg = total_goals / total_matches if total_matches > 0 else 0

        logger.info(f"\nSUMMARY:")
        logger.info(f"  Total Seasons Analyzed: {len(data)}")
        logger.info(f"  Total Matches: {total_matches}")
        logger.info(f"  Total Goals: {total_goals}")
        logger.info(f"  Overall Average: {overall_avg:.2f} goals per game")

        # Find highest and lowest scoring seasons
        highest = max(data, key=lambda x: x['avg_goals_per_game'])
        lowest = min(data, key=lambda x: x['avg_goals_per_game'])

        logger.info(f"\n  Highest Scoring Season (up to this date): {highest['season']} ({highest['avg_goals_per_game']:.2f} goals/game)")
        logger.info(f"  Lowest Scoring Season (up to this date): {lowest['season']} ({lowest['avg_goals_per_game']:.2f} goals/game)")


def main(target_date: datetime, logger):
    """Main execution function"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "seasonal_goals"

    logger.info("Starting seasonal goals comparison analysis...")
    logger.info(f"Database: {db_path}")
    logger.info(f"Target date: {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%B %d')})")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get seasonal goals data
        logger.info("Fetching seasonal goals data...")
        data = get_seasonal_goals_data(cursor, target_date)

        if not data:
            logger.warning("No data found in football_stats table")
            return

        logger.info(f"Found data for {len(data)} seasons")

        # Print summary table
        print_summary_table(data, target_date, logger)

        # Generate CSV report
        csv_file = generate_csv_report(data, output_dir, target_date)
        logger.info(f"\nCSV report saved to: {csv_file}")

        # Generate bar chart
        chart_file = generate_bar_chart(data, output_dir, target_date)
        logger.info(f"Bar chart saved to: {chart_file}")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        conn.close()

    logger.info("\nAnalysis completed successfully")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Compare goals scored across Premier League seasons up to the current date'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Target date for comparison (YYYY-MM-DD). Defaults to today.'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()

    # Use provided date or default to today
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD format.")
            exit(1)
    else:
        target_date = datetime.now()

    main(target_date, logger)
