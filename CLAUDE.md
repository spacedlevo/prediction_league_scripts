# CLAUDE.md - Development Guidelines

Guidelines for Python development in this hobby project, optimized for simplicity and maintainability.

## Project Philosophy

This is a **hobby project for personal use**, not a commercial application. The development approach prioritizes:
- **Simplicity over complexity**
- **Readability over performance optimization**
- **Self-documenting code over extensive comments**
- **Practical functionality over academic perfection**

## Python Best Practices for Hobby Development

### 1. Function Design

**Keep functions simple and focused:**
```python
# Good - Single responsibility, clear purpose
def get_team_id_by_odds_api_name(team_cache, team_name):
    """Get team_id from cached team mapping"""
    return team_cache.get(team_name.lower())

# Avoid - Multiple responsibilities
def process_team_and_update_database_and_log(team_name, cursor, logger):
    # Too many responsibilities in one function
```

**Use descriptive function names:**
```python
# Good - Function name explains what it does
def cleanup_old_sample_files(output_dir, keep_count=5):
    """Keep only the latest N sample files, remove older ones"""

# Avoid - Vague naming
def cleanup(dir, count):
    # What is being cleaned up? What does count mean?
```

**Prefer pure functions when possible:**
```python
# Good - Pure function, easy to test
def calculate_average_odds(odds_list):
    """Calculate average from list of odds values"""
    return sum(odds_list) / len(odds_list) if odds_list else None

# Less ideal - Function with side effects
def calculate_and_log_average_odds(odds_list, logger):
    avg = sum(odds_list) / len(odds_list) if odds_list else None
    logger.info(f"Calculated average: {avg}")
    return avg
```

### 2. Self-Documenting Code

**Write code that explains itself:**
```python
# Good - Variable names explain the logic
def load_team_mapping(cursor):
    cursor.execute("SELECT odds_api_name, team_id FROM teams WHERE odds_api_name IS NOT NULL")
    # Dictionary comprehension with clear intent
    return {api_name.lower(): team_id for api_name, team_id in cursor.fetchall()}

# Avoid - Code that needs comments to understand
def load_mapping(c):
    c.execute("SELECT odds_api_name, team_id FROM teams WHERE odds_api_name IS NOT NULL")
    # Create lookup dict (comment needed because code isn't clear)
    return {x[0].lower(): x[1] for x in c.fetchall()}
```

**Use meaningful variable names:**
```python
# Good - Clear intent
processed_count = 0
skipped_count = 0
for match in odds_data:
    if process_match(match):
        processed_count += 1
    else:
        skipped_count += 1

# Avoid - Generic naming
count1 = 0
count2 = 0
for item in data:
    if process(item):
        count1 += 1
    else:
        count2 += 1
```

### 3. Error Handling

**Handle errors gracefully with context:**
```python
# Good - Specific error handling with context
try:
    response = requests.get(url, params=params, timeout=30)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"API request failed with status {response.status_code}: {response.text}")
        return None
except Timeout:
    logger.error("API request timed out after 30 seconds")
    return None
except RequestException as e:
    logger.error(f"API request failed: {e}")
    return None
```

**Use transactions for database operations:**
```python
# Good - Atomic operations with rollback
def process_odds_data(odds_data, logger):
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    try:
        # Process all data
        for match in odds_data:
            process_match(match, cursor)
        conn.commit()
        logger.info("Successfully processed all odds data")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing odds data: {e}")
        raise
    finally:
        conn.close()
```

### 4. Logging

**Use informative logging messages:**
```python
# Good - Provides context and actionable information
logger.info(f"Loading team mappings...")
team_cache = load_team_mapping(cursor)
logger.info(f"Loaded {len(team_cache)} team mappings")

if not home_team_id or not away_team_id:
    logger.warning(f"Skipping match {home_team} vs {away_team} - teams not found in database")
    skipped_count += 1
    continue

logger.info(f"Successfully processed {processed_count} odds records")
if skipped_count > 0:
    logger.warning(f"Skipped {skipped_count} matches due to missing team mappings")
```

### 5. Configuration Management

**Centralize configuration:**
```python
# Good - Configuration loaded once and passed around
def load_config():
    keys_file = Path(__file__).parent.parent.parent / "keys.json"
    with open(keys_file, 'r') as f:
        return json.load(f)

def main():
    config = load_config()
    odds_api_key = config["odds_api_key"]
    # Use throughout application
```

