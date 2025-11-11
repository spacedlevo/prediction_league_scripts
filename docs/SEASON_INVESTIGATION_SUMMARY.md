# Season Management Investigation - Complete Summary

## Overview

This investigation examined how the Prediction League Script manages seasons across its database, automation systems, and data collection pipelines. The codebase demonstrates a well-structured approach to season handling, though season configuration is currently managed through hardcoded constants in multiple scripts.

**Current Season**: 2025/2026
**Total Database Tables with Season Data**: 10 primary tables
**Hardcoded Season Constants**: 15+ locations across scripts
**Scripts Affected**: 18+ Python scripts

---

## Key Findings

### 1. Database Architecture - Season Storage

The database implements season management across 10 tables:

**Direct Season Column (4 tables)**:
- `fixtures.season` - All ~380 Premier League matches per season
- `football_stats.Season` - Historical data from 1993-2025 (12,324 total matches)
- `fpl_players_bootstrap.season` - Weekly player snapshots
- `season_recommendations.season` - Strategy recommendations

**Indirect Season References (6 tables)**:
- `results` - Linked via fixtures table JOIN
- `predictions` - Linked via fixtures table JOIN
- `fantasy_pl_scores` - Linked via fixtures table JOIN
- `strategy_season_performance` - Season tracking table
- `historical_season_patterns` - Pattern comparison table
- `gameweeks` - Current season only (no season column)

**Season Format**: YYYY/YYYY+1 (e.g., "2025/2026")

### 2. Hardcoded Season Constants - Critical Update Points

**CRITICAL (9 locations) - System fails if missed**:

| Script | Line | Current Value | Priority |
|--------|------|---------------|----------|
| automated_predictions.py | 53 | CURRENT_SEASON = "2025/2026" | FAIL |
| clean_predictions_dropbox.py | 43 | CURRENT_SEASON = "2025_26" | FAIL |
| clean_predictions_dropbox.py | 44 | CURRENT_SEASON_DB = "2025/2026" | FAIL |
| fetch_results.py | 40 | CURRENT_SEASON = "2025/2026" | FAIL |
| fetch_fixtures_gameweeks.py | 49 | CURRENT_SEASON = "2025/2026" | FAIL |
| fetch_fpl_data.py | 91 | CURRENT_SEASON = "2025/2026" | FAIL |
| fetch_football_data.py | 41 | CURRENT_SEASON = "2025/2026" | FAIL |
| fetch_football_data.py | 42 | FOOTBALL_DATA_URL = "...2526/E0.csv" | FAIL |
| fetch_pulse_data.py | 59 | CURRENT_SEASON = "2025/2026" | FAIL |

**HIGH PRIORITY (3 locations) - Functionality breaks**:
- setup_season_recommendations.py (line 121)
- update_season_recommendations.py (line 291)
- verify_predictions_from_messages.py (line 38)

**LOW PRIORITY (3+ locations) - Analysis scripts**:
- migrate_legacy_data.py, ninety_minute_analysis.py, goals_per_gameweek.py, etc.

### 3. Automated Systems and Their Season Dependencies

**Data Collection Pipeline**:
```
FPL API → fixtures, gameweeks, results tables
Football-Data API → football_stats table
Pulse API → match_officials, team_list, match_events
FPL Bootstrap → fpl_players_bootstrap table
Odds API → odds, fixture_odds_summary tables
```

**Prediction Pipeline**:
```
season_recommendations (strategy selection)
  ↓
automated_predictions.py (generates 1-0 or 2-1 strategies)
  ↓
clean_predictions_dropbox.py (uploads to Dropbox)
```

**Analysis & Verification**:
```
update_season_recommendations.py (weekly analysis)
verify_predictions_from_messages.py (accuracy tracking)
```

### 4. Data Flow by System

**Frequency Breakdown**:
- Every minute: fetch_results.py (FPL results)
- Every 30 minutes: fetch_fixtures_gameweeks.py (FPL fixtures)
- Every hour: automated_predictions.py (predictions)
- Every 15 minutes: clean_predictions_dropbox.py (upload cleanup)
- Daily 7 AM: fetch_fpl_data.py (player data)
- Daily 8 AM: fetch_pulse_data.py (match officials)
- Daily 11 AM: verify_predictions_from_messages.py (verification)
- Weekly Sundays 9 AM: fetch_football_data.py (historical data)
- Weekly Sundays 10 AM: update_season_recommendations.py (analysis)

### 5. Critical URL Pattern Discovery

**Football-Data.co.uk URL Construction**:
```
Base: https://www.football-data.co.uk/mmz4281/{XXYY}/E0.csv

Rule: XXYY = last 2 digits of BOTH years (current year + next year)

Examples:
2025/2026 season → mmz4281/2526/E0.csv
2026/2027 season → mmz4281/2627/E0.csv
2027/2028 season → mmz4281/2728/E0.csv
```

This is a critical detail often missed - the URL uses BOTH year digits, not just one.

### 6. Season Recommendations System (NEW)

The system includes an intelligent strategy recommendation engine:

