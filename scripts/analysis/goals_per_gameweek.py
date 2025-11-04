#!/usr/bin/env python3
"""
Analyze goals per gameweek for the current season and create visualization.
"""

import sqlite3 as sql
import logging
from pathlib import Path
import matplotlib.pyplot as plt
import argparse
from datetime import datetime


def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def get_goals_per_gameweek(cursor, season='2025/2026'):
    """Get goals scored per gameweek for specified season"""
    query = """
        SELECT
            f.gameweek,
            COUNT(*) as matches_played,
            SUM(r.home_goals + r.away_goals) as total_goals,
            ROUND(AVG(r.home_goals + r.away_goals), 2) as avg_goals_per_match
        FROM fixtures f
        JOIN results r ON f.fixture_id = r.fixture_id
        WHERE f.season = ?
            AND r.home_goals IS NOT NULL
            AND r.away_goals IS NOT NULL
        GROUP BY f.gameweek
        ORDER BY f.gameweek
    """

    cursor.execute(query, (season,))
    return cursor.fetchall()


def create_visualization(data, season, output_dir):
    """Create bar chart visualization of goals per gameweek"""
    gameweeks = [row[0] for row in data]
    total_goals = [row[2] for row in data]
    avg_goals = [row[3] for row in data]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # Total goals bar chart
    bars1 = ax1.bar(gameweeks, total_goals, color='steelblue', alpha=0.8)
    ax1.set_xlabel('Gameweek', fontsize=12)
    ax1.set_ylabel('Total Goals', fontsize=12)
    ax1.set_title(f'Total Goals per Gameweek - {season}', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_xticks(gameweeks)

    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom', fontsize=9)

    # Average goals per match
    bars2 = ax2.bar(gameweeks, avg_goals, color='coral', alpha=0.8)
    ax2.set_xlabel('Gameweek', fontsize=12)
    ax2.set_ylabel('Average Goals per Match', fontsize=12)
    ax2.set_title(f'Average Goals per Match by Gameweek - {season}', fontsize=14, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    ax2.set_xticks(gameweeks)
    ax2.axhline(y=sum(avg_goals)/len(avg_goals), color='red', linestyle='--',
                label=f'Season Average: {sum(avg_goals)/len(avg_goals):.2f}')
    ax2.legend()

    # Add value labels on bars
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}',
                ha='center', va='bottom', fontsize=9)

    plt.tight_layout()

    # Save the chart
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_dir / f'goals_per_gameweek_{season.replace("/", "_")}_{timestamp}.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    logger.info(f"Chart saved to: {filename}")

    # Show the chart
    plt.show()

    return filename


def generate_summary_report(data, season, output_dir):
    """Generate text summary report"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = output_dir / f'goals_analysis_{season.replace("/", "_")}_{timestamp}.md'

    total_matches = sum(row[1] for row in data)
    total_goals = sum(row[2] for row in data)
    overall_avg = total_goals / total_matches if total_matches > 0 else 0

    # Find highest and lowest scoring gameweeks
    highest_gw = max(data, key=lambda x: x[2])
    lowest_gw = min(data, key=lambda x: x[2])

    with open(report_file, 'w') as f:
        f.write(f"# Goals Analysis - {season}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Overall Statistics\n\n")
        f.write(f"- **Total Gameweeks:** {len(data)}\n")
        f.write(f"- **Total Matches:** {total_matches}\n")
        f.write(f"- **Total Goals:** {total_goals}\n")
        f.write(f"- **Average Goals per Match:** {overall_avg:.2f}\n\n")

        f.write("## Gameweek Highlights\n\n")
        f.write(f"- **Highest Scoring Gameweek:** GW{highest_gw[0]} ({highest_gw[2]} goals in {highest_gw[1]} matches, avg {highest_gw[3]} per match)\n")
        f.write(f"- **Lowest Scoring Gameweek:** GW{lowest_gw[0]} ({lowest_gw[2]} goals in {lowest_gw[1]} matches, avg {lowest_gw[3]} per match)\n\n")

        f.write("## Detailed Breakdown\n\n")
        f.write("| Gameweek | Matches | Total Goals | Avg Goals/Match |\n")
        f.write("|----------|---------|-------------|------------------|\n")

        for row in data:
            f.write(f"| GW{row[0]} | {row[1]} | {row[2]} | {row[3]} |\n")

        f.write("\n")

    logger.info(f"Report saved to: {report_file}")
    return report_file


def main(args, logger):
    """Main script execution"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    output_dir = Path(__file__).parent.parent.parent / "analysis_reports" / "goals_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Analyzing goals per gameweek for season: {args.season}")

    # Connect to database
    conn = sql.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get goals data
        data = get_goals_per_gameweek(cursor, args.season)

        if not data:
            logger.warning(f"No completed fixtures found for season {args.season}")
            return

        logger.info(f"Found {len(data)} gameweeks with completed fixtures")

        # Generate report
        report_file = generate_summary_report(data, args.season, output_dir)

        # Create visualization
        if not args.no_chart:
            chart_file = create_visualization(data, args.season, output_dir)

        # Print summary to console
        total_matches = sum(row[1] for row in data)
        total_goals = sum(row[2] for row in data)
        overall_avg = total_goals / total_matches if total_matches > 0 else 0

        logger.info("=" * 60)
        logger.info(f"GOALS ANALYSIS - {args.season}")
        logger.info("=" * 60)
        logger.info(f"Total Gameweeks: {len(data)}")
        logger.info(f"Total Matches: {total_matches}")
        logger.info(f"Total Goals: {total_goals}")
        logger.info(f"Average Goals per Match: {overall_avg:.2f}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error analyzing goals data: {e}")
        raise
    finally:
        conn.close()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze goals per gameweek and create visualization'
    )
    parser.add_argument(
        '--season',
        type=str,
        default='2025/2026',
        help='Season to analyze (default: 2025/2026)'
    )
    parser.add_argument(
        '--no-chart',
        action='store_true',
        help='Skip chart generation (only create report)'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    main(args, logger)
