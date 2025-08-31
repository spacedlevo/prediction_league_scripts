#!/bin/bash
#
# Scheduler Installation Script
#
# Sets up the Master Scheduler system with proper permissions, directories,
# and cron job configuration.
#
# USAGE:
# ./scripts/scheduler/install_scheduler.sh [options]
#
# OPTIONS:
# --dry-run     Show what would be done without making changes
# --uninstall   Remove scheduler from cron
# --status      Check current installation status
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCHEDULER_SCRIPT="$SCRIPT_DIR/master_scheduler.sh"
CRON_ENTRY="* * * * * $SCHEDULER_SCRIPT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_step() {
    echo -e "${BLUE}==> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_requirements() {
    print_step "Checking requirements"
    
    # Check if running on correct system
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        print_warning "This script is designed for Linux systems"
    fi
    
    # Check if master scheduler exists
    if [[ ! -f "$SCHEDULER_SCRIPT" ]]; then
        print_error "Master scheduler script not found: $SCHEDULER_SCRIPT"
        return 1
    fi
    
    # Check if script is executable
    if [[ ! -x "$SCHEDULER_SCRIPT" ]]; then
        print_warning "Master scheduler script is not executable"
        chmod +x "$SCHEDULER_SCRIPT"
        print_success "Made scheduler script executable"
    fi
    
    # Check if virtual environment exists
    if [[ ! -f "$PROJECT_DIR/venv/bin/python" ]]; then
        print_error "Python virtual environment not found at $PROJECT_DIR/venv/"
        return 1
    fi
    
    # Check if database exists
    if [[ ! -f "$PROJECT_DIR/data/database.db" ]]; then
        print_warning "Database file not found - ensure data setup is complete"
    fi
    
    # Check if keys file exists
    if [[ ! -f "$PROJECT_DIR/keys.json" ]]; then
        print_warning "API keys file not found - some scripts may fail"
    fi
    
    print_success "Requirements check completed"
    return 0
}

create_directories() {
    print_step "Creating required directories"
    
    # Create log directories
    mkdir -p "$PROJECT_DIR/logs/scheduler"
    mkdir -p "$PROJECT_DIR/logs/scheduler/locks"
    
    # Set proper permissions
    chmod 755 "$PROJECT_DIR/logs"
    chmod 755 "$PROJECT_DIR/logs/scheduler"
    chmod 755 "$PROJECT_DIR/logs/scheduler/locks"
    
    print_success "Directories created and permissions set"
}

install_cron_job() {
    print_step "Installing cron job"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "master_scheduler.sh"; then
        print_warning "Cron job already exists"
        echo "Current entry:"
        crontab -l 2>/dev/null | grep "master_scheduler.sh" | sed 's/^/  /'
        return 0
    fi
    
    # Add cron job
    (crontab -l 2>/dev/null || echo ""; echo "$CRON_ENTRY") | crontab -
    
    print_success "Cron job installed successfully"
    echo "Entry: $CRON_ENTRY"
}

uninstall_cron_job() {
    print_step "Uninstalling cron job"
    
    if crontab -l 2>/dev/null | grep -q "master_scheduler.sh"; then
        # Remove the specific cron job
        crontab -l 2>/dev/null | grep -v "master_scheduler.sh" | crontab -
        print_success "Cron job removed successfully"
    else
        print_warning "No cron job found to remove"
    fi
}

show_installation_status() {
    print_step "Installation Status Check"
    
    echo "Project Directory: $PROJECT_DIR"
    echo "Scheduler Script: $SCHEDULER_SCRIPT"
    echo ""
    
    # Check script exists and permissions
    if [[ -f "$SCHEDULER_SCRIPT" && -x "$SCHEDULER_SCRIPT" ]]; then
        print_success "Master scheduler script: Ready"
    elif [[ -f "$SCHEDULER_SCRIPT" ]]; then
        print_warning "Master scheduler script: Not executable"
    else
        print_error "Master scheduler script: Missing"
    fi
    
    # Check directories
    if [[ -d "$PROJECT_DIR/logs/scheduler" ]]; then
        print_success "Log directories: Ready"
    else
        print_error "Log directories: Missing"
    fi
    
    # Check cron job
    if crontab -l 2>/dev/null | grep -q "master_scheduler.sh"; then
        print_success "Cron job: Installed"
        echo "  Entry: $(crontab -l 2>/dev/null | grep master_scheduler.sh)"
    else
        print_error "Cron job: Not installed"
    fi
    
    # Check virtual environment
    if [[ -f "$PROJECT_DIR/venv/bin/python" ]]; then
        print_success "Virtual environment: Ready"
    else
        print_error "Virtual environment: Missing"
    fi
    
    # Check configuration
    if [[ -f "$SCRIPT_DIR/scheduler_config.conf" ]]; then
        print_success "Configuration file: Ready"
    else
        print_warning "Configuration file: Missing (will use defaults)"
    fi
}

run_test() {
    print_step "Running scheduler test"
    
    print_warning "Testing master scheduler (this may take up to 60 seconds)..."
    
    # Run scheduler once manually
    if "$SCHEDULER_SCRIPT"; then
        print_success "Scheduler test completed successfully"
        
        # Show recent log entries
        log_file="$PROJECT_DIR/logs/scheduler/master_scheduler_$(date +%Y%m%d).log"
        if [[ -f "$log_file" ]]; then
            echo "Recent log entries:"
            tail -n 5 "$log_file" | sed 's/^/  /'
        fi
    else
        print_error "Scheduler test failed"
        return 1
    fi
}

# Parse command line arguments
dry_run=false
uninstall=false
show_status=false
run_test_flag=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            dry_run=true
            shift
            ;;
        --uninstall)
            uninstall=true
            shift
            ;;
        --status)
            show_status=true
            shift
            ;;
        --test)
            run_test_flag=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run|--uninstall|--status|--test]"
            exit 1
            ;;
    esac
done

# Main execution
echo -e "${BLUE}Prediction League Scheduler Installer${NC}"
echo "Project: $PROJECT_DIR"
echo ""

if [[ "$show_status" == "true" ]]; then
    show_installation_status
    exit 0
fi

if [[ "$uninstall" == "true" ]]; then
    if [[ "$dry_run" == "true" ]]; then
        echo "DRY RUN: Would uninstall cron job"
    else
        uninstall_cron_job
        print_success "Scheduler uninstalled"
    fi
    exit 0
fi

if [[ "$run_test_flag" == "true" ]]; then
    run_test
    exit $?
fi

# Normal installation
if [[ "$dry_run" == "true" ]]; then
    print_step "DRY RUN MODE - No changes will be made"
    echo ""
fi

if ! check_requirements; then
    print_error "Requirements check failed"
    exit 1
fi

if [[ "$dry_run" == "true" ]]; then
    print_step "Would create directories and set permissions"
    print_step "Would install cron job: $CRON_ENTRY"
    print_step "Installation would be complete"
else
    create_directories
    install_cron_job
    
    echo ""
    print_success "Scheduler installation completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Review configuration: $SCRIPT_DIR/scheduler_config.conf"
    echo "2. Test the installation: $0 --test"
    echo "3. Monitor logs: tail -f $PROJECT_DIR/logs/scheduler/master_scheduler_\$(date +%Y%m%d).log"
    echo "4. Check status: $0 --status"
    echo ""
    echo "The scheduler will now run every minute automatically."
fi