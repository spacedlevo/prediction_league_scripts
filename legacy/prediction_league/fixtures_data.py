import sqlite3
import requests
import pytz
from datetime import datetime
import logging
import subprocess
import json

logging.basicConfig(
    filename="/home/levo/Documents/projects/prediction_league/logs/fixtures_data.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

odds_api_map = team_mapping = {
    "arsenal": "arsenal",
    "aston villa": "aston villa",
    "bournemouth": "bournemouth",
    "brentford": "brentford",
    "brighton and hove albion": "brighton",
    "chelsea": "chelsea",
    "crystal palace": "crystal palace",
    "everton": "everton",
    "fulham": "fulham",
    "ipswich town": "ipswich",
    "leicester city": "leicester",
    "liverpool": "liverpool",
    "manchester city": "man city",
    "manchester united": "man utd",
    "newcastle united": "newcastle",
    "nottingham forest": "nott'm forest",
    "southampton": "southampton",
    "tottenham hotspur": "spurs",
    "west ham united": "west ham",
    "wolverhampton wanderers": "wolves",
    "burnley": "burnley",
    "leeds united": "leeds",
    "sunderland": "sunderland",
}


season = "2025/2026"
uk_tz = pytz.timezone("Europe/London")

fixtures_json = "https://fantasy.premierleague.com/api/fixtures/"
bootstrap = "https://fantasy.premierleague.com/api/bootstrap-static/"
con = sqlite3.connect(
    "/home/levo/Documents/projects/prediction_league/data/database.db"
)
headers = {
    "authority": "users.premierleague.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "origin": "https://fantasy.premierleague.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://fantasy.premierleague.com/my-team",
    "accept-language": "en-US,en;q=0.9,he;q=0.8",
}
cur = con.cursor()


def create_tables():
    print("Creating tables...")
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER NOT NULL, 
            team_name TEXT, 
            available BOOLEAN,
            strength INTEGER,
            strength_overall_home,
            strength_overall_away,
            strength_attack_home,
            strength_attack_away,
            strength_defence_home,
            strength_defence_away,
            pulse_id INTEGER,
            PRIMARY KEY (team_id)
        )
        """
    )

    cur.execute("""
        SELECT 
            team_id, 
            team_name,
            available
        FROM 
            teams
        WHERE 
            available = 1
    """
                )
    existing_teams = cur.fetchall() # teams already in the database
    print(f"Found {len(existing_teams)} existing teams in database")

    if len(existing_teams) < 20:
        print("Fetching team data from FPL API...")
        r = requests.get(bootstrap, headers=headers)
        teams = r.json()["teams"]
        team_list = []
        for team in teams:
            available = not team["unavailable"]
            team_list.append(
                (
                    team["id"],
                    team["name"].lower(),
                    available,
                    team["strength"],
                    team["strength_overall_home"],
                    team["strength_overall_away"],
                    team["strength_attack_home"],
                    team["strength_attack_away"],
                    team["strength_defence_home"],
                    team["strength_defence_away"],
                    team["pulse_id"],
                )
            )

        teams_inserted = 0
        teams_updated = 0
        for team in team_list:
            cur.execute("SELECT team_name FROM teams WHERE team_name = ?", (team[1],))
            exists = cur.fetchone()
            if not exists:
                cur.execute(
                    "INSERT INTO teams (fpl_id, team_name, available, strength, strength_overall_home, strength_overall_away, strength_attack_home, strength_attack_away, strength_defence_home, strength_defence_away, pulse_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    team,
                )
                teams_inserted += 1
                print(f"Inserted team: {team[1]}")
            else:
                # If team is available (unavailable == False), set available to 1
                if team[2]:
                    cur.execute(
                        """UPDATE teams 
                        SET 
                            available = ?
                            ,fpl_id = ?
                            ,strength = ?
                            ,strength_overall_home = ?
                            ,strength_overall_away = ?
                            ,strength_attack_home = ?
                            ,strength_attack_away = ?
                            ,strength_defence_home = ?
                            ,strength_defence_away = ?
                            ,pulse_id = ? 
                        WHERE 
                            team_name = ?""", 
                        
                        (team[2], team[0], team[3], team[4], team[5], team[6], team[7], team[8], team[9], team[10], team[1])
                    )
                    teams_updated += 1
                    print(f"Updated team: {team[1]}")
        print(f"Teams inserted: {teams_inserted}, updated: {teams_updated}")
        con.commit()


    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS "fixtures" (
            "fpl_fixture_id"	INTEGER NOT NULL,
            "fixture_id"	INTEGER NOT NULL,
            "kickoff_dttm"	DATETIME,
            "home_teamid"	INTEGER NOT NULL,
            "away_teamid"	INTEGER NOT NULL,
            "finished"	BOOLEAN DEFAULT 1,
            "started"	BOOLEAN DEFAULT 0,
            "provisional_finished"	BOOLEAN DEFAULT 0,
            "season"	TEXT,
            "gameweek"	INTEGER,
            "home_win_odds"	REAL,
            "draw_odds"	REAL,
            "away_win_odds"	REAL,
            "pulse_id"	INTEGER,
            PRIMARY KEY("fixture_id" AUTOINCREMENT),
            UNIQUE("fixture_id")
        );
        """
    )

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS gameweeks (
            gameweek INTEGER NOT NULL,
            deadline_dttm DATETIME,
            deadline_date DATE,
            deadline_time TIME,
            current_gameweek BOOLEAN,
            next_gameweek BOOLEAN,
            finished BOOLEAN,
            PRIMARY KEY (gameweek)
        );
        """
    )


    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS last_update (
            "table_name"	TEXT,
            "updated"	TEXT,
            "timestamp"	NUMERIC,
            PRIMARY KEY("table_name")
    );
        """
    )

    con.commit()