**Use pathlib for file paths:**
```python
# Good - Cross-platform path handling
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
log_dir = Path(__file__).parent.parent.parent / "logs"
```

### 6. Command Line Interface

**Provide helpful command line options:**
```python
def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch odds data from API and update database')
    parser.add_argument('--test', action='store_true', 
                       help='Run in test mode with sample data')
    parser.add_argument('--cleanup-count', type=int, default=5,
                       help='Number of sample files to keep (0 to disable cleanup)')
    return parser.parse_args()
```

### 7. Database Operations

**Use parameterized queries:**
```python
# Good - Safe from SQL injection
cursor.execute("""
    SELECT fixture_id FROM fixtures 
    WHERE home_teamid = ? AND away_teamid = ? 
    AND datetime(kickoff_dttm) = datetime(?)
""", (home_team_id, away_team_id, kickoff_time))

# Avoid - String formatting in SQL
query = f"SELECT * FROM teams WHERE name = '{team_name}'"  # SQL injection risk
```

**Cache database lookups:**
```python
# Good - Cache frequently accessed data
def load_team_mapping(cursor):
    cursor.execute("SELECT odds_api_name, team_id FROM teams WHERE odds_api_name IS NOT NULL")
    return {name.lower(): team_id for name, team_id in cursor.fetchall()}

# Use cache for lookups instead of repeated database queries
team_cache = load_team_mapping(cursor)
home_team_id = team_cache.get(home_team.lower())
```

## Scripts Structure

### Simple Script Template
```python
#!/usr/bin/env python3
"""
Brief description of what this script does.
"""

import logging
from pathlib import Path
import argparse

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def main_function(args, logger):
    """Main logic of the script"""
    logger.info("Starting script execution...")
    # Implementation here
    logger.info("Script execution completed")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Script description')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    main_function(args, logger)
```

## Testing Approach

### Test with Sample Data
```python
def test_with_sample_data():
    """Test the script using existing sample data"""
    logger = setup_logging()
    logger.info("Starting test with sample data...")
    
    sample_dir = Path(__file__).parent.parent.parent / "samples" / "odds_api"
    sample_files = list(sample_dir.glob("odds_data_*.json"))
    
    if sample_files:
        sample_file = max(sample_files, key=lambda f: f.stat().st_mtime)
        logger.info(f"Testing with sample data from: {sample_file}")
        
        with open(sample_file, 'r') as f:
            test_data = json.load(f)
        
        process_data(test_data, logger)
        logger.info("Test completed successfully")
    else:
        logger.error("No sample data files found")
```

## Comments Policy

**Avoid obvious comments:**
```python
# Bad - Comment states the obvious
count = 0  # Initialize counter to zero
for item in items:  # Loop through items
    count += 1  # Increment counter

# Good - Code is self-explanatory
processed_count = 0
for match in matches:
    if process_match(match):
        processed_count += 1
```

**Use comments for business logic:**
```python
# Good - Explains WHY, not WHAT
def cleanup_old_sample_files(output_dir, keep_count=5):
    """Keep only the latest N sample files, remove older ones"""
    files = list(glob.glob(str(output_dir / "*odds_data_*.json")))
    
    if len(files) <= keep_count:
        return
    
    # Sort files by modification time (newest first) to preserve recent data
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Remove files beyond the keep_count to manage disk space
    files_to_remove = files[keep_count:]
```

## Development Tools

### Virtual Environment Usage
**IMPORTANT**: Always use the virtual environment when running Python scripts:
```bash
# Activate virtual environment first
source venv/bin/activate

# Run scripts with venv Python
python scripts/prediction_league/script.py --test
python scripts/fpl/script.py
python scripts/odds-api/script.py

# Or use direct path to venv Python
./venv/bin/python scripts/prediction_league/script.py --test
```

### Key Dependencies
The project virtual environment includes:
- `requests` - HTTP client for API calls
- `paramiko` - SSH/SFTP for PythonAnywhere uploads  
- `tqdm` - Progress bars for long operations
- `pytz` - **REQUIRED** - Timezone handling for UK time display (BST/GMT conversion)

