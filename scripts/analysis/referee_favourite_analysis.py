#!/usr/bin/env python3
"""
Analyze team performance with specific referees when they are favorites to win.

This script analyzes historical data from the football_stats table to determine
how often a team loses when they are the betting favorite with a specific referee.
"""

import sqlite3
import argparse
from pathlib import Path
from typing import Tuple, Optional


def setup_database_connection():
    """Setup database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)


def get_available_teams(cursor):
    """Get list of available teams from the database"""
    cursor.execute("""
        SELECT DISTINCT HomeTeam FROM football_stats
        WHERE AvgH IS NOT NULL
        UNION
        SELECT DISTINCT AwayTeam FROM football_stats
        WHERE AvgA IS NOT NULL
        ORDER BY 1
    """)
    return [row[0] for row in cursor.fetchall()]


def get_available_referees(cursor):
    """Get list of available referees from the database"""
    cursor.execute("""
        SELECT DISTINCT Referee
        FROM football_stats
        WHERE Referee IS NOT NULL
        AND AvgH IS NOT NULL
        ORDER BY Referee
    """)
    return [row[0] for row in cursor.fetchall()]


def analyze_team_referee_performance(cursor, team_name: str, referee_name: Optional[str] = None):
    """
    Analyze team performance when they are favorites

    Args:
        cursor: Database cursor
        team_name: Name of the team to analyze
        referee_name: Optional name of the referee to filter by

    Returns:
        Tuple of (total_matches, losses, loss_percentage)
    """
    # Build the query to find matches where the team was favorite
    query = """
        WITH favorite_matches AS (
            -- Home matches where team was favorite (lowest odds)
            SELECT
                HomeTeam as Team,
                AwayTeam as Opponent,
                Referee,
                FTR as Result,
                AvgH as TeamOdds,
                AvgA as OpponentOdds,
                'H' as Venue,
                Date,
                Season
            FROM football_stats
            WHERE HomeTeam = ?
            AND AvgH IS NOT NULL
            AND AvgH < AvgD
            AND AvgH < AvgA

            UNION ALL

            -- Away matches where team was favorite (lowest odds)
            SELECT
                AwayTeam as Team,
                HomeTeam as Opponent,
                Referee,
                FTR as Result,
                AvgA as TeamOdds,
                AvgH as OpponentOdds,
                'A' as Venue,
                Date,
                Season
            FROM football_stats
            WHERE AwayTeam = ?
            AND AvgA IS NOT NULL
            AND AvgA < AvgD
            AND AvgA < AvgH
        )
        SELECT
            Team,
            Opponent,
            Referee,
            Result,
            TeamOdds,
            OpponentOdds,
            Venue,
            Date,
            Season,
            CASE
                WHEN (Venue = 'H' AND Result = 'A') OR (Venue = 'A' AND Result = 'H') THEN 1
                ELSE 0
            END as Lost
        FROM favorite_matches
        WHERE Referee IS NOT NULL
    """

    params = [team_name, team_name]

    if referee_name:
        query += " AND Referee = ?"
        params.append(referee_name)

    query += " ORDER BY Date DESC"

    cursor.execute(query, params)
    matches = cursor.fetchall()

    return matches


def print_analysis_results(team_name: str, referee_name: Optional[str], matches: list):
    """Print formatted analysis results"""
    if not matches:
        print(f"\nNo matches found where {team_name} was favorite", end="")
        if referee_name:
            print(f" with referee {referee_name}")
        else:
            print()
        return

    total_matches = len(matches)
    losses = sum(1 for match in matches if match[9] == 1)  # Lost column
    wins = sum(1 for match in matches if match[9] == 0)
    loss_percentage = (losses / total_matches * 100) if total_matches > 0 else 0

    print("\n" + "=" * 80)
    print("REFEREE FAVOURITE ANALYSIS")
    print("=" * 80)
    print(f"\nTeam: {team_name}")
    if referee_name:
        print(f"Referee: {referee_name}")
    else:
        print("Referee: All referees")
    print("\n" + "-" * 80)
    print(f"\nTotal matches as favourite: {total_matches}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"\nLoss rate when favourite: {loss_percentage:.1f}%")
    print("\n" + "-" * 80)

    # Show detailed match results
    print("\nDetailed Match Results:")
    print("-" * 80)
    print(f"{'Date':<12} {'Opponent':<20} {'Referee':<20} {'Venue':<6} {'Result':<8} {'Odds':<6}")
    print("-" * 80)

    for match in matches[:20]:  # Show first 20 matches
        team, opponent, ref, result, team_odds, opp_odds, venue, date, season, lost = match
        result_str = "LOST" if lost == 1 else "WON/DREW"
        print(f"{date:<12} {opponent:<20} {ref:<20} {venue:<6} {result_str:<8} {team_odds:.2f}")

    if len(matches) > 20:
        print(f"\n... and {len(matches) - 20} more matches")

    # Referee breakdown if analyzing all referees
    if not referee_name and total_matches > 0:
        print("\n" + "-" * 80)
        print("BREAKDOWN BY REFEREE:")
        print("-" * 80)

        referee_stats = {}
        for match in matches:
            ref = match[2]
            lost = match[9]
            if ref not in referee_stats:
                referee_stats[ref] = {'total': 0, 'losses': 0}
            referee_stats[ref]['total'] += 1
            referee_stats[ref]['losses'] += lost

        # Sort by loss percentage (highest loss rate first)
        sorted_refs = sorted(referee_stats.items(),
                           key=lambda x: (x[1]['losses'] / x[1]['total'] * 100) if x[1]['total'] > 0 else 0,
                           reverse=True)

        print(f"{'Referee':<30} {'Matches':<10} {'Losses':<10} {'Loss %':<10}")
        print("-" * 80)

        for ref, stats in sorted_refs[:15]:  # Show top 15 referees
            loss_pct = (stats['losses'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"{ref:<30} {stats['total']:<10} {stats['losses']:<10} {loss_pct:.1f}%")

        if len(sorted_refs) > 15:
            print(f"\n... and {len(sorted_refs) - 15} more referees")

    print("\n" + "=" * 80)


def interactive_mode(cursor):
    """Interactive mode to select team and referee"""
    print("\n" + "=" * 80)
    print("REFEREE FAVOURITE ANALYSIS - INTERACTIVE MODE")
    print("=" * 80)

    # Get team selection
    teams = get_available_teams(cursor)
    print(f"\nAvailable teams: {len(teams)} teams in database")
    team_name = input("\nEnter team name (or part of name): ").strip()

    # Find matching teams
    matching_teams = [t for t in teams if team_name.lower() in t.lower()]

    if not matching_teams:
        print(f"No teams found matching '{team_name}'")
        return
    elif len(matching_teams) > 1:
        print("\nMultiple teams found:")
        for i, team in enumerate(matching_teams[:10], 1):
            print(f"  {i}. {team}")
        if len(matching_teams) > 10:
            print(f"  ... and {len(matching_teams) - 10} more")

        choice = input("\nEnter team number (or full name): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= min(10, len(matching_teams)):
            team_name = matching_teams[int(choice) - 1]
        else:
            team_name = choice
    else:
        team_name = matching_teams[0]
        print(f"\nSelected team: {team_name}")

    # Get referee selection
    print("\nEnter referee name (or press Enter to analyze all referees)")
    referee_name = input("Referee: ").strip()

    if referee_name:
        # Find matching referees
        referees = get_available_referees(cursor)
        matching_refs = [r for r in referees if referee_name.lower() in r.lower()]

        if not matching_refs:
            print(f"No referees found matching '{referee_name}'")
            return
        elif len(matching_refs) > 1:
            print("\nMultiple referees found:")
            for i, ref in enumerate(matching_refs[:10], 1):
                print(f"  {i}. {ref}")

            choice = input("\nEnter referee number (or full name): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= min(10, len(matching_refs)):
                referee_name = matching_refs[int(choice) - 1]
            else:
                referee_name = choice
        else:
            referee_name = matching_refs[0]
            print(f"\nSelected referee: {referee_name}")
    else:
        referee_name = None

    # Run analysis
    matches = analyze_team_referee_performance(cursor, team_name, referee_name)
    print_analysis_results(team_name, referee_name, matches)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze team performance with specific referees when they are favorites to win'
    )
    parser.add_argument('--team', type=str, help='Team name to analyze')
    parser.add_argument('--referee', type=str, help='Referee name to filter by (optional)')
    parser.add_argument('--interactive', action='store_true',
                       help='Run in interactive mode')
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_arguments()

    conn = setup_database_connection()
    cursor = conn.cursor()

    try:
        if args.interactive or (not args.team):
            interactive_mode(cursor)
        else:
            matches = analyze_team_referee_performance(cursor, args.team, args.referee)
            print_analysis_results(args.team, args.referee, matches)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