def add_fixtures():
    print("Fetching fixtures from FPL API...")
    with requests.Session() as s:
        try:
            r = s.get(fixtures_json, headers=headers)
            r.raise_for_status()
            json_data = r.json()
            fixtures_inserted = 0
            fixtures_updated = 0
            
            # Save JSON data to file for debugging/backup
            json_filename = f"/home/levo/Documents/projects/prediction_league/data/fixtures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_filename, 'w') as json_file:
                json.dump(json_data, json_file, indent=2)
            print(f"JSON data saved to {json_filename}")
            
            # Pre-load team mappings to avoid repeated queries
            cur.execute("SELECT fpl_id, team_id FROM teams WHERE available = 1")
            team_map = dict(cur.fetchall())
            print(f"Loaded {len(team_map)} team mappings")
            
            # Pre-load existing fixtures to avoid repeated queries
            cur.execute("SELECT fpl_fixture_id, fixture_id FROM fixtures WHERE season = ?", (season,))
            existing_fixtures = dict(cur.fetchall())
            print(f"Found {len(existing_fixtures)} existing fixtures for season {season}")
            
            # Prepare batch data
            fixtures_to_insert = []
            fixtures_to_update = []
            
            for fixture in json_data:
                # Get team IDs from pre-loaded mapping
                home_team_id = team_map.get(fixture["team_h"])
                away_team_id = team_map.get(fixture["team_a"])
                
                if not home_team_id or not away_team_id:
                    print(f"Skipping fixture {fixture['id']} - missing team mapping (h:{fixture['team_h']}, a:{fixture['team_a']})")
                    continue
                
                fixture_data = (
                    fixture["kickoff_time"],
                    fixture["event"],
                    home_team_id,
                    away_team_id,
                    fixture["finished"],
                    fixture.get("started", False),  # Get started status from API, default to False
                    fixture.get("finished_provisional", False),  # Get provisional finished status from API, default to False
                    fixture["pulse_id"],
                    fixture["id"],
                    season
                )
                
                if fixture["id"] in existing_fixtures:
                    # Prepare for update
                    fixtures_to_update.append(fixture_data)
                else:
                    # Prepare for insert
                    fixtures_to_insert.append(fixture_data[:-1])  # Remove season for insert (it's added separately)
            
            # Batch insert new fixtures
            if fixtures_to_insert:
                cur.executemany(
                    "INSERT INTO fixtures (fpl_fixture_id, kickoff_dttm, gameweek, home_teamid, away_teamid, finished, started, provisional_finished, pulse_id, season) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(f[8], f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], season) for f in fixtures_to_insert]
                )
                fixtures_inserted = len(fixtures_to_insert)
                print(f"Batch inserted {fixtures_inserted} new fixtures")
            
            # Batch update existing fixtures
            if fixtures_to_update:
                cur.executemany(
                    """UPDATE fixtures SET 
                       kickoff_dttm = ?, gameweek = ?, home_teamid = ?, 
                       away_teamid = ?, finished = ?, started = ?, provisional_finished = ?, pulse_id = ?
                       WHERE fpl_fixture_id = ? AND season = ?""",
                    fixtures_to_update
                )
                fixtures_updated = len(fixtures_to_update)
                print(f"Batch updated {fixtures_updated} existing fixtures")
                    
            print(f"Total: {fixtures_inserted} inserted, {fixtures_updated} updated")
            con.commit()
            logging.info(f"Fixtures processed successfully: {fixtures_inserted} inserted, {fixtures_updated} updated")

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching fixtures: {e}")
            raise
        except sqlite3.Error as e:
            logging.error(f"Database error: {e}")
            raise


