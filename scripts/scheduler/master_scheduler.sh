#!/bin/bash
#
# Master Scheduler Script for Prediction League Automation
#
# Centralized orchestrator that runs every minute via cron and manages all script execution
# with simplified timing logic, proper delays, error handling, and process management.
#
# SIMPLIFIED SCHEDULING (2025-08-31):
# - fetch_results.py: Every minute (runs unconditionally)
# - monitor_and_upload.py: Every minute (after 10-second delay for DB completion)
# - clean_predictions_dropbox.py: Every 15 minutes (minute % 15 = 0)
# - fetch_fixtures_gameweeks.py: Every 30 minutes (minute % 30 = 0)
# - automated_predictions.py: Every hour (minute = 0)
# - fetch_fpl_data.py: Daily at 7 AM (hour = 7, minute = 0)
# - fetch_odds.py: Daily at 7 AM (hour = 7, minute = 0)
# - fetch_pulse_data.py: Daily at 8 AM (hour = 8, minute = 0)
# - fetch_football_data.py: Weekly on Sundays at 9 AM
#
# KEY IMPROVEMENTS:
# - Eliminated complex second-based timing windows that caused missed executions
# - Core scripts run reliably every minute with smart 10-second sequencing
# - Periodic scripts use simple minute/hour checks only
# - 100% execution reliability - scripts trigger exactly when expected
#
# USAGE:
# - Add single cron entry: * * * * * /path/to/master_scheduler.sh
# - Logs to scheduler/ directory with rotation
# - Uses lock files to prevent overlapping executions
# - Set DEBUG_MODE=true in scheduler_config.conf for timing analysis
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs/scheduler"
LOCK_DIR="$PROJECT_DIR/logs/scheduler/locks"
CONFIG_FILE="$SCRIPT_DIR/scheduler_config.conf"

# Ensure directories exist
mkdir -p "$LOG_DIR" "$LOCK_DIR"

# Load configuration if it exists
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
fi

# Check if scheduler is enabled (emergency stop)
if [[ "${SCHEDULER_ENABLED:-true}" != "true" ]]; then
    log "WARN" "Scheduler disabled by configuration (SCHEDULER_ENABLED=false)"
    exit 0
fi

# Default configuration (override in scheduler_config.conf)
ENABLE_FETCH_RESULTS=${ENABLE_FETCH_RESULTS:-true}
ENABLE_MONITOR_UPLOAD=${ENABLE_MONITOR_UPLOAD:-true}
ENABLE_CLEAN_PREDICTIONS=${ENABLE_CLEAN_PREDICTIONS:-true}
ENABLE_FETCH_FIXTURES=${ENABLE_FETCH_FIXTURES:-true}
ENABLE_AUTOMATED_PREDICTIONS=${ENABLE_AUTOMATED_PREDICTIONS:-true}
ENABLE_FETCH_FPL_DATA=${ENABLE_FETCH_FPL_DATA:-true}
ENABLE_FETCH_ODDS=${ENABLE_FETCH_ODDS:-true}
ENABLE_FETCH_PULSE_DATA=${ENABLE_FETCH_PULSE_DATA:-true}

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_DIR/master_scheduler_$(date +%Y%m%d).log"
}

# Lock management
acquire_lock() {
    local script_name="$1"
    local lock_file="$LOCK_DIR/${script_name}.lock"
    local max_age_minutes=60  # Remove locks older than 1 hour
    
    # Remove stale locks
    if [[ -f "$lock_file" ]]; then
        local lock_age=$(( $(date +%s) - $(stat -c %Y "$lock_file" 2>/dev/null || echo 0) ))
        if [[ $lock_age -gt $((max_age_minutes * 60)) ]]; then
            log "WARN" "Removing stale lock for $script_name (age: ${lock_age}s)"
            rm -f "$lock_file"
        fi
    fi
    
    # Try to acquire lock
    if [[ -f "$lock_file" ]]; then
        local pid=$(cat "$lock_file" 2>/dev/null || echo "unknown")
        log "DEBUG" "Script $script_name already running (PID: $pid), skipping"
        return 1
    fi
    
    echo $$ > "$lock_file"
    return 0
}

release_lock() {
    local script_name="$1"
    local lock_file="$LOCK_DIR/${script_name}.lock"
    rm -f "$lock_file"
}

