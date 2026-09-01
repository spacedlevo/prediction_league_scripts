#!/usr/bin/env python3
"""
Generate the knockout cup competition bracket for a season.

Reads active player standings from the local SQLite database, seeds players by
league position, then creates cup_config and cup_matches rows covering gameweeks
from (38 - num_rounds + 1) through 38. Bottom seeds receive first-round byes.

Usage:
    python scripts/cup/generate_cup_bracket.py
    python scripts/cup/generate_cup_bracket.py --season 2025/2026
    python scripts/cup/generate_cup_bracket.py --season 2025/2026 --force
"""

import sys
import math
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from config import CURRENT_SEASON

END_GAMEWEEK = 38


def get_league_standings(cursor, season):
    """Return active players ordered by total season points (best first)."""
    cursor.execute("""
        SELECT
            p.player_id,
            p.player_name,
            p.web_name,
            COALESCE(
                COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END) +
                COUNT(CASE WHEN pred.home_goals = r.home_goals
                                AND pred.away_goals = r.away_goals THEN 1 END),
                0
            ) AS total_points,
            COALESCE(
                COUNT(CASE WHEN pred.predicted_result = r.result THEN 1 END), 0
            ) AS correct_results,
            COALESCE(
                COUNT(CASE WHEN pred.home_goals = r.home_goals
                                AND pred.away_goals = r.away_goals THEN 1 END), 0
            ) AS correct_scores
        FROM players p
        LEFT JOIN predictions pred ON p.player_id = pred.player_id
        LEFT JOIN fixtures f ON pred.fixture_id = f.fixture_id AND f.season = ?
        LEFT JOIN results r ON f.fixture_id = r.fixture_id
        WHERE p.active = 1 AND p.pundit = 0
        GROUP BY p.player_id, p.player_name, p.web_name
        ORDER BY total_points DESC, correct_results DESC, correct_scores DESC
    """, (season,))
    return [dict(row) for row in cursor.fetchall()]


def create_cup_tables(cursor):
    """Create cup_config and cup_matches tables if they don't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cup_config (
            config_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            season         TEXT    NOT NULL,
            num_rounds     INTEGER NOT NULL,
            start_gameweek INTEGER NOT NULL,
            generated_at   DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cup_matches (
            match_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            season          TEXT    NOT NULL,
            round_number    INTEGER NOT NULL,
            match_number    INTEGER NOT NULL,
            player1_id      INTEGER,
            player2_id      INTEGER,
            player1_seed    INTEGER,
            player2_seed    INTEGER,
            is_bye          INTEGER NOT NULL DEFAULT 0,
            gameweek        INTEGER NOT NULL,
            next_match_id   INTEGER,
            next_match_slot INTEGER
        )
    """)


def generate_bracket_structure(players, season):
    """
    Build the full bracket as a list of match dicts.

    Returns (matches, num_rounds, start_gameweek).

    Seeding: seed 1 = best player (top of league table).
    Bottom seeds (worst performers) receive first-round byes.

    Round 1 pairings for active (non-bye) seeds: top vs bottom of the active group,
    e.g. seed 1 vs seed N_active, seed 2 vs seed N_active-1, etc.
    """
    n = len(players)
    if n < 2:
        raise ValueError(f"Need at least 2 active players, got {n}")

    num_rounds = math.ceil(math.log2(n))
    bracket_size = 2 ** num_rounds
    num_byes = bracket_size - n
    start_gw = END_GAMEWEEK - num_rounds + 1

    # num_active is always even (see plan for proof)
    num_active = n - num_byes
    active_players = players[:num_active]   # top seeds — play round 1
    bye_players = players[num_active:]      # bottom seeds — skip to round 2

    # --- Build all match slot skeletons for every round ---
    # Slot count per round: bracket_size / 2^round
    # (round 1 = bracket_size/2 slots, final = 1 slot)
    # We assign temporary sequential IDs; we'll replace them with DB rowids later.

    temp_id = 0

    def next_temp_id():
        nonlocal temp_id
        temp_id += 1
        return temp_id

    pos_to_match = {}  # (round, slot) → match dict

    for rnd in range(1, num_rounds + 1):
        slots = bracket_size // (2 ** rnd)
        gw = start_gw + rnd - 1
        for slot in range(1, slots + 1):
            pos_to_match[(rnd, slot)] = {
                "_temp_id":     next_temp_id(),
                "season":       season,
                "round_number": rnd,
                "match_number": slot,
                "player1_id":   None,
                "player2_id":   None,
                "player1_seed": None,
                "player2_seed": None,
                "is_bye":       0,
                "gameweek":     gw,
                # These reference _temp_id values; resolved after insert
                "_next_temp_id":   None,
                "_next_slot":      None,
            }

    # --- Wire up next_match links (standard bracket: match N feeds ceil(N/2) in next round) ---
    for rnd in range(1, num_rounds):
        slots = bracket_size // (2 ** rnd)
        for slot in range(1, slots + 1):
            next_slot = (slot + 1) // 2
            current = pos_to_match[(rnd, slot)]
            current["_next_temp_id"] = pos_to_match[(rnd + 1, next_slot)]["_temp_id"]
            current["_next_slot"] = 1 if slot % 2 == 1 else 2

    # --- Populate round 1 player assignments ---
    # Real matches: top vs bottom within the active group
    real_match_count = num_active // 2
    for i in range(real_match_count):
        slot = i + 1
        p1 = active_players[i]
        p2 = active_players[num_active - 1 - i]
        m = pos_to_match[(1, slot)]
        m["player1_id"]   = p1["player_id"]
        m["player2_id"]   = p2["player_id"]
        m["player1_seed"] = i + 1
        m["player2_seed"] = num_active - i

    # Bye matches: one per bye player, in slots after the real matches
    for i, bye_p in enumerate(bye_players):
        slot = real_match_count + 1 + i
        m = pos_to_match[(1, slot)]
        m["player1_id"]   = bye_p["player_id"]
        m["player2_id"]   = None
        m["player1_seed"] = num_active + i + 1
        m["player2_seed"] = None
        m["is_bye"]       = 1

    return list(pos_to_match.values()), num_rounds, start_gw


