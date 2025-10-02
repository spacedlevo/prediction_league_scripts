# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **🎯 Intelligent Strategy Switching Recommendation System** - AI-driven prediction strategy optimization based on real-time season analysis
  - **Real-Time Season Monitoring**: Analyzes low-scoring match percentage (≤2 goals) from completed fixtures
  - **Adaptive Strategy Logic**: Automatically recommends 1-0 strategy when >47% matches are low-scoring, 2-1 strategy otherwise
  - **Historical Pattern Matching**: Leverages 32+ seasons of Premier League data (1993-2025) for validation
  - **Confidence-Based Recommendations**: Early/Moderate/High confidence levels based on sample size (40/80 match thresholds)
  - **Weekly Automated Analysis**: Scheduler integration with Sunday 10 AM execution for recommendation updates
  - **Pushover Notifications**: Smart alerts for strategy changes with priority-based messaging
  - **Database Schema**: New tables for season recommendations, strategy performance, and historical patterns
  - **API Endpoints**: `/api/season-recommendation` for real-time recommendation data
  - **Web Dashboard Integration**: Recommendation widget with current season stats and switch timing guidance
  - **Adaptive Strategy Tab**: New "🎯 Recommended" strategy that dynamically switches between 1-0 and 2-1 predictions
  - **Performance Tracking**: Expected points improvement calculations (+0.05 pts/game for current season)

- **Enhanced Predictions Dashboard** - Major upgrade to prediction analysis capabilities
  - **7 Strategy Options**: Fixed (2-1, 2-0, 1-0), Adaptive, Calibrated, Home/Away Bias, Poisson, Smart Goals, Custom
  - **Season Recommendation Widget**: Prominent dashboard showing current analysis and switch guidance
  - **Historical Context Display**: Shows similar seasons and their optimal strategies
  - **Interactive Strategy Comparison**: Real-time performance metrics across all strategies
  - **Backend Strategy Logic**: Enhanced `generate_prediction_for_fixture()` with adaptive strategy support

- **🎯 Intelligent Automated Predictions** - Refactored automated predictions to use AI-driven strategy recommendations
  - **Adaptive Strategy Integration**: Replaces fixed 2-1 strategy with intelligent season-based recommendations
  - **Real-Time Strategy Selection**: Automatically uses 1-0 strategy for current season (53.3% low-scoring matches)
  - **Fallback Protection**: Gracefully defaults to 2-1 strategy if recommendation system unavailable
  - **Enhanced Logging**: Clear indication of strategy selection and reasoning in output
  - **Expected Performance**: +0.05 pts/game improvement over fixed 2-1 approach
  - **Seamless Integration**: No changes to scheduling, Dropbox uploads, or notification systems

- **Automated Predictions Gameweek Integration** - Enhanced automated predictions to write to main gameweek predictions files
  - **Dual File Creation**: Predictions now automatically appended to both `/predictions_league/odds-api/predictions{gameweek}.txt` and `/predictions_league/Predictions/2025_26/gameweek{gameweek}.txt`
  - **Append/Create Logic**: If gameweek file exists, predictions are appended; if not, new file is created
  - **Dropbox API Integration**: Uses Dropbox download/upload API to read existing content and combine with new predictions
  - **Error Handling**: Graceful handling when one location fails, continues if at least one upload succeeds
  - **Enhanced Logging**: Detailed logging shows success/failure status for both upload locations

- **Automated Predictions Force Mode** - Added CLI arguments to bypass all safety checks for testing and emergency use
  - **Force Flag**: `--force` bypasses deadline, file existence, and recent processing checks
  - **Gameweek Override**: `--gameweek N` allows forcing specific gameweek (requires --force)
  - **Safety Validation**: Prevents `--gameweek` usage without `--force` flag
  - **Complete Logging**: All force mode actions clearly logged with proper file-based logging
  - **Strategy Preservation**: Force mode still uses intelligent 1-0 strategy from database
  - **Use Cases**: Development testing, emergency prediction generation, historical analysis