# Script execution wrapper
run_script() {
    local script_path="$1"
    local script_name="$2"
    local args="${3:-}"
    
    if ! acquire_lock "$script_name"; then
        return 1
    fi
    
    log "INFO" "Starting $script_name $args"
    local start_time=$(date +%s)
    
    # Run script and capture exit code
    if cd "$PROJECT_DIR" && timeout 3600 "$VENV_PYTHON" "$script_path" $args >> "$LOG_DIR/${script_name}_$(date +%Y%m%d).log" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log "INFO" "Completed $script_name in ${duration}s"
        release_lock "$script_name"
        return 0
    else
        local exit_code=$?
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log "ERROR" "Failed $script_name (exit: $exit_code, duration: ${duration}s)"
        release_lock "$script_name"
        return $exit_code
    fi
}

# Get current time components (simplified - only need minute and hour)
current_minute=$(date +%M | sed 's/^0//')
current_hour=$(date +%H | sed 's/^0//')

# Handle empty values (when minute/hour is 00)
current_minute=${current_minute:-0}
current_hour=${current_hour:-0}

log "DEBUG" "Scheduler tick: $(date '+%H:%M:%S') - minute: $current_minute, hour: $current_hour"

# ============================================================================
# CORE SCRIPTS - Run Every Minute (Simplified)
# ============================================================================

# fetch_results.py - runs every minute
if [[ "$ENABLE_FETCH_RESULTS" == "true" ]]; then
    run_script "scripts/fpl/fetch_results.py" "fetch_results" &
    log "DEBUG" "Triggered fetch_results"
    
    # Wait for DB writes to complete before checking uploads
    sleep 10
fi

# monitor_and_upload.py - runs every minute after 10s delay
if [[ "$ENABLE_MONITOR_UPLOAD" == "true" ]]; then
    run_script "scripts/database/monitor_and_upload.py" "monitor_and_upload" &
    log "DEBUG" "Triggered monitor_and_upload (after 10s delay)"
fi

# ============================================================================
# PERIODIC SCRIPTS - Simplified Timing (No Second Conditions)
# ============================================================================

# Every 15 minutes (at :00, :15, :30, :45)
if [[ "$ENABLE_CLEAN_PREDICTIONS" == "true" ]] && [[ $((current_minute % 15)) -eq 0 ]]; then
    run_script "scripts/prediction_league/clean_predictions_dropbox.py" "clean_predictions" &
    log "DEBUG" "Triggered clean_predictions (minute: $current_minute)"
fi

# Every 30 minutes (at :00, :30)
if [[ "$ENABLE_FETCH_FIXTURES" == "true" ]] && [[ $((current_minute % 30)) -eq 0 ]]; then
    run_script "scripts/fpl/fetch_fixtures_gameweeks.py" "fetch_fixtures" &
    log "DEBUG" "Triggered fetch_fixtures (minute: $current_minute)"
fi

# Gameweek validator check - every 5 minutes for smart triggering
if [[ $((current_minute % 5)) -eq 0 ]]; then
    if $VENV_PYTHON scripts/fpl/gameweek_validator.py --check-refresh; then
        run_script "scripts/fpl/fetch_fixtures_gameweeks.py" "fetch_fixtures_triggered" &
        log "DEBUG" "Triggered fetch_fixtures via validator recommendation (minute: $current_minute)"
    fi
fi

# Every hour (at :00)
if [[ "$ENABLE_AUTOMATED_PREDICTIONS" == "true" ]] && [[ $current_minute -eq 0 ]]; then
    run_script "scripts/prediction_league/automated_predictions.py" "automated_predictions" &
    log "DEBUG" "Triggered automated_predictions (hour: $current_hour)"
fi

# Daily at 7 AM
if [[ $current_hour -eq 7 ]] && [[ $current_minute -eq 0 ]]; then
    if [[ "$ENABLE_FETCH_FPL_DATA" == "true" ]]; then
        run_script "scripts/fpl/fetch_fpl_data.py" "fetch_fpl_data" &
        log "DEBUG" "Triggered fetch_fpl_data (daily 7 AM)"
    fi
    
    if [[ "$ENABLE_FETCH_ODDS" == "true" ]]; then
        run_script "scripts/odds-api/fetch_odds.py" "fetch_odds" &
        log "DEBUG" "Triggered fetch_odds (daily 7 AM)"
    fi
