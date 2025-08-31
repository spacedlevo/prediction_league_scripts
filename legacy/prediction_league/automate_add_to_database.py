import sqlite3
import csv
import os
from datetime import datetime
import logging

season = "2025/2026"
# Set up logging
logging.basicConfig(
    filename="/home/levo/Documents/projects/prediction_league/logs/predictions.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# Add in data on when files have been last modified and if they are new or not
def updated():
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y. %H:%M:%S")
    timestamp = dt.timestamp()
    c.execute(
        """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
           VALUES ('predictions', ?, ?)""",
        (now, timestamp),
    )
    db.commit()


db = sqlite3.connect("/home/levo/Documents/projects/prediction_league/data/database.db")
c = db.cursor()
predictions_files = [
    f
    for f in os.listdir(
        "/home/levo/Documents/projects/prediction_league/data/predictions"
    )
    if f.endswith(".csv")
]

predictions_files.sort(
    key=lambda x: os.path.getmtime(
        f"/home/levo/Documents/projects/prediction_league/data/predictions/{x}"
    )
)

for predictions_file in predictions_files:
    with open(
        f"/home/levo/Documents/projects/prediction_league/data/predictions/{predictions_file}"
    ) as f:
        csvreader = csv.reader(f)
        next(csvreader)
        for row in csvreader:
            c.execute(
                """ SELECT player_id FROM players WHERE player_name = ? """, (row[1],)
            )
            user_id = c.fetchone()[0]
            c.execute(
                """ SELECT team_id FROM teams WHERE team_name = ? """, (row[2].strip(),)
            )
            home_teamid = c.fetchone()[0]
            c.execute(
                """ SELECT team_id FROM teams WHERE team_name = ? """, (row[3].strip(),)
            )
            away_teamid = c.fetchone()[0]
            c.execute(
                """ SELECT fixture_id, fpl_fixture_id FROM fixtures WHERE home_teamid = ? AND away_teamid = ? AND season = ? """,
                (home_teamid, away_teamid, season),
            )
            fixture = c.fetchone()
            fixture_id = fixture[0]
            fpl_fixture_id = fixture[1]
            home_goals = row[4]
            away_goals = row[5]
            if home_goals > away_goals:
                result = "HW"
            elif home_goals < away_goals:
                result = "AW"
            else:
                result = "D"
            c.execute(
                """ SELECT * FROM predictions WHERE player_id = ? AND fixture_id = ? """,
                (user_id, fixture_id),
            )
            existing_prediction = c.fetchone()

            if existing_prediction:
                if (
                    f"{existing_prediction[3]}-{existing_prediction[4]}"
                    != f"{home_goals}-{away_goals}"
                ):
                    c.execute(
                        """ UPDATE predictions SET home_goals = ?, away_goals = ?, predicted_result = ? WHERE player_id = ? AND fixture_id = ? """,
                        (home_goals, away_goals, result, user_id, fixture_id),
                    )
                    logging.info(
                        f"Updated prediction for player_id {user_id}, fixture_id {fixture_id}: "
                        f"from {existing_prediction[3]}-{existing_prediction[4]} to {home_goals}-{away_goals}"
                    )
                    updated()
            else:
                c.execute(
                    """ SELECT * FROM predictions WHERE player_id = ? AND fixture_id = ? """,
                    (user_id, fixture_id),
                )
                existing_prediction = c.fetchone()
                if not existing_prediction:
                    c.execute(
                        """ INSERT INTO predictions (player_id, fixture_id, fpl_fixture_id, home_goals, away_goals, predicted_result) VALUES (?, ?, ?, ?, ?, ?)""",
                        (user_id, fixture_id, fpl_fixture_id, home_goals, away_goals, result),
                    )
                    logging.info(
                        f"Added new prediction for player_id {user_id}, fixture_id {fixture_id}: "
                        f"{home_goals}-{away_goals}"
                    )
                    updated()

db.commit()
db.close()
