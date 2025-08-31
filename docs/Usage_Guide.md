# Usage Guide

This guide covers usage of all data fetching and monitoring scripts in the system.

## Master Scheduler System

### Overview

The Master Scheduler provides centralized orchestration of all automation scripts through a single cron job. It manages timing, process isolation, and health monitoring.

#### Installation

```bash
# Test installation
./scripts/scheduler/install_scheduler.sh --dry-run

# Install scheduler
./scripts/scheduler/install_scheduler.sh

# Check installation status
./scripts/scheduler/install_scheduler.sh --status
```

#### Configuration

Edit `scripts/scheduler/scheduler_config.conf` to control:
- Enable/disable individual scripts
- Timing adjustments
- Seasonal modes (off-season)
- Debug settings

```bash
# Key configuration options
ENABLE_FETCH_RESULTS=true
ENABLE_MONITOR_UPLOAD=true
ENABLE_CLEAN_PREDICTIONS=true
ENABLE_FETCH_FIXTURES=true
ENABLE_AUTOMATED_PREDICTIONS=true
ENABLE_FETCH_FPL_DATA=true
ENABLE_FETCH_ODDS=true

DELAY_BETWEEN_RESULTS_UPLOAD=30
OFFSEASON_MODE=false
```

#### Monitoring

```bash
# Check overall system status
./scripts/scheduler/scheduler_status.sh

# Detailed status with logs
./scripts/scheduler/scheduler_status.sh --detailed

# Health metrics only
./scripts/scheduler/scheduler_status.sh --health

# Clean old files
./scripts/scheduler/scheduler_status.sh --clean
```

#### Manual Testing

```bash
# Run scheduler once manually
./scripts/scheduler/master_scheduler.sh

# Test individual validation
./scripts/fpl/gameweek_validator.py

# Force gameweek refresh
./scripts/fpl/fetch_fixtures_gameweeks.py --force-refresh
```

## Database Monitoring Script

### Database Change Monitor & Upload

The `monitor_and_upload.py` script provides automated database change detection and PythonAnywhere upload functionality.

#### Basic Usage

##### Normal Operation (Manual/Interactive)
```bash
python scripts/database/monitor_and_upload.py
```
- Shows console output when run interactively
- Automatically detects if run from terminal vs cron
- Uploads database when changes detected
- Uploads every 30+ minutes as health check
- Logs to daily log files

##### Test Mode with Verbose Output
```bash
python scripts/database/monitor_and_upload.py --test
```
- Forces console output regardless of environment
- Performs actual upload operations  
- Useful for manual testing and validation
- Logs both to console and file

##### Dry Run Mode
```bash
python scripts/database/monitor_and_upload.py --dry-run
```
- Shows what would be uploaded without uploading
- Tests change detection logic
- Safe for development and testing
- No actual SSH connections made

##### Force Upload
```bash
python scripts/database/monitor_and_upload.py --force
```
- Forces upload regardless of changes or timing
- Useful for manual synchronization
- Bypasses all change detection logic
- Still updates upload timestamp

#### Cron Setup
```bash
# Add to crontab for minute-by-minute monitoring
* * * * * cd /home/levo/Documents/projects/prediction_league_script && ./venv/bin/python scripts/database/monitor_and_upload.py >/dev/null 2>&1
```

#### Upload Logic
- **Database Changes**: Uploads immediately when any table updated in `last_update`
- **Health Check**: Uploads every 30+ minutes even without changes
- **Process Locking**: Prevents multiple instances from running simultaneously
- **Error Recovery**: Failed uploads retry on next execution

#### Log Files
- Location: `logs/database_monitor_YYYYMMDD.log`
- Contains: Upload reasons, timing, errors, and success confirmations
- Daily rotation with detailed operation tracking

## Prediction League Scripts

### Dropbox Prediction Cleaning Script

The `clean_predictions_dropbox.py` script monitors Dropbox for prediction files and processes them automatically.

#### Setup - OAuth2 Authentication

**First-time setup** (for new installations or when tokens expire):

```bash
python scripts/prediction_league/setup_dropbox_oauth.py
```