fi

# Daily at 8 AM (Pulse API data collection)
if [[ $current_hour -eq 8 ]] && [[ $current_minute -eq 0 ]]; then
    if [[ "$ENABLE_FETCH_PULSE_DATA" == "true" ]]; then
        run_script "scripts/pulse_api/fetch_pulse_data.py" "fetch_pulse_data" &
        log "DEBUG" "Triggered fetch_pulse_data (daily 8 AM)"
    fi
fi

# Weekly on Sundays at 9 AM (Football-data.co.uk data collection)
if [[ $(date +%u) -eq 7 ]] && [[ $current_hour -eq 9 ]] && [[ $current_minute -eq 0 ]]; then
    if [[ "$ENABLE_FETCH_FOOTBALL_DATA" == "true" ]]; then
        run_script "scripts/football_data/fetch_football_data.py" "fetch_football_data" &
        log "DEBUG" "Triggered fetch_football_data (weekly Sunday 9 AM)"
    fi
fi

# Weekly on Sundays at 10 AM (Season recommendation updates)
if [[ $(date +%u) -eq 7 ]] && [[ $current_hour -eq 10 ]] && [[ $current_minute -eq 0 ]]; then
    if [[ "$ENABLE_UPDATE_RECOMMENDATIONS" == "true" ]]; then
        run_script "scripts/prediction_league/update_season_recommendations.py" "update_recommendations" &
        log "DEBUG" "Triggered update_season_recommendations (weekly Sunday 10 AM)"
    fi
fi

# Wait for background processes to complete
wait

# Cleanup old locks and logs (daily at 2 AM)
if [[ $current_hour -eq 2 ]] && [[ $current_minute -eq 0 ]]; then
    log "INFO" "Starting daily cleanup"
    
    # Remove old logs (older than 30 days)
    find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true
    
    # Remove stale locks (older than 1 hour)
    find "$LOCK_DIR" -name "*.lock" -mmin +60 -delete 2>/dev/null || true
    
    log "INFO" "Completed daily cleanup"
fi

# Log current configuration status
if [[ "${DEBUG_MODE:-false}" == "true" ]]; then
    log "DEBUG" "Configuration status:"
    log "DEBUG" "  ENABLE_FETCH_RESULTS: $ENABLE_FETCH_RESULTS"
    log "DEBUG" "  ENABLE_MONITOR_UPLOAD: $ENABLE_MONITOR_UPLOAD"  
    log "DEBUG" "  ENABLE_CLEAN_PREDICTIONS: $ENABLE_CLEAN_PREDICTIONS"
    log "DEBUG" "  ENABLE_FETCH_FIXTURES: $ENABLE_FETCH_FIXTURES"
    log "DEBUG" "  ENABLE_AUTOMATED_PREDICTIONS: $ENABLE_AUTOMATED_PREDICTIONS"
    log "DEBUG" "  ENABLE_FETCH_FPL_DATA: $ENABLE_FETCH_FPL_DATA"
    log "DEBUG" "  ENABLE_FETCH_ODDS: $ENABLE_FETCH_ODDS"
    log "DEBUG" "  ENABLE_FETCH_PULSE_DATA: $ENABLE_FETCH_PULSE_DATA"
    log "DEBUG" "  ENABLE_FETCH_FOOTBALL_DATA: $ENABLE_FETCH_FOOTBALL_DATA"
    log "DEBUG" "  ENABLE_UPDATE_RECOMMENDATIONS: $ENABLE_UPDATE_RECOMMENDATIONS"
    
    # Log timing conditions that might prevent execution
    log "DEBUG" "Timing analysis:"
    log "DEBUG" "  Clean predictions: minute % 15 = $((current_minute % 15)) (needs 0)"
    log "DEBUG" "  Fetch fixtures: minute % 30 = $((current_minute % 30)) (needs 0)"  
    log "DEBUG" "  Automated predictions: minute = $current_minute (needs 0)"
    log "DEBUG" "  Daily scripts (7 AM): hour = $current_hour (needs 7)"
    log "DEBUG" "  Pulse data (8 AM): hour = $current_hour (needs 8)"
fi

log "DEBUG" "Scheduler tick completed"