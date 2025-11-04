# Data Quality Issue: Inconsistent team_id Storage in match_events Table

## Issue Summary

The `match_events` table contains inconsistent data formats for the `team_id` column across different gameweeks, causing incorrect results when joining to the `teams` table.

**Severity:** High - Results in incorrect match scores and analysis
**Tables Affected:** `match_events`, `teams`
**Date Discovered:** October 4, 2025
**Impact:** All queries joining match_events to teams via team_id column

---

## The Problem

### Inconsistent team_id Format Across Gameweeks

The `match_events.team_id` column stores **different ID formats** depending on the gameweek:

- **Gameweek 1:** Stores **Pulse API IDs** (external system IDs)
- **Gameweek 2+:** Stores **Database team_ids** (internal primary keys)

### Example Data

**Gameweek 1 - Liverpool vs Bournemouth (pulse_id: 124802):**
```sql
SELECT team_id FROM match_events WHERE pulseid = 124802 AND event_type = 'G';
-- Returns: 10, 127 (these are Pulse IDs)

SELECT team_id, pulse_id FROM teams WHERE team_name IN ('Liverpool', 'Bournemouth');
-- Liverpool:   team_id=1,  pulse_id=10
-- Bournemouth: team_id=2,  pulse_id=127
```
✓ In GW1, match_events.team_id **matches teams.pulse_id**

**Gameweek 2 - West Ham vs Chelsea (pulse_id: 124810):**
```sql
SELECT team_id FROM match_events WHERE pulseid = 124810 AND event_type = 'G';
-- Returns: 8, 14 (these are database team_ids)

SELECT team_id, pulse_id FROM teams WHERE team_name IN ('West Ham', 'Chelsea');
-- West Ham: team_id=8,  pulse_id=25
-- Chelsea:  team_id=14, pulse_id=4
```
✓ In GW2+, match_events.team_id **matches teams.team_id**

---

## Impact

### Symptoms Observed

1. **Incorrect Score Calculations**
   - West Ham vs Chelsea showed as "0-0" when it was actually "1-5"
   - All GW1 fixtures showed "0-0" after initial fix attempt

2. **Failed Joins**
   - Queries using `JOIN teams ON match_events.team_id = teams.team_id` work for GW2+ only
   - Queries using `JOIN teams ON match_events.team_id = teams.pulse_id` work for GW1 only

3. **Incorrect Analysis Results**
   - Player rankings completely wrong
   - 90-minute vs full-time comparisons inaccurate

---

## Root Cause Analysis

### Data Ingestion Scripts

The inconsistency likely originated in the `scripts/pulse_api/fetch_pulse_data.py` script:

**Hypothesis:** The script may have changed its behavior between gameweeks:
- **Early implementation:** Stored raw Pulse API team_id values directly
- **Later update:** Added team mapping logic to convert Pulse IDs to database team_ids

### Verification Queries

```sql
-- Check team_id values across gameweeks
SELECT
    f.gameweek,
    f.pulse_id,
    me.team_id,
    t_db.team_name as team_by_db_id,
    t_pulse.team_name as team_by_pulse_id
FROM match_events me
JOIN fixtures f ON me.pulseid = f.pulse_id
LEFT JOIN teams t_db ON me.team_id = t_db.team_id
LEFT JOIN teams t_pulse ON me.team_id = t_pulse.pulse_id
WHERE me.event_type = 'G'
GROUP BY f.gameweek, me.team_id
ORDER BY f.gameweek;
```

**Expected Results:**
- GW1: `team_by_pulse_id` populated, `team_by_db_id` NULL
- GW2+: `team_by_db_id` populated, `team_by_pulse_id` NULL (or mismatched)

---

## Current Workaround

### Dual-Format Handling in Queries

Modified queries to handle **both formats** using OR conditions:

```sql
SELECT
    f.fixture_id,
    t_home.team_name as home_team,
    t_away.team_name as away_team,
    COALESCE(SUM(CASE
        -- Handle BOTH pulse_id (GW1) and team_id (GW2+) formats
        WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
        AND CAST(me.event_time AS INTEGER) <= 5400
        THEN 1 ELSE 0
    END), 0) as home_90min,
    COALESCE(SUM(CASE
        WHEN (me.team_id = t_away.team_id OR me.team_id = t_away.pulse_id)
        AND CAST(me.event_time AS INTEGER) <= 5400
        THEN 1 ELSE 0
    END), 0) as away_90min
FROM fixtures f
JOIN teams t_home ON f.home_teamid = t_home.team_id
JOIN teams t_away ON f.away_teamid = t_away.team_id
LEFT JOIN match_events me ON f.pulse_id = me.pulseid AND me.event_type = 'G'
WHERE f.season = '2025/2026'
GROUP BY f.fixture_id;
```

