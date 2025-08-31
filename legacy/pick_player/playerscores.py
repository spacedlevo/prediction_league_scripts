import requests
import sqlite3
import time
import logging
from random import random
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    filename="/home/levo/Documents/projects/pick_player/playerscores.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def get_player_scores():
    base_url = "https://fantasy.premierleague.com/api/"
    players_url = f"{base_url}bootstrap-static/"
    response = requests.get(players_url)
    data = response.json()

    players = data["elements"]
    player_scores = []

    for player in tqdm(players):
        player_id = player["id"]
        player_name = player["web_name"]
        history_url = f"{base_url}element-summary/{player_id}/"
        time.sleep(random() * 2)
        history_response = requests.get(history_url)
        history_data = history_response.json()

        for gameweek in history_data["history"]:
            player_scores.append(
                {
                    "player_name": player_name,
                    "gameweek": gameweek["round"],
                    "player_id": player_id,
                    "total_points": gameweek["total_points"],
                    "fixture": gameweek["fixture"],
                    "was_home": gameweek["was_home"],
                    "minutes": gameweek["minutes"],
                    "goals_scored": gameweek["goals_scored"],
                    "assists": gameweek["assists"],
                    "clean_sheets": gameweek["clean_sheets"],
                    "goals_conceded": gameweek["goals_conceded"],
                    "own_goals": gameweek["own_goals"],
                    "penalties_saved": gameweek["penalties_saved"],
                    "penalties_missed": gameweek["penalties_missed"],
                    "yellow_cards": gameweek["yellow_cards"],
                    "red_cards": gameweek["red_cards"],
                    "saves": gameweek["saves"],
                    "bonus": gameweek["bonus"],
                    "bps": gameweek["bps"],
                    "influence": gameweek["influence"],
                    "creativity": gameweek["creativity"],
                    "threat": gameweek["threat"],
                    "ict_index": gameweek["ict_index"],
                    "starts": gameweek["starts"],
                    "expected_goals": gameweek["expected_goals"],
                    "expected_assists": gameweek["expected_assists"],
                    "expected_goal_involvements": gameweek[
                        "expected_goal_involvements"
                    ],
                    "expected_goals_conceded": gameweek["expected_goals_conceded"],
                    "value": gameweek["value"],
                    "transfers_balance": gameweek["transfers_balance"],
                    "selected": gameweek["selected"],
                    "transfers_in": gameweek["transfers_in"],
                    "transfers_out": gameweek["transfers_out"],
                }
            )

    return player_scores


if __name__ == "__main__":
    try:
        logging.info("Starting to download player scores.")
        scores = get_player_scores()
        logging.info("Player scores downloaded successfully.")

        # Connect to the database (or create it if it doesn't exist)
        conn = sqlite3.connect(
            "/home/levo/Documents/projects/pick_player/fpl_players.db"
        )
        cursor = conn.cursor()

        # Create the table if it doesn't exist
        cursor.execute("DROP TABLE IF EXISTS player_scores")
        conn.commit()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS player_scores (
                player_name TEXT,
                gameweek INTEGER,
                player_id INTEGER,
                total_points INTEGER,
                fixture INTEGER,
                was_home BOOLEAN,
                minutes INTEGER,
                goals_scored INTEGER,
                assists INTEGER,
                clean_sheets INTEGER,
                goals_conceded INTEGER,
                own_goals INTEGER,
                penalties_saved INTEGER,
                penalties_missed INTEGER,
                yellow_cards INTEGER,
                red_cards INTEGER,
                saves INTEGER,
                bonus INTEGER,
                bps INTEGER,
                influence REAL,
                creativity REAL,
                threat REAL,
                ict_index REAL,
                starts INTEGER,
                expected_goals REAL,
                expected_assists REAL,
                expected_goal_involvements REAL,
                expected_goals_conceded REAL,
                value INTEGER,
                transfers_balance INTEGER,
                selected INTEGER,
                transfers_in INTEGER,
                transfers_out INTEGER
            )
            """
        )

        # Insert the player scores into the table
        for score in scores:
            cursor.execute(
                """
                INSERT INTO player_scores (
                    player_name, gameweek, player_id, total_points, fixture, was_home, minutes, 
                    goals_scored, assists, clean_sheets, goals_conceded, own_goals, penalties_saved, 
                    penalties_missed, yellow_cards, red_cards, saves, bonus, bps, influence, 
                    creativity, threat, ict_index, starts, expected_goals, expected_assists, 
                    expected_goal_involvements, expected_goals_conceded, value, transfers_balance, 
                    selected, transfers_in, transfers_out
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    score["player_name"],
                    score["gameweek"],
                    score["player_id"],
                    score["total_points"],
                    score["fixture"],
                    score["was_home"],
                    score["minutes"],
                    score["goals_scored"],
                    score["assists"],
                    score["clean_sheets"],
                    score["goals_conceded"],
                    score["own_goals"],
                    score["penalties_saved"],
                    score["penalties_missed"],
                    score["yellow_cards"],
                    score["red_cards"],
                    score["saves"],
                    score["bonus"],
                    score["bps"],
                    score["influence"],
                    score["creativity"],
                    score["threat"],
                    score["ict_index"],
                    score["starts"],
                    score["expected_goals"],
                    score["expected_assists"],
                    score["expected_goal_involvements"],
                    score["expected_goals_conceded"],
                    score["value"],
                    score["transfers_balance"],
                    score["selected"],
                    score["transfers_in"],
                    score["transfers_out"],
                ),
            )

        # Commit the transaction and close the connection
        conn.commit()
        conn.close()
        logging.info("Player scores stored in the database successfully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