### Recommended Command Line Testing
```bash
# Activate venv first
source venv/bin/activate

# Run with test data first  
python script.py --test

# Then run with live data
python script.py

# Monitor logs
tail -f logs/script_$(date +%Y%m%d).log
```

### Database Upload System
```bash
# Test database upload system
./venv/bin/python scripts/database/monitor_and_upload.py --test

# Dry run to check logic  
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run

# Force upload regardless of changes
./venv/bin/python scripts/database/monitor_and_upload.py --force

# Set up cron for automated uploads (every minute) - DEPRECATED
# * * * * * cd /path/to/project && ./venv/bin/python scripts/database/monitor_and_upload.py >/dev/null 2>&1

# Use Master Scheduler instead (recommended)
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh
```

**Upload System Features:**
- **Change Detection** - Monitors last_update table for database modifications
- **Automatic Uploads** - Triggers on any table changes since last upload  
- **Health Check** - Fallback uploads every 30 minutes if no changes detected
- **Transaction Integrity** - Fixed Aug 2025: Scripts now properly update timestamps after database changes
- **Smart Timestamps** - Fixed Sep 2025: Scripts only update timestamps when actual data changes occur (no more unnecessary uploads)

### Dropbox OAuth2 System
```bash
# Set up Dropbox OAuth2 tokens (first-time or when expired)
./venv/bin/python scripts/prediction_league/setup_dropbox_oauth.py

# Test Dropbox prediction cleaning
./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --dry-run

# Process specific gameweek
./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --gameweek 3
```

**OAuth2 Features:**
- **Auto-refresh tokens** - No manual token management needed
- **Legacy token migration** - Seamless upgrade from old tokens
- **Interactive setup** - Browser-based authorization flow
- **Secure storage** - Tokens safely stored in keys.json
- **Permission Preservation** - Scripts maintain file permissions when updating tokens (Sep 2025 fix)

### Automated Predictions System (Dual-File Generation)
```bash
# Test automated predictions generation (checks for upcoming gameweeks)
./venv/bin/python scripts/prediction_league/automated_predictions.py

# Force run bypassing all checks (development/testing)
./venv/bin/python scripts/prediction_league/automated_predictions.py --force

# Force run with specific gameweek
./venv/bin/python scripts/prediction_league/automated_predictions.py --force --gameweek 5

# The script automatically runs hourly via scheduler when deadline is within 36 hours
# Creates predictions based on intelligent strategy recommendations (1-0 vs 2-1)
```

**System Features:**
- **Dual-File Upload** - Automatically writes predictions to two Dropbox locations:
  * `/predictions_league/odds-api/predictions{gameweek}.txt` (new file creation)
  * `/predictions_league/Predictions/2025_26/gameweek{gameweek}.txt` (append/create logic)
- **Intelligent Content Management** - Downloads existing gameweek files and appends new predictions
- **UK Timezone Notifications** - Uses pytz for accurate BST/GMT deadline display in Pushover notifications
- **Error Recovery** - Continues operation if one upload location fails
- **Gameweek Validation** - Only runs when deadline is within 36 hours
- **Duplicate Prevention** - Database tracking prevents multiple runs within 1-hour window

**Prediction Logic:**
- **Odds-Based Strategy** - Analyzes home/away odds to determine favorite
- **Consistent Format** - "Tom Levin" header with team capitalization
- **Scoreline Strategy** - Favorite wins 2-1, underdog wins 1-2, default 1-1 for missing odds
- **Fixture Integration** - Uses SQL query to fetch gameweek fixtures with odds data

**Scheduler Integration:**
- **Hourly Execution** - Runs automatically every hour via master scheduler
- **Deadline-Based Activation** - Only processes when gameweek deadline approaches
- **Notification System** - Sends predictions and fixture lists via Pushover
- **Database Tracking** - Updates last_update table to trigger automated uploads

### Pulse API System (Match Data Collection)
```bash
# Test pulse API data collection with sample data
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --test

# Dry run to preview changes without database updates
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --dry-run

# Normal operation - collect missing pulse data
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py

# Sequential processing for gentle API usage
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --max-workers 1 --delay 3.0

# Force fetch all fixtures regardless of existing data
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --force-all

# Process specific season
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --season "2024/2025"
```

