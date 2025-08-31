# Database Schema Documentation

## Overview

The odds system uses SQLite with several related tables to store teams, fixtures, bookmakers, individual odds, and aggregated summaries.

## Core Tables

### `teams`
Stores team information and mapping data for odds integration.

```sql
CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fpl_id INTEGER,
    team_name TEXT,
    available BOOLEAN DEFAULT 0,
    strength INTEGER,
    strength_overall_home INTEGER,
    strength_overall_away INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    pulse_id INTEGER,
    football_data_name TEXT,
    odds_api_name TEXT  -- Used for API team name mapping
);
```

**Key Fields**:
- `team_id`: Primary key for internal references
- `team_name`: Display name (e.g., "Man City")
- `odds_api_name`: Name used by The Odds API (e.g., "manchester city")

### `fixtures`
Stores match fixture information.

```sql
CREATE TABLE fixtures (
    fpl_fixture_id INTEGER NOT NULL,
    fixture_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kickoff_dttm DATETIME,
    home_teamid INTEGER NOT NULL,
    away_teamid INTEGER NOT NULL,
    finished BOOLEAN DEFAULT 1,
    season TEXT,
    home_win_odds REAL,
    draw_odds REAL,
    away_win_odds REAL,
    pulse_id INTEGER,
    gameweek INTEGER,
    started BOOLEAN DEFAULT 0,
    provisional_finished BOOLEAN DEFAULT 0,
    FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
    FOREIGN KEY (away_teamid) REFERENCES teams(team_id)
);
```

**Key Fields**:
- `fixture_id`: Primary key for internal references
- `kickoff_dttm`: Match kickoff time (used for odds linking)
- `home_teamid`, `away_teamid`: References to teams table

### `bookmakers`
Stores bookmaker reference data.

```sql
CREATE TABLE bookmakers (
    bookmaker_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker_name TEXT UNIQUE NOT NULL
);
```

**Sample Data**:
- "paddy power", "betfair", "sky bet", etc.

### `odds`
Stores individual odds from each bookmaker.

```sql
CREATE TABLE odds (
    odd_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,           -- API match identifier
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    bet_type TEXT NOT NULL,           -- "home win", "away win", "draw"
    fixture_id INTEGER,               -- NULL if no fixture match found
    bookmaker_id INTEGER NOT NULL,
    price REAL,                       -- The actual odds value
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
);
```

**Key Fields**:
- `match_id`: Unique identifier from The Odds API
- `bet_type`: "home win", "away win", or "draw"
- `price`: Decimal odds (e.g., 1.85, 2.10, 3.40)
- `fixture_id`: Links to fixtures table (NULL if no match)

### `fixture_odds_summary`
Aggregated average odds per fixture.

```sql
CREATE TABLE fixture_odds_summary (
    fixture_id INTEGER PRIMARY KEY,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    avg_home_win_odds REAL,
    avg_draw_odds REAL,
    avg_away_win_odds REAL,
    bookmaker_count INTEGER,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);
```

**Key Fields**:
- `avg_*_odds`: Averaged odds across all bookmakers
- `bookmaker_count`: Number of bookmakers contributing to averages
- `last_updated`: When averages were last calculated

## Data Relationships

### Primary Relationships
```
teams ←→ odds (via home_team_id, away_team_id)
teams ←→ fixtures (via home_teamid, away_teamid)
fixtures ←→ odds (via fixture_id)
bookmakers ←→ odds (via bookmaker_id)
fixtures ←→ fixture_odds_summary (via fixture_id)
```

### Mapping Flow
1. **API Data** → `odds` table (individual bookmaker odds)
2. **Team Names** → `teams` table (via odds_api_name matching)
3. **Match Info** → `fixtures` table (via team IDs + kickoff time)
4. **Aggregation** → `fixture_odds_summary` table (averaged across bookmakers)

## Data Integrity

### Constraints
- **Unique Bookmakers**: Bookmaker names must be unique
- **Foreign Keys**: All references properly constrained
- **NOT NULL**: Critical fields cannot be empty

### Data Validation
- **Prices**: Must be positive decimal values
- **Bet Types**: Limited to "home win", "away win", "draw"
- **Team Mapping**: Teams must exist before odds insertion

### Update Strategy
- **Odds**: INSERT OR UPDATE based on match_id + bet_type + bookmaker_id
- **Bookmakers**: INSERT OR IGNORE (create if not exists)
- **Summary**: INSERT OR REPLACE (complete refresh)

## Query Examples