**This interactive script will:**
1. Open your browser to Dropbox authorization page
2. Guide you through the OAuth2 flow
3. Exchange authorization code for access token + refresh token  
4. Update keys.json with proper OAuth2 credentials
5. Enable automatic token refresh

**Manual Setup Alternative:**
If the interactive script doesn't work, you can:
1. Visit: `https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&response_type=code&token_access_type=offline`
2. Replace `YOUR_APP_KEY` with your actual app key from keys.json
3. Authorize the app and copy the authorization code
4. Run the setup script and paste the code when prompted

#### Basic Usage

##### Normal Operation
```bash
python scripts/prediction_league/clean_predictions_dropbox.py
```
- Monitors Dropbox /Predictions/2025_26/ folder
- Downloads and processes changed .txt files
- Saves cleaned predictions to CSV and database
- Updates file metadata for change detection

##### Dry Run Mode  
```bash
python scripts/prediction_league/clean_predictions_dropbox.py --dry-run
```
- Shows what would be processed without making changes
- Tests Dropbox connection and file detection
- Safe for development and testing

##### Specific Gameweek
```bash
python scripts/prediction_league/clean_predictions_dropbox.py --gameweek 3
```
- Processes only files for specific gameweek
- Useful for reprocessing individual gameweeks
- Still respects file modification timestamps

#### OAuth2 Features
- **Automatic Token Refresh**: Tokens refresh automatically when expired
- **Legacy Token Support**: Graceful handling of old long-lived tokens
- **Error Recovery**: Clear error messages and setup guidance
- **Secure Storage**: Tokens stored securely in keys.json

#### Troubleshooting

**Token Expired Errors:**
```
WARNING - Dropbox token expired, attempting refresh...
ERROR - Token refresh failed  
```
**Solution:** Run `python scripts/prediction_league/setup_dropbox_oauth.py`

**Missing Credentials:**
```
ERROR - Missing dropbox_app_key or dropbox_app_secret
```
**Solution:** Add credentials to keys.json from your Dropbox app settings

**No Files Found:**
```
WARNING - No files found in Dropbox folder
```
**Solution:** Check Dropbox folder path and file permissions

## FPL Scripts

### Fixtures and Gameweeks Script

The `fetch_fixtures_gameweeks.py` script manages both Premier League fixtures and gameweeks data from the FPL API.

#### Basic Usage

##### Fetch Live Data
```bash
python scripts/fpl/fetch_fixtures_gameweeks.py
```
- Fetches current fixtures and gameweeks from FPL API
- Updates database with fixtures and gameweeks tables
- Maps FPL team IDs to database team references
- Handles timezone conversion for UK kickoff times
- Saves backup JSON file with metadata
- Cleans up old sample files (keeps latest 5)

##### Test Mode
```bash
python scripts/fpl/fetch_fixtures_gameweeks.py --test
```
- Uses most recent sample JSON file instead of live API
- Useful for development and testing
- No API requests made (preserves API access)
- All database operations still performed

##### Dry Run Mode
```bash
python scripts/fpl/fetch_fixtures_gameweeks.py --test --dry-run
```
- Shows what would be processed without making database changes
- Perfect for validating script logic and data processing
- Combines with test mode for safe development

#### Advanced Options

##### Custom Season
```bash
python scripts/fpl/fetch_fixtures_gameweeks.py --season "2024/2025"
```

##### Custom Sample File Management
```bash
# Keep only 3 sample files
python scripts/fpl/fetch_fixtures_gameweeks.py --cleanup-count 3

# Keep 10 sample files  
python scripts/fpl/fetch_fixtures_gameweeks.py --cleanup-count 10

# Disable cleanup (keep all files)
python scripts/fpl/fetch_fixtures_gameweeks.py --cleanup-count 0
```

##### Combined Options
```bash
# Test mode with dry run and custom cleanup
python scripts/fpl/fetch_fixtures_gameweeks.py --test --dry-run --cleanup-count 2
```