def insert_bracket(cursor, config_data, matches):
    """Insert cup_config and all cup_matches rows, resolving next_match_id."""
    # Insert config
    cursor.execute("""
        INSERT INTO cup_config (season, num_rounds, start_gameweek, generated_at)
        VALUES (?, ?, ?, ?)
    """, (
        config_data["season"],
        config_data["num_rounds"],
        config_data["start_gameweek"],
        config_data["generated_at"],
    ))

    # First pass: insert all matches (next_match_id = NULL for now)
    temp_id_to_rowid = {}
    for m in matches:
        cursor.execute("""
            INSERT INTO cup_matches
                (season, round_number, match_number, player1_id, player2_id,
                 player1_seed, player2_seed, is_bye, gameweek, next_match_id, next_match_slot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """, (
            m["season"], m["round_number"], m["match_number"],
            m["player1_id"], m["player2_id"],
            m["player1_seed"], m["player2_seed"],
            m["is_bye"], m["gameweek"],
            m["_next_slot"],
        ))
        temp_id_to_rowid[m["_temp_id"]] = cursor.lastrowid

    # Second pass: update next_match_id using real DB rowids
    for m in matches:
        if m["_next_temp_id"] is not None:
            real_id = temp_id_to_rowid[m["_temp_id"]]
            real_next_id = temp_id_to_rowid[m["_next_temp_id"]]
            cursor.execute(
                "UPDATE cup_matches SET next_match_id = ? WHERE match_id = ?",
                (real_next_id, real_id),
            )


def update_last_update(cursor, table_names):
    """Update last_update table to trigger automatic MySQL sync."""
    now = datetime.now()
    ts = now.timestamp()
    fmt = now.strftime("%d-%m-%Y %H:%M:%S")
    for name in table_names:
        cursor.execute("""
            INSERT OR REPLACE INTO last_update (table_name, updated, timestamp)
            VALUES (?, ?, ?)
        """, (name, fmt, ts))


def main():
    parser = argparse.ArgumentParser(description="Generate cup competition bracket")
    parser.add_argument(
        "--season", default=CURRENT_SEASON,
        help=f"Season string, e.g. 2025/2026 (default: {CURRENT_SEASON})"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Delete and regenerate if a bracket for this season already exists"
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        create_cup_tables(cursor)
        conn.commit()

        # Guard against duplicate generation
        cursor.execute(
            "SELECT config_id, generated_at FROM cup_config WHERE season = ?",
            (args.season,)
        )
        existing = cursor.fetchone()
        if existing:
            if not args.force:
                print(
                    f"Cup bracket for {args.season} already exists "
                    f"(generated {existing['generated_at']}).\n"
                    "Use --force to delete and regenerate."
                )
                sys.exit(0)
            print(f"--force: deleting existing bracket for {args.season}...")
            cursor.execute("DELETE FROM cup_matches WHERE season = ?", (args.season,))
            cursor.execute("DELETE FROM cup_config  WHERE season = ?", (args.season,))
            conn.commit()

        # Fetch standings
        print(f"Fetching standings for season {args.season}...")
        players = get_league_standings(cursor, args.season)

        if not players:
            print(f"ERROR: No active players found for season {args.season}.")
            sys.exit(1)

        print(f"\nActive players ({len(players)}):")
        for i, p in enumerate(players, 1):
            print(f"  {i:2}. {p['player_name']:<25}  {p['total_points']} pts")

        # Generate bracket
        matches, num_rounds, start_gw = generate_bracket_structure(players, args.season)

        n = len(players)
        bracket_size = 2 ** num_rounds
        num_byes = bracket_size - n
        num_active = n - num_byes
        bye_players = players[num_active:]

        print(f"\nBracket:")
        print(f"  Rounds:     {num_rounds}  ({round_name(1, num_rounds)} through Final)")
        print(f"  Gameweeks:  GW{start_gw}–GW{END_GAMEWEEK}")
        print(f"  Byes ({num_byes}):   {', '.join(p['player_name'] for p in bye_players)}")

        # Insert
        config_data = {
            "season":         args.season,
            "num_rounds":     num_rounds,
            "start_gameweek": start_gw,
            "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        insert_bracket(cursor, config_data, matches)
        update_last_update(cursor, ["cup_config", "cup_matches"])
        conn.commit()

        print(f"\nDone — {len(matches)} match records inserted.")
        print("Run mysql_sync.py --full-sync to push to PythonAnywhere.")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


def round_name(round_number, num_rounds):
    """Return display name for a round given its position from the final."""
    rounds_from_final = num_rounds - round_number
    if rounds_from_final == 0:
        return "Final"
    if rounds_from_final == 1:
        return "Semi-Final"
    if rounds_from_final == 2:
        return "Quarter-Final"
    players_in_round = 2 ** (rounds_from_final + 1)
    return f"Round of {players_in_round}"


if __name__ == "__main__":
    main()
