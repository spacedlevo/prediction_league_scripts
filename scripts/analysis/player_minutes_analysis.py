#!/usr/bin/env python3
"""
Calculate player minutes played from pulse API data.

This script analyzes team_list and match_events tables to determine how many
minutes each player has played during the 2025/2026 season (or other seasons).
"""

import sqlite3
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


def setup_database_connection():
    """Setup database connection"""
    db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
    return sqlite3.connect(db_path)


def get_match_duration(cursor, pulseid: int) -> int:
    """
    Get the duration of a match in seconds from match events.

    Correctly calculates playing time using phase markers (PS/PE).
    Event times are cumulative, but the second half "resets" to the 45-minute mark.

    Calculation:
    - Find the PE marker that comes between the two PS markers (first half end with stoppage)
    - Find the second PS marker (always 2700s = 45 min, where second half starts)
    - Find the final PE marker (end of match)
    - Total = first_half_end_time + (final_time - 2700)
    """
    cursor.execute("""
        SELECT event_type, CAST(event_time AS INTEGER) as time
        FROM match_events
        WHERE pulseid = ? AND event_type IN ('PS', 'PE')
        ORDER BY time
    """, (pulseid,))

    phases = cursor.fetchall()

    if not phases or len(phases) < 4:
        # Need at least 2 PS and 2 PE markers
        return 5400

    # Phases in chronological order should be: PS(0), PS(2700), PE(?), PE(final)
    # We need to find which PE represents the first half end
    ps_markers = [p for p in phases if p[0] == 'PS']
    pe_markers = [p for p in phases if p[0] == 'PE']

    if len(ps_markers) < 2 or len(pe_markers) < 2:
        return 5400

    second_half_start = ps_markers[1][1]  # Should be 2700
    final_time = pe_markers[-1][1]  # Last PE marker

    # Find the PE that represents first half end
    # It's the PE that comes closest to but after the 45-minute mark
    first_half_end = None
    for pe_type, pe_time in pe_markers:
        if pe_time >= second_half_start:  # PE after or at the 45-min mark
            if first_half_end is None or pe_time < first_half_end:
                first_half_end = pe_time
                break  # Take the first one we find

    if not first_half_end:
        return 5400

    # Calculate total: first_half_duration + second_half_duration
    first_half_duration = first_half_end  # Includes stoppage time
    second_half_duration = final_time - second_half_start

    return first_half_duration + second_half_duration


def get_substitutions(cursor, pulseid: int) -> Dict[int, List[Tuple[int, str]]]:
    """
    Get substitutions for a match.

    Returns a dict mapping person_id to list of (time, action) tuples
    where action is 'off' or 'on'
    """
    # Get team lists to identify starters vs bench
    cursor.execute("""
        SELECT person_id, is_starting
        FROM team_list
        WHERE pulseid = ?
    """, (pulseid,))

    player_status = {row[0]: row[1] for row in cursor.fetchall()}

    # Get all substitution events
    cursor.execute("""
        SELECT person_id, CAST(event_time AS INTEGER) as time
        FROM match_events
        WHERE pulseid = ? AND event_type = 'S'
        ORDER BY time
    """, (pulseid,))

    substitutions = defaultdict(list)

    for person_id, time in cursor.fetchall():
        # If person was starting, they're coming OFF
        # If person was on bench, they're coming ON
        is_starting = player_status.get(person_id, 0)

        if is_starting == 1:
            substitutions[person_id].append((time, 'off'))
        else:
            substitutions[person_id].append((time, 'on'))

    return substitutions


