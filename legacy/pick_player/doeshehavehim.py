import requests
import sys

response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
data = response.json()
current_gameweek = next(event["id"] for event in data["events"] if event["is_current"])


def get_player_id(player_name):
    response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
    players = response.json()["elements"]
    for player in players:
        if player_name.lower() in player["web_name"].lower():
            return player["id"]
    return None


def get_league_managers(league_id):
    response = requests.get(
        f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    )
    managers = response.json()["standings"]["results"]
    return managers


def get_manager_team(manager_id):
    response = requests.get(
        f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{current_gameweek}/picks/"
    )
    team = response.json()["picks"]
    return team


def main(player_name, league_id):
    player_id = get_player_id(player_name)
    if not player_id:
        print(f"Player {player_name} not found.")
        return

    managers = get_league_managers(league_id)
    managers_with_player = []

    for manager in managers:
        manager_id = manager["entry"]
        team = get_manager_team(manager_id)
        for player in team:
            if player["element"] == player_id:
                managers_with_player.append(manager["player_name"])
                break

    with open("managers_with_player.txt", "w") as file:
        for manager in managers_with_player:
            file.write(f"{manager}\n")

    print(
        f"List of managers with {player_name} has been written to managers_with_player.txt"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python doeshehavehim.py <player_name> <league_id>")
    else:
        player_name = sys.argv[1]
        league_id = sys.argv[2]
        main(player_name, league_id)
