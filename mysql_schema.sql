-- MySQL Schema for Core Prediction League Tables
-- Converted from SQLite schema for PythonAnywhere MySQL database

-- Teams table - Premier League teams
CREATE TABLE teams (
    team_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_id INT,
    team_name VARCHAR(100),
    available TINYINT(1) DEFAULT 0,
    strength INT,
    strength_overall_home INT,
    strength_overall_away INT,
    strength_attack_home INT,
    strength_attack_away INT,
    strength_defence_home INT,
    strength_defence_away INT,
    pulse_id INT,
    football_data_name VARCHAR(100),
    odds_api_name VARCHAR(100)
) ENGINE=InnoDB;

-- Gameweeks table - Premier League gameweek information
CREATE TABLE gameweeks (
    gameweek INT PRIMARY KEY,
    deadline_dttm DATETIME,
    deadline_date DATE,
    deadline_time TIME,
    current_gameweek TINYINT(1),
    next_gameweek TINYINT(1),
    finished TINYINT(1)
) ENGINE=InnoDB;

CREATE INDEX idx_gameweeks_current ON gameweeks(current_gameweek);
CREATE INDEX idx_gameweeks_finished ON gameweeks(finished);

-- Players table - Prediction league participants
CREATE TABLE players (
    player_id INT PRIMARY KEY,
    player_name VARCHAR(100),
    paid TINYINT(1) NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 0,
    mini_league TINYINT(1) NOT NULL DEFAULT 0,
    mini_league_paid TINYINT(1) NOT NULL DEFAULT 0,
    pundit TINYINT(1) NOT NULL DEFAULT 0,
    web_name VARCHAR(100)
) ENGINE=InnoDB;

-- Fixtures table - Match schedule and basic info
CREATE TABLE fixtures (
    fixture_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_fixture_id INT NOT NULL,
    kickoff_dttm DATETIME,
    home_teamid INT NOT NULL,
    away_teamid INT NOT NULL,
    finished TINYINT(1) DEFAULT 1,
    season VARCHAR(20),
    home_win_odds DECIMAL(8,3),
    draw_odds DECIMAL(8,3),
    away_win_odds DECIMAL(8,3),
    pulse_id INT,
    gameweek INT,
    started TINYINT(1) DEFAULT 0,
    provisional_finished TINYINT(1) DEFAULT 0,
    FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
    FOREIGN KEY (away_teamid) REFERENCES teams(team_id),
    UNIQUE KEY unique_fixture (fixture_id)
) ENGINE=InnoDB;

CREATE INDEX idx_fixtures_season ON fixtures(season);
CREATE INDEX idx_fixtures_gameweek ON fixtures(gameweek);
CREATE INDEX idx_fixtures_fpl_id ON fixtures(fpl_fixture_id);

-- Results table - Actual match results
CREATE TABLE results (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    fpl_fixture_id INT NOT NULL,
    fixture_id INT,
    home_goals INT,
    away_goals INT,
    result VARCHAR(1),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
) ENGINE=InnoDB;

-- Predictions table - User predictions
CREATE TABLE predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT,
    fixture_id INT,
    fpl_fixture_id INT,
    home_goals INT,
    away_goals INT,
    predicted_result VARCHAR(1),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    UNIQUE KEY idx_unique_player_fixture (player_id, fixture_id)
) ENGINE=InnoDB;

-- Last update table - Change tracking for sync
CREATE TABLE last_update (
    table_name VARCHAR(50) PRIMARY KEY,
    updated VARCHAR(100),
    timestamp DECIMAL(15,6)
) ENGINE=InnoDB;