**Pulse API Features:**
- **Change Detection** - Only fetches data for finished fixtures missing pulse data
- **Rate Limiting** - Respectful API usage with configurable delays between requests
- **Error Recovery** - Robust handling of API failures with exponential backoff retry logic
- **Concurrent Processing** - Optional threading for faster data collection (default: 3 workers)
- **Smart Caching** - Saves successful responses to avoid re-fetching during development
- **Database Integration** - Uses existing tables: match_officials, team_list, match_events
- **Team Mapping** - Maps pulse team IDs to database team_id for proper relationships
- **Sample Management** - Automatic cleanup of old sample files with configurable retention

**Data Collected:**
- **Match Officials** - Referees and linesmen for each match
- **Team Lists** - Starting lineups and substitutes with positions, shirt numbers, captain status
- **Match Events** - Goals, cards, substitutions with precise timestamps and player/team details

**Scheduler Integration:**
- **Daily Collection** - Runs automatically at 8 AM via master scheduler
- **Change Triggering** - Updates last_update table to trigger automated database uploads
- **Lock Management** - Prevents multiple concurrent executions

### Football-Data.co.uk System (Historical Match Data)
```bash
# Import historical Premier League data (1993-2025)
./venv/bin/python scripts/football_data/migrate_legacy_data.py --test --force

# Download current season data weekly
./venv/bin/python scripts/football_data/fetch_football_data.py --dry-run

# Test with sample data
./venv/bin/python scripts/football_data/fetch_football_data.py --test
```

**Football-Data System Features:**
- **Complete Historical Integration** - 12,324 Premier League matches from 1993-2025 (32 seasons, 100% coverage)
- **Rich Match Data** - Results, statistics, referee info, comprehensive betting odds
- **Team Mapping** - Complete translation for all 51 historical Premier League teams 
- **Weekly Updates** - Automated downloads of current season data every Sunday
- **Change Detection** - Smart updates only when actual data changes occur
- **Sample Management** - Automatic cleanup with configurable retention (5 files default)

**Data Includes:**
- **Match Results** - Full-time/half-time scores and results
- **Team Statistics** - Shots (total/on target), corners, cards, fouls for each team
- **Official Information** - Referee assignments for each match
- **Betting Markets** - Home/Draw/Away odds from multiple bookmakers (Bet365, William Hill, etc.)
- **Advanced Markets** - Over/under goals, Asian handicap, correct score odds

**Scheduler Integration:**
- **Weekly Collection** - Runs automatically on Sundays at 9 AM via master scheduler
- **Change Triggering** - Updates last_update table to trigger automated database uploads
- **Configuration Control** - `ENABLE_FETCH_FOOTBALL_DATA=true/false` in scheduler config

### Master Scheduler System
```bash
# Set up automated execution (single cron entry manages everything)
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh

# Check scheduler status and configuration
./venv/bin/python scripts/scheduler/scheduler_status.sh

# Monitor scheduler activity
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log

# Enable debug mode for detailed timing analysis
echo "DEBUG_MODE=true" >> scripts/scheduler/scheduler_config.conf
```

**Scheduler Features (September 2025 Update):**
- **Centralized Orchestration** - Single cron entry manages all script execution
- **Intelligent Timing** - Scripts run at optimal intervals based on data requirements
- **Process Management** - Lock files prevent overlapping executions
- **Error Handling** - Individual script failures don't affect other scripts
- **Configurable Control** - Enable/disable individual scripts via configuration

**Execution Schedule:**
- **Every Minute**: fetch_results.py, monitor_and_upload.py (with 10s sequencing)
- **Every 15 Minutes**: clean_predictions_dropbox.py
- **Every 30 Minutes**: fetch_fixtures_gameweeks.py
- **Every Hour**: automated_predictions.py (dual-file upload with UK timezone notifications)
- **Daily 7 AM**: fetch_fpl_data.py, fetch_odds.py
- **Daily 8 AM**: fetch_pulse_data.py
- **Weekly Sundays 9 AM**: fetch_football_data.py (NEW - September 2025)
- **Daily 2 AM**: Cleanup old logs and locks

