# CLAUDE.md - Development Guidelines

Guidelines for Python development in this hobby project, optimized for simplicity and maintainability.

## Table of Contents

- [Project Philosophy](#project-philosophy)
- [Quick Start](#quick-start)
- [Python Best Practices](#python-best-practices-for-hobby-development)
  - [Function Design](#1-function-design)
  - [Self-Documenting Code](#2-self-documenting-code)
  - [Error Handling](#3-error-handling)
  - [Logging](#4-logging)
  - [Configuration Management](#5-configuration-management)
  - [Command Line Interface](#6-command-line-interface)
  - [Database Operations](#7-database-operations)
- [Scripts Structure](#scripts-structure)
- [Testing Approach](#testing-approach)
- [Comments Policy](#comments-policy)
- [Development Tools Overview](#development-tools-overview)
- [Summary](#summary)
- [Additional Documentation](#additional-documentation)

---

## Project Philosophy

This is a **hobby project for personal use**, not a commercial application. The development approach prioritizes:
- **Simplicity over complexity**
- **Readability over performance optimization**
- **Self-documenting code over extensive comments**
- **Practical functionality over academic perfection**

---

## Quick Start

### Essential Commands
```bash
# Activate virtual environment (ALWAYS do this first)
source venv/bin/activate

# Test with sample data before live run
python script.py --test

# Run with live data
python script.py

# Monitor logs in real-time
tail -f logs/script_$(date +%Y%m%d).log

# Check database upload status
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run
```

### Common Development Workflow
```bash
# 1. Activate venv
source venv/bin/activate

# 2. Test your script with sample data
python scripts/your_script/script.py --test

# 3. Check logs for errors
tail -f logs/your_script_$(date +%Y%m%d).log

# 4. Run with live data when ready
python scripts/your_script/script.py

# 5. Verify database changes
sqlite3 data/database.db "SELECT * FROM last_update ORDER BY timestamp DESC LIMIT 5;"
```

### Key Dependencies
- `requests` - HTTP client for API calls
- `paramiko` - SSH/SFTP for PythonAnywhere uploads
- `tqdm` - Progress bars for long operations
- `pytz` - **REQUIRED** - Timezone handling for UK time display (BST/GMT conversion)

### Master Scheduler Setup
```bash
# Single cron entry manages all automated scripts
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh

# Monitor scheduler activity
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log
```

---

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

## Development Tools Overview

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

**Note**: See [Quick Start](#quick-start) section for common commands and key dependencies.

### Automated Systems

This project includes several automated systems:

- **Database Upload System** - Monitors database changes and automatically uploads to PythonAnywhere
- **Dropbox OAuth2 System** - Manages Dropbox authentication with automatic token refresh
- **Automated Predictions System** - Generates predictions based on betting odds
- **Pulse API System** - Collects detailed match data (officials, team lists, events)
- **Football-Data System** - Maintains historical Premier League data (1993-2025)
- **Master Scheduler System** - Centralized orchestration of all automated scripts
- **Predictions Analysis System** - Multi-strategy predictions with performance analysis
- **Prediction Verification System** - Validates predictions against WhatsApp messages

For detailed documentation on each system, see: **[docs/SYSTEMS.md](docs/SYSTEMS.md)**

### Production Deployment

For production deployment guides, systemd service configuration, and troubleshooting, see: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**

### Critical System Fixes

For historical fixes and changelog, see: **[docs/FIXES_CHANGELOG.md](docs/FIXES_CHANGELOG.md)**

**Recent Fixes Summary:**

- **Nov 2025**: Upload timestamp visibility on PythonAnywhere
- **Oct 2025**: Upload timestamp logic simplification
- **Sep 2025**: Unnecessary timestamp updates fixed
- **Aug 2025**: Transaction ordering bugs, missing fixtures timestamps, timezone conversion fixes

---

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

---

## Additional Documentation

### Core Documentation

- **[SYSTEMS.md](docs/SYSTEMS.md)** - Detailed documentation for all automated systems
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Production deployment guide and troubleshooting
- **[FIXES_CHANGELOG.md](docs/FIXES_CHANGELOG.md)** - Historical fixes and system improvements

### Quick Reference

**Common Commands:**

```bash
# Virtual environment
source venv/bin/activate

# Test scripts
python script.py --test

# Monitor logs
tail -f logs/script_$(date +%Y%m%d).log

# Database upload
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run

# Scheduler logs
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log
```

**Key Files:**

- `keys.json` - API keys and credentials (permissions: 640)
- `data/database.db` - Main SQLite database
- `scripts/scheduler/scheduler_config.conf` - Scheduler configuration
- `logs/` - All log files organized by system

**Useful SQL Queries:**

```sql
-- Check recent updates
SELECT * FROM last_update ORDER BY timestamp DESC LIMIT 5;

-- Verify fixtures
SELECT gameweek, COUNT(*) FROM fixtures WHERE season='2025/2026' GROUP BY gameweek;

-- Check predictions
SELECT COUNT(*) FROM predictions p JOIN fixtures f ON p.fixture_id = f.fixture_id WHERE f.season='2025/2026';
```