**Tables**:
- `season_recommendations` - Current season analysis (strategy, confidence, patterns)
- `historical_season_patterns` - 32+ seasons of pattern data (1993-2025)
- `strategy_season_performance` - Track which strategies work best

**Strategy Logic**:
- Analyzes low-scoring match percentage
- Recommends "1-0" strategy if >47% matches have ≤2 goals
- Recommends "2-1" strategy if ≤47% matches have ≤2 goals
- Current season (2025/2026): 52.5% low-scoring → 1-0 strategy recommended

**Update Frequency**: Weekly on Sundays at 10 AM

---

## Configuration Files

### Scheduler Configuration
**File**: `scripts/scheduler/scheduler_config.conf`

Key settings:
- `OFFSEASON_MODE=false` (set to true during summer break)
- `ENABLE_AUTOMATED_PREDICTIONS=true` (disable during off-season)
- Individual enable/disable flags for each data collection system

### Other Configuration
- **keys.json** - API credentials (no season-specific settings)
- **webapp/config.json** - Web app configuration (uses dynamic queries)

---

## Complete File Inventory

### Season-Critical Scripts (15 files)
```
scripts/prediction_league/automated_predictions.py
scripts/prediction_league/clean_predictions_dropbox.py
scripts/prediction_league/update_season_recommendations.py
scripts/prediction_league/test_1_0_strategy.py
scripts/fpl/fetch_fixtures_gameweeks.py
scripts/fpl/fetch_results.py
scripts/fpl/fetch_fpl_data.py
scripts/football_data/fetch_football_data.py
scripts/football_data/migrate_legacy_data.py
scripts/pulse_api/fetch_pulse_data.py
scripts/database/setup_season_recommendations.py
scripts/analysis/verify_predictions_from_messages.py
scripts/analysis/ninety_minute_analysis.py
scripts/analysis/goals_per_gameweek.py
scripts/analysis/plot_results_charts.py
(and 3+ more analysis scripts)
```

### Configuration Files (3 files)
```
scripts/scheduler/scheduler_config.conf
keys.json
webapp/config.json
```

### Documentation Generated
```
docs/SEASON_TRANSITION_GUIDE.md (319 lines)
docs/SEASON_MANAGEMENT_OVERVIEW.txt (219 lines)
```

---

## Transition Procedure Summary

### Before Season Starts (June-July)
1. Update 9 CRITICAL CURRENT_SEASON constants across scripts
2. Update FOOTBALL_DATA_URL with correct year digits
3. Test with --dry-run flags

### Week Before Season Starts
1. Run `setup_season_recommendations.py`
2. Verify scheduler config has OFFSEASON_MODE=false

### Opening Day
1. Monitor logs for errors
2. Verify database population
3. Check Dropbox uploads

---

## Common Pitfalls & Solutions

### Missing URL Update
**Symptom**: Football-data script returns empty CSV
**Solution**: Verify both CURRENT_SEASON and FOOTBALL_DATA_URL updated

### Predictions Not Generating
**Symptom**: No files in predictions directory
**Solution**: Check all 9 CRITICAL constants updated

### Wrong Dropbox Directory
**Symptom**: Files uploading to old season folder
**Solution**: Check BOTH CURRENT_SEASON and CURRENT_SEASON_DB in clean_predictions_dropbox.py

### Old Season Still Being Updated
**Symptom**: Gameweek doesn't increment past season end
**Solution**: Verify ALL scripts updated (even one missed causes issues)

---

## Recommendations for Future Development

1. **Consolidate Season Configuration**: Consider moving all CURRENT_SEASON definitions to a single config file or environment variable
2. **Add Season Validation**: Implement startup checks to ensure all scripts have matching season values
3. **Make URL Dynamic**: Calculate football-data URL based on CURRENT_SEASON rather than hardcoding
4. **Command-line Flexibility**: Make more scripts accept --season argument (like pulse_api does)
5. **Documentation**: Keep SEASON_TRANSITION_GUIDE.md updated as scripts evolve

---

## Documentation Created

Two comprehensive guides have been created in `/docs/`:

1. **SEASON_TRANSITION_GUIDE.md** (12 KB)
   - Detailed procedures for season transitions
   - Database schema documentation
   - Complete hardcoded constant inventory
   - Step-by-step timeline
   - Verification procedures
   - Troubleshooting guide

2. **SEASON_MANAGEMENT_OVERVIEW.txt** (9.8 KB)
   - Quick reference format
   - At-a-glance tables
   - Critical success factors
   - URL pattern reference
   - Commands quick reference

Both documents provide everything needed for a smooth season transition.

---

## Conclusion

The Prediction League Script has robust season management despite using hardcoded constants. The key to a smooth transition is:

1. Update all 9 critical CURRENT_SEASON constants
2. Remember to update BOTH the season constant AND the football-data URL
3. Run setup_season_recommendations.py before season starts
4. Monitor opening gameweek carefully
5. Use provided checklists and guides for verification

Most systems will work automatically once constants are updated, as the database design uses parametrized queries and dynamic lookups. The transition process typically takes 30 minutes to plan and execute, with ongoing automation handling all season-dependent data collection.