#### Expected Output
```
2025-08-29 23:01:45 - INFO - Starting fixtures and gameweeks data fetch process...
2025-08-29 23:01:46 - INFO - Fetching FPL bootstrap data for gameweeks...
2025-08-29 23:01:48 - INFO - Retrieved 38 gameweeks from FPL API
2025-08-29 23:01:49 - INFO - Fetching FPL fixtures data...
2025-08-29 23:01:51 - INFO - Retrieved 380 fixtures from FPL API
2025-08-29 23:01:52 - INFO - Loading team mapping...
2025-08-29 23:01:52 - INFO - Loaded 20 team mappings
2025-08-29 23:01:53 - INFO - Processing 38 gameweeks...
2025-08-29 23:01:53 - INFO - Gameweeks: 12 new, 26 updated
2025-08-29 23:01:54 - INFO - Processing 380 fixtures...
2025-08-29 23:01:56 - INFO - Fixtures: 85 new, 295 updated, 0 skipped
2025-08-29 23:01:56 - INFO - Database transaction committed successfully
2025-08-29 23:01:57 - INFO - Sample data saved to: fixtures_gameweeks_20250829_230157.json
2025-08-29 23:01:57 - INFO - Fixtures and gameweeks data fetch process completed successfully
```

### FPL Player Data Script

For comprehensive player performance data, see the dedicated [FPL_DATA_GUIDE.md](FPL_DATA_GUIDE.md).

## Prediction League Scripts

### Automated Predictions Script

The `automated_predictions.py` script provides fully automated prediction generation and notification system.

#### Basic Usage

##### Automated Execution
```bash
python scripts/prediction_league/automated_predictions.py
```
- Checks if next gameweek deadline is within 36 hours
- Generates predictions based on odds data (favorite wins 2-1)
- Uploads predictions to Dropbox at `predictions_league/odds-api/predictions{gameweek}.txt`
- Sends notifications via Pushover API
- Prevents duplicate runs using database tracking

#### Prediction Logic
- **Favorite Detection**: Team with lower odds is considered favorite
- **Score Format**: Favorite wins 2-1, underdog wins 1-2
- **Team Names**: Properly capitalized (e.g., "Chelsea", "Man Utd")
- **Header**: Always includes "Tom Levin" at the top

#### Smart Prevention Features
- ✅ **36-Hour Window**: Only runs when deadline is within 36 hours
- ✅ **File Existence Check**: Skips if predictions file already exists in Dropbox
- ✅ **Recent Processing**: Won't process again if run within the last hour
- ✅ **Database Tracking**: Updates `last_update` table for "predictions" and "send_fixtures"

#### Expected Output
```
2025-08-29 23:39:11 - Starting automated predictions script
2025-08-29 23:39:11 - Next gameweek: 3, deadline: 2025-08-30 10:00:00+00:00
2025-08-29 23:39:11 - Within 36 hours: True
2025-08-29 23:39:12 - Found 10 fixtures with odds for gameweek 3
2025-08-29 23:39:13 - Successfully uploaded predictions to Dropbox
2025-08-29 23:39:14 - Successfully sent Pushover notification
2025-08-29 23:39:14 - Successfully sent Pushover notification (fixtures)
2025-08-29 23:39:14 - Automated predictions script completed
```

#### Prediction Format Example
```
Tom Levin

Chelsea 2-1 Fulham
Man Utd 2-1 Burnley
Spurs 2-1 Bournemouth
Sunderland 1-2 Brentford
Liverpool 2-1 Arsenal
```

#### Notifications Sent
1. **Predictions**: Full prediction list with "Tom Levin" header
2. **Fixtures**: List of upcoming fixtures with deadline time

#### Scheduling with Cron
```bash
# Check every 6 hours during season
0 */6 * * * cd /path/to/project && /path/to/venv/bin/python scripts/prediction_league/automated_predictions.py

# Check twice daily (morning and evening)
0 8,20 * * * cd /path/to/project && /path/to/venv/bin/python scripts/prediction_league/automated_predictions.py
```

#### Dependencies
- **Dropbox API**: For file upload functionality
- **Pushover API**: For notification delivery
- **Database**: Uses existing `gameweeks`, `fixtures`, `odds`, and `last_update` tables
- **API Keys**: Requires `dropbox_oath_token`, `PUSHOVER_USER`, and `PUSHOVER_TOKEN` in `keys.json`

#### Error Handling
- Graceful handling of missing odds data
- Dropbox API error recovery
- Pushover notification failures logged
- Database connection error handling
- Prevents script crashes with comprehensive try/catch blocks

