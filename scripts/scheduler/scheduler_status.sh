#!/bin/bash
#
# Scheduler Status and Health Check Script
#
# Provides comprehensive status information about the Master Scheduler system
# including active processes, recent logs, lock files, and health metrics.
#
# USAGE:
# ./scripts/scheduler/scheduler_status.sh [options]
#
# OPTIONS:
# --detailed    Show detailed information including recent log entries
# --locks       Show only lock file information  
# --logs        Show only recent log information
# --health      Show only health check information
# --clean       Clean up old logs and stale locks
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs/scheduler"
LOCK_DIR="$PROJECT_DIR/logs/scheduler/locks"
CONFIG_FILE="$SCRIPT_DIR/scheduler_config.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_status() {
    local status="$1"
    local message="$2"
    if [[ "$status" == "OK" ]]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [[ "$status" == "WARN" ]]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
    fi
}

get_file_age() {
    local file="$1"
    if [[ -f "$file" ]]; then
        local age_seconds=$(( $(date +%s) - $(stat -c %Y "$file" 2>/dev/null || echo 0) ))
        local age_minutes=$((age_seconds / 60))
        local age_hours=$((age_minutes / 60))
        
        if [[ $age_minutes -lt 60 ]]; then
            echo "${age_minutes}m"
        else
            echo "${age_hours}h"
        fi
    else
        echo "N/A"
    fi
}

# Main status functions
check_cron_status() {
    print_header "CRON JOB STATUS"
    
    if crontab -l 2>/dev/null | grep -q "master_scheduler.sh"; then
        print_status "OK" "Master scheduler cron job is configured"
        echo "Current cron entry:"
        crontab -l 2>/dev/null | grep "master_scheduler.sh" | sed 's/^/  /'
    else
        print_status "ERROR" "Master scheduler cron job not found"
        echo "Expected entry: * * * * * $SCRIPT_DIR/master_scheduler.sh"
    fi
}

check_config_status() {
    print_header "CONFIGURATION STATUS"
    
    if [[ -f "$CONFIG_FILE" ]]; then
        print_status "OK" "Configuration file exists: $(basename "$CONFIG_FILE")"
        
        # Load config and show key settings
        source "$CONFIG_FILE" 2>/dev/null || true
        
        echo "Key settings:"
        echo "  SCHEDULER_ENABLED: ${SCHEDULER_ENABLED:-not set}"
        echo "  DEBUG_MODE: ${DEBUG_MODE:-not set}"
        echo "  OFFSEASON_MODE: ${OFFSEASON_MODE:-not set}"
        
        # Count enabled scripts
        local enabled_count=0
        for script in FETCH_RESULTS MONITOR_UPLOAD CLEAN_PREDICTIONS FETCH_FIXTURES AUTOMATED_PREDICTIONS FETCH_FPL_DATA FETCH_ODDS VERIFY_PREDICTIONS; do
            local var_name="ENABLE_${script}"
            local value="${!var_name:-not set}"
            if [[ "$value" == "true" ]]; then
                ((enabled_count++))
            fi
        done
        echo "  Enabled scripts: $enabled_count/8"
    else
        print_status "WARN" "Configuration file not found - using defaults"
    fi
}