**Status:** ✓ Workaround implemented and tested across all gameweeks

---

## Recommended Permanent Fix

### Option 1: Data Migration (Preferred)

Standardize all `match_events.team_id` values to use **database team_ids**:

```sql
-- Backup table first
CREATE TABLE match_events_backup AS SELECT * FROM match_events;

-- Update GW1 entries to use database team_ids
UPDATE match_events
SET team_id = (
    SELECT t.team_id
    FROM teams t
    WHERE t.pulse_id = match_events.team_id
)
WHERE pulseid IN (
    SELECT pulse_id FROM fixtures WHERE gameweek = 1 AND season = '2025/2026'
);

-- Verify all team_ids now match teams.team_id
SELECT COUNT(*) FROM match_events me
LEFT JOIN teams t ON me.team_id = t.team_id
WHERE t.team_id IS NULL;
-- Should return 0
```

### Option 2: Fix Data Ingestion Script

Update `scripts/pulse_api/fetch_pulse_data.py` to **always** map Pulse API team IDs to database team_ids:

```python
# Ensure team mapping is applied consistently
team_mapping = {pulse_id: team_id for pulse_id, team_id in cursor.execute(
    "SELECT pulse_id, team_id FROM teams WHERE pulse_id IS NOT NULL"
).fetchall()}

# When inserting match_events
db_team_id = team_mapping.get(pulse_team_id)
if db_team_id:
    cursor.execute("""
        INSERT INTO match_events (pulseid, team_id, event_type, event_time, ...)
        VALUES (?, ?, ?, ?, ...)
    """, (pulse_id, db_team_id, event_type, event_time, ...))
```

### Option 3: Schema Change

Add a new column to make the relationship explicit:

```sql
-- Add explicit pulse_team_id column
ALTER TABLE match_events ADD COLUMN pulse_team_id INTEGER;

-- Migrate existing data
UPDATE match_events SET pulse_team_id = team_id
WHERE pulseid IN (SELECT pulse_id FROM fixtures WHERE gameweek = 1);

-- Update team_id to always use database IDs
UPDATE match_events
SET team_id = (SELECT team_id FROM teams WHERE pulse_id = pulse_team_id)
WHERE pulse_team_id IS NOT NULL;

-- Add foreign key constraint
CREATE INDEX idx_match_events_team_id ON match_events(team_id);
```

---

## Testing Verification

### Before Fix
```sql
-- GW1 Liverpool vs Bournemouth
SELECT home_90min, away_90min FROM ninety_minute_analysis WHERE fixture_id = X;
-- Result: 0-0 (INCORRECT)

-- GW2 West Ham vs Chelsea
SELECT home_90min, away_90min FROM ninety_minute_analysis WHERE fixture_id = Y;
-- Result: 0-0 (INCORRECT)
```

### After Workaround
```sql
-- GW1 Liverpool vs Bournemouth
-- Result: 3-2 (CORRECT)

-- GW2 West Ham vs Chelsea
-- Result: 1-5 (CORRECT)
```

---

## Related Issues

### Result Format Inconsistency

Separate but related issue: The database also stores result values in mixed formats:
- Some records: 'H', 'D', 'A'
- Other records: 'HW', 'D', 'AW'

**Current Workaround:** Normalize by taking first character:
```python
pred_result = prediction['predicted_result'][0] if prediction['predicted_result'] else 'D'
actual_res = actual_result['result_90min'][0] if actual_result['result_90min'] else 'D'
```

**Recommendation:** Standardize all result values to single character format ('H'/'D'/'A')

---

## Action Items

- [ ] Review `fetch_pulse_data.py` to identify when/why the team_id format changed
- [ ] Decide on permanent fix approach (Option 1, 2, or 3)
- [ ] Create migration script if Option 1 chosen
- [ ] Update data ingestion script if Option 2 chosen
- [ ] Add data validation tests to catch format inconsistencies early
- [ ] Document expected team_id format in database schema
- [ ] Standardize result format ('H'/'D'/'A' vs 'HW'/'D'/'AW')

---

## Contact

**Discovered by:** Claude Code
**Analysis script:** `scripts/analysis/ninety_minute_analysis.py`
**Date:** October 4, 2025
**Status:** Workaround implemented, permanent fix pending