### Dropbox Prediction Cleaning Script

The `clean_predictions_dropbox.py` script monitors Dropbox prediction files and processes changes automatically.

#### Basic Usage

##### Automated Processing
```bash
python scripts/prediction_league/clean_predictions_dropbox.py
```
- Monitors `.txt` files in Dropbox `/Predictions/2025_26/` folder
- Downloads and processes files that have been modified since last run
- Extracts team names and scores from prediction text
- **Inserts predictions directly into database** with conflict resolution
- Saves cleaned predictions as CSV backup files to `data/predictions/2025_26/`
- Updates database tracking tables

#### Command Line Options

##### Dry Run Mode
```bash
python scripts/prediction_league/clean_predictions_dropbox.py --dry-run
```
- Shows what would be processed without making any changes
- Displays both CSV and database insertion counts
- Perfect for testing and verification

##### Specific Gameweek Processing
```bash
python scripts/prediction_league/clean_predictions_dropbox.py --gameweek 3
```
- Processes only files for the specified gameweek
- Useful for reprocessing individual weeks

##### Combined Options
```bash
python scripts/prediction_league/clean_predictions_dropbox.py --dry-run --gameweek 1
```

#### Processing Logic
- **File Change Detection**: Uses `file_metadata` table to track timestamps
- **Team Recognition**: Extracts team names using database team list
- **Score Extraction**: Parses numeric scores from prediction text
- **Player Validation**: Cross-references against active players in database
- **Missing Players**: Adds default 9-9 scores for players who haven't submitted
- **Duplicate Resolution**: Keeps only latest prediction per player per fixture
- **Database Integration**: Direct insertion with `INSERT OR REPLACE` conflict resolution
- **Foreign Key Mapping**: Converts player names and team pairs to database IDs
- **Predicted Result Calculation**: Generates H/D/A result from goal scores

#### Expected Output
```
2025-08-30 10:21:38 - INFO - Starting Dropbox-based prediction cleaning process
2025-08-30 10:21:38 - INFO - Loaded 29 teams and 26 active players
2025-08-30 10:21:38 - INFO - Found 3 .txt files in Dropbox folder
2025-08-30 10:21:38 - INFO - File gameweek3.txt has been modified and will be processed
2025-08-30 10:21:39 - INFO - Processing gameweek3.txt for gameweek 3
2025-08-30 10:21:39 - INFO - Successfully downloaded gameweek3.txt
2025-08-30 10:21:39 - INFO - Processed 219 predictions from file content
2025-08-30 10:21:39 - INFO - Adding default predictions for 5 missing players
2025-08-30 10:21:39 - WARNING - Fixture 'burnley vs man utd' for gameweek 3 not found - skipping prediction
2025-08-30 10:21:39 - INFO - Database insertion: 113 inserted, 146 skipped
2025-08-30 10:21:39 - INFO - Successfully processed 113 predictions for database insertion
2025-08-30 10:21:39 - WARNING - Skipped 146 predictions due to missing references
2025-08-30 10:21:39 - INFO - Saved 259 predictions to predictions3.csv
2025-08-30 10:21:39 - INFO - Successfully processed 1 files
```

#### File Processing Details
- **Input**: Dropbox `.txt` files (`gameweek1.txt`, `gameweek2.txt`, etc.)
- **Primary Output**: Direct database insertion into `predictions` table
- **Backup Output**: Local CSV files (`predictions1.csv`, `predictions2.csv`, etc.)
- **CSV Format**: Standard CSV with columns: `gameweek,player,home_team,away_team,home_goals,away_goals`
- **CSV Location**: `data/predictions/2025_26/`
- **Database Schema**: Uses `player_id`, `fixture_id`, `fpl_fixture_id`, `home_goals`, `away_goals`, `predicted_result`

#### Token Refresh System
- **Automatic Detection**: Recognizes expired Dropbox tokens (401 errors)
- **OAuth2 Support**: Can refresh tokens using `dropbox_refresh_token`
- **Legacy Token Handling**: Provides guidance for manual token renewal
- **Safe Updates**: Atomically updates `keys.json` with new tokens