check_lock_status() {
    print_header "LOCK FILE STATUS"
    
    if [[ -d "$LOCK_DIR" ]]; then
        local lock_files=($(ls "$LOCK_DIR"/*.lock 2>/dev/null || true))
        
        if [[ ${#lock_files[@]} -eq 0 ]]; then
            print_status "OK" "No active locks found"
        else
            print_status "WARN" "${#lock_files[@]} active locks found"
            for lock_file in "${lock_files[@]}"; do
                local script_name=$(basename "$lock_file" .lock)
                local pid=$(cat "$lock_file" 2>/dev/null || echo "unknown")
                local age=$(get_file_age "$lock_file")
                
                # Check if PID is still running
                if kill -0 "$pid" 2>/dev/null; then
                    echo "  ✓ $script_name (PID: $pid, Age: $age) - RUNNING"
                else
                    echo "  ✗ $script_name (PID: $pid, Age: $age) - STALE"
                fi
            done
        fi
    else
        print_status "ERROR" "Lock directory not found: $LOCK_DIR"
    fi
}

check_log_status() {
    print_header "LOG FILE STATUS"
    
    if [[ -d "$LOG_DIR" ]]; then
        # Check master scheduler log
        local master_log="$LOG_DIR/master_scheduler_$(date +%Y%m%d).log"
        if [[ -f "$master_log" ]]; then
            local age=$(get_file_age "$master_log")
            local size=$(du -h "$master_log" | cut -f1)
            print_status "OK" "Master log exists (Age: $age, Size: $size)"
        else
            print_status "WARN" "Today's master log not found"
        fi
        
        # Check individual script logs
        local scripts=("fetch_results" "monitor_and_upload" "clean_predictions" "fetch_fixtures" "automated_predictions" "fetch_fpl_data" "fetch_odds" "verify_predictions")
        local log_count=0
        
        for script in "${scripts[@]}"; do
            local script_log="$LOG_DIR/${script}_$(date +%Y%m%d).log"
            if [[ -f "$script_log" ]]; then
                ((log_count++))
            fi
        done
        
        echo "Script logs found today: $log_count/${#scripts[@]}"
        
        # Check total log directory size
        local total_size=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1 || echo "unknown")
        echo "Total log directory size: $total_size"
    else
        print_status "ERROR" "Log directory not found: $LOG_DIR"
    fi
}

show_recent_activity() {
    print_header "RECENT ACTIVITY (Last 10 entries)"
    
    local master_log="$LOG_DIR/master_scheduler_$(date +%Y%m%d).log"
    if [[ -f "$master_log" ]]; then
        echo "Master scheduler recent activity:"
        tail -n 10 "$master_log" | sed 's/^/  /'
    else
        echo "No recent master scheduler activity found"
    fi
}

show_health_metrics() {
    print_header "HEALTH METRICS"
    
    # Check system load
    local load_avg=$(uptime | awk -F'load average:' '{ print $2 }' | sed 's/^ *//')
    echo "System load: $load_avg"
    
    # Check available disk space
    local disk_usage=$(df -h "$PROJECT_DIR" | tail -n 1 | awk '{print $4 " available (" $5 " used)"}')
    echo "Disk space: $disk_usage"
    
    # Check Python virtual environment
    if [[ -f "$PROJECT_DIR/venv/bin/python" ]]; then
        print_status "OK" "Python virtual environment found"
    else
        print_status "ERROR" "Python virtual environment not found"
    fi
    
    # Check database
    if [[ -f "$PROJECT_DIR/data/database.db" ]]; then
        local db_size=$(du -h "$PROJECT_DIR/data/database.db" | cut -f1)
        print_status "OK" "Database file exists (Size: $db_size)"
    else
        print_status "ERROR" "Database file not found"
    fi
    
    # Check keys file
    if [[ -f "$PROJECT_DIR/keys.json" ]]; then
        print_status "OK" "API keys file exists"
    else
        print_status "WARN" "API keys file not found"
    fi
}

clean_old_files() {
    print_header "CLEANING OLD FILES"
    
    # Clean old logs
    local deleted_logs=$(find "$LOG_DIR" -name "*.log" -mtime +30 -delete -print 2>/dev/null | wc -l || echo 0)
    echo "Deleted $deleted_logs old log files (>30 days)"
    
    # Clean stale locks
    local deleted_locks=$(find "$LOCK_DIR" -name "*.lock" -mmin +60 -delete -print 2>/dev/null | wc -l || echo 0)
    echo "Deleted $deleted_locks stale lock files (>60 minutes)"
    
    if [[ $deleted_logs -gt 0 || $deleted_locks -gt 0 ]]; then
        print_status "OK" "Cleanup completed"
    else
        print_status "OK" "No cleanup needed"
    fi
}

# Parse command line arguments
show_detailed=false
show_locks_only=false
show_logs_only=false
show_health_only=false
clean_files=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed)
            show_detailed=true
            shift
            ;;
        --locks)
            show_locks_only=true
            shift
            ;;
        --logs)
            show_logs_only=true
            shift
            ;;
        --health)
            show_health_only=true
            shift
            ;;
        --clean)
            clean_files=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--detailed|--locks|--logs|--health|--clean]"
            exit 1
            ;;
    esac
done

# Main execution
echo -e "${BLUE}Prediction League Scheduler Status${NC}"
echo "Generated: $(date)"

if [[ "$clean_files" == "true" ]]; then
    clean_old_files
    exit 0
fi

if [[ "$show_locks_only" == "true" ]]; then
    check_lock_status
elif [[ "$show_logs_only" == "true" ]]; then
    check_log_status
    if [[ "$show_detailed" == "true" ]]; then
        show_recent_activity
    fi
elif [[ "$show_health_only" == "true" ]]; then
    show_health_metrics
else
    # Show all status information
    check_cron_status
    check_config_status
    check_lock_status
    check_log_status
    show_health_metrics
    
    if [[ "$show_detailed" == "true" ]]; then
        show_recent_activity
    fi
fi

echo -e "\n${BLUE}Status check completed${NC}"