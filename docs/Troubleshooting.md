# Troubleshooting Guide

## Common Issues and Solutions

### API-Related Issues

#### API Request Timeout
**Symptom**: `ERROR - API request timed out after 30 seconds`

**Causes**:
- Slow internet connection
- The Odds API server issues
- Network connectivity problems

**Solutions**:
1. Check internet connection
2. Try again in a few minutes
3. Use test mode temporarily: `python scripts/odds-api/fetch_odds.py --test`
4. Check The Odds API status page

#### Invalid API Key
**Symptom**: `ERROR - API request failed with status 401: Invalid API key`

**Causes**:
- Missing or incorrect API key in `keys.json`
- Expired API subscription
- Malformed keys.json file

**Solutions**:
1. Verify `keys.json` format:
   ```json
   {
     "odds_api_key": "your-actual-api-key-here"
   }
   ```
2. Check API key on The Odds API dashboard
3. Ensure no extra spaces or characters in key
4. Test key with curl: `curl "https://api.the-odds-api.com/v4/sports/soccer_epl/odds?apiKey=YOUR_KEY"`

#### Rate Limit Exceeded
**Symptom**: `ERROR - API request failed with status 429: Too Many Requests`

**Solutions**:
1. Wait for rate limit reset (usually hourly/daily)
2. Check API usage in logs for recent request counts
3. Use test mode to avoid additional API calls
4. Upgrade API plan if needed

### Database Issues

#### Database Locked
**Symptom**: `ERROR - Error processing odds data: database is locked`

**Causes**:
- Another process accessing database
- Incomplete previous transaction
- File system permissions

**Solutions**:
1. Check for other running instances: `ps aux | grep fetch_odds`
2. Wait and retry in a few minutes
3. Check database file permissions: `ls -la data/database.db`
4. Restart any long-running database connections

#### Missing Teams  
**Symptom**: `WARNING - Skipping match Liverpool vs Arsenal - teams not found in database`

**Causes**:
- Team name mismatch between API and database
- Missing `odds_api_name` mapping in teams table
- New teams not in database

**Solutions**:
1. Check team mappings:
   ```sql
   SELECT team_name, odds_api_name FROM teams WHERE odds_api_name IS NOT NULL;
   ```
2. Add missing mapping:
   ```sql
   UPDATE teams SET odds_api_name = 'liverpool' WHERE team_name = 'Liverpool';
   ```
3. Check API team names in sample JSON files
4. Update team mappings to match API naming conventions

#### No Fixture Matches
**Symptom**: Many odds records with `fixture_id = NULL`

**Causes**:
- Kickoff time mismatch between API and fixtures table
- Team ID mapping issues
- Missing fixtures in database

**Solutions**:
1. Check fixture data:
   ```sql
   SELECT fixture_id, kickoff_dttm, home_teamid, away_teamid 
   FROM fixtures LIMIT 5;
   ```
2. Compare with API kickoff times in sample files
3. Verify team ID mappings are correct
4. Check for timezone issues in datetime fields

### Data Quality Issues

#### Missing Price Data
**Symptom**: `WARNING - Missing price for Chelsea in match Chelsea vs Arsenal`

**Causes**:
- API returning incomplete data
- Bookmaker-specific issues
- Market not available

**Solutions**:
1. Check sample JSON files for complete data structure
2. Verify API response includes all expected fields
3. May be temporary - retry later
4. Check with specific bookmakers if persistent

#### Unreasonable Odds Values
**Symptom**: Odds values like 0.1 or 100.0

**Causes**:
- API data quality issues
- Suspended markets
- Error in data processing

**Solutions**:
1. Add validation to check reasonable odds ranges (1.01-50.0)
2. Review sample JSON for data quality
3. Check specific bookmaker patterns
4. Consider filtering extreme values

### File System Issues

#### Sample File Not Found (Test Mode)
**Symptom**: `ERROR - No sample data files found`

**Causes**:
- No sample files exist in `samples/odds_api/`
- Incorrect file naming pattern
- File permissions

