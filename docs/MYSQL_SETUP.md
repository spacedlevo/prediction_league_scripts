# MySQL Synchronization Setup Guide

This guide walks you through setting up the hybrid SQLite-to-MySQL synchronization system for the prediction league project.

## Overview

The system keeps your existing SQLite database as the primary data store while synchronizing only the essential 7 tables to MySQL on PythonAnywhere:

- `teams` - Premier League teams
- `gameweeks` - Gameweek schedules and deadlines
- `players` - Prediction league participants
- `fixtures` - Match schedule and basic info
- `results` - Actual match results
- `predictions` - User predictions
- `last_update` - Change tracking

All detailed data (FPL scores, odds, pulse data) remains in SQLite only.

## Step 1: PythonAnywhere Account Setup

**⚠️ URGENT: Complete before January 15, 2025 (or January 8 in EU)**

1. **Upgrade Account**
   - Log into your PythonAnywhere account
   - Go to Account → Billing
   - Upgrade to paid tier to lock in $5/month rate (avoid $10/month)

2. **Create MySQL Database**
   - Navigate to Databases tab in your dashboard
   - Click "Create new MySQL database"
   - Database name format: `yourusername$databasename` (e.g., `spacedlevo$predictions`)
   - Note down the connection details provided

3. **Get Database Credentials**
   - Hostname: `yourusername.mysql.pythonanywhere-services.com`
   - Database: `yourusername$databasename`
   - Username: `yourusername`
   - Password: Set a strong password and save it securely

## Step 2: Configure Local Environment

1. **Update keys.json**
   ```bash
   # Copy template if keys.json doesn't exist
   cp keys.json.template keys.json
   ```
   
   Add your MySQL credentials to `keys.json`:
   ```json
   {
     "mysql_host": "yourusername.mysql.pythonanywhere-services.com",
     "mysql_database": "yourusername$predictions",
     "mysql_username": "yourusername",
     "mysql_password": "your_mysql_password"
   }
   ```

2. **Dependencies Already Installed**
   - PyMySQL has been installed in your virtual environment
   - No additional packages needed

## Step 3: Create MySQL Schema

1. **Access MySQL Console**
   - Go to your PythonAnywhere dashboard
   - Click on "Consoles" tab
   - Start a new MySQL console
   - It should automatically connect to your database

2. **Create Tables**
   - Copy the contents of `mysql_schema.sql` (created in project root)
   - Paste and execute in the MySQL console
   - Verify tables were created: `SHOW TABLES;`

## Step 4: Test Connection and Perform Initial Sync

1. **Test Connection**
   ```bash
   source venv/bin/activate
   python scripts/database/mysql_sync.py --test
   ```
   
   Expected output:
   - MySQL connection successful
   - SQLite connection successful
   - Table count comparison for each table

2. **Initial Full Sync**
   ```bash
   python scripts/database/mysql_sync.py --full-sync
   ```
   
   This will:
   - Clear all data in MySQL tables
   - Copy all data from SQLite to MySQL
   - Show progress for each table

3. **Validate Sync**
   ```bash
   python scripts/database/mysql_validate.py --all
   ```
   
   This checks:
   - Record counts match between databases
   - Sample data is identical
   - Foreign key constraints are valid

## Step 5: Understanding the Sync Process

### Current Capabilities

- **Full Sync**: Complete refresh of all tables (`--full-sync`)
- **Test Mode**: Connection and table status checking (`--test`)
- **Validation**: Comprehensive data integrity checking (separate script)

### Data Flow

```
Local Scripts → SQLite (unchanged)
     ↓
Change Detection (existing last_update table)
     ↓
MySQL Sync (NEW) → PythonAnywhere MySQL
     ↓
Web Application (reads from MySQL)
```

### What Stays Local

All detailed analysis data remains in SQLite:
- `fantasy_pl_scores` (FPL player performance)
- `fpl_players_bootstrap` (FPL cache data)
- `odds` and related tables (betting odds)
- `match_officials`, `team_list`, `match_events` (Pulse API data)

## Step 6: Testing and Verification

### Manual Testing Commands

```bash
# Test connection
python scripts/database/mysql_sync.py --test

# Full sync
python scripts/database/mysql_sync.py --full-sync

# Validate data integrity
python scripts/database/mysql_validate.py --all

# Compare record counts only
python scripts/database/mysql_validate.py --counts

# Check foreign key constraints
python scripts/database/mysql_validate.py --integrity
```

### Expected Results

After successful setup:
- All 7 tables exist in both SQLite and MySQL
- Record counts match exactly
- No foreign key violations
- Sample data is identical

### Troubleshooting

**Connection Issues:**
- Verify credentials in keys.json
- Check PythonAnywhere account status (paid tier required)
- Ensure database name format: `username$dbname`

**Schema Issues:**
- Tables must be created exactly as specified in mysql_schema.sql
- Check for SQL syntax errors in MySQL console
- Verify foreign key relationships

**Data Sync Issues:**
- Check logs in `logs/mysql_sync_YYYYMMDD.log`
- Use validation script to identify specific problems
- Review foreign key constraints if inserts fail

## Step 7: Next Steps

1. **Integration with Monitor System**
   - The sync will be integrated with your existing `monitor_and_upload.py`
   - MySQL sync will run alongside SQLite file upload
   - Incremental sync capability will be added

2. **Web Application Update**
   - Update PythonAnywhere web application to read from MySQL
   - Keep SQLite upload as backup system initially

3. **Monitoring and Maintenance**
   - Monitor sync logs for errors
   - Regular validation checks
   - Performance optimization as needed

## File Structure

After setup, you'll have these new files:

```
project/
├── mysql_schema.sql                    # MySQL table definitions
├── scripts/database/
│   ├── mysql_sync.py                  # Main sync script
│   └── mysql_validate.py              # Data validation script
├── keys.json                         # Updated with MySQL credentials
└── logs/
    ├── mysql_sync_YYYYMMDD.log       # Sync operation logs
    └── mysql_validate_YYYYMMDD.log   # Validation logs
```

## Benefits

- **Faster updates**: ~50KB sync vs 3MB file upload
- **Real-time data**: Immediate availability on PythonAnywhere
- **Reduced costs**: Smaller MySQL footprint
- **Zero disruption**: All existing scripts unchanged
- **Robust backup**: Dual systems (MySQL + SQLite file upload)

## Support

If you encounter issues:
1. Check logs in the `logs/` directory
2. Run validation script to identify problems
3. Verify PythonAnywhere account and database status
4. Test connection with `--test` flag

The system is designed to be robust with comprehensive error handling and logging.