**Configuration Override (scripts/scheduler/scheduler_config.conf):**
```bash
# Emergency disable (stops all scripts)
SCHEDULER_ENABLED=false

# Individual script control
ENABLE_FETCH_RESULTS=true
ENABLE_MONITOR_UPLOAD=true
ENABLE_CLEAN_PREDICTIONS=true
ENABLE_FETCH_FIXTURES=true
ENABLE_AUTOMATED_PREDICTIONS=true
ENABLE_FETCH_FPL_DATA=true
ENABLE_FETCH_ODDS=true
ENABLE_FETCH_PULSE_DATA=true
ENABLE_FETCH_FOOTBALL_DATA=true

# Debug output for timing analysis
DEBUG_MODE=false
```

## Critical System Fixes (August 2025 - September 2025)

### Database Upload System Issues Resolved

**Problem**: Remote scheduler wasn't triggering database uploads despite database changes, and upload timestamps weren't being updated properly.

**Root Causes Identified & Fixed:**

1. **Transaction Ordering Bug in fetch_results.py**
   - **Issue**: `update_last_update_table()` called AFTER `conn.commit()`
   - **Result**: Timestamp updates executed but never committed to database
   - **Fix**: Moved timestamp update BEFORE commit for transaction integrity
   - **Impact**: Results changes now properly trigger upload monitoring

2. **Missing Fixtures Timestamp Updates**
   - **Issue**: `fetch_fixtures_gameweeks.py` only updated "fixtures_gameweeks" timestamp
   - **Result**: "fixtures" table changes undetected (9-day timestamp gap)
   - **Fix**: Now updates both "fixtures" and "fixtures_gameweeks" timestamps when changes occur
   - **Impact**: Fixture changes now trigger automated uploads

3. **Timezone Conversion Bug in Match Window Detection**
   - **Issue**: Database stores UTC times but code added +1 hour offset
   - **Result**: Match window detection failed, preventing results fetching
   - **Fix**: Database times now correctly treated as UTC without conversion
   - **Impact**: Results fetching works during match windows

4. **Duplicate Predictions Data**
   - **Issue**: Fixture matching failed due to team order mismatches
   - **Result**: Multiple duplicate predictions, some fixtures unmatched
   - **Fix**: Enhanced fixture matching to try both team orders
   - **Impact**: Clean prediction data, no duplicates, all fixtures matched

5. **Unnecessary Timestamp Updates (September 2025)**
   - **Issue**: Scripts updated timestamps even when no data changed
   - **Result**: Frequent unnecessary database uploads with no actual changes
   - **Fix**: Modified scripts to only update timestamps when actual data changes occur
   - **Impact**: Reduced database upload frequency, more efficient change detection

### Verification Steps
```bash
# Check last_update table shows recent timestamps
sqlite3 data/database.db "SELECT * FROM last_update ORDER BY timestamp DESC LIMIT 5;"

# Test upload detection works
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run

# Test match window detection
./venv/bin/python scripts/fpl/fetch_results.py --override --dry-run

# Check for prediction duplicates
sqlite3 data/database.db "SELECT COUNT(*) FROM predictions p JOIN fixtures f ON p.fixture_id = f.fixture_id WHERE f.season = '2025/2026' GROUP BY f.gameweek;"
```

## Predictions Analysis System (September 2025)

### Overview

The predictions analysis system provides automated predictions based on betting odds with multiple strategies and comprehensive performance analysis across historical seasons.

### Features

**Core Functionality:**
- **Automated Predictions**: 7 different strategies for generating scoreline predictions
- **Multi-Season Analysis**: Performance comparison across historical seasons (2020-2026)
- **Strategy Performance**: Real-time points calculation and accuracy metrics
- **Season Selector**: Analyze performance for specific seasons or combined historical data
- **Smart Goals Strategy**: Advanced strategy combining 1X2 and Over/Under odds

### Database Schema Updates

**Enhanced Over/Under Support:**
```sql
-- Added to fixture_odds_summary table
ALTER TABLE fixture_odds_summary ADD COLUMN avg_over_2_5_odds REAL DEFAULT NULL;
ALTER TABLE fixture_odds_summary ADD COLUMN avg_under_2_5_odds REAL DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_fixture_odds_totals ON fixture_odds_summary(avg_over_2_5_odds, avg_under_2_5_odds);
```