#### Scheduling with Cron
```bash
# Process hourly during active periods
0 * * * * cd /path/to/project && /path/to/venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py

# Process twice daily
0 8,20 * * * cd /path/to/project && /path/to/venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py
```

#### Dependencies
- **Dropbox API**: For file access and download
- **Database**: Uses `predictions`, `file_metadata`, `teams`, `players`, `fixtures`, `last_update` tables
- **File System**: Creates `data/predictions/2025_26/` directory structure
- **Logging**: Daily log files in `logs/clean_predictions_YYYYMMDD.log`

#### Database Integration Features
- **Direct Insertion**: Primary storage in `predictions` table with full foreign key relationships
- **Conflict Resolution**: Uses `INSERT OR REPLACE` to handle duplicate predictions
- **Constraint Enforcement**: Ensures one prediction per player per fixture
- **Reference Validation**: Skips predictions for missing players or fixtures with detailed logging
- **Transaction Safety**: All database operations use transactions for data integrity
- **Backup CSV**: Maintains CSV files as backup and reference format

#### Error Handling & Logging
- **Missing References**: Gracefully skips predictions for unknown players/fixtures
- **Database Errors**: Comprehensive error handling with transaction rollback
- **Insertion Tracking**: Detailed logging shows successful insertions vs. skipped predictions
- **File Change Detection**: Only processes modified files to prevent unnecessary work
- **Token Refresh**: Automatic Dropbox token renewal for uninterrupted operation

## Odds API Scripts

### Odds Fetching Script

The `fetch_odds.py` script supports several command line options for different use cases.

### Basic Usage

#### Fetch Live Odds
```bash
python scripts/odds-api/fetch_odds.py
```
- Fetches current odds from The Odds API
- Updates database with new/changed odds
- Refreshes aggregated summary table
- Saves backup JSON file
- Cleans up old sample files (keeps latest 5)

#### Test Mode
```bash
python scripts/odds-api/fetch_odds.py --test
```
- Uses most recent sample JSON file instead of API
- Useful for development and testing
- No API requests made (preserves API quota)
- All database operations still performed

### Advanced Options

#### Custom File Cleanup
```bash
# Keep only 3 sample files
python scripts/odds-api/fetch_odds.py --cleanup-count 3

# Keep 10 sample files  
python scripts/odds-api/fetch_odds.py --cleanup-count 10

# Disable cleanup (keep all files)
python scripts/odds-api/fetch_odds.py --cleanup-count 0
```

#### Combined Options
```bash
# Test mode with custom cleanup
python scripts/odds-api/fetch_odds.py --test --cleanup-count 2
```

#### Help
```bash
python scripts/odds-api/fetch_odds.py --help
```

## Output and Logging

### Console Output
The script outputs key information to both console and log files:

```
2025-08-29 00:52:24,123 - INFO - Starting test with sample data...
2025-08-29 00:52:24,123 - INFO - Testing with sample data from: /path/to/sample.json
2025-08-29 00:52:24,128 - INFO - Loading team mappings...
2025-08-29 00:52:24,128 - INFO - Loaded 23 team mappings
2025-08-29 00:52:24,128 - INFO - Processing 20 matches...
2025-08-29 00:52:24,405 - INFO - Successfully processed 981 odds records
2025-08-29 00:52:24,415 - INFO - Updated fixture_odds_summary table with 102 fixture summaries
2025-08-29 00:52:24,415 - INFO - Test completed successfully
```

### Log Files
- **Location**: `logs/odds_fetch_YYYYMMDD.log`
- **Format**: Daily rotation (one file per day)
- **Content**: Same as console output plus detailed error information
- **Retention**: Manual cleanup required

### Sample Files
- **Location**: `samples/odds_api/`
- **Format**: `odds_data_YYYYMMDD_HHMMSS.json`
- **Purpose**: Backup of API responses for testing/debugging
- **Cleanup**: Automatic (configurable retention count)

## Typical Workflows

### Regular Data Collection
```bash
# Create a cron job to run hourly during match days
0 * * * * /usr/bin/python3 /path/to/fetch_odds.py >> /var/log/cron.log 2>&1
```

