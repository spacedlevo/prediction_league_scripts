#!/usr/bin/env python3
"""
Analyze team performance with specific match officials when they are favorites to win.

This script uses Pulse API data from the match_officials table to analyze how teams
perform when they are betting favorites with different match officials (referees, VAR,
linesmen, fourth officials, etc.).
"""

import sqlite3
import argparse
from pathlib import Path
from typing import Optional, List, Tuple


def setup_database_connection():
    """Setup database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)


def get_available_teams(cursor):
    """Get list of available teams from fixtures with pulse data"""
    cursor.execute("""
        SELECT DISTINCT t.team_name
        FROM teams t
        JOIN fixtures f ON (t.team_id = f.home_teamid OR t.team_id = f.away_teamid)
        WHERE f.pulse_id IS NOT NULL
        AND f.home_win_odds IS NOT NULL
        ORDER BY t.team_name
    """)
    return [row[0] for row in cursor.fetchall()]


def get_available_officials(cursor, role_filter: Optional[str] = None):
    """Get list of available officials from the database"""
    query = """
        SELECT DISTINCT mo.name, mo.role, COUNT(*) as match_count
        FROM match_officials mo
        JOIN fixtures f ON mo.pulseid = f.pulse_id
        WHERE mo.name IS NOT NULL
    """

    params = []
    if role_filter and role_filter.upper() != 'ALL':
        query += " AND mo.role = ?"
        params.append(role_filter.upper())

    query += " GROUP BY mo.name, mo.role ORDER BY match_count DESC, mo.name"

    cursor.execute(query, params)
    return cursor.fetchall()


def get_available_roles(cursor):
    """Get list of available official roles"""
    cursor.execute("""
        SELECT DISTINCT role, COUNT(*) as count
        FROM match_officials
        WHERE role IS NOT NULL
        GROUP BY role
        ORDER BY count DESC
    """)
    return cursor.fetchall()


def analyze_team_official_performance(
    cursor,
    team_name: str,
    official_name: Optional[str] = None,
    role_filter: Optional[str] = None,
    season_filter: Optional[str] = None,
    min_matches: int = 1
):
    """
    Analyze team performance when they are favorites with specific officials

    Args:
        cursor: Database cursor
        team_name: Name of the team to analyze
        official_name: Optional name of the official to filter by
        role_filter: Optional role to filter by (MAIN, VAR, etc.)
        season_filter: Optional season to filter by
        min_matches: Minimum number of matches for official to be included

    Returns:
        List of match tuples with official information
    """
    # Build the query to find matches where the team was favorite
    # Uses football_stats odds (AvgH, AvgD, AvgA) when available, falls back to fixtures odds
    query = """
        WITH favorite_matches AS (
            -- Home matches where team was favorite (lowest odds)
            SELECT
                f.fixture_id,
                f.pulse_id,
                ht.team_name as Team,
                at.team_name as Opponent,
                'H' as Venue,
                COALESCE(fs.AvgH, f.home_win_odds) as TeamOdds,
                COALESCE(fs.AvgA, f.away_win_odds) as OpponentOdds,
                COALESCE(fs.AvgD, f.draw_odds) as DrawOdds,
                f.gameweek,
                f.season,
                f.kickoff_dttm,
                r.home_goals,
                r.away_goals,
                CASE
                    WHEN r.home_goals > r.away_goals THEN 'W'
                    WHEN r.home_goals < r.away_goals THEN 'L'
                    WHEN r.home_goals = r.away_goals THEN 'D'
                    ELSE NULL
                END as Result,
                CASE WHEN fs.fixture_id IS NOT NULL THEN 'football_stats' ELSE 'fixtures' END as OddsSource
            FROM fixtures f
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            LEFT JOIN results r ON f.fixture_id = r.fixture_id
            LEFT JOIN football_stats fs ON f.fixture_id = fs.fixture_id
            WHERE ht.team_name = ?
            AND f.pulse_id IS NOT NULL
            AND COALESCE(fs.AvgH, f.home_win_odds) IS NOT NULL
            AND COALESCE(fs.AvgH, f.home_win_odds) < COALESCE(fs.AvgD, f.draw_odds)
            AND COALESCE(fs.AvgH, f.home_win_odds) < COALESCE(fs.AvgA, f.away_win_odds)
            AND f.finished = 1

            UNION ALL

            -- Away matches where team was favorite (lowest odds)
            SELECT
                f.fixture_id,
                f.pulse_id,
                at.team_name as Team,
                ht.team_name as Opponent,
                'A' as Venue,
                COALESCE(fs.AvgA, f.away_win_odds) as TeamOdds,
                COALESCE(fs.AvgH, f.home_win_odds) as OpponentOdds,
                COALESCE(fs.AvgD, f.draw_odds) as DrawOdds,
                f.gameweek,
                f.season,
                f.kickoff_dttm,
                r.away_goals as home_goals,
                r.home_goals as away_goals,
                CASE
                    WHEN r.away_goals > r.home_goals THEN 'W'
                    WHEN r.away_goals < r.home_goals THEN 'L'
                    WHEN r.away_goals = r.home_goals THEN 'D'
                    ELSE NULL
                END as Result,
                CASE WHEN fs.fixture_id IS NOT NULL THEN 'football_stats' ELSE 'fixtures' END as OddsSource
            FROM fixtures f
            JOIN teams ht ON f.home_teamid = ht.team_id
            JOIN teams at ON f.away_teamid = at.team_id
            LEFT JOIN results r ON f.fixture_id = r.fixture_id
            LEFT JOIN football_stats fs ON f.fixture_id = fs.fixture_id
            WHERE at.team_name = ?
            AND f.pulse_id IS NOT NULL
            AND COALESCE(fs.AvgA, f.away_win_odds) IS NOT NULL
            AND COALESCE(fs.AvgA, f.away_win_odds) < COALESCE(fs.AvgD, f.draw_odds)
            AND COALESCE(fs.AvgA, f.away_win_odds) < COALESCE(fs.AvgH, f.home_win_odds)
            AND f.finished = 1
        )
        SELECT DISTINCT
            fm.fixture_id,
            fm.Team,
            fm.Opponent,
            fm.Venue,
            fm.TeamOdds,
            fm.OpponentOdds,
            fm.gameweek,
            fm.season,
            fm.kickoff_dttm,
            fm.Result,
            mo.name as OfficialName,
            mo.role as OfficialRole,
            CASE
                WHEN fm.Result = 'L' THEN 1
                ELSE 0
            END as Lost,
            fm.OddsSource
        FROM favorite_matches fm
        JOIN match_officials mo ON fm.pulse_id = mo.pulseid
        WHERE mo.name IS NOT NULL
    """

    params = [team_name, team_name]

    if official_name:
        query += " AND mo.name = ?"
        params.append(official_name)

    if role_filter and role_filter.upper() != 'ALL':
        query += " AND mo.role = ?"
        params.append(role_filter.upper())

    if season_filter:
        query += " AND fm.season = ?"
        params.append(season_filter)

    query += " ORDER BY fm.kickoff_dttm DESC"

    cursor.execute(query, params)
    matches = cursor.fetchall()

    return matches


def print_analysis_results(
    team_name: str,
    official_name: Optional[str],
    role_filter: Optional[str],
    season_filter: Optional[str],
    matches: list,
    min_matches: int = 1
):
    """Print formatted analysis results"""
    if not matches:
        print(f"\nNo matches found where {team_name} was favorite", end="")
        if official_name:
            print(f" with official {official_name}")
        elif role_filter and role_filter.upper() != 'ALL':
            print(f" with {role_filter} officials")
        else:
            print()
        return

    # Calculate unique fixtures (since one fixture can have multiple officials)
    unique_fixtures = {}
    for match in matches:
        fixture_id = match[0]
        if fixture_id not in unique_fixtures:
            unique_fixtures[fixture_id] = match

    total_matches = len(unique_fixtures)
    losses = sum(1 for match in unique_fixtures.values() if match[12] == 1)  # Lost column
    wins = sum(1 for match in unique_fixtures.values() if match[9] == 'W')
    draws = sum(1 for match in unique_fixtures.values() if match[9] == 'D')
    loss_percentage = (losses / total_matches * 100) if total_matches > 0 else 0
    win_percentage = (wins / total_matches * 100) if total_matches > 0 else 0

    # Check odds sources
    odds_sources = {}
    for match in unique_fixtures.values():
        source = match[13]  # OddsSource column
        odds_sources[source] = odds_sources.get(source, 0) + 1

    print("\n" + "=" * 100)
    print("MATCH OFFICIALS FAVOURITE ANALYSIS")
    print("=" * 100)
    print(f"\nTeam: {team_name}")

    if official_name:
        print(f"Official: {official_name}")
    else:
        print("Official: All officials")

    if role_filter and role_filter.upper() != 'ALL':
        print(f"Role Filter: {role_filter.upper()}")
    else:
        print("Role Filter: All roles")

    if season_filter:
        print(f"Season: {season_filter}")

    # Display odds sources
    print(f"\nOdds Source: ", end="")
    if len(odds_sources) == 1:
        source = list(odds_sources.keys())[0]
        print(f"{source} (all {total_matches} matches)")
    else:
        print(f"Mixed - ", end="")
        parts = []
        for source, count in sorted(odds_sources.items()):
            parts.append(f"{source}: {count}")
        print(", ".join(parts))

    print("\n" + "-" * 100)
    print(f"\nTotal matches as favourite: {total_matches}")
    print(f"Wins: {wins} ({win_percentage:.1f}%)")
    print(f"Draws: {draws} ({draws/total_matches*100:.1f}%)")
    print(f"Losses: {losses} ({loss_percentage:.1f}%)")
    print("\n" + "-" * 100)

    # Show detailed match results
    print("\nDetailed Match Results:")
    print("-" * 100)
    print(f"{'Date':<12} {'Opponent':<18} {'Official':<25} {'Role':<15} {'Venue':<6} {'Result':<8} {'Odds':<6}")
    print("-" * 100)

    shown_fixtures = set()
    shown_count = 0
    for match in matches:
        fixture_id = match[0]
        if fixture_id in shown_fixtures or shown_count >= 25:
            continue

        shown_fixtures.add(fixture_id)
        shown_count += 1

        _, team, opponent, venue, team_odds, opp_odds, gameweek, season, kickoff, result, official, role, lost, odds_source = match
        date = kickoff[:10] if kickoff else "N/A"
        result_str = result if result else "N/A"

        print(f"{date:<12} {opponent[:17]:<18} {official[:24]:<25} {role[:14]:<15} {venue:<6} {result_str:<8} {team_odds:.2f}")

    if len(unique_fixtures) > 25:
        print(f"\n... and {len(unique_fixtures) - 25} more matches")

    # Official breakdown if analyzing all officials
    if not official_name and total_matches > 0:
        print("\n" + "-" * 100)
        print(f"BREAKDOWN BY OFFICIAL (minimum {min_matches} matches):")
        print("-" * 100)

        official_stats = {}
        for match in matches:
            fixture_id, _, _, _, _, _, _, _, _, result, official, role, lost, odds_source = match

            key = (official, role)
            if key not in official_stats:
                official_stats[key] = {
                    'fixtures': set(),
                    'losses': 0,
                    'wins': 0,
                    'draws': 0
                }

            # Track unique fixtures for this official
            if fixture_id not in official_stats[key]['fixtures']:
                official_stats[key]['fixtures'].add(fixture_id)
                if result == 'L':
                    official_stats[key]['losses'] += 1
                elif result == 'W':
                    official_stats[key]['wins'] += 1
                elif result == 'D':
                    official_stats[key]['draws'] += 1

        # Convert to sortable list with match counts
        official_list = []
        for (official, role), stats in official_stats.items():
            match_count = len(stats['fixtures'])
            if match_count >= min_matches:
                loss_pct = (stats['losses'] / match_count * 100) if match_count > 0 else 0
                win_pct = (stats['wins'] / match_count * 100) if match_count > 0 else 0
                official_list.append((official, role, match_count, stats['wins'], stats['draws'], stats['losses'], win_pct, loss_pct))

        # Sort by loss percentage (highest loss rate first), then by match count
        sorted_officials = sorted(official_list, key=lambda x: (-x[7], -x[2]))

        print(f"{'Official':<30} {'Role':<15} {'Matches':<8} {'W':<4} {'D':<4} {'L':<4} {'Win %':<8} {'Loss %':<8}")
        print("-" * 100)

        for official, role, matches_count, wins, draws, losses, win_pct, loss_pct in sorted_officials[:20]:
            print(f"{official[:29]:<30} {role[:14]:<15} {matches_count:<8} {wins:<4} {draws:<4} {losses:<4} {win_pct:>6.1f}% {loss_pct:>6.1f}%")

        if len(sorted_officials) > 20:
            print(f"\n... and {len(sorted_officials) - 20} more officials")

    print("\n" + "=" * 100)


def interactive_mode(cursor):
    """Interactive mode to select team, official, and role"""
    print("\n" + "=" * 100)
    print("MATCH OFFICIALS FAVOURITE ANALYSIS - INTERACTIVE MODE")
    print("=" * 100)

    # Get team selection
    teams = get_available_teams(cursor)
    print(f"\nAvailable teams: {len(teams)} teams in database with Pulse API data")
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

    # Get role selection
    print("\nAvailable official roles:")
    roles = get_available_roles(cursor)
    print("  0. ALL (all roles)")
    for i, (role, count) in enumerate(roles, 1):
        print(f"  {i}. {role} ({count} records)")

    role_choice = input("\nEnter role number or name (or press Enter for ALL): ").strip()

    if not role_choice or role_choice == "0":
        role_filter = "ALL"
    elif role_choice.isdigit() and 1 <= int(role_choice) <= len(roles):
        role_filter = roles[int(role_choice) - 1][0]
    else:
        role_filter = role_choice.upper()

    print(f"Selected role: {role_filter}")

    # Get official selection
    print("\nEnter official name (or press Enter to analyze all officials)")
    official_name = input("Official: ").strip()

    if official_name:
        # Find matching officials
        officials = get_available_officials(cursor, role_filter if role_filter != "ALL" else None)
        matching_officials = [o for o in officials if official_name.lower() in o[0].lower()]

        if not matching_officials:
            print(f"No officials found matching '{official_name}'")
            return
        elif len(matching_officials) > 1:
            print("\nMultiple officials found:")
            for i, (off_name, off_role, match_count) in enumerate(matching_officials[:15], 1):
                print(f"  {i}. {off_name} ({off_role}, {match_count} matches)")

            choice = input("\nEnter official number (or full name): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= min(15, len(matching_officials)):
                official_name = matching_officials[int(choice) - 1][0]
            else:
                official_name = choice
        else:
            official_name = matching_officials[0][0]
            print(f"\nSelected official: {official_name} ({matching_officials[0][1]})")
    else:
        official_name = None

    # Get minimum matches filter
    min_matches_input = input("\nMinimum matches for official breakdown (default: 5): ").strip()
    min_matches = int(min_matches_input) if min_matches_input.isdigit() else 5

    # Run analysis
    matches = analyze_team_official_performance(
        cursor,
        team_name,
        official_name,
        role_filter,
        season_filter=None,
        min_matches=min_matches
    )
    print_analysis_results(team_name, official_name, role_filter, None, matches, min_matches)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze team performance with match officials when they are favorites to win (Pulse API data)'
    )
    parser.add_argument('--team', type=str, help='Team name to analyze')
    parser.add_argument('--official', type=str, help='Official name to filter by (optional)')
    parser.add_argument('--role', type=str, default='ALL',
                       help='Official role to filter by: MAIN, VAR, FOURTH_OFFICIAL, LINEOFFICIAL, ALL (default: ALL)')
    parser.add_argument('--season', type=str, help='Season to filter by (e.g., 2024/2025)')
    parser.add_argument('--min-matches', type=int, default=5,
                       help='Minimum matches for official to be included in breakdown (default: 5)')
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
            matches = analyze_team_official_performance(
                cursor,
                args.team,
                args.official,
                args.role,
                args.season,
                args.min_matches
            )
            print_analysis_results(
                args.team,
                args.official,
                args.role,
                args.season,
                matches,
                args.min_matches
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