### Get Odds for Specific Match
```sql
SELECT 
    t1.team_name as home_team,
    t2.team_name as away_team,
    o.bet_type,
    o.price,
    b.bookmaker_name
FROM odds o
JOIN teams t1 ON t1.team_id = o.home_team_id
JOIN teams t2 ON t2.team_id = o.away_team_id
JOIN bookmakers b ON b.bookmaker_id = o.bookmaker_id
WHERE o.match_id = 'your-match-id';
```

### Get Average Odds Summary
```sql
SELECT 
    t1.team_name as home_team,
    t2.team_name as away_team,
    ROUND(s.avg_home_win_odds, 2) as home_win,
    ROUND(s.avg_draw_odds, 2) as draw,
    ROUND(s.avg_away_win_odds, 2) as away_win,
    s.bookmaker_count
FROM fixture_odds_summary s
JOIN teams t1 ON t1.team_id = s.home_team_id
JOIN teams t2 ON t2.team_id = s.away_team_id
ORDER BY s.last_updated DESC;
```

### Get Bookmaker Coverage
```sql
SELECT 
    b.bookmaker_name,
    COUNT(*) as odds_count,
    COUNT(DISTINCT o.match_id) as matches_covered
FROM odds o
JOIN bookmakers b ON b.bookmaker_id = o.bookmaker_id
GROUP BY b.bookmaker_id, b.bookmaker_name
ORDER BY odds_count DESC;
```

## Performance Considerations

### Indexes
Current indexes (automatically created):
- Primary keys on all tables
- Unique constraint on bookmaker_name

### Potential Optimizations
```sql
-- For frequent odds lookups by match
CREATE INDEX idx_odds_match_id ON odds(match_id);

-- For team name lookups
CREATE INDEX idx_teams_odds_api_name ON teams(odds_api_name);

-- For fixture matching
CREATE INDEX idx_fixtures_teams_kickoff ON fixtures(home_teamid, away_teamid, kickoff_dttm);
```

### Data Volume
- **Teams**: ~23 Premier League teams
- **Bookmakers**: ~19 bookmakers  
- **Fixtures**: ~380 fixtures per season
- **Odds**: ~57,000 records per full season (380 × 3 bet types × ~50 bookmaker odds)
- **Summary**: ~380 summaries per season

## Maintenance

### Regular Tasks
- **Log Monitoring**: Check daily log files for processing errors
- **Data Validation**: Verify odds prices are reasonable (> 1.0)
- **Storage Management**: Monitor database size growth
- **Backup Strategy**: Regular database backups recommended

## FPL Data Tables (NEW)

The system now includes dedicated tables for Fantasy Premier League data integration.

### `gameweeks` (Core)
Stores Premier League gameweek information and deadlines:

```sql
CREATE TABLE gameweeks (
    gameweek INTEGER NOT NULL,
    deadline_dttm DATETIME,
    deadline_date DATE,
    deadline_time TIME,
    current_gameweek BOOLEAN,
    next_gameweek BOOLEAN,
    finished BOOLEAN,
    PRIMARY KEY (gameweek)
);
```

**Key Fields**:
- `gameweek`: Primary key (1-38 for Premier League season)
- `deadline_dttm`: Full datetime for FPL deadline (UTC)
- `deadline_date`, `deadline_time`: Parsed UK timezone components
- `current_gameweek`, `next_gameweek`: Status flags from FPL API
- `finished`: Whether gameweek has completed

**Data Source**: FPL Bootstrap API (`/api/bootstrap-static/`)

### `fantasy_pl_scores` (Enhanced)
Enhanced player performance table with team relationship:

```sql
CREATE TABLE fantasy_pl_scores (
    player_name TEXT,
    gameweek INTEGER,
    player_id INTEGER,
    total_points INTEGER,
    fixture_id INTEGER,
    team_id INTEGER,              -- NEW: Links to teams table
    was_home BOOLEAN,
    -- ... 30+ performance metrics
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)  -- NEW
);
```

**Key Enhancements**:
- `team_id` column links players to their Premier League teams
- Enables team-based queries and analysis
- Foreign key relationship maintains data integrity

### `fpl_players_bootstrap` (NEW)
Bootstrap cache table for performance optimization:

