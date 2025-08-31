import sqlite3
import requests
import time
import json
import os
import random

CACHE_EXPIRY = 86400
LEAGUE_ID = 300076

# Connect to SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect("fpl_players.db")
cursor = conn.cursor()


def fetch_bootstrap():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    data = response.json()
    return data


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
def add_to_datbase(players, position_dict):
    conn = sqlite3.connect("fpl_players.db")
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
        form TEXT,
        team_code INTEGER,
        minutes INTEGER,
        goals_scored INTEGER,
        assists INTEGER,
        clean_sheets INTEGER,
        goals_conceded INTEGER,
        bonus INTEGER,
        bps INTEGER
    )
    """
    )

    # Insert player data into the database
    for player in players:
        player_position = position_dict[player["element_type"]]
        cursor.execute(
            """
        INSERT OR REPLACE INTO players (
            id, first_name, second_name, web_name, position, total_points,
            chance_of_playing_this_round, chance_of_playing_next_round, now_cost,
            selected_by_percent, points_per_game, form, team_code, minutes,
            goals_scored, assists, clean_sheets, goals_conceded, bonus, bps
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                player["team_code"],
                player["minutes"],
                player["goals_scored"],
                player["assists"],
                player["clean_sheets"],
                player["goals_conceded"],
                player["bonus"],
                player["bps"],
            ),
        )

    # Commit changes and close the connection
    conn.commit()
    conn.close()


def fetch_players(position, pts):
    conn = sqlite3.connect("fpl_players.db")
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
    conn = sqlite3.connect("fpl_players.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, web_name, position FROM players WHERE total_points = ?",
        (pts,),
    )
    players = cursor.fetchall()
    conn.close()
    return players


def find_if_user_has_player(player, user_data_json):
    users = []
    for user, team in user_data_json.items():
        for players in team["picks"]:
            if players["element"] == player:
                users.append(user)
    return users


def get_players_data(player_id):
    conn = sqlite3.connect("fpl_players.db")
    cursor = conn.cursor()
    cursor.execute("SELECT web_name, position FROM players WHERE id = ?", (player_id,))
    player_data = cursor.fetchone()
    conn.close()
    return player_data


if __name__ == "__main__":
    bootstrap_data = load_cache("bootstrap_cache.json")
    if bootstrap_data is None:
        bootstrap_data = fetch_bootstrap()
        save_cache(bootstrap_data, "bootstrap_cache.json")

    current_gameweek = fetch_current_gameweek(bootstrap_data)

    players = bootstrap_data["elements"]
    positions = bootstrap_data["element_types"]
    positions_dict = {
        position["id"]: position["singular_name_short"] for position in positions
    }
    add_to_datbase(players, positions_dict)

    league_data = load_cache("league_cache.json")
    if league_data is None:
        league_data = fetch_league_data(LEAGUE_ID)
        save_cache(league_data, "league_cache.json")

    users_id_list = []
    for user in league_data["standings"]["results"]:
        users_id_list.append((user["player_name"], user["entry"]))

    user_data = load_cache("user_cache.json")
    if user_data is None:
        user_data_json = {}
        for user in users_id_list:
            user_data_json[user[1]] = fetch_user_data(user, current_gameweek)
        save_cache(user_data_json, "user_cache.json")
        user_data = user_data_json

    position_required = input("Enter the position you want to find: ")
    position_required = position_required.upper()

    final_dict = {}
    players = fetch_players(position_required, 0)
    players_id_list = [player[0] for player in players]

    random_player_pick = random.choice(players)
    print("Random player picked:", random_player_pick[1])

    final_dict[random_player_pick[0]] = find_if_user_has_player(
        random_player_pick[0], user_data
    )

    if len(final_dict[random_player_pick[0]]) == 0:
        print("No one has this player in their team.")
    elif len(final_dict[random_player_pick[0]]) > 1:
        winner = random.choice(final_dict[random_player_pick[1]])
    else:
        winner = final_dict[random_player_pick[0]][0]
        print(user_data[winner]["player_name"])

    all_player_dict = {}
    all_players = fetch_all_players(0)
    for player in all_players:
        all_player_dict[player[0]] = find_if_user_has_player(player[0], user_data)

    defenders = 0
    midfielders = 0
    attackers = 0
    goalkeepers = 0

    for player in all_player_dict:
        if len(all_player_dict[player]) > 1:
            player_name = get_players_data(player)[0]
            print(f"{player_name} has more than one user.")
        if len(all_player_dict[player]) == 1:
            pos = get_players_data(player)[1]
            if pos == "DEF":
                defenders += 1
            elif pos == "MID":
                midfielders += 1
            elif pos == "FWD":
                attackers += 1
            elif pos == "GKP":
                goalkeepers += 1

    print("The number of possible players held in the league with 0 points.")
    print(
        f"Goalkeepers: {goalkeepers} Defenders: {defenders} Midfielders: {midfielders} Attackers: {attackers}"
    )

    print("Players with 0 points and who in the league have them.")

    all_players_list = []
    for player in all_player_dict:
        if len(all_player_dict[player]) == 0:
            player_name = get_players_data(player)[0]
            all_players_list.append([player_name, get_players_data(player)[1], None])
        else:
            users_names = []
            for user in all_player_dict[player]:
                users_names.append(user_data[user]["player_name"])
            all_players_list.append(
                [get_players_data(player)[0], get_players_data(player)[1], users_names]
            )
    all_players_list_sorted = sorted(all_players_list, key=lambda player: player[0])

    print("\n")
    print("Goalkeepers:")
    for player in all_players_list_sorted:
        if player[1] == "GKP":
            if player[2] is not None:
                print(f"{player[0]} - Users: {', '.join(player[2])}")
            else:
                print(f"{player[0]} - Users: NA")

    print("\n")
    print("Defenders:")
    for player in all_players_list:
        if player[1] == "DEF":
            if player[2] is not None:
                print(f"{player[0]} - Users: {', '.join(player[2])}")
            else:
                print(f"{player[0]} - Users: NA")

    print("\n")
    print("Midfielders:")
    for player in all_players_list:
        if player[1] == "MID":
            if player[2] is not None:
                print(f"{player[0]} - Users: {', '.join(player[2])}")
            else:
                print(f"{player[0]} - Users: NA")

    print("\n")
    print("Fowards:")
    for player in all_players_list:
        if player[1] == "FWD":
            if player[2] is not None:
                print(f"{player[0]} - Users: {', '.join(player[2])}")
            else:
                print(f"{player[0]} - Users: NA")

    # Dictionary to store the count of each user
    user_count = {}

    # Iterate over all players
    for player in all_players_list:
        # Check if player[2] is not None
        if player[2] is not None:
            for user in player[2]:
                # Increment the user's count in the dictionary
                if user in user_count:
                    user_count[user] += 1
                else:
                    user_count[user] = 1

    sorted_user_count = sorted(user_count.items(), key=lambda x: x[1], reverse=True)

    # After counting and sorting, print the occurrences
    print("\nUser appearances (sorted by count):")
    for user, count in sorted_user_count:
        print(f"{user}: {count}")
