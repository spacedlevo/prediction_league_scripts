# Fantasy Premier League Data Guide

Comprehensive guide for using the FPL data fetching system in the Prediction League Script project.

## Overview

The FPL data system fetches player performance data from the official Fantasy Premier League API and maintains it in the `fantasy_pl_scores` table with **bootstrap-based change detection** for optimal performance. The system dramatically reduces processing time on subsequent runs by only fetching data for players whose key metrics have changed.

## Quick Start

```bash
# Fetch latest FPL data (optimized with bootstrap detection)
python scripts/fpl/fetch_fpl_data.py

# Test with sample data first
python scripts/fpl/fetch_fpl_data.py --test

# See what would change without making updates
python scripts/fpl/fetch_fpl_data.py --dry-run

# Use concurrent processing with custom worker count
python scripts/fpl/fetch_fpl_data.py --max-workers 10

# Debug bootstrap change detection
python scripts/fpl/fetch_fpl_data.py --debug --dry-run
```

## System Architecture

### Data Flow (Optimized)
1. **Bootstrap API Call**: Fetch list of all ~700 Premier League players with summary stats
2. **Bootstrap Change Detection**: Compare current bootstrap data against cached version
3. **Smart Filtering**: Only process players whose key metrics have changed
4. **Concurrent Player Calls**: Get detailed performance history for filtered players using ThreadPoolExecutor
5. **Team Mapping**: Convert FPL team IDs to database team_id references
6. **Fixture Mapping**: Convert FPL fixture IDs to database fixture_id references
7. **Upsert Operations**: Insert new records or update only changed data
8. **Sample Backup**: Save API responses for testing and debugging

### Performance Characteristics
- **First Run**: ~20-30 minutes (processes all players, creates bootstrap cache)
- **Subsequent Runs**: **Seconds to minutes** (only processes changed players)
- **Typical Reduction**: 60-80% fewer API calls after initial run
- **Concurrent Processing**: 5-10x faster API calls with configurable workers

### Database Integration
- **Target Table**: `fantasy_pl_scores` (now includes `team_id` column)
- **Bootstrap Cache**: `fpl_players_bootstrap` table for change detection
- **Key Relationships**: 
  - Links to `fixtures` table via `fixture_id`
  - Links to `teams` table via `team_id` (NEW)
- **Season Mapping**: Currently maps to 2025/2026 season
- **Team Mapping**: FPL team IDs mapped to database team_id values
- **Indexes**: Optimized for player_id, gameweek, fixture_id, and team_id queries

## Command Line Options

### Basic Usage
```bash
python scripts/fpl/fetch_fpl_data.py [OPTIONS]
```

### Available Options
- `--test`: Use cached sample data instead of live API calls
- `--dry-run`: Show what would change without making database updates
- `--cleanup-count N`: Keep N most recent sample files (default: 5)
- `--max-workers N`: Number of concurrent API requests (default: 5, recommended: 2-10)
- `--debug`: Enable detailed bootstrap change detection logging

### Usage Examples
```bash
# Production data fetch (optimized)
python scripts/fpl/fetch_fpl_data.py

# Development testing
python scripts/fpl/fetch_fpl_data.py --test --dry-run

# High-performance concurrent processing
python scripts/fpl/fetch_fpl_data.py --max-workers 10

# Debug bootstrap change detection
python scripts/fpl/fetch_fpl_data.py --debug --dry-run --max-workers 2

# Conservative API usage (slower but gentler)
python scripts/fpl/fetch_fpl_data.py --max-workers 2

# Custom sample management
python scripts/fpl/fetch_fpl_data.py --cleanup-count 10

# Disable sample cleanup
python scripts/fpl/fetch_fpl_data.py --cleanup-count 0
```

## Data Schema

### Player Performance Metrics (33 fields)

**Basic Statistics**:
- `player_name`, `player_id`, `gameweek`
- `total_points`, `minutes`, `starts`
- `goals_scored`, `assists`, `clean_sheets`
- `goals_conceded`, `own_goals`
- `penalties_saved`, `penalties_missed`
- `yellow_cards`, `red_cards`, `saves`

