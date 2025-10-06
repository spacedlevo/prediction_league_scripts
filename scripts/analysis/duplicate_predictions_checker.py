#!/usr/bin/env python3
"""
Duplicate Predictions Checker

Analyzes predictions to find players who have submitted identical predictions
for entire gameweeks. This helps identify potential collusion or copying.

DETECTION LOGIC:
- Compares all predictions within each gameweek
- Only flags as duplicate if ALL predictions for that gameweek match
- Partial matches are not flagged
- Reports both players involved in each duplicate pair

OUTPUT:
- Markdown report saved to analysis_reports/
- Summary statistics of duplicates found
- Detailed breakdown by gameweek and player pair

USAGE:
    python scripts/analysis/duplicate_predictions_checker.py
    python scripts/analysis/duplicate_predictions_checker.py --season "2024/2025"
    python scripts/analysis/duplicate_predictions_checker.py --gameweek 5
"""

import sqlite3 as sql
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Set

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
REPORTS_DIR = PROJECT_ROOT / "analysis_reports"

# Create reports directory
REPORTS_DIR.mkdir(exist_ok=True)


def get_predictions_by_gameweek(cursor: sql.Cursor, season: str, gameweek: int = None) -> Dict:
    """
    Get all predictions organized by gameweek and player

    Returns:
        {
            gameweek: {
                player_name: {
                    fixture_id: "predicted_score"
                }
            }
        }
    """
    gameweek_filter = ""
    params = [season]

    if gameweek:
        gameweek_filter = "AND f.gameweek = ?"
        params.append(gameweek)

    query = f"""
        SELECT
            f.gameweek,
            pl.player_name,
            p.fixture_id,
            p.home_goals || '-' || p.away_goals as predicted_score,
            t_home.team_name as home_team,
            t_away.team_name as away_team
        FROM predictions p
        JOIN fixtures f ON p.fixture_id = f.fixture_id
        JOIN players pl ON p.player_id = pl.player_id
        JOIN teams t_home ON f.home_teamid = t_home.team_id
        JOIN teams t_away ON f.away_teamid = t_away.team_id
        WHERE f.season = ? {gameweek_filter}
        ORDER BY f.gameweek, pl.player_name, f.fixture_id
    """

    cursor.execute(query, params)

    # Organize predictions
    gameweeks = defaultdict(lambda: defaultdict(dict))

    for row in cursor.fetchall():
        gw, player, fixture_id, score, home_team, away_team = row
        gameweeks[gw][player][fixture_id] = {
            'score': score,
            'home_team': home_team,
            'away_team': away_team
        }

    return dict(gameweeks)


def find_duplicate_gameweeks(gameweek_data: Dict) -> List[Tuple[str, str]]:
    """
    Find players with identical predictions for entire gameweek

    Returns list of (player1, player2) tuples with duplicate predictions
    """
    duplicates = []
    players = list(gameweek_data.keys())

    # Compare each pair of players
    for i in range(len(players)):
        for j in range(i + 1, len(players)):
            player1 = players[i]
            player2 = players[j]

            predictions1 = gameweek_data[player1]
            predictions2 = gameweek_data[player2]

            # Check if they have predictions for same fixtures
            fixtures1 = set(predictions1.keys())
            fixtures2 = set(predictions2.keys())

            # Only compare if they have predictions for the same fixtures
            if fixtures1 != fixtures2:
                continue

            # If no fixtures, skip
            if not fixtures1:
                continue

            # Check if all predictions match
            all_match = True
            for fixture_id in fixtures1:
                if predictions1[fixture_id]['score'] != predictions2[fixture_id]['score']:
                    all_match = False
                    break

            if all_match:
                duplicates.append((player1, player2))

    return duplicates


