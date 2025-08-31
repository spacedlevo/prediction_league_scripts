import requests
import json
import sqlite3
import paramiko
from datetime import datetime, timezone, timedelta
import sys
import logging
import shutil


EVENT_URL = "https://fantasy.premierleague.com/api/fixtures/?event="
DATABASE_FILE = "/home/levo/Documents/projects/prediction_league/data/database.db"
con = sqlite3.connect(DATABASE_FILE)
cur = con.cursor()
season = "2025/2026"

# Setup logging
logging.basicConfig(
    filename="/home/levo/Documents/projects/prediction_league/logs/results.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def log_results_change(fixture_id, old_result, new_result):
    logging.info(
        f"Result changed for fixture_id {fixture_id}: {old_result} -> {new_result}"
    )


def log_new_result(fixture_id, result):
    logging.info(f"New result added for fixture_id {fixture_id}: {result}")

def get_team_id(fpl_id):
    cur.execute(
        "SELECT team_id FROM teams WHERE fpl_id = ? AND available = 1", (fpl_id,)
    )
    return cur.fetchone()[0] 


def calculate_match_result(home_goals, away_goals):
    """Calculate match result: HW (Home Win), AW (Away Win), or D (Draw)"""
    if home_goals > away_goals:
        return "HW"
    elif home_goals < away_goals:
        return "AW"
    else:
        return "D" 


def add_to_database(results):
    results_data = []


    for row in results:
        # Get the result from database
        home_teamid = cur.execute('SELECT team_id FROM teams WHERE available = 1 AND fpl_id = ?', (row[0],)).fetchone()[0]
        away_teamid = cur.execute('SELECT team_id FROM teams WHERE available = 1 AND fpl_id = ?', (row[1],)).fetchone()[0]
        
        # Get fixture_id first - we'll need it in multiple places
        fixture_id = cur.execute(
            """ SELECT fixture_id FROM fixtures WHERE home_teamid = ? AND away_teamid = ? AND season = ? """,
            (home_teamid, away_teamid, season),
        ).fetchone()[0]
        
        cur.execute(
            """ SELECT home_goals, away_goals FROM results WHERE fixture_id = ? """,
            (fixture_id,),
        )
        db_result = cur.fetchone()
        # Does the result exist?
        if db_result:
            # Check whether the result is the same as the one we have
            # Handle potential NULL values in database
            db_home_goals, db_away_goals = db_result
            if (db_home_goals is not None and db_away_goals is not None and 
                db_home_goals == row[2] and db_away_goals == row[3]):
                continue
            else:
                log_results_change(fixture_id, db_result, (row[2], row[3]))
                results_data.append((row, fixture_id))  # Store fixture_id with the row
        else:
            # Result doesn't exist, add it
            results_data.append((row, fixture_id))  # Store fixture_id with the row
    for result_data in results_data:
        result, fixture_id = result_data  # Unpack the result and fixture_id
        
        # No need to recalculate fixture_id, we already have it
        print(f"Processing fixture_id: {fixture_id}, season: {season}")
        
        # Check if result already exists for this fixture
        cur.execute(
            "SELECT result_id FROM results WHERE fixture_id = ?",
            (fixture_id,)
        )
        existing_result = cur.fetchone()
        
        if existing_result:
            # Calculate result outcome
            match_result = calculate_match_result(result[2], result[3])
            
            # Update existing result
            cur.execute(
                """
                UPDATE results 
                SET fpl_fixture_id = ?, home_goals = ?, away_goals = ?, result = ?
                WHERE fixture_id = ?
                """,
                (result[4], result[2], result[3], match_result, fixture_id),
            )
        else:
            # Calculate result outcome
            match_result = calculate_match_result(result[2], result[3])
            
            # Insert new result
            cur.execute(
                """
                INSERT INTO results (fixture_id, fpl_fixture_id, home_goals, away_goals, result)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fixture_id, result[4], result[2], result[3], match_result),
            )
        log_new_result(fixture_id, (result[2], result[3]))
    con.commit()  # Commit the changes to the database
    if len(results_data) == 0:
        return False
    else:
        return True


def print_results(gw):
    cur.execute(
        """
    SELECT
        home_team.team_name as home_team,
        results.home_goals as results_home_goals,
        results.away_goals as results_away_goals,
        away_team.team_name as away_team
    from fixtures
    inner join teams as away_team on away_team.team_id = fixtures.away_teamid
    inner join teams as home_team on home_team.team_id = fixtures.home_teamid
    left join results on results.fixture_id = fixtures.fixture_id
    where 
        gameweek = ? 
        AND results_home_goals NOT NULL 
        AND fixtures.season = ?
        """,
        (gw, season),
    )
    results_db = cur.fetchall()
    for i in results_db:
        print(f"{i[0].title()} {i[1]}-{i[2]} {i[3].title()}")


def upload_db():
    # SSH the new database to the website
    last_update = cur.execute(
        """SELECT updated, timestamp FROM last_update WHERE table_name = 'uploaded'"""
    ).fetchone()
    try:
        updated("uploaded")
        with open("/home/levo/Documents/projects/prediction_league/keys.json") as f:
            users_deets = json.load(f)

        # Use paramiko instead of pysftp
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname="ssh.pythonanywhere.com",
            username=users_deets["user"],
            password=users_deets["psw"]
        )
        
        sftp = ssh.open_sftp()
        sftp.put(DATABASE_FILE, "/home/spacedlevo/predictions_league/site/data/database.db")
        sftp.close()
        ssh.close()
        
        logging.info("Database upload successful.")
        return True
    except Exception as e:
        logging.error(f"Failed to upload database: {e}")
        cur.execute(
            """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
        VALUES (?, ?, ?)""",
            ("uploaded", last_update[0], last_update[1]),
        )
        con.commit()
        check_db = cur.execute(
            "SELECT updated FROM last_update WHERE table_name = 'uploaded'"
        ).fetchone()
        logging.info(f"upload time reset to: {check_db[0]}")
        return False


def updated(val):
    try:
        dt = datetime.now()
        now = dt.strftime("%d-%m-%Y. %H:%M:%S")
        timestamp = dt.timestamp()
        cur.execute(
            """INSERT OR REPLACE INTO last_update (table_name, updated, timestamp) 
               VALUES (?, ?, ?)""",
            (val, now, timestamp),
        )
        con.commit()
    except Exception as e:
        logging.error(f"Failed to update {val}: {e}")


def cache_gameweek(current_gw, next_gw_deadline_time):
    cur.execute("""DROP TABLE IF EXISTS gameweek_cache""")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gameweek_cache (
            current_gw INTEGER PRIMARY KEY,
            next_gw_deadline_time TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT OR REPLACE INTO gameweek_cache (current_gw, next_gw_deadline_time)
        VALUES (?, ?)
        """,
        (current_gw, next_gw_deadline_time),
    )
    updated("gameweek_cache")
    con.commit()


def current_gameweek():
    cur.execute("SELECT current_gw, next_gw_deadline_time FROM gameweek_cache")
    row = cur.fetchone()
    if row:
        current_gw, next_gw_deadline_time = row
        next_gw_deadline_time = datetime.strptime(
            next_gw_deadline_time, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        if next_gw_deadline_time > datetime.now(timezone.utc):
            print("Using Cache")
            return current_gw
    response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
    data = response.json()
    try:
        gw = next(event["id"] for event in data["events"] if event["is_current"])
    except StopIteration:
        logging.error("No current gameweek found in API response")
        # Fallback to the most recent gameweek or return None
        events = data.get("events", [])
        if events:
            gw = events[-1]["id"]  # Use the last gameweek as fallback
            logging.info(f"Using fallback gameweek: {gw}")
        else:
            logging.error("No gameweeks found in API response")
            return None
    
    try:
        next_gameweek = next(
            event["deadline_time"] for event in data["events"] if event["is_next"]
        )
        next_gameweek = (
            datetime.strptime(next_gameweek, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except StopIteration:
        next_gameweek = (
            "2024-12-31T23:59:59Z"  # Default value if no next gameweek found
        )
    print(f"Current Gameweek: {gw}, Next Gameweek Deadline: {next_gameweek}")
    cache_gameweek(gw, next_gameweek)
    return gw


def get_results(gw):
    results = []
    r = requests.get(f"{EVENT_URL}{gw}")
    print(f"Getting {EVENT_URL}{gw}")
    result_json = r.json()
    for result in result_json:
        # Only process fixtures that have started and have score data
        if result["started"] and result["team_h_score"] is not None and result["team_a_score"] is not None:
            results.append(
                [
                    result["team_h"],
                    result["team_a"],
                    result["team_h_score"],
                    result["team_a_score"],
                    result["id"],  # fpl_fixture_id
                    result.get("finished", False),  # Include finished status
                    result.get("finished_provisional", False),  # Include provisional finished status
                ]
            )
    return results


def update_fixture_finished_status_from_results(results):
    """Update the finished and provisional_finished status for fixtures when we have results data"""
    finished_updates = 0
    
    for row in results:
        if len(row) >= 6:  # Check if finished status is included
            fpl_fixture_id = row[4]
            finished_status = row[5] if len(row) > 5 else True  # Assume finished if we have results
            provisional_finished_status = row[6] if len(row) > 6 else finished_status  # Use provisional if available
            
            # Update both finished and provisional_finished status in fixtures table
            cur.execute(
                """
                UPDATE fixtures 
                SET finished = ?, provisional_finished = ?
                WHERE fpl_fixture_id = ? AND season = ?
                """,
                (finished_status, provisional_finished_status, fpl_fixture_id, season),
            )
            
            if cur.rowcount > 0:
                finished_updates += 1
    
    if finished_updates > 0:
        con.commit()
        logging.info(f"Updated finished/provisional_finished status for {finished_updates} fixtures based on results data")
    
    return finished_updates


def update_fixture_status(gw):
    """Update the started, finished, and provisional_finished status for fixtures based on FPL API data"""
    try:
        r = requests.get(f"{EVENT_URL}{gw}")
        print(f"Updating fixture status from {EVENT_URL}{gw}")
        result_json = r.json()
        
        status_changes = {
            'started': 0,
            'finished': 0,
            'provisional_finished': 0,
            'total_updated': 0
        }
        
        for fixture in result_json:
            fpl_fixture_id = fixture["id"]
            started_status = fixture.get("started", False)
            finished_status = fixture.get("finished", False)
            provisional_finished_status = fixture.get("finished_provisional", False)
            
            # Get current status from database
            cur.execute(
                """
                SELECT started, finished, provisional_finished 
                FROM fixtures 
                WHERE fpl_fixture_id = ? AND season = ?
                """,
                (fpl_fixture_id, season),
            )
            current_status = cur.fetchone()
            
            if current_status:
                current_started, current_finished, current_provisional_finished = current_status
                status_changed = False
                
                # Check if started status changed
                if current_started != started_status:
                    status_changes['started'] += 1
                    status_changed = True
                    logging.info(f"Fixture {fpl_fixture_id} started status changed: {current_started} -> {started_status}")
                
                # Check if finished status changed
                if current_finished != finished_status:
                    status_changes['finished'] += 1
                    status_changed = True
                    logging.info(f"Fixture {fpl_fixture_id} finished status changed: {current_finished} -> {finished_status}")
                
                # Check if provisional_finished status changed
                if current_provisional_finished != provisional_finished_status:
                    status_changes['provisional_finished'] += 1
                    status_changed = True
                    logging.info(f"Fixture {fpl_fixture_id} provisional_finished status changed: {current_provisional_finished} -> {provisional_finished_status}")
                
                # Update the database if any status changed
                if status_changed:
                    cur.execute(
                        """
                        UPDATE fixtures 
                        SET started = ?, finished = ?, provisional_finished = ?
                        WHERE fpl_fixture_id = ? AND season = ?
                        """,
                        (started_status, finished_status, provisional_finished_status, fpl_fixture_id, season),
                    )
                    
                    if cur.rowcount > 0:
                        status_changes['total_updated'] += 1
        
        con.commit()
        print(f"Updated status for {status_changes['total_updated']} fixtures")
        print(f"Started changes: {status_changes['started']}, Finished changes: {status_changes['finished']}, Provisional finished changes: {status_changes['provisional_finished']}")
        logging.info(f"Updated status for {status_changes['total_updated']} fixtures in gameweek {gw}")
        logging.info(f"Started changes: {status_changes['started']}, Finished changes: {status_changes['finished']}, Provisional finished changes: {status_changes['provisional_finished']}")
        
        return status_changes
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching fixture status: {e}")
        return None
    except sqlite3.Error as e:
        logging.error(f"Database error updating fixture status: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error updating fixture status: {e}")
        return None


def get_gameweek_deadlines():
    cur.execute(
        """
        SELECT gameweek, deadline_dttm FROM gameweeks
        """
    )
    return cur.fetchall()


def runtimes(gw):
    cur.execute(
        """
        SELECT MIN(kickoff_dttm), MAX(kickoff_dttm)
        FROM fixtures 
        WHERE 
			gameweek = ? AND season = ?
			AND DATE(kickoff_dttm) = DATE('now')
        """,
        (gw, season),
    )

    min_kickoff, max_kickoff = cur.fetchone()
    current_time = datetime.now(timezone.utc)

    if min_kickoff is None or max_kickoff is None:
        print("No fixtures found for the current gameweek.")
        return False

    # Remove the 'Z' and replace 'T' with a space
    min_kickoff = min_kickoff.replace("Z", "").replace("T", " ")
    max_kickoff = max_kickoff.replace("Z", "").replace("T", " ")

    min_kickoff_dt = datetime.strptime(min_kickoff, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    max_kickoff_dt = datetime.strptime(max_kickoff, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )

    if (
        min_kickoff_dt
        <= current_time
        <= max_kickoff_dt + timedelta(hours=2, minutes=30)
    ):
        print("Current time is within the range.")
        return True
    else:
        print("Current time is outside the range.")
        return False


def predictions_updated_after_results():
    cur.execute(
        """
        SELECT updated FROM last_update WHERE table_name = 'predictions'
        """
    )
    predictions_updated = cur.fetchone()

    cur.execute(
        """
        SELECT updated FROM last_update WHERE table_name = 'uploaded'
        """
    )
    results_updated = cur.fetchone()

    if predictions_updated and results_updated:
        predictions_time = datetime.strptime(
            predictions_updated[0], "%d-%m-%Y. %H:%M:%S"
        )
        results_time = datetime.strptime(results_updated[0], "%d-%m-%Y. %H:%M:%S")
        return predictions_time > results_time
    return False


def predictions_updated_before_uploaded():
    cur.execute(
        """
        SELECT MAX(timestamp), updated FROM last_update WHERE updated <> 'uploaded'
        """
    )
    predictions_updated = cur.fetchone()

    cur.execute(
        """
        SELECT updated FROM last_update WHERE table_name = 'uploaded'
        """
    )
    uploaded_updated = cur.fetchone()

    if predictions_updated[1] and uploaded_updated and uploaded_updated[0]:
        predictions_time = datetime.strptime(
            predictions_updated[1], "%d-%m-%Y. %H:%M:%S"
        )
        uploaded_time = datetime.strptime(uploaded_updated[0], "%d-%m-%Y. %H:%M:%S")
        return uploaded_time < predictions_time
    return False


def uploaded_within_last_30_minutes():
    cur.execute(
        """
        SELECT timestamp FROM last_update WHERE table_name = 'uploaded'
        """
    )
    uploaded_updated = cur.fetchone()

    if uploaded_updated and uploaded_updated[0] is not None:
        uploaded_time = uploaded_updated[0]
        current_time = datetime.now().timestamp()
        time_difference = current_time - uploaded_time
        if time_difference < 1740:
            return True
    return False


def main():
    gw = current_gameweek()
    
    # Always update fixture status (started and finished) first
    status_changes = update_fixture_status(gw)
    
    if status_changes:
        # Log any significant status changes
        if status_changes['started'] > 0:
            print(f"{status_changes['started']} fixtures changed to started")
        if status_changes['finished'] > 0:
            print(f"{status_changes['finished']} fixtures changed to finished")
        if status_changes['provisional_finished'] > 0:
            print(f"{status_changes['provisional_finished']} fixtures changed to provisional finished")
    
    run_schedule = runtimes(gw)
    if run_schedule:
        results = get_results(gw)
        # Update finished status based on results data
        update_fixture_finished_status_from_results(results)
        need_to_update = add_to_database(results)
        if need_to_update:
            updated("results")
            upload_db()
            print("Database uploaded")
        elif predictions_updated_after_results():
            logging.info("New predictions found, database uploaded.")
            upload_db()

        else:
            logging.info("Check ran, but no new results were added.")
            print("No new results to upload")
    elif predictions_updated_before_uploaded():
        logging.info("New predictions found, database uploaded.")
        upload_db()

    if len(sys.argv) > 1 and sys.argv[1] == "o":
        # Override mode - also update fixture status
        update_fixture_status(gw)
        results = get_results(gw)
        # Update finished status based on results data
        update_fixture_finished_status_from_results(results)
        need_to_update = add_to_database(results)
        updated("results")
        upload_db()
        print("Database uploaded")
        logging.info("Override used, database uploaded")
    if uploaded_within_last_30_minutes() is False:
        print("Database not uploaded within the last 30 minutes")
        if upload_db():
            logging.info("Laptop health check completed, database uploaded")
    con.close()

    # Copy database to v2 site
    try:
        shutil.copy2(DATABASE_FILE, "/home/levo/Documents/projects/predictions_league_v2/site/data/database.db")
        logging.info("Database copied to predictions_league_v2/site/data successfully")
    except Exception as e:
        logging.error(f"Failed to copy database to v2 site: {e}")

if __name__ == "__main__":
    main()