- **Enhanced Logging System** - Upgraded automated_predictions.py from print-based to proper file logging
  - **File-Based Logs**: Creates `logs/automated_predictions_YYYYMMDD.log` files
  - **Dual Output**: Logs to both file and console for monitoring
  - **Proper Log Levels**: INFO, WARNING, ERROR levels with timestamps
  - **Project Consistency**: Follows established logging patterns from other scripts

### Fixed
- **Database Upload Timestamp Logic** - Simplified and improved `monitor_and_upload.py` timestamp update logic
  - **Issue**: Complex prepare/rollback system was unnecessary and could lead to inconsistent states
  - **Impact**: Upload timestamps might be updated before upload completed, causing potential tracking issues
  - **Solution**: Simplified to only update `last_update` table **after** successful uploads
  - **Removed**: `prepare_upload_timestamp()` and `rollback_upload_timestamp()` functions
  - **Added**: Single `update_upload_timestamp()` function that runs only after successful upload
  - **Result**: Clean flow - upload → verify success → update timestamp; no updates if upload fails or doesn't occur
  - **Enhanced Logging**: Added comprehensive status indicators showing exactly when/why uploads occur or are skipped

- **Season Recommendations Database Update** - Fixed `update_season_recommendations.py` not populating the "updated" column in last_update table
  - **Issue**: Script was only inserting into `table_name` and `timestamp` columns, ignoring the `updated` column
  - **Impact**: Database upload monitoring couldn't detect season recommendation changes
  - **Solution**: Modified `update_last_update_table()` to populate all three columns: `table_name`, `updated` (ISO format), and `timestamp` (Unix timestamp)
  - **Result**: Season recommendation updates now properly trigger automated database uploads

- **Keys.json Permission Preservation** - Fixed scripts that were resetting file permissions during token updates
  - **Issue**: `clean_predictions_dropbox.py` and `setup_dropbox_oauth.py` were changing keys.json permissions to 0600 (owner-only) when refreshing Dropbox tokens
  - **Impact**: Broke group read access for `predictionleague` group on production servers
  - **Solution**: Modified both scripts to preserve original file permissions and ownership after atomic file updates
  - **Implementation**: Added `os.stat()` capture before `shutil.move()` and `os.chmod()`/`os.chown()` restoration after
  - **Files Modified**: `scripts/prediction_league/clean_predictions_dropbox.py`, `scripts/prediction_league/setup_dropbox_oauth.py`
  - **Production Ready**: Scripts now maintain 640 permissions (owner rw, group r) for multi-user access

- **JavaScript Syntax Errors in Predictions Template** - Fixed critical syntax errors preventing predictions page from loading
  - **Issue**: Used Python-style docstrings (`"""`) in JavaScript functions causing "Unexpected string" errors
  - **Solution**: Replaced Python docstrings with proper JavaScript comments (`//`) in all recommendation functions
  - **Affected Functions**: `loadSeasonRecommendation()`, `updateRecommendationWidget()`, `getConfidenceColor()`, `hideRecommendationWidget()`, `updateAdaptiveStrategyDescription()`
  - **Result**: Predictions page now loads correctly with functional recommendation widget and adaptive strategy

- **Timezone Display** - Fixed deadline time display in automated predictions notifications
  - **Issue**: Deadline times were showing in UTC instead of local UK time
  - **Solution**: Added pytz dependency and proper timezone conversion using `Europe/London` timezone
  - **Result**: Pushover notifications now display correct London time (handles BST/GMT automatically)
  - **Implementation**: `create_fixtures_string()` function now converts UTC timestamps to London time

### Changed
- **Automated Predictions** - Updated fixture notification timing from 1 hour to 24 hour cooldown
  - **Improvement**: Reduced notification frequency while maintaining timely fixture delivery
  - **Logic**: Fixtures are less time-sensitive than predictions, 24-hour spacing prevents spam
  - **Context**: Script still only runs when deadline is within 36 hours

## [3.2.1] - 2025-09-11

