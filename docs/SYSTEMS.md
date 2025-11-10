# Systems Documentation

Comprehensive documentation for all automated systems in the prediction league project.

## Table of Contents

- [Database Upload System](#database-upload-system)
- [Dropbox OAuth2 System](#dropbox-oauth2-system)
- [Automated Predictions System](#automated-predictions-system)
- [Pulse API System](#pulse-api-system)
- [Football-Data System](#football-data-system)
- [Master Scheduler System](#master-scheduler-system)
- [Predictions Analysis System](#predictions-analysis-system)
- [Prediction Verification System](#prediction-verification-system)

---

## Database Upload System

### Overview

Monitors database changes and automatically uploads to PythonAnywhere when modifications are detected. Uses change detection and health checks to ensure the remote database stays synchronized.

### Commands

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

### Features

- **Change Detection** - Monitors last_update table for database modifications
- **Automatic Uploads** - Triggers on any table changes since last upload
- **Health Check** - Fallback uploads every 30 minutes if no changes detected
- **Transaction Integrity** - Scripts properly update timestamps within transactions
- **Smart Timestamps** - Only updates timestamps when actual data changes occur
- **Prepare/Rollback Upload Logic** - Timestamp updates BEFORE upload (included in file) with rollback on failure
- **PythonAnywhere Visibility** - Upload timestamp visible in remote database
- **Enhanced Logging** - Clear indicators showing exactly when/why uploads occur or are skipped

### Logging Examples

**No Upload Needed:**
```
════════════════════════════════════════════════════════════
DATABASE UPLOAD MONITOR
════════════════════════════════════════════════════════════
Database: database.db (14.32 MB)
→ Last upload: 2025-10-02 15:41:46
→ No database changes since last upload
→ Health check: Last upload was 0.6 minutes ago (<30 min threshold)
No upload performed: No database changes detected and last upload was within 30 minutes
```

**Upload with Changes Detected:**
```
Database: database.db (14.32 MB)
→ Last upload: 2025-11-07 15:39:08
→ Changes detected in 1 table(s): fixtures (at 15:41:20)
Upload triggered: Database Changes
Prepared upload timestamp: 07-11-2025. 15:42:00
Uploading database (15015936 bytes)...
Database upload successful
✓ Upload completed successfully due to: database changes
✓ Timestamp included in upload - PythonAnywhere database shows upload time
```

**Upload Failure with Rollback:**
```
Database: database.db (14.32 MB)
→ Last upload: 2025-11-07 15:30:00
→ Changes detected in 1 table(s): fixtures (at 15:41:20)
Upload triggered: Database Changes
Prepared upload timestamp: 07-11-2025. 15:42:00
Connecting to PythonAnywhere...
✗ Upload failed: Connection timeout
✗ Upload failed - rolling back timestamp
Rolled back upload timestamp to: 07-11-2025. 15:30:00
✓ Timestamp rolled back - upload will be retried on next run due to: database changes
```

---

## Dropbox OAuth2 System

### Overview

Manages Dropbox OAuth2 authentication with automatic token refresh for predictions file management.

### Commands

```bash
# Set up Dropbox OAuth2 tokens (first-time or when expired)
./venv/bin/python scripts/prediction_league/setup_dropbox_oauth.py

# Test Dropbox prediction cleaning
./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --dry-run

# Process specific gameweek
./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --gameweek 3
```

### Features

- **Auto-refresh tokens** - No manual token management needed
- **Legacy token migration** - Seamless upgrade from old tokens
- **Interactive setup** - Browser-based authorization flow
- **Secure storage** - Tokens safely stored in keys.json
- **Permission Preservation** - Scripts maintain file permissions when updating tokens

---

## Automated Predictions System

### Overview

Generates automated predictions based on betting odds and uploads to two Dropbox locations with intelligent strategy recommendations.

### Commands

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

### System Features

- **Dual-File Upload** - Automatically writes predictions to two Dropbox locations:
  - `/predictions_league/odds-api/predictions{gameweek}.txt` (new file creation)
  - `/predictions_league/Predictions/2025_26/gameweek{gameweek}.txt` (append/create logic)
- **Intelligent Content Management** - Downloads existing gameweek files and appends new predictions
- **UK Timezone Notifications** - Uses pytz for accurate BST/GMT deadline display in Pushover notifications
- **Error Recovery** - Continues operation if one upload location fails
- **Gameweek Validation** - Only runs when deadline is within 36 hours
- **Duplicate Prevention** - Database tracking prevents multiple runs within 1-hour window

### Prediction Logic

- **Odds-Based Strategy** - Analyzes home/away odds to determine favorite
- **Consistent Format** - "Tom Levin" header with team capitalization
- **Scoreline Strategy** - Favorite wins 2-1, underdog wins 1-2, default 1-1 for missing odds
- **Fixture Integration** - Uses SQL query to fetch gameweek fixtures with odds data

### Scheduler Integration

- **Hourly Execution** - Runs automatically every hour via master scheduler
- **Deadline-Based Activation** - Only processes when gameweek deadline approaches
- **Notification System** - Sends predictions and fixture lists via Pushover
- **Database Tracking** - Updates last_update table to trigger automated uploads

---

## Pulse API System

### Overview

Collects detailed match data including officials, team lists, and match events from the Pulse API.

### Commands

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

# Fix team_id data quality issues (drop tables and re-fetch all seasons)
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --fix-team-ids

# Preview fix without making changes (shows which seasons will be processed)
./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --fix-team-ids --dry-run

# Note: --fix-team-ids automatically processes ALL seasons with pulse_ids
# The --season argument is ignored when using this flag
```

### Features

- **Change Detection** - Only fetches data for finished fixtures missing pulse data
- **Rate Limiting** - Respectful API usage with configurable delays between requests
- **Error Recovery** - Robust handling of API failures with exponential backoff retry logic
- **Concurrent Processing** - Optional threading for faster data collection (default: 3 workers)
- **Smart Caching** - Saves successful responses to avoid re-fetching during development
- **Database Integration** - Uses existing tables: match_officials, team_list, match_events
- **Team Mapping** - Maps pulse team IDs to database team_id for proper relationships
- **Sample Management** - Automatic cleanup of old sample files with configurable retention
- **Data Quality Fix** - `--fix-team-ids` flag to correct historical team_id inconsistencies

### Data Collected

- **Match Officials** - Referees and linesmen for each match
- **Team Lists** - Starting lineups and substitutes with positions, shirt numbers, captain status
- **Match Events** - Goals, cards, substitutions with precise timestamps and player/team details

### Scheduler Integration

- **Daily Collection** - Runs automatically at 8 AM via master scheduler
- **Change Triggering** - Updates last_update table to trigger automated database uploads
- **Lock Management** - Prevents multiple concurrent executions

---

## Football-Data System

### Overview

Imports and maintains historical Premier League data from Football-Data.co.uk (1993-2025), including match results, statistics, and comprehensive betting odds.

### Commands

```bash
# Import historical Premier League data (1993-2025)
./venv/bin/python scripts/football_data/migrate_legacy_data.py --test --force

# Download current season data weekly
./venv/bin/python scripts/football_data/fetch_football_data.py --dry-run

# Test with sample data
./venv/bin/python scripts/football_data/fetch_football_data.py --test
```

### Features

- **Complete Historical Integration** - 12,324 Premier League matches from 1993-2025 (32 seasons, 100% coverage)
- **Rich Match Data** - Results, statistics, referee info, comprehensive betting odds
- **Team Mapping** - Complete translation for all 51 historical Premier League teams
- **Weekly Updates** - Automated downloads of current season data every Sunday
- **Change Detection** - Smart updates only when actual data changes occur
- **Sample Management** - Automatic cleanup with configurable retention (5 files default)

### Data Includes

- **Match Results** - Full-time/half-time scores and results
- **Team Statistics** - Shots (total/on target), corners, cards, fouls for each team
- **Official Information** - Referee assignments for each match
- **Betting Markets** - Home/Draw/Away odds from multiple bookmakers (Bet365, William Hill, etc.)
- **Advanced Markets** - Over/under goals, Asian handicap, correct score odds

### Scheduler Integration

- **Weekly Collection** - Runs automatically on Sundays at 9 AM via master scheduler
- **Change Triggering** - Updates last_update table to trigger automated database uploads
- **Configuration Control** - `ENABLE_FETCH_FOOTBALL_DATA=true/false` in scheduler config

---

## Master Scheduler System

### Overview

Centralized orchestration system that manages all automated script execution with a single cron entry.

### Commands

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

### Features

- **Centralized Orchestration** - Single cron entry manages all script execution
- **Intelligent Timing** - Scripts run at optimal intervals based on data requirements
- **Process Management** - Lock files prevent overlapping executions
- **Error Handling** - Individual script failures don't affect other scripts
- **Configurable Control** - Enable/disable individual scripts via configuration

### Execution Schedule

- **Every Minute**: fetch_results.py, monitor_and_upload.py (with 10s sequencing)
- **Every 15 Minutes**: clean_predictions_dropbox.py
- **Every 30 Minutes**: fetch_fixtures_gameweeks.py
- **Every Hour**: automated_predictions.py (dual-file upload with UK timezone notifications)
- **Daily 7 AM**: fetch_fpl_data.py, fetch_odds.py
- **Daily 8 AM**: fetch_pulse_data.py
- **Weekly Sundays 9 AM**: fetch_football_data.py
- **Daily 2 AM**: Cleanup old logs and locks

### Configuration Override

Edit `scripts/scheduler/scheduler_config.conf`:

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

---

## Predictions Analysis System

### Overview

Automated predictions system with 7 different strategies for generating scoreline predictions, with comprehensive performance analysis across historical seasons.

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

### Performance Metrics

**Metrics Calculated:**

- **Total Points**: Sum of all prediction points (2 for exact score, 1 for correct result)
- **Accuracy Rate**: Percentage of correct results predicted
- **Correct Results**: Count of matches where result (H/D/A) was correct
- **Exact Scores**: Count of matches where exact scoreline was predicted
- **Games Analyzed**: Total fixtures with both odds and results available
- **Avg Points/Game**: Average points earned per fixture

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

---

## Prediction Verification System

### Overview

Automated verification system that compares predictions in the database against WhatsApp messages and text files in Dropbox, identifying discrepancies and ensuring data accuracy.

### Features

**Data Sources:**

- All `.txt` files in `/Messages` Dropbox folder (with timestamp support: `DD/MM/YYYY, HH:MM`)
- WhatsApp chat exports (`.zip` files containing `_chat.txt` with `[DD/MM/YYYY, HH:MM:SS]` timestamps)
- Database predictions table

**Timestamp-Based Priority Logic:**

1. **Predictions with scores take priority** over predictions without scores
2. When both have scores (or both don't), **latest timestamp wins**
3. **Tom Levin/Thomas Levin predictions without scores are ignored** (fixture-only messages)

**Verification Categories:**

- **Matches**: Same player/fixture/score in both database and messages
- **Score Mismatches**: Same player/fixture, different scores
- **In Messages Only**: Predictions found in messages but not in database
- **In Database Only**: Predictions in database but not found in messages

### Database Schema

**Table: `prediction_verification`**

```sql
CREATE TABLE prediction_verification (
    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    player_id INTEGER,
    fixture_id INTEGER,
    db_home_goals INTEGER,
    db_away_goals INTEGER,
    message_home_goals INTEGER,
    message_away_goals INTEGER,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);

-- Indexes for performance
CREATE INDEX idx_verification_category ON prediction_verification(category);
CREATE INDEX idx_verification_player ON prediction_verification(player_id);
CREATE INDEX idx_verification_fixture ON prediction_verification(fixture_id);
```

### Name Alias Mapping

The system handles player name variations between messages and database:

```python
NAME_ALIASES = {
    'ed fenna': 'edward fenna',
    'steven harrison': 'ste harrison',
    'steve harrison': 'ste harrison',
    'thomas levin': 'tom levin',
    'tom levo': 'tom levin',
    'olly spence-robb': 'olly spence robb',
}
```

### Team Order Preservation

Critical fix (October 2025): Teams are extracted based on **position in text**, not alphabetical order, preventing fixtures like "Everton vs Crystal Palace" being reversed to "Crystal Palace vs Everton".

```python
def extract_teams_from_line(line, teams):
    """Extract team names from line based on their position in the text"""
    team_positions = []
    for team in teams:
        if team in line:
            pos = line.find(team)
            team_positions.append((pos, team))
    # Sort by position in text (earliest first)
    team_positions.sort(key=lambda x: x[0])
    return [team for pos, team in team_positions]
```

### Running Verification

```bash
# Run full verification
./venv/bin/python scripts/analysis/verify_predictions_from_messages.py

# Verify specific gameweek
./venv/bin/python scripts/analysis/verify_predictions_from_messages.py --gameweek 7

# Verify specific player
./venv/bin/python scripts/analysis/verify_predictions_from_messages.py --player "Chris Hart"
```

### Output

**Database Table:**

- Results saved to `prediction_verification` table
- Table is cleared and repopulated on each run
- Supports SQL queries for analysis

**CSV Report:**

- Backup report: `analysis_reports/prediction_verification_YYYYMMDD_HHMMSS.csv`
- Contains: Category, Player, Gameweek, Fixture, DB Score, Message Score

**Console Summary:**

- Match count, mismatch count
- Detailed list of any score mismatches
- List of predictions only in messages

### Message Format Examples

**Text File Format with Timestamp:**

```
Josh Jones

04/10/2025, 20:40

Bournemouth v Fulham              # No score - ignored
Leeds v Spurs                      # No score - ignored
Aston Villa 2-0 Burnley           # HAS SCORE - used
Everton 1-2 Crystal Palace        # HAS SCORE - used
```

**WhatsApp Format:**

```
[09/10/2025, 14:02:35] Josh Jones: Brighton 0 - 2 Wolves
[09/10/2025, 14:03:12] Josh Jones: Man City 3 - 0 Brentford
```

### Common Issues Fixed

1. **Player Name Mismatches**: Name aliases resolve variations like "Ed Fenna" → "Edward Fenna"
2. **Team Order Reversal**: Text position-based extraction maintains correct home/away order
3. **Prediction Attribution**: Unrecognized player names no longer cause predictions to be attributed to wrong players
4. **Timestamp Priority**: Predictions with scores take priority; latest timestamp wins when both have/lack scores (Oct 2025)

### Example Query

```sql
-- Find all score mismatches
SELECT
    p.player_name,
    f.gameweek,
    ht.team_name || ' vs ' || at.team_name as fixture,
    pv.db_home_goals || '-' || pv.db_away_goals as db_score,
    pv.message_home_goals || '-' || pv.message_away_goals as message_score
FROM prediction_verification pv
JOIN players p ON pv.player_id = p.player_id
JOIN fixtures f ON pv.fixture_id = f.fixture_id
JOIN teams ht ON f.home_teamid = ht.team_id
JOIN teams at ON f.away_teamid = at.team_id
WHERE pv.category = 'Score Mismatch';
```
