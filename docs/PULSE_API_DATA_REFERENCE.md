# Pulse API Data Reference

## Overview

The Pulse API provides detailed match event data from Premier League fixtures, including match officials, team lineups, and in-game events (goals, cards, substitutions, etc.). This data is fetched by `scripts/pulse_api/fetch_pulse_data.py` and stored in the database.

---

## Database Tables

### 1. `match_events`

Stores all in-game events from the Pulse API with precise timing information.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS match_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pulseid INT NOT NULL,           -- Links to fixtures.pulse_id
    person_id INT,                  -- Player ID from Pulse API
    team_id INT,                    -- Database team_id (NOT pulse team_id)
    assist_id INT,                  -- Player ID of assisting player (for goals)
    event_type TEXT NOT NULL,       -- Type of event (see Event Types below)
    event_time TEXT NOT NULL        -- Time in seconds from kickoff
)
```

**Key Fields:**
- **pulseid**: Links to `fixtures.pulse_id` to identify which match this event belongs to
- **person_id**: Pulse API player ID (can be used to look up player details in raw JSON)
- **team_id**: **DATABASE team_id** (important: this is NOT the Pulse API team ID)
- **event_time**: Time in **seconds** from kickoff (e.g., 5400 = 90 minutes)

**Important Notes:**
- `team_id` stores the **database team_id**, not the Pulse team_id
- For historical reasons, some early data may have Pulse team IDs in `team_id` column
- Always join using both `team_id` and `pulse_id` when matching to teams table:
  ```sql
  WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
  ```

---

## Event Types

### Goal-Scoring Events

| Type | Description | Example |
|------|-------------|---------|
| **G** | Regular goal | Open play goal, header, volley |
| **P** | Penalty goal | Penalty kick scored |
| **O** | Own goal | Player scores into their own net |

**Critical:** When counting goals, you MUST include all three types:
```sql
WHERE event_type IN ('G', 'P', 'O')
```

### Card Events

| Type | Description | Notes |
|------|-------------|-------|
| **B** | Booking (Yellow card) | First yellow card |
| **Y** | Second yellow card | Results in sending off |
| **R** | Red card | Direct red card |

### Substitution Events

| Type | Description | Notes |
|------|-------------|-------|
| **S** | Substitution | Two events: one "ON", one "OFF" |

**Example:**
```
Type: S, Person: 50848, Description: ON  (Player coming on)
Type: S, Person: 51202, Description: OFF (Player going off)
```

### Match Phase Events

| Type | Description | Notes |
|------|-------------|-------|
| **PS** | Period start | Kickoff (first/second half) |
| **PE** | Period end | Half-time or full-time whistle |

### Other Events

| Type | Description | Notes |
|------|-------------|-------|
| **VAR** | VAR review | VAR check/decision |

---

## Event Timing

### Time Format
- **Unit:** Seconds from kickoff
- **90 minutes:** 5400 seconds (90 × 60)
- **Injury time:** Anything > 5400 seconds

### Example Timeline
```
0s      = 0'     Kickoff
1620s   = 27'    Own goal (before 90 mins)
3300s   = 55'    Goal (before 90 mins)
3420s   = 57'    Goal (before 90 mins)
3960s   = 66'    Goal (before 90 mins)
5400s   = 90'    Regular time ends
5820s   = 97'    Penalty (injury time - 90+7')
6120s   = 102'   Full-time whistle
```

### Calculating Minutes from Seconds
```python
minutes = event_time // 60
seconds = event_time % 60
display = f"{minutes}:{seconds:02d}"
```

### Filtering by Time Period
```sql
-- Goals scored before 90 minutes
WHERE event_type IN ('G', 'P', 'O')
  AND CAST(event_time AS INTEGER) <= 5400

-- Goals scored in injury time
WHERE event_type IN ('G', 'P', 'O')
  AND CAST(event_time AS INTEGER) > 5400
```

---

## Common Query Patterns

### Count Goals at 90 Minutes
```sql
SELECT
    f.fixture_id,
    t_home.team_name,
    t_away.team_name,
    -- Home team goals at 90 mins
    COALESCE(SUM(CASE
        WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
        AND CAST(me.event_time AS INTEGER) <= 5400
        THEN 1 ELSE 0
    END), 0) as home_90min,
    -- Away team goals at 90 mins
    COALESCE(SUM(CASE
        WHEN (me.team_id = t_away.team_id OR me.team_id = t_away.pulse_id)
        AND CAST(me.event_time AS INTEGER) <= 5400
        THEN 1 ELSE 0
    END), 0) as away_90min
