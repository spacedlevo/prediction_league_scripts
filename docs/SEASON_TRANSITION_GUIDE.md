# Season Transition Guide for Prediction League Script

## Executive Summary

This document provides a comprehensive guide for transitioning the Prediction League Script to a new season. The system currently runs for **2025/2026** season. All critical season-dependent components, their locations, and transition procedures are documented below.

## 🎯 CENTRALIZED SEASON CONFIGURATION (Updated 2025)

**IMPORTANT:** Season management has been centralized! Instead of updating 9+ individual files, you now only need to update **ONE file**: `scripts/config.py`

### Quick Season Transition (New Method)
```python
# scripts/config.py - Update this ONE line for new season
CURRENT_SEASON = "2026/2027"  # Change this line only
```

All scripts automatically import from this central configuration. The helper functions handle format conversions:
- `get_football_data_url_code()` - Converts "2026/2027" → "2627" for API URL
- `get_season_dropbox_format()` - Converts "2026/2027" → "2026_27" for Dropbox paths
- `get_season_database_format()` - Returns "2026/2027" for database queries

**Files that use centralized config:**
- ✅ All 7 critical data collection scripts
- ✅ All 3 high priority prediction/analysis scripts
- ✅ Automatic format conversion (no manual URL updates needed!)

---

## Part 1: Database Schema - Season-Related Tables

### Overview
The database stores season information across multiple tables. The season format is **"YYYY/YYYY+1"** (e.g., "2025/2026").

### Tables Containing Season Data

#### 1. **fixtures** table
- **Column**: `season` (TEXT)
- **Purpose**: Stores which season each match belongs to
- **Example values**: "2025/2026", "2024/2025"
- **Records per season**: ~380 matches (Premier League standard)

#### 2. **results** table
- **Linked to**: fixtures via `fpl_fixture_id` or `fixture_id`
- **No direct season column** - Use JOIN with fixtures to get season
- **Stores**: Match outcomes (goals scored)

#### 3. **predictions** table
- **Linked to**: fixtures via `fixture_id`
- **No direct season column** - Use JOIN to get season
- **Stores**: Player predictions for matches

#### 4. **fantasy_pl_scores** table
- **Linked to**: fixtures via `fixture_id`
- **Stores**: Player gameweek performance data from FPL API

#### 5. **football_stats** table
- **Column**: `Season` (TEXT)
- **Purpose**: Historical match data from football-data.co.uk (1993-2025)
- **Records**: 12,324 total matches across 32 seasons

#### 6. **fpl_players_bootstrap** table
- **Column**: `season` (TEXT)
- **Purpose**: Player profile snapshots from FPL API
- **Updated**: Weekly or when FPL data changes

#### 7. **season_recommendations** table (NEW - Strategic Recommendations)
- **Column**: `season` (TEXT)
- **Purpose**: Strategy recommendations based on season characteristics
- **Records**: One per season with analysis updates

#### 8. **strategy_season_performance** table
- **Column**: `season` (TEXT)
- **Purpose**: Track performance of different strategies per season

#### 9. **historical_season_patterns** table
- **Column**: `season` (TEXT)
- **Purpose**: Pre-calculated patterns for historical seasons for comparison

#### 10. **gameweeks** table (Season-adjacent)
- **No direct season column** BUT contains deadline data for current season
- **Scope**: Current/active season only

---

## Part 2: Centralized Season Configuration (NEW)

The current season is defined as **"2025/2026"** in the centralized configuration file: `scripts/config.py`

### ✅ NEW: Single Update Location

**File:** `scripts/config.py`

```python
CURRENT_SEASON = "2025/2026"  # Update this ONE line for season transitions
```

**What happens automatically when you update this:**
1. All 10 scripts import and use the new season value
2. Helper functions generate correct formats:
   - Football-data URL: Automatically converts to "2526" format
   - Dropbox paths: Automatically converts to "2025_26" format
   - Database queries: Uses "2025/2026" format

### 📋 Scripts Using Centralized Config (All Updated Automatically)