def calculate_player_minutes(cursor, pulseid: int) -> Dict[int, int]:
    """
    Calculate minutes played for each player in a match.

    Returns a dict mapping person_id to minutes played.
    """
    match_duration = get_match_duration(cursor, pulseid)
    substitutions = get_substitutions(cursor, pulseid)

    # Get all players who were in the squad
    cursor.execute("""
        SELECT person_id, is_starting, player_name
        FROM team_list
        WHERE pulseid = ?
    """, (pulseid,))

    player_minutes = {}

    for person_id, is_starting, player_name in cursor.fetchall():
        if is_starting == 1:
            # Player started - played from 0 until subbed off or end of match
            if person_id in substitutions:
                # Find when they came off
                off_events = [t for t, action in substitutions[person_id] if action == 'off']
                if off_events:
                    # Player was subbed off
                    time_off = off_events[0]
                    minutes_played = time_off / 60
                else:
                    # Shouldn't happen but handle it
                    minutes_played = match_duration / 60
            else:
                # Played full match
                minutes_played = match_duration / 60
        else:
            # Player was on bench
            if person_id in substitutions:
                on_events = [t for t, action in substitutions[person_id] if action == 'on']
                if on_events:
                    # Player came on as sub
                    time_on = on_events[0]

                    # Check if they were later subbed off
                    off_events = [t for t, action in substitutions[person_id] if action == 'off']
                    if off_events:
                        time_off = off_events[0]
                        minutes_played = (time_off - time_on) / 60
                    else:
                        # Played from sub time to end
                        minutes_played = (match_duration - time_on) / 60
                else:
                    # On bench but never used
                    minutes_played = 0
            else:
                # On bench but never used
                minutes_played = 0

        player_minutes[person_id] = minutes_played

    return player_minutes


def get_player_name(cursor, person_id: int) -> str:
    """Get player name from team_list table"""
    cursor.execute("""
        SELECT player_name
        FROM team_list
        WHERE person_id = ?
        LIMIT 1
    """, (person_id,))

    result = cursor.fetchone()
    return result[0] if result else f"Unknown Player {person_id}"


def analyze_season_minutes(cursor, season: str = "2025/2026", team_name: str = None):
    """
    Analyze player minutes for a season.

    Args:
        cursor: Database cursor
        season: Season string (e.g., "2025/2026")
        team_name: Optional team name to filter by
    """
    # Build query to get matches with pulse data
    query = """
        SELECT DISTINCT f.pulse_id, f.fixture_id, f.gameweek,
               ht.team_name as home_team, at.team_name as away_team
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE f.season = ?
        AND f.pulse_id IS NOT NULL
    """

    params = [season]

    if team_name:
        query += """ AND (ht.team_name LIKE ? OR at.team_name LIKE ?)"""
        params.extend([f"%{team_name}%", f"%{team_name}%"])

    query += " ORDER BY f.gameweek"

    cursor.execute(query, params)
    matches = cursor.fetchall()

    if not matches:
        print(f"No matches found with pulse data for season {season}")
        if team_name:
            print(f"(filtered by team: {team_name})")
        return

    print(f"\nAnalyzing {len(matches)} matches from {season} season")
    if team_name:
        print(f"Filtered by team: {team_name}")
    print("=" * 80)

    # Track total minutes per player
    total_minutes = defaultdict(float)
    appearances = defaultdict(int)
    starts = defaultdict(int)
    sub_appearances = defaultdict(int)

    # Process each match
    for pulse_id, fixture_id, gameweek, home_team, away_team in matches:
        player_minutes = calculate_player_minutes(cursor, pulse_id)

        # Get starting info
        cursor.execute("""
            SELECT person_id, is_starting
            FROM team_list
            WHERE pulseid = ?
        """, (pulse_id,))

        starting_info = {row[0]: row[1] for row in cursor.fetchall()}

        for person_id, minutes in player_minutes.items():
            total_minutes[person_id] += minutes

            if minutes > 0:
                appearances[person_id] += 1

                if starting_info.get(person_id) == 1:
                    starts[person_id] += 1
                else:
                    sub_appearances[person_id] += 1

    # Print results
    print("\nPLAYER MINUTES SUMMARY:")
    print("=" * 80)
    print(f"{'Player Name':<30} {'Minutes':<10} {'Apps':<6} {'Starts':<7} {'Sub':<5} {'Avg/Game':<10}")
    print("-" * 80)

    # Sort by total minutes (highest first)
    sorted_players = sorted(total_minutes.items(), key=lambda x: x[1], reverse=True)

    for person_id, minutes in sorted_players:
        player_name = get_player_name(cursor, person_id)
        apps = appearances[person_id]
        start_count = starts[person_id]
        sub_count = sub_appearances[person_id]
        avg_minutes = minutes / apps if apps > 0 else 0

        print(f"{player_name:<30} {minutes:>9.1f} {apps:>6} {start_count:>7} {sub_count:>5} {avg_minutes:>9.1f}")

    print("-" * 80)
    print(f"Total players: {len(sorted_players)}")
    print("=" * 80)