**Migration Commands:**
```bash
# Run database migration for Over/Under odds
./venv/bin/python scripts/odds-api/migrate_summary_totals.py

# Refresh odds summary to populate totals
./venv/bin/python scripts/odds-api/fetch_odds.py --test
```

### Prediction Strategies

**1. Fixed Strategies:**
- **Fixed (2-1 Favourite)**: Favourite always wins 2-1
- **Fixed (2-0 Favourite)**: Favourite always wins 2-0 (clean sheet strategy)
- **Fixed (1-0 Favourite)**: Favourite always wins 1-0 (conservative strategy)

**2. Dynamic Strategies:**
- **Calibrated**: Variable scorelines based on favourite strength
  - ≤1.50 odds = 3-0/2-0
  - 1.51-2.00 = 2-1
  - 2.01-2.50 = 1-0
  - >2.50 = 1-1
- **Home/Away Bias**: Considers venue advantage
  - Home favourites: 2-0
  - Away favourites: 2-1

**3. Advanced Strategies:**
- **Poisson Model**: Mathematical distribution-based predictions (placeholder)
- **Smart Goals**: Combines 1X2 and Over/Under odds
  - Short favourite + high goals expected → 2-1 or 3-1
  - Short favourite + low goals expected → 1-0
  - Uses fallback values when Over/Under data unavailable

**4. Custom Strategy:**
- **Manual Entry**: User can enter custom predictions and see point calculations

### Smart Goals Strategy Logic

```python
# Core logic for Smart Goals strategy
if favourite_odds <= 1.67:  # Short favourite
    if goals_market_favours_high:
        if over_2_5_odds <= 1.70:
            # Very heavy over 2.5 odds
            prediction = "3-1" if home_favourite else "1-3"
        else:
            # Heavy over 2.5 odds  
            prediction = "2-1" if home_favourite else "1-2"
    else:
        # Under 2.5 favoured
        prediction = "1-0" if home_favourite else "0-1"
```

### Multi-Season Data Access

**Data Sources (Prioritized):**
1. **fixture_odds_summary**: Primary source for recent seasons with complete odds data
2. **football_stats**: Fallback source for historical data using AvgH/AvgA as 1X2 odds and Avg>2.5/Avg<2.5 for totals

**Supported Seasons:**
- **2025/2026**: Current season (primary data source)
- **2024/2025**: Recent season with odds data
- **2020-2024**: Historical seasons with fallback data
- **All Seasons**: Combined analysis across all available data
- **Historical Only**: Excludes current season for baseline comparison

### Webapp API Endpoints

**Core Endpoints:**
```bash
# Get fixtures and odds for specific gameweek
GET /api/predictions/gameweek/{gameweek}

# Get season performance analysis
GET /api/predictions/season-performance?season={season}
```

**Authentication Requirements:**
- **Main predictions page**: Requires login (`@require_auth`)
- **API endpoints**: Temporarily made public for debugging (remove auth decorators)
- **Debug endpoint**: Public access for troubleshooting

### Performance Analysis

**Metrics Calculated:**
- **Total Points**: Sum of all prediction points (2 for exact score, 1 for correct result)
- **Accuracy Rate**: Percentage of correct results predicted
- **Correct Results**: Count of matches where result (H/D/A) was correct
- **Exact Scores**: Count of matches where exact scoreline was predicted
- **Games Analyzed**: Total fixtures with both odds and results available
- **Avg Points/Game**: Average points earned per fixture

**Example Performance Results (2025/2026 season, 30 games):**
- **Smart Goals**: 18 points, 46.7% accuracy, 4 exact scores
- **Fixed (1-0)**: 18 points, 46.7% accuracy, 4 exact scores  
- **Calibrated**: 17 points, 46.7% accuracy, 3 exact scores

### Frontend Features

**Strategy Tabs:**
- Interactive strategy selection with real-time calculations
- Strategy descriptions explaining prediction logic
- Points display for completed matches

**Season Selector:**
- Dropdown for selecting analysis period
- Options: Individual seasons, all seasons, historical only
- Real-time performance comparison updates

**Bulk Prediction Tools (Custom Strategy):**
- Quick-fill options (1-0, 2-1, 1-1, 0-0)
- Apply score to all fixtures
- Clear all predictions
- Real-time points calculation

### Troubleshooting

