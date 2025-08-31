import sqlite3 as sql
from datetime import datetime, timedelta
import subprocess
import requests
import json

predictions_db_location = (
    "/home/levo/Documents/projects/prediction_league/data/database.db"
)
gameweek_file = "/home/levo/Dropbox/Apps/predictions_league/gameweek.txt"
season = "2025/2026"

with open("/home/levo/Documents/projects/prediction_league/keys.json", "r") as file:
    PUSHOVER_API = json.load(file)


def fetch_next_deadline():
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
	        gameweek
	        ,CAST(strftime('%s', deadline_dttm) AS INT) [deadline_dttm]
        FROM gameweeks WHERE deadline_dttm > datetime("now") ORDER BY deadline_dttm ASC LIMIT 1
    """
    )
    deadline = c.fetchone()
    conn.close()
    return deadline


def is_within_12_hours(timestamp):
    now = datetime.now()
    target_time = datetime.fromtimestamp(timestamp)
    hours_until_deadline = (timestamp - now.timestamp()) / 3600
    
    print(f"Deadline: {target_time}")
    print(f"Now: {now}")
    print(f"Hours until deadline: {hours_until_deadline:.2f}")
    
    # Check if deadline is in the future and within 36 hours
    is_future = target_time > now
    is_within_36_hours = hours_until_deadline <= 36
    
    print(f"Is deadline in future: {is_future}")
    print(f"Is within 36 hours: {is_within_36_hours}")
    print(f"Combined result: {is_future and is_within_36_hours}")
    
    return is_future and is_within_36_hours


def run_createdata_script(gw):
    script_path = "/home/levo/Documents/projects/odds-api/createdata.py"
    script_path2 = "/home/levo/Documents/projects/odds-api/predictions.py"
    subprocess.run(["python3", script_path, "--market", "soccer_epl"])
    subprocess.run(["python3", script_path2, str(gw)])


def read_predictions_file(gw):
    file_path = (
        f"/home/levo/Dropbox/Apps/predictions_league/odds-api/predictions{gw}.txt"
    )
    with open(file_path, "r") as file:
        predictions = file.read()
    predictions = "\nTom Levin\n\n" + predictions
    return predictions


def save_predictions(gw, predictions):
    file_path = f"/home/levo/Dropbox/Predictions/2025_26/gameweek{gw}.txt"
    with open(file_path, "a") as file:
        file.write(predictions)


def check_if_predictions_exist(gw):
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
            COUNT(*)
        FROM fixtures AS F
        JOIN predictions AS P ON P.fixture_id = F.fixture_id
        WHERE 
            gameweek = ?
            AND season = ?
            AND player_id = 24
              """,
        (gw, season),
    )

    count = c.fetchone()[0]

    c.execute(
        """
            SELECT 
                home_goals
                ,away_goals
            FROM 
                predictions
                JOIN fixtures ON predictions.fixture_id = fixtures.fixture_id
            WHERE 
                player_id = 24
                AND gameweek = ?
                AND season = ?
            ORDER BY home_goals DESC
              """,
        (gw, season),
    )
    predictions = c.fetchall()
    conn.close()
    if count != len(predictions):
        return False
    if not predictions or (predictions[0] == 9):
        return False
    else:
        return True


def fetch_fixtures(gw):
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
            ht.team_name
            ,at.team_name
            ,deadline_time
        FROM 
            fixtures AS F
            JOIN teams AS ht ON ht.team_id = home_teamid
            JOIN teams AS at ON at.team_id = away_teamid 
            JOIN gameweeks AS gw on gw.gameweek = F.gameweek
        WHERE 
            f.gameweek = ?
            AND f.season = ?
        ORDER BY f.kickoff_dttm
              """,
        (gw, season),
    )
    fixtures = c.fetchall()
    conn.close()
    return fixtures


def create_string():
    gw, deadline = fetch_next_deadline()
    fixtures = fetch_fixtures(gw)
    fixtures_str = "\n".join(
        [f"{home.title()} v {away.title()}" for home, away, _ in fixtures]
    )
    deadline_time = datetime.fromtimestamp(deadline).strftime("%H:%M")
    result = f"{fixtures_str}\n\nDeadline tomorrow at {deadline_time}"
    return result


def fetch_sent_message():
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
            updated
        FROM 
            last_update
        WHERE 
            table_name = 'checked_missing_predictions'
              """,
    )
    updated = c.fetchone()
    conn.close()
    if updated:
        updated = int(datetime.strptime(updated[0], "%d-%m-%Y. %H:%M:%S").timestamp())
    return updated


