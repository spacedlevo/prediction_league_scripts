# Master Scheduler System

Centralized orchestration system for all Prediction League automation scripts.

## Overview

The Master Scheduler runs every minute via a single cron job and intelligently manages the execution of all automation scripts based on configurable timing rules.

## Components

### Core Files

- **`master_scheduler.sh`** - Main orchestrator script
- **`scheduler_config.conf`** - Configuration file for timing and enable/disable controls
- **`README.md`** - This documentation

### Supporting Scripts

- **`scripts/fpl/gameweek_validator.py`** - Validates gameweek data accuracy
- **Updated `scripts/fpl/fetch_fixtures_gameweeks.py`** - Now includes gameweek validation

## Installation

### 1. Set Up Cron Job

```bash
# Edit crontab
crontab -e

# Add single entry to run every minute
* * * * * /home/youruser/projects/prediction_league_script/scripts/scheduler/master_scheduler.sh
```

### 2. Configure Settings

Edit `scripts/scheduler/scheduler_config.conf` to customize:
- Enable/disable individual scripts
- Adjust timing intervals
- Set maintenance modes

### 3. Test Setup

```bash
# Test scheduler manually
cd /path/to/project
./scripts/scheduler/master_scheduler.sh

# Check logs
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log
```

## Scheduling Logic

### Execution Schedule

| Script | Frequency | Timing | Notes |
|--------|-----------|---------|-------|
| `fetch_results.py` | Every minute | :00-:15 seconds | FPL results processing |
| `monitor_and_upload.py` | Every minute | :30-:45 seconds | Database upload with delay |
| `clean_predictions_dropbox.py` | Every 15 minutes | :00, :15, :30, :45 | Dropbox prediction cleanup |
| `fetch_fixtures_gameweeks.py` | Every 30 minutes | :00, :30 | Fixtures/gameweeks with validation |
| `automated_predictions.py` | Every hour | :00 (45-60 seconds) | Prediction generation |
| `fetch_fpl_data.py` | Daily | 7:00 AM | FPL data refresh |
| `fetch_odds.py` | Daily | 7:00 AM | Odds data collection |

### Timing Windows

Scripts execute within specific second windows to prevent overlap:
- **Results**: 0-15 seconds
- **Upload**: 30-45 seconds (30s delay)
- **Other scripts**: 15-30 second windows

## Features

### Process Management

- **Lock Files**: Prevents script overlap
- **PID Tracking**: Monitors running processes
- **Timeout Protection**: 1-hour maximum execution time
- **Stale Lock Cleanup**: Auto-removes old locks

### Error Handling

- **Individual Script Isolation**: One script failure doesn't affect others
- **Comprehensive Logging**: Separate logs per script
- **Exit Code Tracking**: Monitors success/failure
- **Graceful Degradation**: Continues operation despite individual failures

### Gameweek Validation

- **Pre-execution Validation**: Checks gameweek accuracy before API calls
- **Deadline Comparison**: Validates current gameweek against deadlines
- **Auto-refresh Triggers**: Forces API refresh when validation fails
- **Post-update Verification**: Confirms data accuracy after updates

## Configuration Options

### Basic Controls

```bash
# Enable/disable individual scripts
ENABLE_FETCH_RESULTS=true
ENABLE_MONITOR_UPLOAD=true
ENABLE_CLEAN_PREDICTIONS=true
ENABLE_FETCH_FIXTURES=true
ENABLE_AUTOMATED_PREDICTIONS=true
ENABLE_FETCH_FPL_DATA=true
ENABLE_FETCH_ODDS=true
```

### Advanced Settings

```bash
# Timing controls
DELAY_BETWEEN_RESULTS_UPLOAD=30

# Emergency controls
SCHEDULER_ENABLED=true
DEBUG_MODE=false

# Seasonal adjustments
OFFSEASON_MODE=false
```

## Operational Modes

### Normal Operation
All scripts enabled with standard timing.

### Development Mode
```bash
# Disable all scripts for testing
ENABLE_FETCH_RESULTS=false
# ... set all to false
DEBUG_MODE=true
```

### Maintenance Mode
```bash
# Only essential services
ENABLE_MONITOR_UPLOAD=true
# ... disable others
```

### Off-Season Mode
```bash
# Reduced activity during FPL off-season
OFFSEASON_MODE=true
```

## Monitoring

### Log Files

- **Master Log**: `logs/scheduler/master_scheduler_YYYYMMDD.log`
- **Individual Scripts**: `logs/scheduler/SCRIPT_NAME_YYYYMMDD.log`
- **Lock Status**: `logs/scheduler/locks/SCRIPT_NAME.lock`

### Log Rotation

- Automatic cleanup of logs older than 30 days
- Runs daily at 2:00 AM
- Configurable retention period

### Health Monitoring

```bash
# Check scheduler status
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log

# View active locks
ls -la logs/scheduler/locks/

# Check individual script logs
tail -f logs/scheduler/fetch_results_$(date +%Y%m%d).log
```

## Troubleshooting

### Common Issues

**Scripts Not Running**
1. Check cron job is active: `crontab -l`
2. Verify script permissions: `chmod +x master_scheduler.sh`
3. Check configuration: Review `scheduler_config.conf`

**Scripts Stuck/Overlapping**
1. Check for stale locks: `ls logs/scheduler/locks/`
2. Remove old locks: `rm logs/scheduler/locks/*.lock`
3. Review timeout settings in config

**Gameweek Validation Failing**
1. Run validation manually: `./scripts/fpl/gameweek_validator.py`
2. Force refresh: `./scripts/fpl/fetch_fixtures_gameweeks.py --force-refresh`
3. Check database connectivity

**Database Uploads Not Triggering** (Fixed Aug 2025)
1. Check last_update table: `SELECT * FROM last_update ORDER BY timestamp DESC;`
2. Verify scripts update timestamps after changes
3. Common cause was transaction bugs preventing timestamp updates
4. Test upload detection: `./scripts/database/monitor_and_upload.py --dry-run`

**Match Window Detection Issues** (Fixed Aug 2025)
1. Database stores kickoff times as UTC (not UK local time)
2. Previous timezone conversion bugs prevented results fetching
3. Test timing: `./scripts/fpl/fetch_results.py --override --dry-run`

### Manual Operations

```bash
# Run individual scripts manually
./venv/bin/python scripts/fpl/fetch_results.py
./venv/bin/python scripts/database/monitor_and_upload.py

# Test gameweek validation
./venv/bin/python scripts/fpl/gameweek_validator.py

# Force fixture refresh
./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py --force-refresh

# Emergency stop all automation
echo "SCHEDULER_ENABLED=false" >> scripts/scheduler/scheduler_config.conf
```

## Security Considerations

- Scripts run with user permissions (not root)
- Lock files prevent privilege escalation
- Logs contain no sensitive information
- Configuration files are version-controlled (exclude keys)

## Performance

- **CPU Impact**: Minimal - most scripts idle/wait
- **Memory Usage**: Low - scripts run sequentially
- **Disk I/O**: Controlled - batched database operations
- **Network**: Rate-limited API calls with proper delays

## Future Enhancements

- Web dashboard for monitoring
- SMS/email alerts for critical failures
- Dynamic scheduling based on FPL calendar
- Integration with systemd services
- Prometheus metrics export