**Advanced Metrics**:
- `bonus`, `bps` (Bonus Point System)
- `influence`, `creativity`, `threat`, `ict_index`
- `expected_goals`, `expected_assists`
- `expected_goal_involvements`, `expected_goals_conceded`

**Transfer & Ownership Data**:
- `value` (player price in FPL)
- `transfers_in`, `transfers_out`, `transfers_balance`
- `selected` (ownership percentage)

**Match Context**:
- `fixture_id` (links to fixtures table)
- `team_id` (links to teams table - NEW)
- `was_home` (boolean - played at home)

## API Management

### Rate Limiting
- **Delay Range**: 1-3 seconds between player requests
- **Concurrent Processing**: 2-10 parallel requests (configurable)
- **Random Intervals**: Prevents API pattern detection
- **Timeout Protection**: 30-second limit per request
- **Error Recovery**: Individual player failures don't stop process
- **Smart Filtering**: Only processes players with actual changes

### API Endpoints Used
1. **Bootstrap**: `https://fantasy.premierleague.com/api/bootstrap-static/`
   - Gets all player basic information
   - Called once per fetch

2. **Element Summary**: `https://fantasy.premierleague.com/api/element-summary/{player_id}/`
   - Gets detailed player history
   - **Optimized**: Only called for players with bootstrap changes
   - **Concurrent**: Multiple requests processed in parallel

### Error Handling
- **Network Timeouts**: Logged and skipped
- **API Rate Limits**: Graceful backoff
- **Data Format Changes**: Individual record validation
- **Database Errors**: Transaction rollback with detailed logging

## Efficient Updates

### Bootstrap Change Detection Strategy
The system uses a two-tier approach for maximum efficiency:

**Level 1 - Bootstrap Detection:**
- Compares current bootstrap API data against cached `fpl_players_bootstrap` table
- Tracks 23+ key fields: minutes, total_points, ict_index, goals_scored, assists, etc.
- Only processes players where these summary fields have changed
- **Result**: 60-80% reduction in API calls after initial run

**Level 2 - Record-Level Detection:**
- For changed players, compares detailed gameweek data against existing records
- Only updates database records where specific performance data has changed
- Handles floating-point precision issues (e.g., "0.00" vs 0.0)
- **Result**: Efficient database operations with minimal writes

### Upsert Implementation
```sql
INSERT OR REPLACE INTO fantasy_pl_scores (...) VALUES (...)
```
- Atomic operation with proper conflict resolution
- Maintains database integrity and foreign key relationships
- Handles both new records and updates efficiently

### Performance Optimization

#### Recent Improvements (2025-08-31)
- **Field Optimization**: Reduced bootstrap monitoring from 23 to 13 essential fields (65% reduction)
- **Essential Fields Only**: Now tracks only gameplay statistics: `total_points`, `minutes`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `saves`, `yellow_cards`, `red_cards`, `bonus`, `bps`
- **Eliminated False Positives**: No longer monitors market/popularity metrics that don't affect gameplay
- **Reduced API Calls**: Fewer false changes mean significantly fewer individual player API requests

#### Core Optimizations
- **Bootstrap Cache**: `fpl_players_bootstrap` table eliminates redundant API calls
- **Concurrent Processing**: ThreadPoolExecutor with configurable worker count
- **Team Mapping Cache**: FPL team ID to database team_id mapping loaded once
- **Fixture Mapping Cache**: Loads once, used for all players
- **Existing Data Cache**: Compares changes in memory
- **Smart Type Handling**: Proper numeric comparison handles API format variations
- **Index Usage**: Leverages database indexes for fast lookups

## Bootstrap Cache System

### fpl_players_bootstrap Table
The system maintains a dedicated table to track player summary statistics for change detection:

