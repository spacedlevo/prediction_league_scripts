-- Season Recommendations Table
-- Tracks seasonal scoring patterns and strategy recommendations
CREATE TABLE IF NOT EXISTS season_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season TEXT NOT NULL,
    current_gameweek INTEGER NOT NULL,
    total_matches INTEGER NOT NULL,
    low_scoring_matches INTEGER NOT NULL, -- matches with ≤2 total goals
    low_scoring_percentage REAL NOT NULL,
    goals_per_game_avg REAL NOT NULL,
    recommended_strategy TEXT NOT NULL, -- '1-0' or '2-1'
    confidence_level TEXT NOT NULL, -- 'early', 'moderate', 'high'
    recommendation_reason TEXT NOT NULL,
    historical_precedents TEXT, -- JSON array of similar seasons
    expected_points_improvement REAL,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, current_gameweek)
);

-- Strategy Performance Tracking Table
-- Track how different strategies perform across different season types
CREATE TABLE IF NOT EXISTS strategy_season_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    total_points INTEGER NOT NULL,
    total_matches INTEGER NOT NULL,
    correct_results INTEGER NOT NULL,
    exact_scores INTEGER NOT NULL,
    accuracy_percentage REAL NOT NULL,
    avg_points_per_game REAL NOT NULL,
    season_type TEXT, -- 'low_scoring', 'high_scoring', 'mixed'
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, strategy_name)
);

-- Historical Season Patterns Table
-- Store characteristics of historical seasons for pattern matching
CREATE TABLE IF NOT EXISTS historical_season_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season TEXT NOT NULL UNIQUE,
    total_matches INTEGER NOT NULL,
    low_scoring_matches INTEGER NOT NULL,
    low_scoring_percentage REAL NOT NULL,
    goals_per_game_avg REAL NOT NULL,
    optimal_strategy TEXT NOT NULL, -- determined from analysis
    strategy_advantage REAL NOT NULL, -- points per game advantage
    season_classification TEXT NOT NULL, -- 'low_scoring', 'high_scoring', 'mixed'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_season_recommendations_season ON season_recommendations(season);
CREATE INDEX IF NOT EXISTS idx_season_recommendations_gameweek ON season_recommendations(current_gameweek);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_season ON strategy_season_performance(season);
CREATE INDEX IF NOT EXISTS idx_historical_patterns_season ON historical_season_patterns(season);
CREATE INDEX IF NOT EXISTS idx_historical_patterns_classification ON historical_season_patterns(season_classification);