### Fixed
- **Webapp Script Execution System** - Resolved critical path resolution bugs preventing scripts from running
  - **Root Cause**: Script execution failing due to improper path handling when webapp deployed with absolute paths in config
  - **Database Path Bug**: `get_db_connection()` function using relative path concatenation with absolute paths from config
  - **Working Directory Bug**: Scripts executed from webapp directory instead of project root, breaking relative path dependencies  
  - **Script Path Bug**: `execute_script()` function incorrectly concatenating absolute paths
  - **Result**: Scripts now run successfully from webapp with proper logging and output capture

### Enhanced
- **Improved Script Execution Environment**
  - **Working Directory Fix**: Scripts now execute from correct project root directory (`/home/predictionleague/projects/prediction_league_scripts`)
  - **Path Resolution**: Enhanced path handling to support both absolute and relative paths in config
  - **Debug Logging**: Added comprehensive debug logging for script execution troubleshooting
  - **Error Handling**: Enhanced exception capture with full tracebacks for better debugging
  
- **Football Data Script Integration**
  - **Webapp Integration**: Added `fetch_football_data.py` to available scripts in webapp configuration
  - **Script Configuration**: Proper timeout (180s) and description for football data updates
  - **Historical Data Access**: Weekly Premier League data collection now manageable through webapp

- **Debug Tools**
  - **Test Script**: Added `scripts/test_script.py` for debugging webapp execution environment
  - **Environment Validation**: Test script validates working directory, file access, and Python environment
  - **Webapp Integration**: Test script available through webapp interface for troubleshooting

### Technical Details
- **Path Resolution Logic**: Added absolute vs relative path detection for `scripts_path`, `venv_path`, and `database_path`
- **Working Directory**: `subprocess.Popen` now uses `cwd` parameter set to project root directory
- **Error Capture**: Script status tracking enhanced with detailed error information and output logs
- **Debug Logging**: Comprehensive logging including file existence, paths, commands, and process IDs

### Before/After Comparison
**Before Fix:**
- Scripts triggered 302 redirects with no logging
- Database connection failures due to path resolution
- Working directory `/opt/prediction-league` breaking script dependencies
- No error visibility for troubleshooting

**After Fix:**
- Scripts execute successfully with proper output capture
- Database connections work with absolute path configuration
- Scripts run from correct project root directory
- Full debug logging and error reporting available

### Configuration
Scripts now support both deployment scenarios:
```json
// Production (absolute paths)
{
  "database_path": "/home/predictionleague/projects/prediction_league_scripts/data/database.db",
  "scripts_path": "/home/predictionleague/projects/prediction_league_scripts/scripts",
  "venv_path": "/home/predictionleague/projects/prediction_league_scripts/venv/bin/python"
}

// Development (relative paths) 
{
  "database_path": "../data/database.db",
  "scripts_path": "../scripts", 
  "venv_path": "../venv/bin/python"
}
```

## [3.1.1] - 2025-09-11

### Fixed
- **Football-Data Historical Coverage** - Resolved incomplete historical data integration
  - **Root Cause**: 24 historical Premier League teams were missing from database, causing 5,148 matches (42%) to be skipped during migration
  - **Solution**: Added all missing historical teams (Blackburn, West Brom, Bolton, Middlesbrough, Stoke, Wigan, Birmingham, Portsmouth, etc.)
  - **Result**: Achieved perfect 100% historical data coverage (12,324/12,324 matches)

### Enhanced
- **Complete Team Coverage**: Added 24 missing historical Premier League teams to database
  - **Major Historical Teams**: Blackburn Rovers, West Bromwich Albion, Bolton Wanderers, Middlesbrough, Stoke City, Wigan Athletic
  - **Additional Teams**: Birmingham City, Portsmouth, Charlton Athletic, Sheffield Wednesday, Cardiff City, Hull City, QPR, Reading, Derby County, Swansea City, plus 8 others
  - **Team Mapping**: Updated migration script to handle all 51 historical Premier League teams
  
