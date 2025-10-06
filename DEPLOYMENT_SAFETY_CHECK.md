# Deployment Safety Check: webapp/app.py → webappdeployed/prediction-league/app.py

## Summary
✅ **SAFE TO DEPLOY** - All changes are backward compatible

## Changes Overview

### 1. New Function: get_verification_mismatches()
- **Location**: Lines 1864-1907 in webapp/app.py
- **Purpose**: Retrieves prediction verification mismatches from database
- **Safety**: 
  - ✅ Wrapped in try/except - returns empty dict on error
  - ✅ Tested with missing table - handles gracefully
  - ✅ Tested with empty table - works correctly
  - ✅ No breaking changes to existing functionality

### 2. Dashboard Route Updates
- **Changes**: 
  - Added call to get_verification_mismatches()
  - Added verification_mismatches to template context
- **Safety**:
  - ✅ Existing parameters unchanged
  - ✅ Error handling includes verification_mismatches={}
  - ✅ Template gracefully handles empty mismatches

### 3. Whitespace Changes
- **Changes**: Trailing whitespace removed (render_template calls)
- **Safety**: ✅ No functional impact

## Database Requirements

### Verification Table Auto-Creation
✅ **Table is auto-created by verification script**

The `prediction_verification` table is automatically created when the verification script runs:
- Script: `scripts/analysis/verify_predictions_from_messages.py`
- Function: `create_verification_table()` (lines 730-770)
- Runs: Daily at 11:00 AM via master scheduler
- Uses: `CREATE TABLE IF NOT EXISTS` - safe to run multiple times

**Table Schema:**
```sql
CREATE TABLE IF NOT EXISTS prediction_verification (
    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    player_id INTEGER,
    fixture_id INTEGER,
    db_home_goals INTEGER,
    db_away_goals INTEGER,
    message_home_goals INTEGER,
    message_away_goals INTEGER,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
)
```

**Indexes:**
- `idx_verification_category` on category
- `idx_verification_player` on player_id
- `idx_verification_fixture` on fixture_id

### Current Status
✅ Table exists with 1820 records

## Template Requirements

### dashboard.html Changes Required
The dashboard template must also be updated to include the verification section.

Status check:
⚠️  Template needs updating - copy webapp/templates/dashboard.html

## Testing Results

### Test 1: Function with existing table (empty)
✅ PASS - Returns empty dict, no errors

### Test 2: Function with missing table
✅ PASS - Catches exception, returns empty dict, gracefully handles missing table

### Test 3: Error handling in dashboard route
✅ PASS - Falls back to empty dict in exception handler

### Test 4: Table auto-creation
✅ PASS - Verification script creates table if it doesn't exist
✅ PASS - Idempotent (safe to run multiple times)

## Deployment Steps

1. **Copy app.py**:
   ```bash
   cp webapp/app.py webappdeployed/prediction-league/app.py
   ```

2. **Copy dashboard.html**:
   ```bash
   cp webapp/templates/dashboard.html webappdeployed/prediction-league/templates/dashboard.html
   ```

3. **Restart service**:
   ```bash
   sudo systemctl restart prediction-league.service
   ```

4. **Verify**:
   - Check service status: `sudo systemctl status prediction-league.service`
   - Check logs: `sudo journalctl -u prediction-league.service -n 50`
   - Visit dashboard to confirm no errors

5. **First verification run** (if table doesn't exist yet):
   - Wait for scheduled run (daily at 11:00 AM)
   - OR manually trigger: `./venv/bin/python scripts/analysis/verify_predictions_from_messages.py`

## Rollback Plan

Backups already exist:
- webappdeployed/prediction-league/app.py.backup
- Can restore with: `cp app.py.backup app.py && sudo systemctl restart prediction-league.service`

## Verification Script Updates

### Table Auto-Creation Added
- **New Function**: `create_verification_table()` 
- **Location**: Lines 730-770 in verify_predictions_from_messages.py
- **Called**: At start of main() before any database operations
- **Safety**: Uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`

## Conclusion

✅ **SAFE TO DEPLOY**
- All changes are additive (no breaking changes)
- Error handling is comprehensive
- Function gracefully handles missing table
- Verification script auto-creates table if needed
- Template changes are optional (won't break if missing, just won't display alerts)
- Table creation is idempotent and safe

## Notes

- The webapp will work immediately after deployment
- Verification alerts will appear after first verification run (11 AM daily)
- If table doesn't exist yet, webapp returns empty dict (no errors)
- Manual verification run will create table immediately if needed
