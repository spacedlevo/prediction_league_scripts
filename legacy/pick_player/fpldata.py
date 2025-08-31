import sqlite3
import requests
import time
import json
import os

CACHE_EXPIRY = 43200
LEAGUE_ID = 300076
USER_ID = 20852

# Connect to SQLite database (or create it if it doesn't exist)
db_loc = "/home/levo/Documents/projects/pick_player/fpl_players.db"
bootstrap_loc = "/home/levo/Documents/projects/pick_player/bootstrap_cache.json"
fixture_loc = "/home/levo/Documents/projects/pick_player/fixtures_cache.json"
conn = sqlite3.connect(db_loc)
cursor = conn.cursor()


def fetch_bootstrap(data_required):
    if data_required == "bootstrap":
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    elif data_required == "fixtures":
        url = "https://fantasy.premierleague.com/api/fixtures/"
    response = requests.get(url)
    data = response.json()
    return data


def get_user_team(user_id, current_gameweek):
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{current_gameweek}/picks/"
    response = requests.get(url)
    data = response.json()
    player_ids = [pick["element"] for pick in data["picks"]]
    return player_ids


def fetch_league_data(league_id):
    url = (
        f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    )
    response = requests.get(url)
    data = response.json()
    return data


def fetch_current_gameweek(bootstrap_data):
    for event in bootstrap_data["events"]:
        if event["is_current"]:
            return event["id"]


def fetch_user_data(user, current_gameweek):
    user_id = user[1]
    url = f"https://fantasy.premierleague.com/api/entry/{user_id}/event/{current_gameweek}/picks/"
    response = requests.get(url)
    data = response.json()
    data["player_name"] = user[0]
    return data


def load_cache(cache_name):
    if os.path.exists(cache_name):
        cache_mtime = os.path.getmtime(cache_name)
        if time.time() - cache_mtime < CACHE_EXPIRY:
            with open(cache_name, "r") as f:
                return json.load(f)
    return None


def save_cache(data, cache_name):
    with open(cache_name, "w") as f:
        json.dump(data, f)


# Create table for players
def add_to_datbase(players, position_dict, myteam):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY,
        first_name TEXT,
        second_name TEXT,
        web_name TEXT,
        position TEXT,
        total_points INTEGER,
        chance_of_playing_this_round INTEGER,
        chance_of_playing_next_round INTEGER,
        now_cost INTEGER,
        selected_by_percent TEXT,
        points_per_game TEXT,
        form REAL,
        team INTEGER,
        team_code INTEGER,
        minutes INTEGER,
        expected_goals REAL,
        expected_assists REAL,
        expected_goal_involvement REAL,
        expected_goals_conceded REAL,
        expected_goals_per_90 INTEGER,
        saves_per_90 INTEGER,
        expected_assists_per_90 INTEGER,
        expected_goal_involvement_per_90 INTEGER,
        expected_goals_conceded_per_90 INTEGER,
        clean_sheets_per_90 INTEGER,
        goals_scored INTEGER,
        assists INTEGER,
        clean_sheets INTEGER,
        goals_conceded INTEGER,
        bonus INTEGER,
        bps INTEGER,
        influence INTEGER,
        creativity INTEGER,
        threat INTEGER,
        starts INTEGER,
        ict_index INTEGER,
        yellow_cards INTEGER,
        red_cards INTEGER,
        in_team BOOLEAN DEFAULT FALSE

    )
    """
    )

    # Insert player data into the database
    for player in players:
        in_team = player["id"] in [p for p in myteam]
        player_position = position_dict[player["element_type"]]
        if player.get("chance_of_playing_next_round", 100) is None:
            player["chance_of_playing_next_round"] = 100
        if player.get("chance_of_playing_this_round", 100) is None:
            player["chance_of_playing_this_round"] = 100
        cursor.execute(
            """
        INSERT OR REPLACE INTO players (
            id, first_name, second_name, web_name, position, total_points,
            chance_of_playing_this_round, chance_of_playing_next_round, now_cost,
            selected_by_percent, points_per_game, form, team, team_code, minutes,
            expected_goals, expected_assists, expected_goal_involvement,
            expected_goals_conceded, expected_goals_per_90, saves_per_90,
            expected_assists_per_90, expected_goal_involvement_per_90,
            expected_goals_conceded_per_90, clean_sheets_per_90,
            goals_scored, assists, clean_sheets, goals_conceded, bonus, bps,
            influence, creativity, threat, starts, ict_index, yellow_cards,
            red_cards, in_team
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                player["id"],
                player["first_name"],
                player["second_name"],
                player["web_name"],
                player_position,
                player["total_points"],
                player.get("chance_of_playing_this_round", 100),
                player.get("chance_of_playing_next_round", 100),
                player["now_cost"],
                player["selected_by_percent"],
                player["points_per_game"],
                player["form"],
                player["team"],
                player["team_code"],
                player["minutes"],
                player["expected_goals"],
                player["expected_assists"],
                player["expected_goal_involvements"],
                player["expected_goals_conceded"],
                player["expected_goals_per_90"],
                player["saves_per_90"],
                player["expected_assists_per_90"],
                player["expected_goal_involvements_per_90"],
                player["expected_goals_conceded_per_90"],
                player["clean_sheets_per_90"],
                player["goals_scored"],
                player["assists"],
                player["clean_sheets"],
                player["goals_conceded"],
                player["bonus"],
                player["bps"],
                player["influence"],
                player["creativity"],
                player["threat"],
                player["starts"],
                player["ict_index"],
                player["yellow_cards"],
                player["red_cards"],
                True if in_team else False,
            ),
        )

    # Commit changes and close the connection
    conn.commit()
    conn.close()