**Solutions**:
1. Run API mode first to generate sample files
2. Check directory exists: `ls -la samples/odds_api/`
3. Verify file naming: `odds_data_YYYYMMDD_HHMMSS.json`
4. Check file permissions

#### Log Directory Issues
**Symptom**: Logging errors or no log files created

**Solutions**:
1. Verify logs directory exists and is writable
2. Check disk space: `df -h`
3. Check permissions: `ls -la logs/`
4. Create directory if missing: `mkdir -p logs`

### Performance Issues

#### Slow Processing
**Symptom**: Script takes much longer than expected

**Causes**:
- Large number of odds records
- Database performance issues
- Network latency

**Solutions**:
1. Check record counts: `SELECT COUNT(*) FROM odds;`
2. Monitor system resources during execution
3. Consider database optimization/indexes
4. Run during off-peak hours

#### Memory Usage
**Symptom**: High memory consumption or out-of-memory errors

**Solutions**:
1. Check for memory leaks in error handling
2. Monitor memory usage: `top -p $(pgrep -f fetch_odds)`
3. Restart script regularly if running frequently
4. Check for large sample files accumulating

### Scheduler/Automation Issues

#### Scheduler Not Running Scripts
**Symptom**: Expected scripts not appearing in logs

**Diagnosis**:
1. Check scheduler status: `./scripts/scheduler/scheduler_status.sh --detailed`
2. Enable debug mode: Set `DEBUG_MODE=true` in `scheduler_config.conf`
3. Monitor timing: `tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log`

**Common Causes & Solutions**:
- **Cron Not Set Up**: Add cron entry `* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh`
- **Configuration Disabled**: Check `ENABLE_*` flags in `scheduler_config.conf`
- **Emergency Stop**: Check `SCHEDULER_ENABLED=true` in config
- **Wrong Timing**: Check debug logs for timing analysis (e.g., `minute % 15 = 5` when script needs `= 0`)

#### Scripts Failing to Execute
**Symptom**: "Script already running" or lock file errors

**Solutions**:
1. Check for stale locks: `ls -la logs/scheduler/locks/`
2. Clean stale locks: `./scripts/scheduler/scheduler_status.sh --clean` 
3. Kill hung processes: `pkill -f "script_name.py"`
4. Remove specific lock: `rm logs/scheduler/locks/script_name.lock`

**Prevention**:
- Locks auto-expire after 60 minutes
- Check process health before assuming stale locks

#### Debug Scheduler Timing
**Enable detailed timing analysis**:
```bash
# Enable debug mode
echo "DEBUG_MODE=true" >> scripts/scheduler/scheduler_config.conf

# Watch timing decisions  
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log

# Manual test execution
./scripts/scheduler/master_scheduler.sh
```

**Simplified Timing Requirements**:
- **Core scripts**: Run every minute unconditionally (`fetch_results` + 10s delay + `monitor_and_upload`)
- **Periodic tasks**: Simple minute checks (`minute % 15 = 0`, `minute % 30 = 0`, etc.)  
- **Daily tasks**: Simple hour/minute checks (`hour = 7, minute = 0`)

#### Configuration Troubleshooting
**Check current settings**:
```bash
# View all scheduler settings
cat scripts/scheduler/scheduler_config.conf

# Test configuration loading
source scripts/scheduler/scheduler_config.conf && echo "ENABLE_FETCH_RESULTS: $ENABLE_FETCH_RESULTS"
```

**Common Config Issues**:
- **Typos in variable names**: Must match exact variable names in script
- **Wrong boolean values**: Use `true`/`false` (lowercase)
- **Missing permissions**: Ensure config file is readable

#### Emergency Controls
**Disable all automation**:
```bash
echo "SCHEDULER_ENABLED=false" >> scripts/scheduler/scheduler_config.conf
```

**Selective script disabling**:
```bash
# Disable problematic script
echo "ENABLE_AUTOMATED_PREDICTIONS=false" >> scripts/scheduler/scheduler_config.conf
```