```sql
CREATE TABLE fpl_players_bootstrap (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL,
    team_id INTEGER,              -- FPL team ID
    db_team_id INTEGER,          -- Mapped database team_id
    position TEXT,               -- Player position (1-4)
    minutes INTEGER,             -- Total minutes played
    total_points INTEGER,        -- Total FPL points
    ict_index REAL,             -- ICT index
    goals_scored INTEGER,        -- Goals scored
    assists INTEGER,            -- Assists
    clean_sheets INTEGER,       -- Clean sheets
    saves INTEGER,              -- Saves (goalkeepers)
    yellow_cards INTEGER,       -- Yellow cards
    red_cards INTEGER,          -- Red cards
    bonus INTEGER,              -- Bonus points
    bps INTEGER,                -- Bonus Point System score
    influence REAL,             -- Influence metric
    creativity REAL,            -- Creativity metric
    threat REAL,                -- Threat metric
    starts INTEGER,             -- Starts
    expected_goals REAL,        -- Expected goals
    expected_assists REAL,      -- Expected assists
    value INTEGER,              -- Player price
    transfers_in INTEGER,       -- Transfers in
    transfers_out INTEGER,      -- Transfers out
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    season TEXT DEFAULT '2025/2026',
    FOREIGN KEY (db_team_id) REFERENCES teams(team_id)
);
```

**Purpose**:
- **Performance Optimization**: Eliminates 60-80% of API calls
- **Change Detection**: Only processes players with modified statistics
- **Team Integration**: Maps FPL teams to database team records
- **Historical Tracking**: Maintains bootstrap change history

### Indexes (Updated)

```sql
-- Existing indexes
CREATE INDEX idx_odds_match_id ON odds(match_id);
CREATE INDEX idx_teams_odds_api_name ON teams(odds_api_name);
CREATE INDEX idx_fixtures_teams_kickoff ON fixtures(home_teamid, away_teamid, kickoff_dttm);

-- FPL-specific indexes
CREATE INDEX idx_player_scores_fixture_id ON fantasy_pl_scores(fixture_id);
CREATE INDEX idx_player_scores_player_id ON fantasy_pl_scores(player_id);
CREATE INDEX idx_player_scores_gameweek ON fantasy_pl_scores(gameweek);
CREATE INDEX idx_player_scores_team_id ON fantasy_pl_scores(team_id);  -- NEW
CREATE INDEX idx_bootstrap_player_season ON fpl_players_bootstrap(player_id, season);  -- NEW

-- Gameweeks indexes
CREATE INDEX idx_gameweeks_current ON gameweeks(current_gameweek);  -- NEW
CREATE INDEX idx_gameweeks_finished ON gameweeks(finished);  -- NEW
```

### Data Volume (Updated)

- **Teams**: ~23 Premier League teams
- **Bookmakers**: ~19 bookmakers  
- **Fixtures**: ~380 fixtures per season
- **Gameweeks**: 38 gameweeks per season (NEW)
- **Odds**: ~57,000 records per full season
- **Summary**: ~380 summaries per season
- **FPL Players**: ~700 Premier League players (NEW)
- **FPL Scores**: ~15,000-25,000 performance records per season (NEW)
- **FPL Bootstrap**: ~700 cached player summaries per season (NEW)

## Prediction League Tables (NEW)

The system now includes full prediction league database integration for storing and managing user predictions.

### `players` (Core)
Stores player information for the prediction league:

```sql
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT,
    paid INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 0,
    mini_league INTEGER NOT NULL DEFAULT 0,
    mini_league_paid INTEGER NOT NULL DEFAULT 0,
    pundit INTEGER NOT NULL DEFAULT 0,
    web_name TEXT
);
```

**Key Fields**:
- `player_id`: Primary key for internal references
- `player_name`: Display name for player (e.g., "Tom Levin")
- `active`: Whether player participates in current season
- `paid`: Payment status for league participation

### `predictions` (Enhanced)
Stores individual player predictions with full database integration:

```sql
CREATE TABLE predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    fixture_id INTEGER NOT NULL,
    fpl_fixture_id INTEGER,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    predicted_result TEXT NOT NULL,           -- H/D/A result
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);
```

**Key Fields**:
- `prediction_id`: Unique identifier for each prediction
- `player_id`: Links to players table
- `fixture_id`: Links to fixtures table for match details
- `home_goals`, `away_goals`: Predicted score
- `predicted_result`: Calculated result ("H" = Home win, "D" = Draw, "A" = Away win)

**Data Source**: Dropbox API via `clean_predictions_dropbox.py` script

### `file_metadata` (Tracking)
Tracks Dropbox file changes for efficient processing:

```sql
CREATE TABLE file_metadata (
    filename TEXT PRIMARY KEY,
    last_modified TIMESTAMP
);
```

**Purpose**: Enables change detection to process only modified prediction files

### Prediction Data Flow (NEW)

#### 1. Dropbox Integration
```
Dropbox Files → clean_predictions_dropbox.py → Database
    ↓
gameweek1.txt, gameweek2.txt, etc.
    ↓
Direct database insertion + CSV backup
```

