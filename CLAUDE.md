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
- **Every Hour**: automated_predictions.py
- **Daily 7 AM**: fetch_fpl_data.py, fetch_odds.py
- **Daily 8 AM**: fetch_pulse_data.py (NEW - September 2025)
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