def analyze_player_game_by_game(cursor, player_name: str, season: str = "2025/2026"):
    """
    Analyze a specific player's minutes on a game-by-game basis.

    Args:
        cursor: Database cursor
        player_name: Player name to search for (case-insensitive partial match)
        season: Season string (e.g., "2025/2026")
    """
    # Find player(s) matching the name
    cursor.execute("""
        SELECT DISTINCT person_id, player_name
        FROM team_list
        WHERE LOWER(player_name) LIKE LOWER(?)
    """, (f"%{player_name}%",))

    matching_players = cursor.fetchall()

    if not matching_players:
        print(f"No players found matching: {player_name}")
        return

    if len(matching_players) > 1:
        print(f"Multiple players found matching '{player_name}':")
        for person_id, name in matching_players:
            print(f"  - {name}")
        print("\nPlease be more specific with the player name.")
        return

    person_id, full_player_name = matching_players[0]

    # Get all matches where this player appeared
    cursor.execute("""
        SELECT DISTINCT
            f.pulse_id,
            f.fixture_id,
            f.gameweek,
            f.kickoff_dttm,
            ht.team_name as home_team,
            at.team_name as away_team,
            tl.team_id as player_team_id,
            tl.is_starting,
            r.home_goals,
            r.away_goals
        FROM team_list tl
        JOIN fixtures f ON tl.pulseid = f.pulse_id
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE tl.person_id = ?
        AND f.season = ?
        ORDER BY f.gameweek
    """, (person_id, season))

    games = cursor.fetchall()

    if not games:
        print(f"No games found for {full_player_name} in {season} season")
        return

    # Get player's team name
    cursor.execute("""
        SELECT t.team_name
        FROM team_list tl
        JOIN teams t ON tl.team_id = t.team_id
        WHERE tl.person_id = ?
        LIMIT 1
    """, (person_id,))

    player_team = cursor.fetchone()[0]

    print(f"\n{'='*100}")
    print(f"GAME-BY-GAME ANALYSIS: {full_player_name} ({player_team})")
    print(f"Season: {season}")
    print(f"{'='*100}\n")

    print(f"{'GW':<4} {'Date':<12} {'Opponent':<25} {'Result':<8} {'Started':<8} {'Minutes':<8} {'Status':<20}")
    print("-" * 100)

    total_minutes = 0
    total_games = 0
    starts_count = 0
    sub_appearances = 0
    unused_sub = 0

    for pulse_id, fixture_id, gameweek, kickoff, home_team, away_team, player_team_id, is_starting, home_goals, away_goals in games:
        # Calculate minutes for this match
        player_minutes_dict = calculate_player_minutes(cursor, pulse_id)
        minutes_played = player_minutes_dict.get(person_id, 0)

        # Determine opponent
        if player_team_id == cursor.execute("SELECT team_id FROM teams WHERE team_name = ?", (home_team,)).fetchone()[0]:
            opponent = f"vs {away_team}"
        else:
            opponent = f"@ {home_team}"

        # Format result
        if home_goals is not None and away_goals is not None:
            result = f"{home_goals}-{away_goals}"
        else:
            result = "N/A"

        # Determine status
        started = "Yes" if is_starting == 1 else "No"

        if minutes_played == 0:
            status = "Unused substitute"
            unused_sub += 1
        elif is_starting == 1:
            if minutes_played >= 90:
                status = "Full match"
            else:
                status = f"Subbed off ({minutes_played:.0f}')"
            starts_count += 1
        else:
            status = f"Subbed on ({minutes_played:.0f}')"
            sub_appearances += 1

        # Format date
        date_str = kickoff[:10] if kickoff else "Unknown"

        print(f"{gameweek:<4} {date_str:<12} {opponent:<25} {result:<8} {started:<8} {minutes_played:>7.0f} {status:<20}")

        total_minutes += minutes_played
        if minutes_played > 0:
            total_games += 1

    print("-" * 100)
    print("\nSUMMARY:")
    print(f"  Total Appearances: {len(games)}")
    print(f"  Games Played: {total_games} (started: {starts_count}, sub: {sub_appearances}, unused: {unused_sub})")
    print(f"  Total Minutes: {total_minutes:.0f}")
    print(f"  Average Minutes per Appearance: {total_minutes/len(games):.1f}")
    print(f"  Average Minutes per Game Played: {total_minutes/total_games:.1f}" if total_games > 0 else "  Average Minutes per Game Played: N/A")
    print(f"{'='*100}\n")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze player minutes from pulse API data'
    )
    parser.add_argument('--season', type=str, default='2025/2026',
                       help='Season to analyze (default: 2025/2026)')
    parser.add_argument('--team', type=str, help='Filter by team name')
    parser.add_argument('--player', type=str, help='Show game-by-game minutes for specific player')
    parser.add_argument('--test', action='store_true',
                       help='Run test on single match')
    return parser.parse_args()


