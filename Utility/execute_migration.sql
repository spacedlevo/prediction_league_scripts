-- Attach the legacy odds database
ATTACH DATABASE '/home/levo/Documents/projects/prediction_league_script/legacy/odds-api/odds.db' AS legacy_odds;

-- First, create the bookmakers table
CREATE TABLE IF NOT EXISTS bookmakers (
    bookmaker_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker_name TEXT UNIQUE NOT NULL
);

-- Create the odds table
CREATE TABLE IF NOT EXISTS odds (
    odd_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    fixture_id INTEGER,
    bookmaker_id INTEGER NOT NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
);

-- Insert unique bookmakers from the legacy odds data
INSERT OR IGNORE INTO bookmakers (bookmaker_name)
SELECT DISTINCT B.name
FROM legacy_odds.odds AS O
JOIN legacy_odds.team AS HT on HT.id = O.home_team_id
JOIN legacy_odds.team AS AT ON AT.id = O.away_team_id
JOIN legacy_odds.bookmaker AS B on B.id = O.bookmaker_id
WHERE O.market = 'soccer_epl';

-- Insert odds data with proper team_id mappings and fixture_id mappings
INSERT INTO odds (match_id, home_team_id, away_team_id, bet_type, fixture_id, bookmaker_id)
SELECT 
    O.match_id,
    ht_main.team_id as home_team_id,
    at_main.team_id as away_team_id,
    O.bet_type,
    f.fixture_id,
    bm.bookmaker_id
FROM legacy_odds.odds AS O
    JOIN legacy_odds.team AS HT on HT.id = O.home_team_id
    JOIN legacy_odds.team AS AT ON AT.id = O.away_team_id
    JOIN legacy_odds.bookmaker AS B on B.id = O.bookmaker_id
    -- Map to main database teams using odds_api_name
    JOIN teams AS ht_main ON ht_main.odds_api_name = HT.name
    JOIN teams AS at_main ON at_main.odds_api_name = AT.name
    -- Map to fixtures using home_team, away_team and kickoff time
    LEFT JOIN fixtures AS f ON (
        f.home_teamid = ht_main.team_id 
        AND f.away_teamid = at_main.team_id
        AND datetime(f.kickoff_dttm) = datetime(O.kickoffTime)
    )
    -- Get bookmaker_id from the newly created bookmakers table
    JOIN bookmakers AS bm ON bm.bookmaker_name = B.name
WHERE 
    O.market = 'soccer_epl';

-- Detach the legacy database
DETACH DATABASE legacy_odds;