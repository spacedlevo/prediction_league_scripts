# Force Mode for Automated Predictions Script

## Overview
The automated_predictions.py script now supports a `--force` mode that bypasses all normal checks and safety mechanisms.

## Usage

### Basic Force Mode
```bash
# Force run with next upcoming gameweek
./venv/bin/python scripts/prediction_league/automated_predictions.py --force
```

### Force Mode with Specific Gameweek
```bash
# Force run with specific gameweek
./venv/bin/python scripts/prediction_league/automated_predictions.py --force --gameweek 5
```

### Help
```bash
# Show all available options
./venv/bin/python scripts/prediction_league/automated_predictions.py --help
```

## What Force Mode Bypasses

### Normal Checks (Bypassed in Force Mode):
1. **36-hour deadline check** - Normally only runs when deadline is within 36 hours
2. **Existing file check** - Normally skips if predictions file already exists in Dropbox
3. **Recent processing check** - Normally skips if predictions were processed in last hour
4. **Fixtures notification frequency** - Normally only sends fixtures notification once per 24 hours

### What Still Happens in Force Mode:
- ✅ Strategy retrieval from database (1-0 vs 2-1)
- ✅ Odds data fetching and prediction generation
- ✅ Dropbox upload attempts (both locations)
- ✅ Pushover notifications
- ✅ Database timestamp updates
- ✅ Complete logging

## Use Cases

### Development & Testing
```bash
# Test prediction generation without waiting for deadline
./venv/bin/python scripts/prediction_league/automated_predictions.py --force --gameweek 5
```

### Emergency Prediction Generation
```bash
# Generate predictions when normal schedule fails
./venv/bin/python scripts/prediction_league/automated_predictions.py --force
```

### Historical Analysis
```bash
# Generate predictions for past gameweeks (if odds data exists)
./venv/bin/python scripts/prediction_league/automated_predictions.py --force --gameweek 3
```

## Error Handling

### Invalid Usage
```bash
# This will fail with helpful error message
./venv/bin/python scripts/prediction_league/automated_predictions.py --gameweek 5
# Error: --gameweek requires --force mode. Use --force --gameweek N
```

### Force Mode Behavior
- **No odds data**: Script will log warning and complete normally
- **Dropbox failures**: Script continues and logs errors (same as normal mode)
- **Invalid gameweek**: Script will attempt to process but may find no data

## Log Output Examples

### Force Mode with Specific Gameweek:
```
INFO - Starting automated predictions script in FORCE mode - bypassing all checks
INFO - Force mode: Using specified gameweek 5
INFO - Force mode: Skipping deadline check
INFO - Force mode: Skipping file existence and recent processing checks
INFO - Found 10 fixtures with odds for gameweek 5
INFO - Using 1-0 strategy for automated predictions
INFO - Created 1-0 strategy predictions for 10 fixtures
```

### Force Mode with Upcoming Gameweek:
```
INFO - Starting automated predictions script in FORCE mode - bypassing all checks
INFO - Next gameweek: 5, deadline: 2025-09-20 10:00:00+00:00
INFO - Force mode: Skipping deadline check
INFO - Force mode: Skipping fixtures notification recent processing check
```

## Safety Notes

- Force mode bypasses all safety checks - use responsibly
- Can generate duplicate predictions if run multiple times
- May send multiple notifications if Pushover is working
- Always check logs for any errors or issues
- Consider the impact on API rate limits and Dropbox usage

## Current Strategy Verification

As of September 2025, the script correctly uses the **1-0 strategy** for favorites based on season recommendations:
- Home favorites: "Team A 1-0 Team B"
- Away favorites: "Team A 0-1 Team B"
- Missing odds: "Team A 1-1 Team B"