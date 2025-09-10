# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Fixed
- **JavaScript Syntax Errors**: Resolved duplicate variable declarations in strategy switch cases
- **Authentication Issues**: Temporarily removed auth requirements from prediction APIs for development
- **Null Value Handling**: Fixed TypeError when Over/Under odds contain None values
- **Season Detection**: Corrected current season from 2024/2025 to 2025/2026

### Technical Details
- **Strategy Logic**: Smart Goals combines favourite odds strength with goals market preferences
- **Data Sources**: Prioritized access to fixture_odds_summary with football_stats fallback
- **Timezone Function**: `convert_to_uk_time()` handles timestamps, ISO strings, and datetime objects
- **Performance Calculation**: 2 points for exact scores, 1 point for correct results
- **Season Support**: Individual seasons, all seasons combined, historical seasons only

### Configuration
```bash
# Database migration for Over/Under odds
./venv/bin/python scripts/odds-api/migrate_summary_totals.py

# Refresh odds summary to populate totals
./venv/bin/python scripts/odds-api/fetch_odds.py --test

# Timezone configuration in config.json
"timezone": "Europe/London"
```

## [3.1.0] - 2025-09-10

### Added
- **Football-Data.co.uk Integration System** - Complete historical Premier League data integration
  - **Historical Migration**: `scripts/football_data/migrate_legacy_data.py` - Import 32 seasons (1993-2025) of Premier League data
  - **Weekly Data Fetch**: `scripts/football_data/fetch_football_data.py` - Automated current season data downloads
  - **Rich Dataset**: 7,146+ historical matches with results, statistics, referee info, and comprehensive betting odds
  - **Team Mapping**: Automatic translation between football-data.co.uk team names and database teams
  - **Scheduler Integration**: Weekly automated updates every Sunday at 9 AM
  - **Sample Management**: Automatic cleanup of downloaded CSV files with configurable retention

### Changed
- **Scheduler Configuration**: Added `ENABLE_FETCH_FOOTBALL_DATA` control to master scheduler
- **Database Schema**: Enhanced `teams` table with `football_data_name` column for team name mapping
- **Master Scheduler**: Extended to support weekly execution pattern for football-data collection
- **Gitignore**: Added `legacy/` directory to exclude large historical datasets from version control

### Technical Details
- **Database**: New `football_stats` table with 192 columns including all historical match data
- **Data Coverage**: Premier League matches from 1993/94 to 2025/26 seasons
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