- **Perfect Data Coverage**: Achieved 100% historical match coverage across all eras
  - **1990s**: 2,824/2,824 matches (100.0% coverage) ✅
  - **2000s**: 3,800/3,800 matches (100.0% coverage) ✅  
  - **2010s**: 3,800/3,800 matches (100.0% coverage) ✅
  - **2020s**: 1,900/1,900 matches (100.0% coverage) ✅

### Technical Details
- **Database Schema**: Added 24 historical teams (team_ids 30-53) with proper football_data_name mappings
- **Migration Script**: Enhanced `create_team_name_mapping()` function with complete historical team coverage
- **Data Integrity**: All 32 seasons now have perfect match counts matching original football-data.co.uk source
- **Performance**: Comprehensive indexes ensure optimal query performance with larger dataset

### Before/After Comparison
**Before Fix (v3.1.0):**
- 7,176 matches migrated (58.2% coverage)
- 27 teams mapped, 24 historical teams missing
- Significant data gaps in early Premier League eras

**After Fix (v3.1.1):**  
- 12,324 matches migrated (100% coverage)
- 51 teams mapped (complete historical coverage)
- Perfect data integrity across all 32 seasons

## [3.2.0] - 2025-09-10

### Added
- **Predictions Analysis System** - Comprehensive automated predictions with multiple strategies
  - **7 Prediction Strategies**: Fixed, Calibrated, Home/Away Bias, Poisson, Smart Goals, Custom predictions
  - **Smart Goals Strategy**: Advanced strategy combining 1X2 and Over/Under odds for intelligent predictions
  - **Multi-Season Analysis**: Performance comparison across historical seasons (2020-2026)
  - **Season Performance API**: Real-time strategy comparison with accuracy metrics and points calculation
  - **Interactive Frontend**: Strategy tabs, season selector, bulk prediction tools
  - **Over/Under Odds Support**: Database schema enhanced with avg_over_2_5_odds and avg_under_2_5_odds columns

- **UK Timezone Display** - All timestamps now display in UK time (BST/GMT)
  - **Automatic BST/GMT Handling**: Uses pytz to correctly handle British Summer Time transitions
  - **Dashboard Updates**: Recent updates table shows UK time instead of UTC
  - **Predictions API**: Kickoff times converted to UK format (DD/MM/YYYY HH:MM)
  - **Configuration Driven**: Uses timezone setting from config.json

### Enhanced
- **Database Schema**: Added Over/Under 2.5 odds columns to fixture_odds_summary table
- **API Endpoints**: New `/api/predictions/gameweek/{gameweek}` and `/api/predictions/season-performance` endpoints
- **Multi-Season Data Access**: Fallback system using football_stats when fixture_odds_summary unavailable
- **Error Handling**: Improved JavaScript error handling with authentication detection
- **Performance Metrics**: Total points, accuracy rate, correct results, exact scores analysis
- **Timezone Display**: Added BST/GMT indicators to all timestamp displays for better user clarity

### Fixed
- **JavaScript Syntax Errors**: Resolved duplicate variable declarations in strategy switch cases
- **Authentication Issues**: Temporarily removed auth requirements from prediction APIs for development
- **Null Value Handling**: Fixed TypeError when Over/Under odds contain None values
- **Season Detection**: Corrected current season from 2024/2025 to 2025/2026

### Technical Details
- **Strategy Logic**: Smart Goals combines favourite odds strength with goals market preferences
- **Data Sources**: Prioritized access to fixture_odds_summary with football_stats fallback
- **Timezone Function**: `convert_to_uk_time()` handles timestamps, ISO strings, and datetime objects with BST/GMT indicators
- **Performance Calculation**: 2 points for exact scores, 1 point for correct results
- **Season Support**: Individual seasons, all seasons combined, historical seasons only

### Configuration
```bash
# Database migration for Over/Under odds
./venv/bin/python scripts/odds-api/migrate_summary_totals.py

# Refresh odds summary to populate totals
./venv/bin/python scripts/odds-api/fetch_odds.py --test

# Timezone dependency installation (required for production)
pip install pytz

# Timezone configuration in config.json
"timezone": "Europe/London"
```