**Force manual execution**:
```bash
# Run specific script manually
./venv/bin/python scripts/fpl/fetch_results.py

# Run without scheduler timing restrictions
./venv/bin/python scripts/fpl/automated_predictions.py --force
```

## Debugging Techniques

### Log Analysis
```bash
# Check recent errors
grep "ERROR" logs/odds_fetch_$(date +%Y%m%d).log

# Check warnings  
grep "WARNING" logs/odds_fetch_$(date +%Y%m%d).log

# Monitor live execution
tail -f logs/odds_fetch_$(date +%Y%m%d).log
```

### Database Inspection
```bash
# Check recent odds data
sqlite3 data/database.db "
SELECT COUNT(*) as total_odds, 
       COUNT(CASE WHEN price IS NOT NULL THEN 1 END) as with_price,
       COUNT(CASE WHEN fixture_id IS NOT NULL THEN 1 END) as with_fixture
FROM odds;"

# Check team mappings
sqlite3 data/database.db "
SELECT team_name, odds_api_name 
FROM teams 
WHERE odds_api_name IS NOT NULL 
ORDER BY team_name;"

# Check recent summary updates
sqlite3 data/database.db "
SELECT COUNT(*), MAX(last_updated) 
FROM fixture_odds_summary;"
```

### Sample File Analysis
```bash
# Check sample file structure
jq '.[0] | keys' samples/odds_api/odds_data_*.json

# Count matches in sample
jq 'length' samples/odds_api/odds_data_*.json

# Check team names in sample
jq '.[].home_team' samples/odds_api/odds_data_*.json | sort | uniq
```

### Network Testing
```bash
# Test API connectivity
curl -w "Time: %{time_total}s\nStatus: %{http_code}\n" \
     "https://api.the-odds-api.com/v4/sports/soccer_epl/odds?apiKey=YOUR_KEY&regions=uk&oddsFormat=decimal"

# Test with timeout
timeout 30s curl "https://api.the-odds-api.com/v4/sports/soccer_epl/odds?apiKey=YOUR_KEY"
```

## Prevention Strategies

### Monitoring Setup
```bash
# Create monitoring script
#!/bin/bash
LOGFILE="logs/odds_fetch_$(date +%Y%m%d).log"
ERROR_COUNT=$(grep -c "ERROR" "$LOGFILE" 2>/dev/null || echo "0")

if [ "$ERROR_COUNT" -gt "0" ]; then
    echo "Found $ERROR_COUNT errors in $LOGFILE"
    # Send alert (email, slack, etc.)
fi
```

### Data Validation
```sql
-- Check for data quality issues
SELECT 'Price validation' as check_type, 
       COUNT(*) as issues
FROM odds 
WHERE price IS NOT NULL AND (price < 1.0 OR price > 50.0)

UNION ALL

SELECT 'Missing fixtures' as check_type,
       COUNT(*) as issues  
FROM odds
WHERE fixture_id IS NULL

UNION ALL

SELECT 'Missing prices' as check_type,
       COUNT(*) as issues
FROM odds  
WHERE price IS NULL;
```

### Regular Maintenance
1. **Daily**: Check log files for errors
2. **Weekly**: Validate data quality queries
3. **Monthly**: Clean up old log files and verify database integrity
4. **Seasonally**: Archive old data and optimize database

## Emergency Recovery

### Database Corruption
1. Stop all database access
2. Create backup: `cp data/database.db data/database_backup_$(date +%Y%m%d).db`
3. Run integrity check: `sqlite3 data/database.db "PRAGMA integrity_check;"`
4. If corrupted, restore from recent backup
5. Rebuild from sample files if necessary

### Complete Data Loss
1. Restore database from backup
2. Re-run historical sample files in chronological order
3. Verify data integrity with validation queries
4. Resume normal operations

### API Key Compromise
1. Immediately revoke old key on The Odds API dashboard
2. Generate new API key
3. Update `keys.json` with new key
4. Test with new key before resuming operations