def analyze_duplicates(cursor: sql.Cursor, season: str, gameweek: int = None) -> Dict:
    """Analyze all duplicates for the season or specific gameweek"""

    print(f"Analyzing duplicate predictions for season {season}...")
    if gameweek:
        print(f"Filtering for gameweek {gameweek}...")

    # Get all predictions
    gameweeks_data = get_predictions_by_gameweek(cursor, season, gameweek)

    if not gameweeks_data:
        print(f"No predictions found for season {season}")
        return {}

    # Find duplicates for each gameweek
    results = {}

    for gw, players_data in sorted(gameweeks_data.items()):
        print(f"\nChecking gameweek {gw}...")
        print(f"  Players with predictions: {len(players_data)}")

        duplicates = find_duplicate_gameweeks(players_data)

        if duplicates:
            print(f"  ⚠️  Found {len(duplicates)} duplicate pair(s)")
            results[gw] = {
                'duplicates': duplicates,
                'players_data': players_data,
                'total_players': len(players_data)
            }
        else:
            print(f"  ✓ No duplicates found")

    return results


def generate_markdown_report(results: Dict, season: str, gameweek: int = None) -> str:
    """Generate markdown report of duplicate predictions"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build filename
    if gameweek:
        filename = f"duplicate_predictions_{season.replace('/', '_')}_gw{gameweek}.md"
    else:
        filename = f"duplicate_predictions_{season.replace('/', '_')}.md"

    output_path = REPORTS_DIR / filename

    # Count total duplicates
    total_duplicates = sum(len(data['duplicates']) for data in results.values())
    total_gameweeks = len(results)

    # Build report
    lines = [
        "# Duplicate Predictions Analysis",
        "",
        f"**Season:** {season}",
        f"**Analysis Date:** {timestamp}",
        ""
    ]

    if gameweek:
        lines.append(f"**Gameweek Filter:** {gameweek}")
        lines.append("")

    lines.extend([
        "## Summary",
        "",
        f"- **Total Gameweeks with Duplicates:** {total_gameweeks}",
        f"- **Total Duplicate Pairs Found:** {total_duplicates}",
        ""
    ])

    if total_duplicates == 0:
        lines.extend([
            "✓ **No duplicate predictions found!**",
            "",
            "All players have unique predictions for their gameweeks.",
            ""
        ])
    else:
        lines.extend([
            "⚠️ **Duplicate predictions detected!**",
            "",
            "The following players have submitted identical predictions:",
            ""
        ])

    # Detailed breakdown by gameweek
    if results:
        lines.extend([
            "---",
            "",
            "## Detailed Analysis",
            ""
        ])

        for gw in sorted(results.keys()):
            data = results[gw]
            duplicates = data['duplicates']
            players_data = data['players_data']

            lines.extend([
                f"### Gameweek {gw}",
                "",
                f"**Total Players:** {data['total_players']}",
                f"**Duplicate Pairs:** {len(duplicates)}",
                ""
            ])

            for player1, player2 in duplicates:
                lines.extend([
                    f"#### 🔴 {player1} ↔ {player2}",
                    "",
                    "**Identical Predictions:**",
                    "",
                    "| Fixture | Prediction |",
                    "|---------|------------|"
                ])

                # Show their matching predictions
                for fixture_id in sorted(players_data[player1].keys()):
                    pred = players_data[player1][fixture_id]
                    home_team = pred['home_team']
                    away_team = pred['away_team']
                    score = pred['score']

                    lines.append(f"| {home_team} vs {away_team} | {score} |")

                lines.append("")

    # Write to file
    report_content = "\n".join(lines)

    with open(output_path, 'w') as f:
        f.write(report_content)

    return str(output_path)


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Detect duplicate predictions between players'
    )
    parser.add_argument('--season', type=str, default='2025/2026',
                       help='Season to analyze (default: 2025/2026)')
    parser.add_argument('--gameweek', type=int, default=None,
                       help='Specific gameweek to analyze (optional)')

    args = parser.parse_args()

    print("="*60)
    print("DUPLICATE PREDICTIONS CHECKER")
    print("="*60)

    # Connect to database
    conn = sql.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Analyze duplicates
        results = analyze_duplicates(cursor, args.season, args.gameweek)

        # Generate report
        if results or args.gameweek:  # Generate report even if no duplicates when filtering
            report_path = generate_markdown_report(results, args.season, args.gameweek)
            print("\n" + "="*60)
            print("ANALYSIS COMPLETE")
            print("="*60)
            print(f"\nReport saved to: {report_path}")
        else:
            print("\n" + "="*60)
            print("No predictions found for the specified criteria")
            print("="*60)

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
