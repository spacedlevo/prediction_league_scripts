import re
import csv
from collections import Counter
import sqlite3
from datetime import datetime
import os
import subprocess
import logging

db = sqlite3.connect("/home/levo/Documents/projects/prediction_league/data/database.db")
c = db.cursor()

logging.basicConfig(
    filename="/home/levo/Documents/projects/prediction_league/logs/clean_predictions.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logging.info("Starting the prediction cleaning process")

teams_names = {}
season = "2025_26"
seasondb = "2025/2026"


def updated():
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y. %H:%M:%S")
    timestamp = dt.timestamp()
    c.execute(
        """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
           VALUES ('cleaned_predictions', ?, ?)""",
        (now, timestamp),
    )
    db.commit()


predictions_dir = f"/home/levo/Dropbox/Predictions/{season}/"
c.execute("SELECT team_name FROM teams")
teams = [team[0].lower() for team in c.fetchall()]
c.execute("SELECT player_name FROM players WHERE active = 1")
players = [player[0] for player in c.fetchall()]
fixtures_ids = fixtures_ids = c.execute(
    "SELECT fixture_id FROM fixtures WHERE gameweek",
).fetchall()
fixture_len = len(fixtures_ids)
header = ["gameweek", "player", "home_team", "away_team", "home_goals", "away_goals"]


def create_meta_table():
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS file_metadata (
            filename TEXT PRIMARY KEY,
            last_modified TIMESTAMP
        )
        """
    )


def get_file_metadata(file_path):
    file_name = os.path.basename(file_path)
    last_modified = os.path.getmtime(file_path)
    return file_name, last_modified


def is_file_modified(file_path):
    file_name, last_modified = get_file_metadata(file_path)
    c.execute(
        """
        SELECT last_modified FROM file_metadata WHERE filename = ?
        """,
        (file_name,),
    )
    result = c.fetchone()
    if result is None:
        logging.info(f"File {file_name} is new and will be processed")
        return True
    elif last_modified > result[0]:
        logging.info(f"File {file_name} has been modified and will be processed")
        return True
    else:
        logging.info(f"File {file_name} has not been modified")
        return False


def insert_file_metadata(file_path):
    file_name, last_modified = get_file_metadata(file_path)
    try:
        c.execute(
            """
            INSERT INTO file_metadata (filename, last_modified)
            VALUES (?, ?)
            ON CONFLICT(filename) DO UPDATE SET last_modified=excluded.last_modified
            """,
            (file_name, last_modified),
        )
        db.commit()
        logging.info(f"Inserted/Updated metadata for file {file_name}")
    except Exception as e:
        logging.error(f"Failed to insert/update metadata for file {file_name}: {e}")


def find_scores(line):
    goals = []
    current_score = ""
    for char in line:
        if char.isdigit():
            current_score += char
        elif current_score:
            goals.append(int(current_score))
            current_score = ""
    if current_score:  # Add the last score if any
        goals.append(int(current_score))
    logging.debug(f"Scores found in line '{line}': {goals}")
    return goals


def rename_team(string):
    string = string.replace(" ' ", "")
    for key, value in teams_names.items():
        new_string = re.sub(key, value, string)
        if new_string != string:
            logging.info(f"Renamed team from '{key}' to '{value}' in line: '{string}'")
        string = new_string
        string = " ".join(string.split())
    return string


def get_predictions(text_msg_file):
    try:
        with open(text_msg_file, "r", encoding="utf-8-sig") as f:
            content = f.read()
            logging.info(f"Successfully read predictions from {text_msg_file}")
            return content
    except Exception as e:
        logging.error(f"Failed to read predictions from {text_msg_file}: {e}")
        raise


def clean_teams(string):
    predictions_list = []
    string = string.lower()
    lines = string.splitlines()
    for line in lines:
        original_line = line
        line = rename_team(line)
        if original_line != line:
            logging.info(f"Cleaned team names in line: '{original_line}' to '{line}'")
        predictions_list.append(line)
    return predictions_list


def extract_teams(line):
    sides = []
    for team in teams:
        if team.lower() in line.lower():
            sides.append(team)
    logging.info(f"Extracted teams from line '{line}': {sides}")
    return sides


def re_extract_teams(line):
    sides = []
    found = re.findall(r"\s?[v]?\s?[a-z']+\s?[a-z']+\s?", line, re.IGNORECASE)
    logging.debug(f"Found potential teams in line '{line}': {found}")
    for i in found:
        for j in teams:
            team = re.findall(r"\b{}\b".format(j), i)
            if len(team) > 0:
                sides.append(team[0])
                logging.debug(f"Matched team '{team[0]}' in line '{line}'")
    logging.info(f"Extracted teams from line '{line}': {sides}")
    return sides


def get_counts():
    with open(
        "/home/levo/Documents/projects/prediction_league/data/predictions/predictions{}.csv".format(
            gw
        ),
        "r",
    ) as f:
        names = []
        prediction_reader = csv.reader(f)
        next(prediction_reader)
        for row in prediction_reader:
            names.append(row[1])
        counts = Counter(names)
        for k, i in counts.items():
            if i != fixture_len:
                print("{} has {} entries".format(k.title(), i))


def check_for_players(predictions):
    submitted_players = set([player[1] for player in predictions])
    not_submitted = [person for person in players if person not in submitted_players]
    if not_submitted:
        logging.info(
            f"Players who have not submitted predictions: {', '.join(not_submitted)}"
        )
    return not_submitted


def add_missing_players(not_submitted):
    predictions_list = []
    c.execute(
        """
        SELECT 
            gameweek
            ,ht.team_name
            ,at.team_name
        FROM fixtures
            JOIN teams AS ht ON ht.team_id = fixtures.home_teamid
            JOIN teams AS at ON at.team_id = fixtures.away_teamid
        WHERE 
            gameweek = ?
            and season = ?

        """,
        (gw, seasondb),
    )
    fixtures = c.fetchall()
    for player in not_submitted:
        for fixture in fixtures:
            add_in_nines = [gw, player, fixture[1], fixture[2], 9, 9]
            predictions_list.append(add_in_nines)
            logging.info(
                f"Added missing prediction for player {player} for fixture {fixture[1]} vs {fixture[2]}"
            )
    return predictions_list


def remove_duplicates(predictions):
    seen = set()
    unique_predictions = []
    for prediction in predictions:
        prediction_tuple = tuple(prediction)
        if prediction_tuple not in seen:
            seen.add(prediction_tuple)
            unique_predictions.append(prediction)
    return unique_predictions


if __name__ == "__main__":
    create_meta_table()
    num_files = len(
        [
            name
            for name in os.listdir(predictions_dir)
            if os.path.isfile(os.path.join(predictions_dir, name))
            and name.endswith(".txt")
        ]
    )
    print([name for name in os.listdir(predictions_dir)])
    for i in range(1, num_files + 1):
        predictions = []

        gw = i
        predictions_file = f"{predictions_dir}gameweek{gw}.txt"
        logging.info(f"Processing predictions file: {predictions_file}")
        string = get_predictions(predictions_file)
        last_modified = is_file_modified(predictions_file)
        if last_modified:
            insert_file_metadata(predictions_file)
            formatted_teams = clean_teams(string)
            for line in formatted_teams:
                if line.strip() in players:
                    player = line.strip()
                sides = re_extract_teams(line)
                goals = find_scores(line)
                if len(sides) == 2:
                    try:
                        predict_line = [
                            gw,
                            player,
                            sides[0],
                            sides[1],
                            goals[0],
                            goals[1],
                        ]
                    except IndexError:
                        predict_line = [gw, player, sides[0], sides[1], 9, 9]
                    predictions.append(predict_line)
            not_submitted = check_for_players(predictions)
            predictions.extend(add_missing_players(not_submitted))
            predictions = remove_duplicates(predictions)
            with open(
                "/home/levo/Documents/projects/prediction_league/data/predictions/predictions{}.csv".format(
                    gw
                ),
                "w",
            ) as f:
                csvwriter = csv.writer(f)
                csvwriter.writerow(header)
                for line in predictions:
                    csvwriter.writerow(line)
            logging.info(f"Predictions for gameweek {gw} written to CSV")

            updated()
            logging.info(f"Database updated for gameweek {gw}")
            second_script = "/home/levo/Documents/projects/prediction_league/scripts/automation/automate_add_to_database.py"
            subprocess.run(["python3", second_script], check=True)
            logging.info(f"Ran second script: {second_script}")
        else:
            logging.info("No new predictions to process")
            continue

    c.close()