## [3.1.0] - 2025-09-10

### Added
- **Football-Data.co.uk Integration System** - Complete historical Premier League data integration
  - **Historical Migration**: `scripts/football_data/migrate_legacy_data.py` - Import 32 seasons (1993-2025) of Premier League data
  - **Weekly Data Fetch**: `scripts/football_data/fetch_football_data.py` - Automated current season data downloads
  - **Complete Historical Dataset**: 12,324 historical matches with results, statistics, referee info, and comprehensive betting odds (100% coverage)  
  - **Team Mapping**: Complete translation for all 51 historical Premier League teams
  - **Scheduler Integration**: Weekly automated updates every Sunday at 9 AM
  - **Sample Management**: Automatic cleanup of downloaded CSV files with configurable retention

### Changed
- **Scheduler Configuration**: Added `ENABLE_FETCH_FOOTBALL_DATA` control to master scheduler
- **Database Schema**: Enhanced `teams` table with `football_data_name` column for team name mapping
- **Master Scheduler**: Extended to support weekly execution pattern for football-data collection
- **Gitignore**: Added `legacy/` directory to exclude large historical datasets from version control

### Technical Details
- **Database**: New `football_stats` table with 192 columns including all historical match data
- **Data Coverage**: Complete Premier League matches from 1993/94 to 2025/26 seasons (12,324 matches, 100% coverage)
- **Match Data**: Full-time/half-time results, team statistics, referee assignments, betting odds
- **Betting Markets**: Home/Draw/Away odds, over/under goals, Asian handicap, correct score from multiple bookmakers
- **Team Statistics**: Shots (total/on target), corners, cards, fouls for both teams
- **Change Detection**: Smart updates to prevent unnecessary database operations
- **Foreign Keys**: Proper relationships to existing teams table for data integrity

### Configuration
```bash
# New scheduler configuration options
ENABLE_FETCH_FOOTBALL_DATA=true
OFFSEASON_ENABLE_FETCH_FOOTBALL_DATA=false

# New execution schedule
# Weekly on Sundays at 9 AM: fetch_football_data.py
```

## [3.0.0] - 2025-09-01

### Added
- **Pulse API Integration System** - Match officials and team list data collection
  - **Data Collection**: `scripts/pulse_api/fetch_pulse_data.py` - Collect match officials, team lists, and events
  - **Database Tables**: `match_officials`, `team_list`, `match_events` for comprehensive match data
  - **Team Mapping**: Integration with existing team database structure
  - **Daily Automation**: Runs automatically at 8 AM via master scheduler

### Fixed
- **Critical Database Upload Bug**: Fixed transaction ordering in `fetch_results.py` where `update_last_update_table()` was called after `conn.commit()`, causing timestamp updates to never be committed
- **Missing Fixtures Timestamp Updates**: Enhanced `fetch_fixtures_gameweeks.py` to update both "fixtures" and "fixtures_gameweeks" timestamps when changes occur
- **Timezone Conversion Bug**: Fixed match window detection by correctly treating database times as UTC without adding timezone offset
- **Duplicate Predictions**: Improved fixture matching to handle team order variations, eliminating duplicate entries
- **Unnecessary Timestamp Updates**: Modified scripts to only update timestamps when actual data changes occur, reducing unnecessary database uploads

### Changed
- **Upload System Reliability**: Database upload monitoring now properly detects changes with fixed timestamp management
- **Transaction Integrity**: All scripts now correctly update timestamps within the same transaction as data changes
- **Change Detection**: More intelligent detection of actual data changes vs. no-op operations

## [2.0.0] - 2025-08-01

### Added
- **Master Scheduler System** - Centralized automation orchestrator
  - **Single Cron Entry**: `* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh`
  - **Intelligent Timing**: Scripts run at optimal intervals based on data requirements
  - **Process Management**: Lock files prevent overlapping executions
  - **Configuration Control**: Enable/disable individual scripts via `scheduler_config.conf`