FROM fixtures f
JOIN teams t_home ON f.home_teamid = t_home.team_id
JOIN teams t_away ON f.away_teamid = t_away.team_id
LEFT JOIN match_events me ON f.pulse_id = me.pulseid
    AND me.event_type IN ('G', 'P', 'O')  -- ALL goal types
GROUP BY f.fixture_id
```

### Find All Goals for a Match
```sql
SELECT
    event_time,
    event_type,
    person_id,
    team_id
FROM match_events
WHERE pulseid = 124816  -- Man Utd vs Burnley
  AND event_type IN ('G', 'P', 'O')
ORDER BY CAST(event_time AS INTEGER)
```

### Count Cards by Team
```sql
SELECT
    t.team_name,
    COUNT(*) as yellow_cards
FROM match_events me
JOIN teams t ON me.team_id = t.team_id
WHERE me.pulseid = 124816
  AND me.event_type = 'B'  -- Yellow cards
GROUP BY t.team_name
```

---

## Data Quality Notes

### Known Issues

#### 1. Team ID Format Inconsistency
- **Problem:** Early gameweeks stored Pulse team IDs in `team_id` column
- **Gameweek 1:** `team_id` contains Pulse API IDs (e.g., 10, 127)
- **Gameweek 2+:** `team_id` contains database team_ids (e.g., 8, 14)
- **Solution (Workaround):** Always use OR condition in queries:
  ```sql
  WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
  ```
- **Solution (Permanent Fix):** Use `--fix-team-ids` flag to correct data:
  ```bash
  # Preview the fix
  ./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --fix-team-ids --dry-run

  # Execute the fix (drops tables and re-fetches all data)
  ./venv/bin/python scripts/pulse_api/fetch_pulse_data.py --fix-team-ids
  ```
- **Status:** Workaround implemented in all analysis scripts; permanent fix available via `--fix-team-ids`
- **See:** `analysis_reports/DATA_QUALITY_ISSUE_match_events_team_id.md`

#### 2. Missing Event Type 'O' and 'P' in Early Analysis
- **Problem:** Original analysis scripts only counted `event_type = 'G'`
- **Impact:** Own goals and penalties were excluded from 90-minute analysis
- **Example:** Man Utd vs Burnley showed 1-2 instead of 2-2 at 90 minutes
  - Missing: Own goal at 27' and penalty at 90+7'
- **Fixed:** October 2025 - Changed to `event_type IN ('G', 'P', 'O')`

#### 3. Incomplete Data from Pulse API
- The Pulse API sometimes returns incomplete event data
- Always verify critical matches by checking event counts
- Example verification:
  ```sql
  -- Should match full-time score
  SELECT COUNT(*) FROM match_events
  WHERE pulseid = 124816 AND event_type IN ('G', 'P', 'O')
  ```

---

## Example: Man Utd 3-2 Burnley (GW3)

### Raw Events from JSON
```json
{
  "events": [
    {"type": "O", "teamId": 12, "personId": 10539, "clock": {"secs": 1620}},  // Own goal (27')
    {"type": "G", "teamId": 43, "personId": 64282, "clock": {"secs": 3300}},  // Burnley goal (55')
    {"type": "G", "teamId": 12, "personId": 66360, "clock": {"secs": 3420}},  // Man Utd goal (57')
    {"type": "G", "teamId": 43, "personId": 50460, "clock": {"secs": 3960}},  // Burnley goal (66')
    {"type": "P", "teamId": 12, "personId": 23396, "clock": {"secs": 5820}}   // Penalty (90+7')
  ]
}
```

### Stored in Database
```
pulseid | event_type | event_time | team_id | person_id
124816  | O          | 1620       | 9       | 10539      (Own goal - 27')
124816  | G          | 3300       | 3       | 64282      (Goal - 55')
124816  | G          | 3420       | 9       | 66360      (Goal - 57')
124816  | G          | 3960       | 3       | 50460      (Goal - 66')
124816  | P          | 5820       | 9       | 23396      (Penalty - 90+7')
```

### Analysis Results
- **90-minute score:** 2-2 (4 goals before 5400s)
  - Own goal counted for Burnley (opposition benefit)
  - 2 Man Utd goals (57', plus own goal helps them)
  - 2 Burnley goals (55', 66')
- **Full-time score:** 3-2 (5 goals total)
  - Penalty at 5820s (90+7') gave Man Utd the winner

---

## Related Tables

### `team_list`
Stores team lineups and substitutes from Pulse API.

### `match_officials`
Stores match officials (referees, linesmen, VAR) from Pulse API.

### `fixtures`
Links to Pulse API via `pulse_id` column.

---

## Scripts

### Data Collection
- **`scripts/pulse_api/fetch_pulse_data.py`** - Fetches and stores Pulse API data
  - Runs daily at 8 AM via master scheduler
  - Processes finished fixtures with `pulse_id`
  - Saves sample JSON to `samples/pulse_api/`
  - **Flags:**
    - `--test` - Use sample data for testing
    - `--dry-run` - Preview changes without database updates
    - `--force-all` - Fetch all fixtures regardless of existing data
    - `--force-refresh` - Clear existing data and re-fetch all fixtures
    - `--fix-team-ids` - Drop tables and re-fetch to fix team_id inconsistencies
    - `--max-workers N` - Control concurrent API requests (default: 3)
    - `--delay N` - Delay between requests in seconds (default: 2.0)

### Data Analysis
- **`scripts/analysis/ninety_minute_analysis.py`** - Analyzes 90-minute vs full-time scores
  - Uses `event_type IN ('G', 'P', 'O')` to count all goals
  - Filters by `event_time <= 5400` for 90-minute scores
  - Generates markdown reports in `analysis_reports/`

---

## API Response Format

### Sample Pulse API Response
```json
{
  "id": 124816,
  "teams": [
    {"team": {"id": 12, "name": "Manchester United"}, "score": 3},
    {"team": {"id": 43, "name": "Burnley"}, "score": 2}
  ],
  "events": [
    {
      "id": 172617,
      "type": "O",
      "personId": 10539,
      "teamId": 12,
      "clock": {"secs": 1620, "label": "27'00"},
      "score": {"homeScore": 1, "awayScore": 0}
    },
    {
      "type": "G",
      "personId": 64282,
      "teamId": 43,
      "assistId": 19831,
      "clock": {"secs": 3300, "label": "55'00"},
      "score": {"homeScore": 1, "awayScore": 1}
    }
  ]
}
```

### Field Mapping
| JSON Field | Database Column | Notes |
|------------|----------------|--------|
| `type` | `event_type` | Event type code |
| `personId` | `person_id` | Player ID |
| `teamId` | `team_id` | Mapped to database team_id |
| `assistId` | `assist_id` | Assisting player ID |
| `clock.secs` | `event_time` | Time in seconds |

---

## Best Practices

### 1. Always Include All Goal Types
```python
# WRONG - Misses penalties and own goals
WHERE event_type = 'G'

# CORRECT - Includes all scoring events
WHERE event_type IN ('G', 'P', 'O')
```

### 2. Handle Team ID Format Inconsistency
```sql
-- Use OR condition to handle both formats
WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
```

### 3. Cast event_time to INTEGER
```sql
-- Ensures numeric comparison works correctly
CAST(me.event_time AS INTEGER) <= 5400
```

### 4. Verify Data Completeness
```sql
-- Check if goal count matches final score
SELECT
    COUNT(*) as goals_in_events,
    r.home_goals + r.away_goals as goals_in_result
FROM match_events me
JOIN fixtures f ON me.pulseid = f.pulse_id
JOIN results r ON f.fixture_id = r.fixture_id
WHERE me.event_type IN ('G', 'P', 'O')
  AND f.pulse_id = 124816
GROUP BY r.home_goals, r.away_goals
```

---

## Troubleshooting

### Problem: Goals missing from count
**Solution:** Check you're including all event types: `IN ('G', 'P', 'O')`

### Problem: Wrong team attributed to goal
**Solution:** Use OR condition for team_id matching:
```sql
WHEN (me.team_id = t_home.team_id OR me.team_id = t_home.pulse_id)
```

### Problem: Own goals counted incorrectly
**Remember:** Own goals benefit the **opposing team**. Type 'O' events have `teamId` of the team that **conceded** the own goal, not who scored it.

### Problem: Penalty not counted in 90-minute score
**Solution:** Verify `event_type IN ('G', 'P', 'O')` includes 'P' and check if penalty was before or after 5400s.

---

## Version History

- **October 2025** - Added `--fix-team-ids` flag to permanently fix team_id inconsistencies
- **October 2025** - Fixed event_type filtering to include 'P' and 'O'
- **September 2025** - Documented team_id format inconsistency
- **August 2025** - Initial Pulse API data collection implemented

---

## See Also

- `analysis_reports/DATA_QUALITY_ISSUE_match_events_team_id.md` - Detailed analysis of team_id inconsistency
- `scripts/pulse_api/fetch_pulse_data.py` - Data collection script
- `scripts/analysis/ninety_minute_analysis.py` - Example usage of match_events data