#### 2. Database Integration Process
1. **File Monitoring**: Track `.txt` file timestamps in `file_metadata`
2. **Change Detection**: Process only files modified since last run
3. **Content Processing**: Extract player names, teams, and scores from text
4. **Foreign Key Resolution**: Convert names to database IDs
5. **Duplicate Resolution**: Keep only latest prediction per player per fixture
6. **Database Insertion**: Use `INSERT OR REPLACE` for conflict resolution
7. **Result Calculation**: Generate H/D/A based on goal difference

#### 3. Conflict Resolution Strategy
- **Constraint**: One prediction per `(player_id, fixture_id)` combination
- **Latest Wins**: If player submits multiple predictions for same fixture, keep the last one in file
- **Validation**: Skip predictions for missing players or fixtures
- **Transaction Safety**: All insertions within database transactions

### Prediction Processing Functions (NEW)

#### Foreign Key Resolution
```python
def get_player_id(player_name, cursor):
    """Convert player name to database player_id"""
    cursor.execute("SELECT player_id FROM players WHERE LOWER(player_name) = LOWER(?)", (player_name,))
    return cursor.fetchone()[0] if cursor.fetchone() else None

def get_fixture_id(home_team, away_team, gameweek, cursor):
    """Match team names and gameweek to fixture_id"""
    cursor.execute("""
        SELECT f.fixture_id, f.fpl_fixture_id FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE LOWER(ht.team_name) = LOWER(?) AND LOWER(at.team_name) = LOWER(?)
        AND f.gameweek = ? AND f.season = ?
    """, (home_team, away_team, gameweek, "2025/2026"))
```

#### Result Calculation
```python
def calculate_predicted_result(home_goals, away_goals):
    """Generate H/D/A result from goal scores"""
    if home_goals > away_goals:
        return 'H'  # Home win
    elif home_goals < away_goals:
        return 'A'  # Away win
    else:
        return 'D'  # Draw
```

### Query Examples (Predictions)

#### Get All Predictions for Gameweek
```sql
SELECT 
    pl.player_name,
    ht.team_name as home_team,
    at.team_name as away_team,
    p.home_goals,
    p.away_goals,
    p.predicted_result
FROM predictions p
JOIN players pl ON p.player_id = pl.player_id
JOIN fixtures f ON p.fixture_id = f.fixture_id
JOIN teams ht ON f.home_teamid = ht.team_id
JOIN teams at ON f.away_teamid = at.team_id
WHERE f.gameweek = 3;
```

#### Check Prediction Coverage
```sql
SELECT 
    f.gameweek,
    COUNT(DISTINCT p.player_id) as players_predicted,
    COUNT(*) as total_predictions,
    (SELECT COUNT(*) FROM players WHERE active = 1) as active_players
FROM predictions p
JOIN fixtures f ON p.fixture_id = f.fixture_id
GROUP BY f.gameweek
ORDER BY f.gameweek;
```

### Indexes (Updated)

```sql
-- Existing indexes
CREATE INDEX idx_fixtures_season ON fixtures(season);
CREATE INDEX idx_fixtures_gameweek ON fixtures(gameweek);
CREATE INDEX idx_fixtures_fpl_id ON fixtures(fpl_fixture_id);

-- NEW: Prediction-specific indexes
CREATE INDEX idx_predictions_player_fixture ON predictions(player_id, fixture_id);  -- Constraint enforcement
CREATE INDEX idx_predictions_fixture_id ON predictions(fixture_id);  -- Join performance
CREATE INDEX idx_predictions_player_id ON predictions(player_id);    -- Player-based queries
CREATE INDEX idx_file_metadata_filename ON file_metadata(filename);  -- Change detection
```

### Data Volume (Updated)

- **Teams**: ~23 Premier League teams
- **Bookmakers**: ~19 bookmakers  
- **Fixtures**: ~380 fixtures per season
- **Gameweeks**: 38 gameweeks per season
- **Odds**: ~57,000 records per full season
- **Summary**: ~380 summaries per season
- **FPL Players**: ~700 Premier League players
- **FPL Scores**: ~15,000-25,000 performance records per season
- **FPL Bootstrap**: ~700 cached player summaries per season
- **Prediction Players**: ~26 active league participants (NEW)
- **Predictions**: ~9,880 predictions per season (26 players × 380 fixtures) (NEW)
- **File Metadata**: ~38 tracked files per season (NEW)

### Data Cleanup (Updated)
- **Old Sample Files**: Automatically managed (configurable retention)
- **Log Files**: Manual cleanup of old daily logs
- **Stale Data**: Consider archiving old season data
- **Bootstrap Cache**: Automatically updated with each fetch
- **Prediction Files**: Processed incrementally based on file changes (NEW)
- **Database Integrity**: Foreign key constraints maintain referential integrity (NEW)