def add_gameweeks():
    print("Fetching gameweeks data...")
    url = bootstrap
    try:
        r = requests.get(url)
        r.raise_for_status()
        events = r.json()["events"]
        gameweeks = []

        for event in events:
            start_dttm = event["deadline_time"].replace("Z", "")
            utc_dttm = datetime.strptime(start_dttm, "%Y-%m-%dT%H:%M:%S")
            uk_dttm = utc_dttm.replace(tzinfo=pytz.utc).astimezone(uk_tz)
            deadline_date = uk_dttm.strftime("%Y-%m-%d")
            deadline_time = uk_dttm.strftime("%H:%M")
            current_gameweek = event["is_current"]
            next_gameweek = event["is_next"]
            gameweeks.append(
                (
                    event["id"],
                    event["deadline_time"],
                    deadline_date,
                    deadline_time,
                    current_gameweek,
                    next_gameweek,
                    event["finished"],
                )
            )
        cur.executemany(
            "INSERT OR REPLACE INTO gameweeks VALUES (?, ?, ?, ?, ?, ?, ?)", gameweeks
        )
        print(f"Added/updated {len(gameweeks)} gameweeks")
        con.commit()
        logging.info("Gameweeks added successfully.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching gameweeks: {e}")
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")


def updated():
    dt = datetime.now()
    now = dt.strftime("%d-%m-%Y. %H:%M:%S")
    timestamp = dt.timestamp()
    try:
        cur.execute(
            """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
               VALUES ('fixtures', ?, ?)""",
            (
                now,
                timestamp,
            ),
        )
        con.commit()
        logging.info("Last update timestamp added successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")