**Critical Scripts (7):**
1. `scripts/prediction_league/automated_predictions.py` - Prediction generation
2. `scripts/prediction_league/clean_predictions_dropbox.py` - Dropbox sync
3. `scripts/fpl/fetch_results.py` - Match results
4. `scripts/fpl/fetch_fixtures_gameweeks.py` - Fixture schedule
5. `scripts/fpl/fetch_fpl_data.py` - Player data
6. `scripts/football_data/fetch_football_data.py` - Historical data (with auto URL generation)
7. `scripts/pulse_api/fetch_pulse_data.py` - Match officials/team lists

**High Priority Scripts (3):**
8. `scripts/database/setup_season_recommendations.py` - Season initialization
9. `scripts/prediction_league/update_season_recommendations.py` - Weekly analysis
10. `scripts/analysis/verify_predictions_from_messages.py` - Prediction verification

### 🔧 Helper Functions Available

```python
from scripts.config import (
    CURRENT_SEASON,                   # "2025/2026"
    get_football_data_url_code,       # Returns "2526"
    get_season_dropbox_format,        # Returns "2025_26"
    get_season_database_format        # Returns "2025/2026"
)
```

### ⚠️ OPTIONAL UPDATES (Analysis Scripts - Not Updated)

These scripts still have hardcoded seasons for historical analysis purposes:
11. `scripts/football_data/migrate_legacy_data.py` Line 31
12. `scripts/analysis/ninety_minute_analysis.py` Lines 25, 241
13. `scripts/analysis/goals_per_gameweek.py` Line 23
14. `scripts/analysis/plot_results_charts.py` Lines 74, 209
15. `scripts/analysis/player_minutes_analysis.py` Line 512

**Note:** These are analysis scripts that may intentionally target specific historical seasons.

---

## Part 3: Scripts and Systems by Function

### Data Collection Systems

#### FPL Data Collection (Fantasy Premier League API)
- Scripts: fetch_fixtures_gameweeks.py, fetch_results.py, fetch_fpl_data.py
- Frequency: Continuous (every 30 mins to 1 hour)
- Season handling: Automatic - stops when season ends
- Action: Update CURRENT_SEASON constant

#### Football-Data.co.uk Data (Historical + Current Season)
- Script: fetch_football_data.py
- Frequency: Weekly (Sundays at 9 AM)
- CRITICAL: Update both CURRENT_SEASON and FOOTBALL_DATA_URL
- URL pattern: mmz4281/XXYY/E0.csv (XXYY = last 2 digits of both season years)

#### Pulse Live API (Match officials, team lists, events)
- Script: fetch_pulse_data.py
- Frequency: Daily at 8 AM
- Season handling: Accepts --season argument for flexibility
- Action: Update CURRENT_SEASON default

#### Odds Data Collection (Betting odds)
- Script: fetch_odds.py
- Season handling: Automatic via fixture references
- Action: No code changes needed

### Prediction Systems

#### Automated Predictions
- Script: automated_predictions.py
- Frequency: Every hour
- Uses CURRENT_SEASON to determine gameweek
- Integration: Uses season_recommendations for strategy selection
- CRITICAL: Update CURRENT_SEASON

#### Season Recommendations
- Scripts: setup_season_recommendations.py (initial), update_season_recommendations.py (weekly)
- Database: season_recommendations, historical_season_patterns, strategy_season_performance tables
- Frequency: Weekly analysis (Sundays at 10 AM)
- New season action: Run setup script, add patterns table entries

---

## Part 4: Configuration and Scheduling

### Scheduler Configuration
File: `scripts/scheduler/scheduler_config.conf`

Off-season settings (update only during summer break):
```conf
OFFSEASON_MODE=false  # Set to true during off-season
ENABLE_AUTOMATED_PREDICTIONS=true  # Disable during off-season
ENABLE_FETCH_RESULTS=true
ENABLE_FETCH_FIXTURES=true
ENABLE_FETCH_FPL_DATA=true
```

