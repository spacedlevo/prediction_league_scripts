# Critical System Fixes Changelog

Historical record of critical fixes and system improvements in chronological order.

## Table of Contents

- [December 2025](#december-2025)
- [November 2025](#november-2025)
- [October 2025](#october-2025)
- [September 2025](#september-2025)
- [August 2025](#august-2025)
- [Verification Steps](#verification-steps)

---

## December 2025

### Result Code Format Standardization

**Date**: December 2025

**Issue**: Database used three-letter result codes (HW/AW/D) which were verbose and inconsistent with common single-letter format

**Result**: Less readable API responses, more complex comparison logic, unnecessary verbosity in database

**Fix**: Standardized all result codes to single-letter format (H/A/D) across predictions and results tables

**Migration Details**:
- Created dedicated migration script: `scripts/database/update_result_codes.py`
- Dry-run mode for safe testing: `--dry-run` flag
- Affected 52,870 records across two tables:
  - `predictions.predicted_result`: 51,282 records updated
  - `results.result`: 1,588 records updated
- Updates: `HW → H` (31,531 records), `AW → A` (21,339 records)

**Implementation**:
```python
# Update predictions table
UPDATE predictions SET predicted_result = 'H' WHERE predicted_result = 'HW'
UPDATE predictions SET predicted_result = 'A' WHERE predicted_result = 'AW'

# Update results table
UPDATE results SET result = 'H' WHERE result = 'HW'
UPDATE results SET result = 'A' WHERE result = 'AW'
```

**Safety Features**:
- Transaction-safe with rollback on error
- Comprehensive logging to `logs/update_result_codes_YYYYMMDD.log`
- Automatic `last_update` table updates for both predictions and results
- Analysis mode shows current state before changes

**Impact**: Cleaner, more readable database schema aligned with industry standards; simplified comparison logic in scoring systems

**Files Modified**:
- New: `scripts/database/update_result_codes.py`
- Updated: All future code expects H/A/D format

**Usage**:
```bash
# Preview changes
python scripts/database/update_result_codes.py --dry-run

# Execute migration
python scripts/database/update_result_codes.py
```

---

## November 2025

### Upload Timestamp Visibility on PythonAnywhere

**Date**: November 2025

**Issue**: Timestamp updated AFTER upload meant PythonAnywhere database didn't show when it was uploaded

**Result**: Users querying remote database couldn't see upload time, only local modification time

**Fix**: Re-implemented prepare/rollback system - timestamp updates BEFORE upload (included in file) with rollback on failure

**Added Functions**:

- `get_current_upload_timestamp()`
- `prepare_upload_timestamp()`
- `rollback_upload_timestamp()`

**Impact**: PythonAnywhere database now shows actual upload time; rollback ensures consistency if upload fails

**Flow**: Save current timestamp → Update to now → Upload (with new timestamp) → Keep if success / Rollback if failure

**Files Modified**:

- `scripts/database/monitor_and_upload.py`

---

## October 2025

### Upload Timestamp Logic Simplification

**Date**: October 2025

**Issue**: Complex prepare/rollback system in `monitor_and_upload.py` was updating timestamps before upload completed

**Result**: Risk of inconsistent state if upload failed after timestamp update

**Fix**: Simplified to single `update_upload_timestamp()` function that runs ONLY after successful upload

**Removed Functions**:

- `prepare_upload_timestamp()`
- `rollback_upload_timestamp()`

**Impact**: Clean flow: upload → verify success → update timestamp; no updates if upload fails or doesn't occur

**Enhanced Logging**: Added comprehensive status indicators (→, ✓, ✗) showing exactly when/why uploads occur or are skipped

**Files Modified**:

- `scripts/database/monitor_and_upload.py`

### Team Order Preservation in Prediction Verification

**Date**: October 2025

**Issue**: Teams were extracted alphabetically, causing fixtures like "Everton vs Crystal Palace" to be reversed to "Crystal Palace vs Everton"

**Result**: Prediction matching failed, leading to false mismatches

**Fix**: Teams now extracted based on position in text, not alphabetical order

**Implementation**:

```python
def extract_teams_from_line(line, teams):
    """Extract team names from line based on their position in the text"""
    team_positions = []
    for team in teams:
        if team in line:
            pos = line.find(team)
            team_positions.append((pos, team))
    # Sort by position in text (earliest first)
    team_positions.sort(key=lambda x: x[0])
    return [team for pos, team in team_positions]
```

**Impact**: Accurate prediction verification with correct home/away team ordering

**Files Modified**:

- `scripts/analysis/verify_predictions_from_messages.py`

---

## September 2025

### Unnecessary Timestamp Updates

**Date**: September 2025

**Issue**: Scripts updated timestamps even when no data changed

**Result**: Frequent unnecessary database uploads with no actual changes

**Fix**: Modified scripts to only update timestamps when actual data changes occur

**Implementation**: Added change detection logic before timestamp updates

```python
# Only update timestamp if data actually changed
if data_changed:
    update_last_update_table(cursor, "table_name")
```

**Impact**: Reduced database upload frequency, more efficient change detection

**Files Modified**:

- `scripts/fpl/fetch_results.py`
- `scripts/fpl/fetch_fixtures_gameweeks.py`
- `scripts/odds-api/fetch_odds.py`
- `scripts/pulse_api/fetch_pulse_data.py`

### Permission Preservation for Keys.json

**Date**: September 2025

**Issue**: Scripts reset keys.json permissions to 0600 (owner-only) when updating Dropbox tokens

**Result**: Multi-user production environments lost group read access

**Fix**: Scripts now preserve original file permissions when updating tokens

**Implementation**: Save permissions before update, restore after update

```python
import os
import stat

# Save original permissions
original_mode = os.stat(keys_file).st_mode

# Update keys.json
with open(keys_file, 'w') as f:
    json.dump(keys_data, f, indent=2)

# Restore permissions
os.chmod(keys_file, original_mode)
```

**Impact**: Group permissions maintained for multi-user access

**Files Modified**:

- `scripts/prediction_league/clean_predictions_dropbox.py`
- `scripts/prediction_league/setup_dropbox_oauth.py`

### Football-Data.co.uk System Integration

**Date**: September 2025

**Feature**: Added weekly automated downloads of current season data from Football-Data.co.uk

**Implementation**:

- Historical data migration: 12,324 matches from 1993-2025 (32 seasons)
- Weekly updates every Sunday at 9 AM
- Complete team mapping for 51 historical Premier League teams
- Comprehensive betting odds and match statistics

**Impact**: Rich historical data for predictions analysis and strategy backtesting

**Files Added**:

- `scripts/football_data/fetch_football_data.py`
- `scripts/football_data/migrate_legacy_data.py`

**Scheduler Updated**: Added Sunday 9 AM execution to master scheduler

---

## August 2025

### Transaction Ordering Bug in fetch_results.py

**Date**: August 2025

**Issue**: `update_last_update_table()` called AFTER `conn.commit()`

**Result**: Timestamp updates executed but never committed to database

**Fix**: Moved timestamp update BEFORE commit for transaction integrity

**Implementation**:

```python
# OLD (incorrect)
conn.commit()
update_last_update_table(cursor, "fixtures")

# NEW (correct)
update_last_update_table(cursor, "fixtures")
conn.commit()
```

**Impact**: Results changes now properly trigger upload monitoring

**Files Modified**:

- `scripts/fpl/fetch_results.py`

### Missing Fixtures Timestamp Updates

**Date**: August 2025

**Issue**: `fetch_fixtures_gameweeks.py` only updated "fixtures_gameweeks" timestamp

**Result**: "fixtures" table changes undetected (9-day timestamp gap observed)

**Fix**: Now updates both "fixtures" and "fixtures_gameweeks" timestamps when changes occur

**Implementation**:

```python
# Update both timestamps
if fixtures_changed:
    update_last_update_table(cursor, "fixtures")
if gameweeks_changed:
    update_last_update_table(cursor, "fixtures_gameweeks")
```

**Impact**: Fixture changes now trigger automated uploads

**Files Modified**:

- `scripts/fpl/fetch_fixtures_gameweeks.py`

### Timezone Conversion Bug in Match Window Detection

**Date**: August 2025

**Issue**: Database stores UTC times but code added +1 hour offset

**Result**: Match window detection failed, preventing results fetching

**Fix**: Database times now correctly treated as UTC without conversion

**Implementation**:

```python
# OLD (incorrect)
match_time = datetime.fromisoformat(kickoff_dttm) + timedelta(hours=1)

# NEW (correct)
match_time = datetime.fromisoformat(kickoff_dttm)  # Already in UTC
```

**Impact**: Results fetching works during match windows

**Files Modified**:

- `scripts/fpl/fetch_results.py`

### Duplicate Predictions Data

**Date**: August 2025

**Issue**: Fixture matching failed due to team order mismatches

**Result**: Multiple duplicate predictions, some fixtures unmatched

**Fix**: Enhanced fixture matching to try both team orders

**Implementation**:

```python
# Try both team orders when matching fixtures
fixture_id = get_fixture_id(home_team, away_team) or get_fixture_id(away_team, home_team)
```

**Impact**: Clean prediction data, no duplicates, all fixtures matched

**Files Modified**:

- `scripts/prediction_league/clean_predictions_dropbox.py`

---

## Upload System Logging Examples

### No Upload Needed (Typical Output)

```
════════════════════════════════════════════════════════════
DATABASE UPLOAD MONITOR
════════════════════════════════════════════════════════════
Database: database.db (14.32 MB)
→ Last upload: 2025-10-02 15:41:46
→ No database changes since last upload
→ Health check: Last upload was 0.6 minutes ago (<30 min threshold)
No upload performed: No database changes detected and last upload was within 30 minutes
```

### Upload with Changes Detected

```
Database: database.db (14.32 MB)
→ Last upload: 2025-11-07 15:39:08
→ Changes detected in 1 table(s): fixtures (at 15:41:20)
Upload triggered: Database Changes
Prepared upload timestamp: 07-11-2025. 15:42:00
Uploading database (15015936 bytes)...
Database upload successful
✓ Upload completed successfully due to: database changes
✓ Timestamp included in upload - PythonAnywhere database shows upload time
```

### Upload Failure with Rollback

```
Database: database.db (14.32 MB)
→ Last upload: 2025-11-07 15:30:00
→ Changes detected in 1 table(s): fixtures (at 15:41:20)
Upload triggered: Database Changes
Prepared upload timestamp: 07-11-2025. 15:42:00
Connecting to PythonAnywhere...
✗ Upload failed: Connection timeout
✗ Upload failed - rolling back timestamp
Rolled back upload timestamp to: 07-11-2025. 15:30:00
✓ Timestamp rolled back - upload will be retried on next run due to: database changes
```

### Dry Run Mode

```
Upload triggered: Forced
DRY RUN: Would upload database to PythonAnywhere
✓ Dry run completed - would have uploaded due to: forced
✓ No timestamp update in dry-run mode
```

---

## Verification Steps

### Check Last Update Timestamps

```bash
# Check last_update table shows recent timestamps
sqlite3 data/database.db "SELECT * FROM last_update ORDER BY timestamp DESC LIMIT 5;"
```

### Test Upload Detection

```bash
# Test upload detection works
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run
```

### Test Match Window Detection

```bash
# Test match window detection
./venv/bin/python scripts/fpl/fetch_results.py --override --dry-run
```

### Check for Prediction Duplicates

```bash
# Check for prediction duplicates
sqlite3 data/database.db "SELECT COUNT(*) FROM predictions p JOIN fixtures f ON p.fixture_id = f.fixture_id WHERE f.season = '2025/2026' GROUP BY f.gameweek;"
```

### Verify Permissions

```bash
# Verify keys.json permissions
ls -la keys.json
# Should show: -rw-r----- 1 user predictionleague

# Check group ownership
stat -c '%U %G %a' keys.json
```

---

## Best Practices Learned

### Transaction Integrity

- Always update timestamps WITHIN the same transaction as data changes
- Call `update_last_update_table()` BEFORE `conn.commit()`
- Never update timestamps after commit unless using prepare/rollback pattern

### Timestamp Management

- Only update timestamps when actual data changes occur
- Use change detection logic before timestamp updates
- Consider prepare/rollback for upload operations

### File Permissions

- Preserve original file permissions when updating files
- Use `os.stat()` to save permissions before modifications
- Restore permissions with `os.chmod()` after updates

### Team/Fixture Matching

- Always try both team orders when matching fixtures
- Use position-based extraction, not alphabetical ordering
- Implement fallback logic for edge cases

### Error Handling

- Implement rollback logic for critical operations
- Log detailed error information with context
- Use status indicators (→, ✓, ✗) for clarity

---

## Related Documentation

- **Main Documentation**: [CLAUDE.md](../CLAUDE.md)
- **Systems Documentation**: [SYSTEMS.md](SYSTEMS.md)
- **Production Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md)