**Common Issues:**
1. **"Loading predictions..." hanging**
   - **Cause**: JavaScript authentication errors or syntax errors
   - **Fix**: Check browser console for errors, ensure proper login

2. **Season performance 500 errors**
   - **Cause**: None values in Over/Under odds causing float() errors
   - **Fix**: Use `fixture.get('over_2_5_odds') or 1.90` instead of default parameters

3. **Duplicate variable declarations**
   - **Cause**: Multiple `const favouriteOdds` in JavaScript switch cases
   - **Fix**: Use unique variable names per strategy (e.g., `smartFavouriteOdds`)

**Debug Commands:**
```bash
# Test API endpoints directly
curl http://localhost:5000/debug
curl http://localhost:5000/api/predictions/gameweek/3
curl "http://localhost:5000/api/predictions/season-performance?season=2025/2026"

# Check Over/Under odds availability
sqlite3 data/database.db "SELECT COUNT(*) FROM fixture_odds_summary WHERE avg_over_2_5_odds IS NOT NULL;"

# Verify current gameweek logic
sqlite3 data/database.db "SELECT gameweek FROM gameweeks WHERE current_gameweek = 1 OR next_gameweek = 1 ORDER BY gameweek ASC LIMIT 1;"
```

### Development Notes

**JavaScript Error Handling:**
```javascript
// Improved error handling for authentication
fetch('/api/predictions/gameweek/' + gameweek)
    .then(response => {
        if (response.status === 200 && response.headers.get('content-type')?.includes('application/json')) {
            return response.json();
        } else if (response.url.includes('/login')) {
            throw new Error('Authentication required - please log in first');
        }
        // Handle other errors...
    })
```

**Null Value Handling:**
```python
# Safe handling of None values in odds data
over_2_5_odds = float(fixture.get('over_2_5_odds') or 1.90)  # 'or' handles None
under_2_5_odds = float(fixture.get('under_2_5_odds') or 1.90)
```

**Variable Scoping:**
```javascript
// Avoid duplicate variable declarations in switch cases
case 'calibrated':
    const favouriteOdds = Math.min(homeOdds, awayOdds);
    break;
case 'smart-goals':
    const smartFavouriteOdds = Math.min(homeOdds, awayOdds);  // Unique name
    break;
```

## Production Deployment

### Critical Dependencies for Production
When deploying to production servers (Ubuntu/systemd), ensure all dependencies are installed:

```bash
# Essential timezone dependency (service will fail without this)
pip install pytz

# Verify installation
python -c "import pytz; print('pytz installed successfully')"
```

**Common Production Issues:**
- **Service fails with exit code 3**: Usually indicates missing `pytz` dependency
- **Check logs**: `journalctl -u prediction-league.service --no-pager -l`
- **Test app import**: `python -c "import app"` to verify all dependencies

### Systemd Service Requirements
- Ensure virtual environment includes all dependencies
- Working directory must be set to webapp directory
- Config.json must be accessible with correct timezone setting

### Keys.json Permission Configuration
Critical for multi-user production environments where scripts run under different users:

```bash
# Set appropriate permissions for group access
chmod 640 keys.json                    # Owner read/write, group read
chgrp predictionleague keys.json       # Set group ownership

# Verify permissions
ls -la keys.json
# Should show: -rw-r----- 1 user predictionleague
```

**Permission Preservation (Sept 2025 Fix):**
- Scripts now preserve original file permissions when updating Dropbox tokens
- `clean_predictions_dropbox.py` (runs every 15 minutes) maintains group permissions
- `setup_dropbox_oauth.py` (manual setup) preserves permissions during token refresh
- Prevents automatic reset to 0600 (owner-only) permissions

## Summary

For this hobby project:
1. **Prioritize readability** - Code should tell a story
2. **Keep functions simple** - One clear purpose per function  
3. **Handle errors gracefully** - Always expect things to go wrong
4. **Log meaningfully** - Help future you understand what happened
5. **Test with sample data** - Don't waste API calls during development
6. **Use meaningful names** - Variables and functions should explain themselves
7. **Fail fast and clearly** - Better to stop with a clear error than continue with bad data
8. **Maintain transaction integrity** - Always update timestamps within the same transaction as data changes

Remember: This is a hobby project. Perfect is the enemy of done. Focus on code that works reliably and can be easily understood and modified months later.