### Keys and Web Configuration
- `keys.json` - No season-specific settings (API keys only)
- `webapp/config.json` - No season-specific settings (web app uses dynamic queries)

---

## Part 5: Step-by-Step Transition Timeline (NEW SIMPLIFIED PROCESS)

### ⚡ June-July (Before Season Starts) - Now Just 5 Minutes!

#### 1. **Update Season Configuration** (1 minute)

Edit `scripts/config.py` and change ONE line:

```python
# scripts/config.py
CURRENT_SEASON = "2026/2027"  # Update this line
```

That's it! All 10 scripts will automatically use the new season.

#### 2. **Verify Import Works** (30 seconds)

```bash
# Activate virtual environment
source venv/bin/activate

# Test the config imports correctly
python -c "from scripts.config import CURRENT_SEASON, get_football_data_url_code; print(f'Season: {CURRENT_SEASON}, URL Code: {get_football_data_url_code()}')"

# Expected output: Season: 2026/2027, URL Code: 2627
```

#### 3. **Test Scripts with Dry-Run** (2 minutes)

```bash
# Test key scripts to ensure they work with new season
python scripts/fpl/fetch_fixtures_gameweeks.py --dry-run
python scripts/prediction_league/automated_predictions.py --dry-run
python scripts/football_data/fetch_football_data.py --test
```

All scripts should now reference the new season automatically!

### 📅 Week Before Season Starts

#### 1. **Initialize Season Recommendations** (1 minute)

```bash
python scripts/database/setup_season_recommendations.py
```

This populates the season_recommendations tables with initial data for the new season.

#### 2. **Verify Scheduler Configuration** (30 seconds)

```bash
# Check all automated systems are enabled
grep "^ENABLE_" scripts/scheduler/scheduler_config.conf

# All should show 'true'
```

### 🚀 Opening Day of Season

#### 1. **Monitor System Logs** (ongoing)

```bash
# Watch key systems
tail -f logs/automated_predictions_*.log
tail -f logs/fixtures_gameweeks_*.log
tail -f logs/fetch_football_data_*.log
```

#### 2. **Verify Database Entries** (see verification section below)

---

## Part 6: Verification Checklist (SIMPLIFIED)

### ✅ Quick Verification Steps

#### 1. Verify Config Update (10 seconds)

```bash
# Check the centralized config file
cat scripts/config.py | grep "CURRENT_SEASON ="

# Should show: CURRENT_SEASON = "2026/2027"
```

#### 2. Test Import and Helper Functions (10 seconds)

```bash
# Verify all helper functions work
python -c "
from scripts.config import CURRENT_SEASON, get_football_data_url_code, get_season_dropbox_format
print(f'Season: {CURRENT_SEASON}')
print(f'Football-data URL code: {get_football_data_url_code()}')
print(f'Dropbox format: {get_season_dropbox_format()}')
"

# Expected output:
# Season: 2026/2027
# Football-data URL code: 2627
# Dropbox format: 2026_27
```

#### 3. Verify Database Has New Season Fixtures (30 seconds)

```bash
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect("data/database.db")
c = conn.cursor()
c.execute("SELECT DISTINCT season FROM fixtures ORDER BY season DESC LIMIT 5")
print("Seasons in database:", c.fetchall())
c.execute("SELECT COUNT(*) FROM fixtures WHERE season = '2026/2027'")
print("Fixtures for new season:", c.fetchone()[0])
conn.close()
EOF
```

#### 4. Test Critical Scripts (2 minutes)

```bash
# Test with dry-run flags
python scripts/prediction_league/automated_predictions.py --dry-run
python scripts/fpl/fetch_fixtures_gameweeks.py --dry-run
python scripts/football_data/fetch_football_data.py --test
```

### 🔍 Optional: Verify All Scripts Import Correctly