```sql
CREATE TABLE fpl_players_bootstrap (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL,
    team_id INTEGER,              -- FPL team ID
    db_team_id INTEGER,          -- Database team_id (mapped)
    position TEXT,               -- Player position (1-4)
    minutes INTEGER,             -- Total minutes played
    total_points INTEGER,        -- Total FPL points
    ict_index REAL,             -- ICT index
    -- ... 20+ additional fields for comprehensive change detection
    last_updated TIMESTAMP,
    season TEXT,
    FOREIGN KEY (db_team_id) REFERENCES teams(team_id)
);
```

### Bootstrap Benefits
- **Instant Detection**: Identifies changed players without individual API calls
- **Team Integration**: Maps FPL teams to database team records
- **Historical Tracking**: Maintains change history for analysis
- **Debug Support**: `--debug` flag shows exactly which fields changed

## Sample Data System

### File Structure
```
samples/fantasypl/
├── fpl_data_20250829_143022.json  # Most recent
├── fpl_data_20250829_120515.json
├── fpl_data_20250828_181203.json
├── fpl_data_20250828_143891.json
└── fpl_data_20250827_162344.json  # Oldest kept
```

### Sample File Format
```json
{
  "players": [...],           # Bootstrap data (all players)
  "player_scores": [...],     # Processed performance records (changed players only)
  "team_mapping": {...},      # FPL team ID to database team_id mapping
  "metadata": {
    "fetch_time": "2025-08-29T14:30:22",
    "total_players": 709,
    "players_updated": 156,   # NEW: Only changed players processed
    "total_records": 1247,    # Records for changed players only
    "api_errors": 2,
    "season": "2025/2026"
  }
}
```

### Cleanup Management
- **Default**: Keep 5 most recent files
- **Configurable**: `--cleanup-count` option
- **Automatic**: Runs after each successful fetch
- **Safety**: Never deletes all files

## Logging System

### Log Files
- **Location**: `logs/fpl_fetch_YYYYMMDD.log`
- **Rotation**: Daily log files
- **Formats**: Timestamped entries with log levels

### Log Information
- API request progress and timing
- Player processing success/failure rates
- Database operation statistics
- Error details with context
- Performance metrics

### Example Log Output

**First Run (Full Processing):**
```
2025-08-29 14:30:22 - INFO - Starting FPL data fetch process...
2025-08-29 14:30:23 - INFO - Fetching FPL bootstrap data...
2025-08-29 14:30:25 - INFO - Retrieved 709 players from FPL API
2025-08-29 14:30:25 - INFO - Loading team mapping...
2025-08-29 14:30:25 - INFO - Loaded 20 team mappings
2025-08-29 14:30:25 - INFO - Loading existing bootstrap data for comparison...
2025-08-29 14:30:25 - INFO - Loaded 0 existing bootstrap records
2025-08-29 14:30:25 - INFO - Players to update: 709 total (709 new, 0 changed)
2025-08-29 14:30:25 - INFO - Fetching individual player history for 709 players using 5 concurrent workers...
2025-08-29 14:35:42 - INFO - Collected 4589 player performance records
2025-08-29 14:35:43 - INFO - Database operations: 234 inserted, 156 updated, 4199 unchanged
2025-08-29 14:35:45 - INFO - FPL data fetch process completed successfully
```

**Subsequent Run (Optimized Processing):**
```
2025-08-29 15:45:12 - INFO - Starting FPL data fetch process...
2025-08-29 15:45:13 - INFO - Fetching FPL bootstrap data...
2025-08-29 15:45:14 - INFO - Retrieved 709 players from FPL API
2025-08-29 15:45:14 - INFO - Loading existing bootstrap data for comparison...
2025-08-29 15:45:15 - INFO - Loaded 709 existing bootstrap records
2025-08-29 15:45:16 - INFO - Players to update: 0 total (0 new, 0 changed)
2025-08-29 15:45:16 - INFO - Skipping 709 unchanged players
2025-08-29 15:45:16 - INFO - No players need updating - using existing data
2025-08-29 15:45:16 - INFO - FPL data fetch process completed successfully
```

