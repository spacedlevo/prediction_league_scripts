from dotenv import load_dotenv
import sqlite3
import requests
import os
import argparse

# Load the API key from an environment variable
load_dotenv()
API_KEY = os.getenv("MY_API_KEY")
super_6_db = os.getenv("SUPER_6_DB")


team_mapping = {
    "tottenham": "tottenham hotspur",
    "man city": "manchester city",
    "man utd": "manchester united",
    "leicester": "leicester city",
    "newcastle": "newcastle united",
    "nottm forest": "nottingham forest",
    "brighton": "brighton and hove albion",
    "west ham": "west ham united",
    "wolverhampton": "wolverhampton wanderers",
    "ipswich": "ipswich town",
    "bayern munich": "bayern münchen",
    "inter milan": "internazionale milano",
    "slovan bratislava": "šk slovan bratislava",
    "psg": "paris saint germain",
    "bayern munich": "bayern münchen",
    "lille": "losc lille",
    "preston": "preston north end",
    "sporting": "sporting lisbon",
    "tamworth": "tamworth fc",
    "west brom": "west bromwich albion",
    "brighton": "brighton and hove albion",
    "salford": "salford city",
    "norwich": "norwich city",
    "atletico madrid": "atlético madrid",
    "psv": "psv eindhoven",
    "birmingham": "birmingham city",
    "plymouth": "plymouth argyle",
    "qpr": "queens park rangers",
    "sheff utd": "sheffield united",
    "derby": "derby county",
    "leeds": "leeds united",
    "blackburn": "blackburn rovers",
    "cardiff": "cardiff city",
    "swansea": "swansea city",
    "coventry": "coventry city",
    "doncaster": "doncaster rovers",
}


def markets():
    url = f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        sports = response.json()
        soccer_keys = [
            sport["key"] for sport in sports if sport.get("group") == "Soccer"
        ]
        return soccer_keys
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return []


