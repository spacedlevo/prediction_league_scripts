import sqlite3 as sql
import sys

gw = sys.argv[1]
season = '2025/2026'

odds_db = "odds.db"
predictions_database = (
    "data/database.db"
)

team_mapping = {
    "arsenal": "arsenal",
    "aston villa": "aston villa",
    "bournemouth": "bournemouth",
    "brentford": "brentford",
    "brighton": "brighton and hove albion",
    "chelsea": "chelsea",
    "crystal palace": "crystal palace",
    "everton": "everton",
    "fulham": "fulham",
    "ipswich": "ipswich town",
    "leicester": "leicester city",
    "liverpool": "liverpool",
    "man city": "manchester city",
    "man utd": "manchester united",
    "newcastle": "newcastle united",
    "nott'm forest": "nottingham forest",
    "southampton": "southampton",
    "spurs": "tottenham hotspur",
    "west ham": "west ham united",
    "wolves": "wolverhampton wanderers",
    "burnley": "burnley",
    "leeds": "leeds united",
    "sunderland": "sunderland",
}


def get_fixtures():
    with sql.connect(predictions_database) as conn:
        cur = conn.cursor()
        cur.execute(
            """
                    SELECT
                        fixture_id 
                        ,ht.team_name AS home
                        ,at.team_name AS away
                    FROM 
                        fixtures
                            JOIN teams AS HT On HT.team_id = home_teamid
                            JOIN teams AS AT On AT.team_id = away_teamid

                    WHERE 
                        gameweek = ?
                        AND season = ?
                    ORDER BY 
                        kickoff_dttm
            """,
            (gw, season),
        )
        fixtures = cur.fetchall()

    # Map the team names using the team_mapping dictionary
    mapped_fixtures = []
    for fixture in fixtures:
        fixture_id, home_team, away_team = fixture
        mapped_fixtures.append(
            (
                fixture_id,
                team_mapping.get(home_team, home_team),
                team_mapping.get(away_team, away_team),
            )
        )
    return mapped_fixtures


def get_odds(fixture):
    scores = []
    with sql.connect(odds_db) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                bet_type,
                AVG(odds) AS average_odds
            FROM 
                odds
                JOIN team AS ht ON ht.id = odds.home_team_id
                JOIN team AS at ON at.id = odds.away_team_id
            WHERE 
                ht.name = ?
                AND at.name = ?
                AND bet_type IN ('home win', 'away win')
            GROUP BY 
                bet_type;

            """,
            (fixture[1], fixture[2]),
        )
        odds = cur.fetchall()
        diff = odds[0][1] - odds[1][1]
        if diff > -0.06 and diff < 0.06:
            score_home = 1
            score_away = 1
        elif odds[0][1] < odds[1][1]:
            score_home = 1
            score_away = 2
        elif odds[0][1] > odds[1][1]:
            score_home = 2
            score_away = 1
        scores.append((fixture[0], score_home, score_away))

    return scores


def write_prediction(prediction):
    with sql.connect(predictions_database) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                ht.team_name [ht]
                ,at.team_name [at]
            FROM
                fixtures
                JOIN teams AS ht ON ht.team_id = fixtures.home_teamid
                JOIN teams AS at ON at.team_id = fixtures.away_teamid
            WHERE fixture_id = ?
            """,
            (prediction[0],),
        )
        teams = cur.fetchone()
        return f"{teams[0]} {prediction[1]} - {prediction[2]} {teams[1]}"


predictions = []
fixtures = get_fixtures()
for fixture in fixtures:
    predictions.append(get_odds(fixture))

final_predictions = []
for prediction in predictions:
    final_predictions.append(write_prediction(prediction[0]))

with open(
    f"/home/levo/Dropbox/Apps/predictions_league/odds-api/predictions{gw}.txt", "w"
) as file:
    for prediction in final_predictions:
        file.write(prediction.title() + "\n")