## Troubleshooting

### Common Issues

**API Rate Limiting**:
- Symptoms: Multiple timeout errors
- Solution: Script handles automatically with backoff
- Check: API response headers in logs

**Fixture Mapping Errors**:
- Symptoms: "No fixture mapping found" warnings
- Solution: Ensure current season fixtures are loaded
- Check: `fixtures` table has 2025/2026 season data

**Database Lock Errors**:
- Symptoms: "Database is locked" errors
- Solution: Ensure no other processes accessing database
- Check: Close other database connections

**Missing Sample Data**:
- Symptoms: "--test" mode fails
- Solution: Run live fetch once to create sample data
- Check: `samples/fantasypl/` directory exists

### Performance Tips

**For Large Updates**:
- Use `--dry-run` first to see scope of changes
- Monitor log files for progress
- **First Run**: Expect 20-30 minutes (bootstrap cache creation)
- **Subsequent Runs**: Expect seconds to minutes (optimized)

**For Development**:
- Always use `--test` mode to avoid API limits
- Use `--dry-run` to validate logic changes
- Use `--debug` to troubleshoot bootstrap change detection
- Keep cleanup count low to save disk space

**Concurrent Processing**:
- Use `--max-workers 10` for faster processing (higher API load)
- Use `--max-workers 2` for conservative API usage
- Default of 5 workers provides good balance

**Bootstrap Optimization**:
- First run creates bootstrap cache and processes all players
- Subsequent runs only process players with changed statistics
- Use `--debug` to see exactly which players/fields triggered updates

## Integration Examples

### Basic Database Queries
```sql
-- Top scorers current gameweek
SELECT player_name, total_points 
FROM fantasy_pl_scores 
WHERE gameweek = (SELECT MAX(gameweek) FROM fantasy_pl_scores)
ORDER BY total_points DESC LIMIT 10;

-- Players with highest expected goals
SELECT player_name, SUM(expected_goals) as total_xg
FROM fantasy_pl_scores 
GROUP BY player_id, player_name
ORDER BY total_xg DESC LIMIT 10;

-- Most transferred in players
SELECT player_name, SUM(transfers_in) as total_transfers_in
FROM fantasy_pl_scores 
GROUP BY player_id, player_name
ORDER BY total_transfers_in DESC LIMIT 10;
```

### Team Analysis (NEW)
```sql
-- Player performance by team (using new team_id column)
SELECT t.team_name, 
       COUNT(*) as player_count,
       AVG(fps.total_points) as avg_points_per_player
FROM fantasy_pl_scores fps
JOIN teams t ON fps.team_id = t.team_id
WHERE fps.gameweek = (SELECT MAX(gameweek) FROM fantasy_pl_scores)
GROUP BY t.team_id, t.team_name
ORDER BY avg_points_per_player DESC;

-- Fixture Analysis
SELECT f.home_teamid, f.away_teamid, 
       AVG(fps.total_points) as avg_points
FROM fantasy_pl_scores fps
JOIN fixtures f ON fps.fixture_id = f.fixture_id
GROUP BY f.home_teamid, f.away_teamid
ORDER BY avg_points DESC;
```

## Best Practices

### Development Workflow
1. **Test First**: Always use `--test --dry-run` for development
2. **Monitor Logs**: Check daily log files for issues
3. **Sample Management**: Keep recent samples for debugging
4. **Database Backups**: Backup before major changes

### Production Usage
1. **Schedule Regularly**: Run after gameweek completion
2. **Monitor API Health**: Watch for increased error rates
3. **Database Maintenance**: Regular cleanup and optimization
4. **Log Monitoring**: Set up alerts for repeated failures

### Error Recovery
1. **Individual Failures**: Script continues despite single player errors
2. **Network Issues**: Automatic timeout and retry handling
3. **Database Problems**: Transaction rollback preserves data integrity
4. **API Changes**: Detailed logging helps identify format changes

This guide provides comprehensive coverage of the FPL data system. For additional support, check the main project documentation and log files.