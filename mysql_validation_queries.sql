-- MySQL Validation Queries for PythonAnywhere Console
-- Copy and paste these queries into your MySQL console

-- 1. Check all tables exist
SHOW TABLES;

-- 2. Record counts (should match SQLite exactly)
SELECT 'teams' as table_name, COUNT(*) as records FROM teams
UNION ALL
SELECT 'gameweeks', COUNT(*) FROM gameweeks  
UNION ALL
SELECT 'players', COUNT(*) FROM players
UNION ALL
SELECT 'fixtures', COUNT(*) FROM fixtures
UNION ALL
SELECT 'results', COUNT(*) FROM results
UNION ALL
SELECT 'predictions', COUNT(*) FROM predictions
UNION ALL
SELECT 'last_update', COUNT(*) FROM last_update
ORDER BY table_name;

-- 3. Sample data from key tables
SELECT 'Teams Sample:' as info;
SELECT team_id, team_name, fpl_id FROM teams ORDER BY team_id LIMIT 3;

SELECT 'Current Gameweek:' as info;
SELECT * FROM gameweeks WHERE current_gameweek = 1;

SELECT 'Recent Fixtures:' as info;
SELECT f.fixture_id, ht.team_name as home_team, at.team_name as away_team, 
       f.gameweek, f.season
FROM fixtures f
JOIN teams ht ON f.home_teamid = ht.team_id
JOIN teams at ON f.away_teamid = at.team_id
WHERE f.season = '2025/2026'
ORDER BY f.gameweek DESC, f.fixture_id DESC LIMIT 5;

SELECT 'Active Players:' as info;
SELECT player_name, paid, active FROM players 
WHERE active = 1 ORDER BY player_name LIMIT 5;

SELECT 'Recent Predictions:' as info;
SELECT p.prediction_id, pl.player_name, p.home_goals, p.away_goals, p.predicted_result
FROM predictions p
JOIN players pl ON p.player_id = pl.player_id
ORDER BY p.prediction_id DESC LIMIT 5;

-- 4. Data quality checks
SELECT 'Foreign Key Check - Orphaned Results:' as info;
SELECT COUNT(*) as orphaned_count
FROM results r 
LEFT JOIN fixtures f ON r.fixture_id = f.fixture_id 
WHERE r.fixture_id IS NOT NULL AND f.fixture_id IS NULL;

SELECT 'Foreign Key Check - Orphaned Predictions:' as info;
SELECT COUNT(*) as orphaned_count
FROM predictions p
LEFT JOIN fixtures f ON p.fixture_id = f.fixture_id
WHERE p.fixture_id IS NOT NULL AND f.fixture_id IS NULL;

-- 5. Summary statistics
SELECT 'Prediction Activity by Active Player:' as info;
SELECT pl.player_name, COUNT(p.prediction_id) as prediction_count
FROM players pl
LEFT JOIN predictions p ON pl.player_id = p.player_id  
WHERE pl.active = 1
GROUP BY pl.player_id, pl.player_name
HAVING COUNT(p.prediction_id) > 0
ORDER BY prediction_count DESC LIMIT 10;

SELECT 'Fixtures by Season:' as info;
SELECT season, COUNT(*) as fixture_count, MIN(gameweek) as min_gw, MAX(gameweek) as max_gw
FROM fixtures 
GROUP BY season 
ORDER BY season DESC;