### Development & Testing
```bash
# Use test mode to avoid API calls
python scripts/odds-api/fetch_odds.py --test

# Keep more sample files during development
python scripts/odds-api/fetch_odds.py --cleanup-count 10

# Disable cleanup completely
python scripts/odds-api/fetch_odds.py --cleanup-count 0
```

### Debugging Issues
```bash
# Check recent log files
tail -f logs/odds_fetch_$(date +%Y%m%d).log

# Run in test mode to reproduce issues
python scripts/odds-api/fetch_odds.py --test

# Check database contents
sqlite3 data/database.db "SELECT COUNT(*) FROM odds WHERE price IS NOT NULL;"
```

## Performance Expectations

### API Mode
- **Duration**: 5-15 seconds depending on API response time
- **API Quota**: 1 request per run
- **Database**: ~1000 odds records processed typical
- **Network**: Requires internet connection

### Test Mode  
- **Duration**: 1-3 seconds (no network requests)
- **API Quota**: No consumption
- **Database**: Same processing as API mode
- **Network**: Not required

### Resource Usage
- **Memory**: Minimal (< 50MB typical)
- **CPU**: Light processing load
- **Disk**: ~200KB per sample file, log files grow over time
- **Network**: Single HTTPS request in API mode

## Error Scenarios

### API Issues
```bash
# API timeout
ERROR - API request timed out after 30 seconds

# Invalid API key
ERROR - API request failed with status 401: Invalid API key

# API rate limit exceeded
ERROR - API request failed with status 429: Too Many Requests
```

### Data Issues
```bash
# Team not found in database
WARNING - Skipping match Liverpool vs Arsenal - teams not found in database

# Missing price data
WARNING - Missing price for Chelsea in match Chelsea vs Arsenal

# Database connection issues
ERROR - Error processing odds data: database is locked
```

### Resolution Steps
1. **Check API Key**: Verify `keys.json` contains valid API key
2. **Check Network**: Ensure internet connectivity
3. **Check Database**: Verify `data/database.db` is accessible
4. **Check Logs**: Review detailed error messages in log files
5. **Test Mode**: Use `--test` to isolate API vs processing issues

## Best Practices

### Production Usage
- Set up monitoring for log files
- Implement alerts for consecutive failures
- Regular database backups
- Monitor API quota usage
- Schedule during off-peak hours

### Development Usage  
- Use `--test` mode to avoid API consumption
- Keep extra sample files (`--cleanup-count 10+`)
- Monitor log files for warnings
- Test with various sample data files

### Maintenance
- **Daily**: Check log files for errors
- **Weekly**: Review API quota usage 
- **Monthly**: Clean up old log files
- **Seasonal**: Archive old odds data

## Integration Examples

### Database Queries
```bash
# Get latest averaged odds
sqlite3 data/database.db "
SELECT 
    home_team, away_team,
    ROUND(avg_home_win_odds, 2) as home_win,
    ROUND(avg_draw_odds, 2) as draw, 
    ROUND(avg_away_win_odds, 2) as away_win
FROM fixture_odds_summary s
JOIN teams h ON h.team_id = s.home_team_id
JOIN teams a ON a.team_id = s.away_team_id
ORDER BY last_updated DESC
LIMIT 10;"
```

### Scripting Integration
```bash
#!/bin/bash
# Example monitoring script

LOGFILE="logs/odds_fetch_$(date +%Y%m%d).log"

# Run odds fetch
python3 scripts/odds-api/fetch_odds.py

# Check for errors
if grep -q "ERROR" "$LOGFILE"; then
    echo "Errors found in odds fetch - check $LOGFILE"
    exit 1
fi

echo "Odds fetch completed successfully"
```

### Python Integration
```python
import sqlite3
from pathlib import Path

# Connect to database
db_path = Path("data/database.db") 
conn = sqlite3.connect(db_path)

# Get averaged odds for analysis
cursor = conn.cursor()
cursor.execute("""
    SELECT fixture_id, avg_home_win_odds, avg_draw_odds, avg_away_win_odds
    FROM fixture_odds_summary 
    WHERE avg_home_win_odds IS NOT NULL
""")

for row in cursor.fetchall():
    fixture_id, home_odds, draw_odds, away_odds = row
    # Process odds for predictions...

conn.close()
```