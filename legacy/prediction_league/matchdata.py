import sqlite3 as sql
import requests
from tqdm import tqdm

pulse_api = "https://footballapi.pulselive.com/football/fixtures/{id}"

db = "/home/levo/Documents/projects/prediction_league/data/database.db"
conn = sql.connect(db)
cursor = conn.cursor()


def fetch_data_from_api(pulse_id):
    response = requests.get(pulse_api.format(id=pulse_id))
    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_pulse_id():
    cursor.execute(
        """SELECT
            pulse_id
            ,me.pulseid
        FROM 
            fixtures
            LEFT JOIN match_events as me on me.pulseid = fixtures.pulse_id
        WHERE finished = 1
            AND me.pulseid IS NULL"""
    )

    return cursor.fetchall()


def create_tables():
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS match_officials
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    matchOfficialID INT NOT NULL,
    pulseid INT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    FOREIGN KEY (pulseid) REFERENCES fixtures(pulse_id)
    );"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS team_list
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    pulseid INT NOT NULL,
    team_id INT,
    person_id INT,
    player_name TEXT NOT NULL,
    match_shirt_number INT,
    is_captain BOOLEAN,
    position TEXT NOT NULL,
    is_starting BOOLEAN,
    FOREIGN KEY (pulseid) REFERENCES fixtures(pulseid)
    );"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS match_events
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    pulseid INT NOT NULL,
    person_id INT,
    team_id INT,
    assist_id INT,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    FOREIGN KEY (pulseid) REFERENCES fixtures(pulseid)
    );"""
    )

    conn.commit()


def insert_match_officials(pulseid, officials):
    for official in officials:
        role = official.get("role", "LINEOFFICIAL")
        cursor.execute(
            """INSERT OR REPLACE INTO match_officials (matchOfficialID, pulseid, name, role)
            VALUES (?, ?, ?, ?)""",
            (
                official["matchOfficialId"],
                pulseid,
                official["name"]["display"],
                role,
            ),
        )
    conn.commit()


def insert_team_list(pulseid, teams):
    for team in teams:
        teamID = team.get("teamId")
        for player in team["lineup"]:
            cursor.execute(
                """INSERT OR REPLACE INTO team_list (pulseid, player_name, match_shirt_number, is_captain, position, is_starting, person_id, team_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pulseid,
                    player["name"]["display"],
                    player["matchShirtNumber"],
                    player["captain"],
                    player["matchPosition"],
                    True,
                    player["id"],
                    teamID,
                ),
            )
        for player in team["substitutes"]:
            cursor.execute(
                """INSERT OR REPLACE INTO team_list (pulseid, player_name, match_shirt_number, is_captain, position, is_starting, person_id, team_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pulseid,
                    player["name"]["display"],
                    player["matchShirtNumber"],
                    player["captain"],
                    player["matchPosition"],
                    False,
                    player["id"],
                    teamID,
                ),
            )
    conn.commit()


def insert_match_events(pulseid, events):
    for event in events:
        person_id = event.get("personId", None)
        teamID = event.get("teamId", None)
        assistID = event.get("assistId", None)
        cursor.execute(
            """INSERT INTO match_events (pulseid, event_type, event_time, person_id, team_id, assist_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                pulseid,
                event["type"],
                event["clock"]["secs"],
                person_id,
                teamID,
                assistID,
            ),
        )
    conn.commit()


create_tables()
pulse_apis = get_pulse_id()
if pulse_apis:
    for pulse_id in tqdm(pulse_apis):
        data = fetch_data_from_api(pulse_id[0])
        if data:
            insert_match_officials(pulse_id[0], data["matchOfficials"])
            insert_team_list(pulse_id[0], data["teamLists"])
            insert_match_events(pulse_id[0], data["events"])
else:
    print("No data to fetch")

conn.close()