```bash
# Check that all 10 scripts can import the config
for script in \
  scripts/prediction_league/automated_predictions.py \
  scripts/prediction_league/clean_predictions_dropbox.py \
  scripts/fpl/fetch_results.py \
  scripts/fpl/fetch_fixtures_gameweeks.py \
  scripts/fpl/fetch_fpl_data.py \
  scripts/football_data/fetch_football_data.py \
  scripts/pulse_api/fetch_pulse_data.py \
  scripts/database/setup_season_recommendations.py \
  scripts/prediction_league/update_season_recommendations.py \
  scripts/analysis/verify_predictions_from_messages.py
do
  echo "Testing: $script"
  python -c "import sys; sys.path.insert(0, '.'); exec(open('$script').read().split('if __name__')[0])" 2>&1 | head -1
done
```

---

## Part 7: Critical Issues and Solutions (UPDATED)

### ✅ Issue: Football-Data URL Wrong

**OLD Problem:** Had to manually calculate and update URL code (2526, 2627, etc.)
**NEW Solution:** URL is automatically generated by `get_football_data_url_code()` helper function!

If you still get 404 errors:
```bash
# Check the URL is being generated correctly
python -c "from scripts.config import get_football_data_url_code; print(get_football_data_url_code())"
```

### ✅ Issue: Predictions Not Generating for New Season

**Symptom:** No predictions created, no Dropbox uploads

**NEW Solution:**
1. Verify `scripts/config.py` has correct season
2. Check fixtures exist for upcoming gameweek
3. Verify season_recommendations table populated:
   ```bash
   python scripts/database/setup_season_recommendations.py
   ```

### ✅ Issue: Import Error When Running Scripts

**Symptom:** `ModuleNotFoundError: No module named 'scripts.config'`

**Solution:**
```bash
# Make sure you're in the project root directory
pwd  # Should show: /path/to/prediction_league_script

# Run scripts from project root
python scripts/fpl/fetch_results.py
```

### ✅ Issue: Config Shows Old Season

**Symptom:** Scripts still using old season after updating `scripts/config.py`

**Solution:**
```bash
# 1. Verify the file was saved
cat scripts/config.py | grep CURRENT_SEASON

# 2. Check for Python cache issues
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# 3. Test import again
python -c "from scripts.config import CURRENT_SEASON; print(CURRENT_SEASON)"
```

---

## Summary: NEW vs OLD Transition Process

### 🎉 NEW CENTRALIZED APPROACH (Implemented 2025)

| **What to Update** | **Where** | **Time Required** |
|-------------------|-----------|-------------------|
| Season configuration | `scripts/config.py` line 9 | 10 seconds |
| **Total files to edit** | **1 file** | **~5 minutes total** |

**All 10 scripts automatically updated!** ✅

### 📊 OLD APPROACH (Before 2025)

| **What to Update** | **Count** | **Time Required** |
|-------------------|-----------|-------------------|
| Individual script constants | 10 files | 15-20 minutes |
| Manual URL calculations | 1 file | 2 minutes |
| Format conversions | 3 locations | 3 minutes |
| Risk of missing a file | High ⚠️ | - |
| **Total files to edit** | **10+ files** | **~30 minutes** |

### 🚀 Improvement Summary

- **90% less time** - 5 minutes instead of 30 minutes
- **90% fewer files** - 1 file instead of 10+ files
- **Zero calculation errors** - Helper functions handle all format conversions
- **Zero missed updates** - All scripts import from one source
- **Easier maintenance** - Single source of truth

### 📝 Quick Reference Card

```bash
# NEW SEASON TRANSITION PROCESS (5 Minutes Total)

# 1. Edit ONE file (1 minute)
vim scripts/config.py  # Change CURRENT_SEASON line

# 2. Verify import works (30 seconds)
python -c "from scripts.config import CURRENT_SEASON; print(CURRENT_SEASON)"

# 3. Test key scripts (2 minutes)
python scripts/fpl/fetch_fixtures_gameweeks.py --dry-run
python scripts/prediction_league/automated_predictions.py --dry-run

# 4. Initialize new season (1 minute)
python scripts/database/setup_season_recommendations.py

# Done! All systems ready for new season.
```