def fetch_players(position, pts):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, web_name FROM players WHERE total_points = ? AND position = ?",
        (
            pts,
            position,
        ),
    )
    players = cursor.fetchall()
    conn.close()
    return players


def fetch_all_players(pts):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, web_name, position FROM players WHERE total_points = ?",
        (pts,),
    )
    players = cursor.fetchall()
    conn.close()
    return players


def get_players_data(player_id):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute("SELECT web_name, position FROM players WHERE id = ?", (player_id,))
    player_data = cursor.fetchone()
    conn.close()
    return player_data


def add_teams_to_database(teams):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER NOT NULL, 
            team_name TEXT, 
            unavailable BOOLEAN,
            strength INTEGER,
            strength_overall_home INTEGER,
            strength_overall_away INTEGER,
            strength_attack_home INTEGER,
            strength_attack_away INTEGER,
            strength_defence_home INTEGER,
            strength_defence_away INTEGER,
            PRIMARY KEY (team_id)
        )
        """
    )

    for team in teams:
        cursor.execute(
            """
            INSERT OR REPLACE INTO teams (
                team_id, team_name, unavailable, strength, strength_overall_home,
                strength_overall_away, strength_attack_home, strength_attack_away,
                strength_defence_home, strength_defence_away
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team["id"],
                team["name"],
                team["unavailable"],
                team["strength"],
                team["strength_overall_home"],
                team["strength_overall_away"],
                team["strength_attack_home"],
                team["strength_attack_away"],
                team["strength_defence_home"],
                team["strength_defence_away"],
            ),
        )

    conn.commit()
    conn.close()


def add_fixtures_to_database(fixtures, season):
    conn = sqlite3.connect(db_loc)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id INTEGER NOT NULL, 
            kickoff_dttm DATETIME, 
            gameweek INTEGER, 
            home_teamid INTEGER NOT NULL, 
            away_teamid INTEGER NOT NULL, 
            finished BOOLEAN, 
            season TEXT,
            PRIMARY KEY (fixture_id, season), 
            UNIQUE (fixture_id, season)
        )
        """
    )

    for fixture in fixtures:
        cursor.execute(
            """
            INSERT OR REPLACE INTO fixtures (
                fixture_id, kickoff_dttm, gameweek, home_teamid, away_teamid, finished, season
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture["id"],
                fixture["kickoff_time"],
                fixture["event"],
                fixture["team_h"],
                fixture["team_a"],
                fixture["finished"],
                season,
            ),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    bootstrap_data = load_cache(bootstrap_loc)
    fixtures = load_cache(fixture_loc)
    if bootstrap_data is None:
        bootstrap_data = fetch_bootstrap("bootstrap")
        save_cache(bootstrap_data, bootstrap_loc)
    if fixtures is None:
        fixtures = fetch_bootstrap("fixtures")
        save_cache(fixtures, fixture_loc)

    current_gameweek = fetch_current_gameweek(bootstrap_data)

    players = bootstrap_data["elements"]
    positions = bootstrap_data["element_types"]
    teams = bootstrap_data["teams"]
    positions_dict = {
        position["id"]: position["singular_name_short"] for position in positions
    }
    add_teams_to_database(teams)
    add_fixtures_to_database(fixtures, "2024/25")
    add_to_datbase(players, positions_dict, get_user_team(USER_ID, current_gameweek))
    print("database updated")