def test_single_match(cursor):
    """Test the calculation on a single match"""
    print("Testing on a single match...")
    print("=" * 80)

    # Get a match with substitutions
    cursor.execute("""
        SELECT f.pulse_id, f.gameweek, ht.team_name, at.team_name
        FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE f.pulse_id IS NOT NULL
        AND f.season = '2025/2026'
        LIMIT 1
    """)

    result = cursor.fetchone()
    if not result:
        print("No matches found with pulse data")
        return

    pulse_id, gameweek, home_team, away_team = result

    print(f"\nMatch: {home_team} vs {away_team} (Gameweek {gameweek})")
    print(f"PulseID: {pulse_id}")

    match_duration = get_match_duration(cursor, pulse_id)
    print(f"Match duration: {match_duration}s ({match_duration/60:.1f} minutes)")

    print("\n" + "-" * 80)
    print("PLAYER MINUTES:")
    print("-" * 80)

    player_minutes = calculate_player_minutes(cursor, pulse_id)

    # Get team info for each player
    cursor.execute("""
        SELECT tl.person_id, tl.player_name, tl.is_starting, tl.position, t.team_name
        FROM team_list tl
        JOIN teams t ON tl.team_id = t.team_id
        WHERE tl.pulseid = ?
        ORDER BY t.team_name, tl.is_starting DESC, tl.position
    """, (pulse_id,))

    current_team = None
    for person_id, player_name, is_starting, position, team_name in cursor.fetchall():
        if team_name != current_team:
            print(f"\n{team_name}:")
            current_team = team_name

        minutes = player_minutes.get(person_id, 0)
        status = "Started" if is_starting == 1 else "Bench"

        print(f"  {player_name:<25} {position:<2} {status:<8} {minutes:>6.1f} mins")


def main():
    """Main function"""
    args = parse_arguments()

    conn = setup_database_connection()
    cursor = conn.cursor()

    try:
        if args.test:
            test_single_match(cursor)
        elif args.player:
            analyze_player_game_by_game(cursor, args.player, args.season)
        else:
            analyze_season_minutes(cursor, args.season, args.team)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