def updated(update):
    db = sql.connect(predictions_db_location)
    c = db.cursor()
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y. %H:%M:%S")
    timestamp = dt.timestamp()
    c.execute(
        """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
           VALUES (?, ?, ?)""",
        (update, now, timestamp),
    )
    db.commit()


def send_pushover_message(message):

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API["PUSHOVER_TOKEN"],
        "user": PUSHOVER_API["PUSHOVER_USER"],
        "message": message,
    }

    response = requests.post(url, data=data)
    if response.status_code != 200:
        raise Exception(f"Error sending message: {response.text}")


def has_deadline_passed():
    gw, deadline = fetch_next_deadline()
    now = datetime.now().timestamp()
    deadline -= 3600
    return now > deadline


def fetch_players_without_predictions(gw):
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT DISTINCT
            web_name
        FROM
            predictions AS P
            JOIN fixtures AS F ON F.fixture_id = P.fixture_id
            JOIN players AS pl ON pl.player_id = p.player_id
                AND pl.active = 1
        WHERE 
            gameweek = ?
            AND home_goals = 9 
            AND away_goals = 9
            AND season = ?
        ORDER BY 1
        """,
        (gw, season),
    )
    players = c.fetchall()
    conn.close()
    print(players)
    return "\n".join([player[0].title() for player in players])


def was_send_fixtures_recently_updated():
    conn = sql.connect(predictions_db_location)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
            timestamp
        FROM 
            last_update
        WHERE 
            table_name = 'send_fixtures'
        """
    )
    result = c.fetchone()
    conn.close()
    if result:
        last_updated_timestamp = result[0]
        now = datetime.now().timestamp()
        updated = now - last_updated_timestamp
        if (now - last_updated_timestamp) <= 3600:
            return True
    return False


def main():
    gw, deadline = fetch_next_deadline()
    
    print(f"Current gameweek: {gw}")
    print(f"Deadline timestamp: {deadline}")

    # Debug the conditions
    within_timeframe = is_within_12_hours(deadline)
    predictions_exist = check_if_predictions_exist(gw)
    recently_updated = was_send_fixtures_recently_updated()
    
    print(f"Within 36 hours: {within_timeframe}")
    print(f"Predictions exist: {predictions_exist}")
    print(f"Recently updated: {recently_updated}")
    print(f"Should trigger: {within_timeframe and not predictions_exist and not recently_updated}")

    # run_createdata_script(gw)
    # with open(gameweek_file, "w") as file:
    #     file.write(str(gw))
    # predictions = read_predictions_file(gw)
    # save_predictions(gw, predictions)
    # message = create_string()
    # send_pushover_message(message)
    # predictions = predictions.replace("\nTom Levin\n\n", "").strip()
    # print(predictions)
    # send_pushover_message(predictions)
    # updated("send_fixtures")
    # print("Data Saved")


    if (
        is_within_12_hours(deadline)
        and not check_if_predictions_exist(gw)
        and not was_send_fixtures_recently_updated()
    ):
        run_createdata_script(gw)
        with open(gameweek_file, "w") as file:
            file.write(str(gw))
        predictions = read_predictions_file(gw)
        save_predictions(gw, predictions)
        message = create_string()
        send_pushover_message(message)
        predictions = predictions.replace("\nTom Levin\n\n", "").strip()
        print(predictions)
        send_pushover_message(predictions)
        updated("send_fixtures")
        print("Data Saved")
    else:
        print("No deadline within timeframe")
    if has_deadline_passed():
        sent_message_time = fetch_sent_message()
        if sent_message_time is None or sent_message_time < (deadline - 3600):
            players = fetch_players_without_predictions(gw)
            send_pushover_message(players)
            updated("checked_missing_predictions")


main()