# Load the super 6 team IDs from the SQLite database
def super6_ids():
    conn = sqlite3.connect(super_6_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM teams")
    teams = cursor.fetchall()
    conn.close()

    team_dict = {}
    for id, name in teams:
        lower_name = name.lower()
        if lower_name in team_mapping:
            lower_name = team_mapping[lower_name]
        team_dict[lower_name] = id
    return team_dict


# Load the JSON data from the file
def get_uefa_european_championship_odds(api_key):

    url = f"https://api.the-odds-api.com/v4/sports/{market_arg}/odds"
    params = {"regions": "uk", "oddsFormat": "decimal", "apiKey": api_key}
    response = requests.get(url, params=params)
    print(f"Request URL: {response.url}")

    if response.status_code == 200:
        odds_data = response.json()
        return odds_data
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return None


def write_database(data):
    # Prepare sets for unique bookmakers and teams
    bookmakers = set()
    teams = set()

    # Prepare lists for inserting odds
    odds_data = []

    for match in data:
        home_team = match["home_team"].lower()  # Convert to lower case
        away_team = match["away_team"].lower()  # Convert to lower case
        match_id = match["id"]

        teams.add(home_team)
        teams.add(away_team)

        kickOffTime = match["commence_time"]

        for bookmaker in match["bookmakers"]:
            bookmaker_name = bookmaker["title"].lower()  # Convert to lower case
            bookmakers.add(bookmaker_name)
            for market in bookmaker["markets"]:
                if market["key"] == "h2h":
                    for outcome in market["outcomes"]:
                        if outcome["name"].lower() == home_team:
                            odds_data.append(
                                (
                                    match_id,
                                    home_team,
                                    away_team,
                                    bookmaker_name,
                                    "home win",
                                    outcome["price"],
                                    kickOffTime,
                                )
                            )
                        elif outcome["name"].lower() == away_team:
                            odds_data.append(
                                (
                                    match_id,
                                    home_team,
                                    away_team,
                                    bookmaker_name,
                                    "away win",
                                    outcome["price"],
                                    kickOffTime,
                                )
                            )
                        elif outcome["name"].lower() == "draw":
                            odds_data.append(
                                (
                                    match_id,
                                    home_team,
                                    away_team,
                                    bookmaker_name,
                                    "draw",
                                    outcome["price"],
                                    kickOffTime,
                                )
                            )

    # Create the SQLite database
    conn = sqlite3.connect("/home/levo/Documents/projects/odds-api/odds.db")
    cursor = conn.cursor()

    # Create tables for bookmakers, teams, and odds
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS bookmaker (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS team (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        super6_id INTEGER DEFAULT NULL
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS "odds" (
        "id"	INTEGER,
        "match_id"	TEXT,
        "home_team_id"	INTEGER,
        "away_team_id"	INTEGER,
        "bookmaker_id"	INTEGER,
        "bet_type"	TEXT,
        "odds"	REAL,
        "market"	TEXT,
        "kickoffTime"	TEXT,
        PRIMARY KEY("id"),
        FOREIGN KEY("away_team_id") REFERENCES "team"("id"),
        FOREIGN KEY("bookmaker_id") REFERENCES "bookmaker"("id"),
        FOREIGN KEY("home_team_id") REFERENCES "team"("id")
    )
    """
    )
    conn.commit()
    cursor.execute("""DROP TABLE IF EXISTS pivoted_odds""")

    cursor.execute(
        """
    CREATE TABLE pivoted_odds (
    match_id TEXT PRIMARY KEY,
	home_team_id INTEGER,
	away_team_id INTEGER,
    home_team_name TEXT,
    away_team_name TEXT,
    competition TEXT,
    kickOffTime TEXT,
    average_home_win_odds REAL,
    average_draw_odds REAL,
    average_away_win_odds REAL
    )"""
    )
    conn.commit()

    # Insert unique bookmakers into the bookmaker table
    for bookmaker in bookmakers:
        cursor.execute(
            "INSERT OR IGNORE INTO bookmaker (name) VALUES (?)", (bookmaker,)
        )

    # Insert unique teams into the team table
    for team in teams:
        try:
            super6_id = super6.get(team)
            if super6_id:
                cursor.execute(
                    "INSERT OR IGNORE INTO team (name, super6_id) VALUES (?, ?)",
                    (team, super6_id),
                )
            else:
                cursor.execute("INSERT OR IGNORE INTO team (name) VALUES (?)", (team,))
        except KeyError:
            cursor.execute("INSERT OR IGNORE INTO team (name) VALUES (?)", (team,))

    # Commit the transactions for teams and bookmakers
    conn.commit()

    # Create a mapping from names to IDs for teams and bookmakers
    cursor.execute("SELECT id, name FROM team")
    team_id_map = {name: id for id, name in cursor.fetchall()}

    cursor.execute("SELECT id, name FROM bookmaker")
    bookmaker_id_map = {name: id for id, name in cursor.fetchall()}

    # Insert or update odds data into the odds table
    for (
        match_id,
        home_team,
        away_team,
        bookmaker,
        bet_type,
        odds,
        kickOffTime,
    ) in odds_data:
        home_team_id = team_id_map[home_team]
        away_team_id = team_id_map[away_team]
        bookmaker_id = bookmaker_id_map[bookmaker]

        # Check if the record already exists
        cursor.execute(
            """
        SELECT id FROM odds
        WHERE match_id = ? AND home_team_id = ? AND away_team_id = ? AND bookmaker_id = ? AND bet_type = ?
        """,
            (match_id, home_team_id, away_team_id, bookmaker_id, bet_type),
        )

        result = cursor.fetchone()

        if result:
            # Update the existing record
            cursor.execute(
                """
            UPDATE odds
            SET odds = ?, market = ?

            WHERE id = ?
            """,
                (odds, market_arg, result[0]),
            )
        else:
            # Insert the new record
            cursor.execute(
                """
            INSERT INTO odds (match_id, home_team_id, away_team_id, bookmaker_id, bet_type, odds, market, kickoffTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    match_id,
                    home_team_id,
                    away_team_id,
                    bookmaker_id,
                    bet_type,
                    odds,
                    market_arg,
                    kickOffTime,
                ),
            )
    # Update super6_id for teams if it becomes available
    for team in teams:
        super6_id = super6.get(team)
        if super6_id:
            cursor.execute(
                """
            UPDATE team
            SET super6_id = ?
            WHERE name = ?
            """,
                (super6_id, team),
            )

    # Commit the transactions for odds
    conn.commit()

    cursor.execute(
        """
    INSERT OR REPLACE INTO pivoted_odds (match_id,home_team_id, away_team_id, home_team_name, away_team_name, competition, kickoffTime, average_home_win_odds, average_draw_odds, average_away_win_odds)
    SELECT 
        o.match_id,
        ht.id AS home_team_id,
        at.id AS away_team_id,
        ht.name AS home_team_name,
        at.name AS away_team_name,
        o.market AS competition,
        o.kickoffTime,
        -- Calculate average odds for home win
        (SELECT AVG(odds) FROM odds WHERE match_id = o.match_id AND bet_type = 'home win') AS average_home_win_odds,
        -- Calculate average odds for draw
        (SELECT AVG(odds) FROM odds WHERE match_id = o.match_id AND bet_type = 'draw') AS average_draw_odds,
        -- Calculate average odds for away win
        (SELECT AVG(odds) FROM odds WHERE match_id = o.match_id AND bet_type = 'away win') AS average_away_win_odds
    FROM 
        odds o
        JOIN team ht ON o.home_team_id = ht.id
        JOIN team at ON o.away_team_id = at.id
    GROUP BY o.match_id;
        """
    )

    conn.commit()
    # Close the connection
    conn.close()
    print("Data written to the database")


if __name__ == "__main__":
    api_key = API_KEY  # Your API key here
    parser = argparse.ArgumentParser(description="Select a market.")
    parser.add_argument(
        "--market",
        type=str,
        choices=markets(),
        required=True,
        help="Market to select",
    )
    args = parser.parse_args()
    market_arg = args.market
    print(f"Selected market: {market_arg}")

    # Get odds from the API
    odds = get_uefa_european_championship_odds(api_key)
    super6 = super6_ids()

    if odds:
        write_database(odds)