### Changed
- **Simplified Scheduling**: Eliminated complex second-based timing windows that caused missed executions
- **Execution Schedule**:
  - Every minute: `fetch_results.py`, `monitor_and_upload.py` (10s delay)
  - Every 15 minutes: `clean_predictions_dropbox.py`  
  - Every 30 minutes: `fetch_fixtures_gameweeks.py`
  - Every hour: `automated_predictions.py`
  - Daily 7 AM: `fetch_fpl_data.py`, `fetch_odds.py`
  - Daily 8 AM: `fetch_pulse_data.py`
  - Daily 2 AM: Cleanup old logs and locks

## [1.0.0] - 2025-07-01

### Added
- **Initial Release** - Basic prediction league automation system
- **FPL Data Integration**: Player scores, fixtures, and gameweeks
- **Prediction Management**: Automated predictions and Dropbox cleaning
- **Results Processing**: Match results fetching and processing
- **Database Upload**: Automated database monitoring and upload system
- **OAuth2 System**: Dropbox integration with automatic token refresh

### Features
- Fantasy Premier League data collection
- Automated prediction generation
- Results processing and validation
- Database backup and upload to remote server
- Comprehensive logging and error handling
- Sample data management for testing

---

## Release Notes

### Version 3.2.0 - Predictions Analysis & UK Timezone
This major feature release introduces a comprehensive predictions analysis system with multiple strategies and UK timezone display throughout the application.

**Key Features:**
- **Smart Predictions**: 7 different strategies including advanced Smart Goals combining 1X2 and Over/Under odds
- **Historical Analysis**: Performance comparison across multiple seasons (2020-2026)
- **UK Time Display**: All timestamps automatically converted to British time (BST/GMT)
- **Interactive Dashboard**: Real-time strategy performance comparison and accuracy metrics
- **Multi-Season Data**: Intelligent fallback system using historical football_stats data

**Strategy Performance Example (2025/2026, 30 games):**
- **Smart Goals**: 18 points, 46.7% accuracy, 4 exact scores
- **Fixed (1-0)**: 18 points, 46.7% accuracy, 4 exact scores
- **Calibrated**: 17 points, 46.7% accuracy, 3 exact scores

**Migration Required:**
```bash
# Add Over/Under odds support
./venv/bin/python scripts/odds-api/migrate_summary_totals.py
./venv/bin/python scripts/odds-api/fetch_odds.py --test
```

### Version 3.1.0 - Football-Data Integration
This major feature release adds comprehensive historical Premier League data dating back to 1993. The integration provides rich match statistics, betting odds, and automated weekly updates for the current season.

**Key Benefits:**
- **30+ Years of Data**: Complete Premier League history for analysis and predictions
- **Rich Statistics**: Team performance data, referee assignments, comprehensive betting markets  
- **Automated Updates**: Weekly data collection with intelligent change detection
- **Seamless Integration**: Works with existing team structure and scheduler system

**Migration Required:**
Run the migration script to import historical data:
```bash
./venv/bin/python scripts/football_data/migrate_legacy_data.py --force
```

### Version 3.0.0 - Pulse API & Critical Fixes
This release resolves critical database synchronization issues and adds detailed match data collection. The fixes ensure reliable automated database uploads and eliminate data inconsistencies.

**Critical Fixes Applied:**
- Database upload monitoring now works correctly in production
- Transaction integrity maintained across all data operations  
- Timezone handling fixed for accurate match window detection
- Duplicate data eliminated through improved matching logic

### Version 2.0.0 - Scheduler Revolution
Complete redesign of the automation system with centralized orchestration. This release eliminates timing issues and provides 100% execution reliability.

**Migration Required:**
Replace existing cron entries with single master scheduler entry:
```bash
# Remove old cron entries, add this single line:
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh
```

---

*For technical implementation details, see CLAUDE.md. For usage instructions, see README.md.*