def add_odds_data():
    print("Fetching odds data...")
    odds_db = sqlite3.connect("/home/levo/Documents/projects/odds-api/odds.db")
    odds_cur = odds_db.cursor()
    try:
        odds_cur.execute(
            """ 
        SELECT 
            home_team_name,
            away_team_name,
            average_home_win_odds,
            average_draw_odds,
            average_away_win_odds,
            kickoffTime
        FROM 
            pivoted_odds
        WHERE 1=1
            AND (competition = 'soccer_epl' OR competition IS NULL)
        """
        )
        odds_data = odds_cur.fetchall()
        print(f"Found {len(odds_data)} odds records to process")
        
        if not odds_data:
            print("No odds data found to process")
            return
        
        # Pre-load team mappings to avoid repeated queries
        cur.execute("SELECT team_name, team_id FROM teams WHERE available = 1")
        team_name_map = dict(cur.fetchall())
        print(f"Loaded {len(team_name_map)} team name mappings")
        
        # Prepare batch update data
        odds_updates = []
        odds_not_found = 0
        
        for odds in odds_data:
            try:
                # Map team names using the odds_api_map
                home_team = odds_api_map.get(odds[0].lower())
                away_team = odds_api_map.get(odds[1].lower())
                
                if not home_team or not away_team:
                    print(f"Team mapping not found: {odds[0]} -> {home_team}, {odds[1]} -> {away_team}")
                    odds_not_found += 1
                    continue

                home_team_id = team_name_map.get(home_team)
                away_team_id = team_name_map.get(away_team)
                
                if not home_team_id or not away_team_id:
                    print(f"Team ID not found: {home_team} -> {home_team_id}, {away_team} -> {away_team_id}")
                    odds_not_found += 1
                    continue

                odds_updates.append((
                    round(float(odds[2]), 2) if odds[2] else None,  # home_win_odds
                    round(float(odds[3]), 2) if odds[3] else None,  # draw_odds
                    round(float(odds[4]), 2) if odds[4] else None,  # away_win_odds
                    home_team_id,
                    away_team_id,
                    season,
                    odds[5],  # kickoff_time
                ))
                
            except (ValueError, TypeError) as e:
                print(f"Error processing odds data: {e}, odds: {odds}")
                odds_not_found += 1
                continue
        
        # Batch update odds
        if odds_updates:
            cur.executemany(
                """
                UPDATE fixtures
                SET home_win_odds = ?, draw_odds = ?, away_win_odds = ?
                WHERE home_teamid = ? AND away_teamid = ? AND season = ? AND kickoff_dttm = ?
                """,
                odds_updates
            )
            
            print(f"Batch updated odds for {len(odds_updates)} fixtures")
            
            # Check how many were actually updated
            cur.execute("""
                SELECT COUNT(*) FROM fixtures 
                WHERE home_win_odds IS NOT NULL AND season = ?
            """, (season,))
            total_with_odds = cur.fetchone()[0]
            print(f"Total fixtures with odds in database: {total_with_odds}")
        else:
            print("No valid odds data to update")
            
        if odds_not_found > 0:
            print(f"Warning: {odds_not_found} odds records could not be processed due to missing team mappings")
                
        con.commit()
        logging.info(f"Odds data processed: {len(odds_updates)} updates attempted, {odds_not_found} skipped")
        
    except sqlite3.Error as e:
        logging.error(f"Database error in odds processing: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error in odds processing: {e}")
        raise
    finally:
        odds_db.close()


def main():
    print("Starting data update process...")
    try:
        # Start transaction for better performance
        cur.execute("BEGIN TRANSACTION")
        
        create_tables()
        add_fixtures()
        add_gameweeks()
        add_odds_data()
        updated()
        
        # Commit all changes
        con.commit()
        print("Data update process completed successfully!")
        
    except Exception as e:
        # Rollback on any error
        con.rollback()
        logging.error(f"Error in main process: {e}")
        print(f"Data update process failed: {e}")
        raise
    finally:
        con.close()
    
    # Run subsequent scripts
    second_script = "/home/levo/Documents/projects/prediction_league/scripts/automation/matchdata.py"
    try:
        subprocess.run(["python3", second_script], check=True)
        logging.info(f"{second_script} executed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing {second_script}: {e}")
    
    third_script = "/home/levo/Documents/projects/pick_player/playerscores.py"
    try:
        subprocess.run(["python3", third_script], check=True)
        logging.info(f"{third_script} executed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing {third_script}: {e}")


if __name__ == "__main__":
    main()
