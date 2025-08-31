# API Integration Guide

This document explains how the system integrates with external APIs to fetch and process sports data.

## FPL API Integration

### Overview
The Fantasy Premier League API provides official fixture, gameweek, and player data for the Premier League. The system uses two primary endpoints for comprehensive data coverage.

### API Endpoints

#### Bootstrap API
- **URL**: `https://fantasy.premierleague.com/api/bootstrap-static/`
- **Method**: GET
- **Purpose**: Provides gameweek information and season metadata
- **Timeout**: 30 seconds
- **No Authentication Required**

#### Fixtures API  
- **URL**: `https://fantasy.premierleague.com/api/fixtures/`
- **Method**: GET
- **Purpose**: Provides fixture data for all Premier League matches
- **Timeout**: 30 seconds
- **No Authentication Required**

#### FPL Results Processing
- **URL**: `https://fantasy.premierleague.com/api/fixtures/?event={gameweek}`
- **Method**: GET  
- **Purpose**: Fetches fixtures data for specific gameweek to track match results and status
- **Usage**: Only called during match days within timing windows
- **Timeout**: 30 seconds
- **No Authentication Required**

### FPL Response Structure

#### Bootstrap/Gameweeks Data
```json
{
  "events": [
    {
      "id": 1,
      "name": "Gameweek 1",
      "deadline_time": "2025-08-16T17:30:00Z",
      "is_current": false,
      "is_next": true,
      "finished": false,
      "is_previous": false
    }
  ]
}
```

#### Fixtures Data
```json
[
  {
    "id": 1,
    "code": 12345,
    "event": 1,
    "finished": false,
    "started": false,
    "kickoff_time": "2025-08-17T14:00:00Z",
    "team_h": 1,
    "team_a": 2,
    "team_h_score": null,
    "team_a_score": null,
    "finished_provisional": false,
    "pulse_id": 98765
  }
]
```

### FPL Data Processing Flow

#### 1. Gameweeks Processing
- Fetches all 38 gameweeks from bootstrap API
- Converts UTC deadline times to UK timezone format
- Extracts date and time components for database storage
- Uses INSERT OR REPLACE for efficient upsert operations
- Maps current/next/finished gameweek status

#### 2. Fixtures Processing
- Fetches all ~380 fixtures from fixtures API
- Maps FPL team IDs to database team_id references
- Handles timezone conversion for kickoff times
- Links fixtures to gameweek information
- Processes match status (started, finished, provisional)

#### 3. Team Mapping
- Loads FPL team ID to database team_id mapping
- Cached in memory for efficient lookup during processing
- Skips fixtures where team mapping is missing
- Logs warnings for unmapped teams

#### 4. Database Operations
- Creates tables if they don't exist (schema-compatible)
- Batch INSERT OR REPLACE operations for performance
- Single transaction per API response for data integrity
- Updates last_update tracking table with timestamp

### FPL Error Handling
- **Network Timeouts**: 30-second limit prevents hanging
- **API Changes**: Validates expected JSON structure
- **Team Mapping**: Graceful handling of missing team references
- **Database Errors**: Transaction rollback on failures
- **Data Validation**: Skips records with invalid data

### FPL Performance Optimizations
- **Team Mapping Cache**: Single query loads all mappings
- **Batch Operations**: Efficient database bulk operations
- **Schema Compatibility**: Works with existing database structure
- **Sample Data System**: JSON backups for testing and debugging

## FPL Results Processing Integration

### Overview
The FPL Results Processing system provides intelligent match day monitoring and database updates for fixture status and match results.

### Smart Timing Logic
- **Match Day Detection**: Queries database for fixtures on current date
- **Timing Windows**: Only runs between first kickoff and last kickoff + 2.5 hours
- **API Efficiency**: Avoids unnecessary calls when no matches scheduled
- **Override Mode**: Development option to bypass timing restrictions

### Results Processing Flow

#### 1. Gameweek Detection
```python
def get_current_gameweek(cursor):
    """Determine current gameweek from database"""
    cursor.execute("""
        SELECT gameweek FROM gameweeks 
        WHERE is_current = 1 OR is_next = 1 
        ORDER BY is_current DESC LIMIT 1
    """)
```

#### 2. Match Day Window Calculation
```python  
def is_match_day_window(gameweek, cursor, logger):
    """Check if within match day processing window"""
    # Query fixtures for current date
    # Calculate first kickoff to last kickoff + 2.5 hours window
    # Return True if current time is within window
```

#### 3. Change Detection
- **Fixture Status**: Compares started, finished, provisional_finished flags
- **Results Data**: Checks for new or changed goal scores
- **Database Efficiency**: Only updates records with actual changes
- **Transaction Safety**: Atomic operations with rollback protection

#### 4. Status Mapping
```python
def process_fixtures_status_changes(fixtures_data, cursor, logger, dry_run=False):
    """Map FPL status to database boolean flags"""
    # started: fixture.started -> fixtures.started  
    # finished: fixture.finished -> fixtures.finished
    # provisional: fixture.finished_provisional -> fixtures.provisional_finished
```

#### 5. Results Processing
```python  
def process_results_changes(fixtures_data, cursor, logger, dry_run=False):
    """Process match results when scores available"""
    # team_h_score -> home_goals
    # team_a_score -> away_goals  
    # Calculate H/D/A result from goal difference
    # Insert/update results table with change detection
```

### Error Handling
- **Network Timeouts**: 30-second API request limits
- **API Failures**: Graceful handling of FPL API errors
- **Database Errors**: Transaction rollback on failures
- **Missing Data**: Handles null scores and incomplete fixtures
- **Change Detection**: Prevents unnecessary database operations

### Sample Data System
- **JSON Backups**: Automatic sample file creation for testing
- **Cleanup Management**: Configurable retention of sample files
- **Test Mode**: Use cached sample data instead of API calls
- **Development Support**: Override timing for testing during development

## Dropbox API Integration

### Overview
The Dropbox API is used for automated file storage of prediction data, providing cloud-based backup and access for prediction files.

### API Configuration
```json
{
  "dropbox_oath_token": "sl.u.xxxxx...",
  "dropbox_app_key": "your-app-key", 
  "dropbox_app_secret": "your-app-secret"
}
```

### Dropbox Operations

#### File Upload
- **Endpoint**: `https://content.dropboxapi.com/2/files/upload`
- **Method**: POST
- **Authentication**: Bearer token in Authorization header
- **Content Type**: `application/octet-stream`
- **Upload Mode**: `add` (creates new files, autorenames if exists)

#### File Existence Check
- **Endpoint**: `https://api.dropboxapi.com/2/files/get_metadata`
- **Method**: POST
- **Purpose**: Prevents duplicate file uploads
- **Response**: HTTP 200 if file exists, 409 if not found

#### File Path Structure
```
/predictions_league/odds-api/predictions{gameweek}.txt
```

### Dropbox Error Handling
- **Network Timeouts**: 30-second timeout protection
- **API Rate Limits**: Handles 429 responses gracefully
- **File Conflicts**: Uses autorename to prevent overwrites
- **Authentication**: Validates bearer token before operations
- **Token Refresh**: Automatic detection and renewal of expired tokens

### Dropbox Token Refresh System

#### Automatic Token Renewal
The system includes sophisticated token refresh capabilities for seamless operation:

#### OAuth2 Refresh Flow
```python
# Automatic refresh when 401 errors detected
refresh_data = {
    'grant_type': 'refresh_token',
    'refresh_token': config['dropbox_refresh_token'],
    'client_id': config['dropbox_app_key'],
    'client_secret': config['dropbox_app_secret']
}
```

#### Token Update Process
1. **Error Detection**: Recognizes 401 "expired_access_token" responses
2. **Refresh Attempt**: Uses refresh token + app credentials to get new access token
3. **Atomic Update**: Safely updates `keys.json` using temporary files
4. **Operation Retry**: Reloads config and retries original API call

#### File Path Structure
For App-sandboxed Dropbox access:
```
/Predictions/2025_26/           # App root (no /Apps prefix needed)
├── gameweek1.txt              # Individual prediction files
├── gameweek2.txt
└── gameweek3.txt
```

#### File Processing Flow
1. **List Files**: Get all `.txt` files with metadata
2. **Change Detection**: Compare timestamps against `file_metadata` table  
3. **Download**: Retrieve modified files using download API
4. **Content Processing**: Extract predictions from file text with duplicate resolution
5. **Database Integration**: Insert predictions directly into database with conflict resolution
6. **Backup Storage**: Save as CSV files in `data/predictions/2025_26/`
7. **Metadata Update**: Update file timestamps and last_update tracking

#### Database Integration Details

##### Foreign Key Resolution
```python
def get_player_id(player_name, cursor):
    """Convert player name to database player_id"""
    cursor.execute("SELECT player_id FROM players WHERE LOWER(player_name) = LOWER(?)", (player_name,))
    return cursor.fetchone()[0] if cursor.fetchone() else None

def get_fixture_id(home_team, away_team, gameweek, cursor):
    """Match team names and gameweek to fixture_id"""
    cursor.execute("""
        SELECT f.fixture_id, f.fpl_fixture_id FROM fixtures f
        JOIN teams ht ON f.home_teamid = ht.team_id
        JOIN teams at ON f.away_teamid = at.team_id
        WHERE LOWER(ht.team_name) = LOWER(?) AND LOWER(at.team_name) = LOWER(?)
        AND f.gameweek = ? AND f.season = ?
    """, (home_team, away_team, gameweek, "2025/2026"))
```

##### Conflict Resolution Strategy
- **Constraint**: One prediction per `(player_id, fixture_id)` combination
- **Resolution**: Uses `INSERT OR REPLACE` to overwrite existing predictions
- **Validation**: Skips predictions where player or fixture cannot be matched
- **Logging**: Tracks successful insertions vs. skipped records with detailed reasons

##### Predicted Result Calculation
```python
def calculate_predicted_result(home_goals, away_goals):
    """Generate H/D/A result from goal scores"""
    if home_goals > away_goals:
        return 'H'  # Home win
    elif home_goals < away_goals:
        return 'A'  # Away win
    else:
        return 'D'  # Draw
```

## Pushover API Integration

### Overview
Pushover provides instant push notifications to mobile devices and desktop applications for real-time alerts and updates.

### API Configuration
```json
{
  "PUSHOVER_USER": "user-key-here",
  "PUSHOVER_TOKEN": "app-token-here"
}
```

### Pushover Operations

#### Message Sending
- **Endpoint**: `https://api.pushover.net/1/messages.json`
- **Method**: POST
- **Content Type**: `application/x-www-form-urlencoded`
- **Required Fields**: `token`, `user`, `message`

#### Message Types
1. **Predictions Notifications**: Full prediction text with "Tom Levin" header
2. **Fixtures Notifications**: List of upcoming fixtures with deadline information

### Pushover Error Handling
- **API Limits**: Respects monthly message limits
- **Network Errors**: Logs failures without stopping execution
- **Invalid Tokens**: Validates response codes for authentication issues
- **Message Length**: Handles long messages within Pushover limits

## The Odds API Integration

This section explains how the system integrates with The Odds API to fetch and process betting odds data.

## API Configuration

### Required Setup
```json
// keys.json
{
  "odds_api_key": "your-api-key-here"
}
```

### API Endpoint
- **URL**: `https://api.the-odds-api.com/v4/sports/soccer_epl/odds`
- **Method**: GET
- **Timeout**: 30 seconds
- **Parameters**:
  - `regions`: "uk"
  - `oddsFormat`: "decimal"  
  - `apiKey`: from keys.json

## API Response Structure

### Match Data
```json
{
  "id": "unique-match-id",
  "sport_key": "soccer_epl",
  "home_team": "Chelsea", 
  "away_team": "Arsenal",
  "commence_time": "2025-01-15T15:00:00Z",
  "bookmakers": [...]
}
```

### Bookmaker Data
```json
{
  "key": "paddypower",
  "title": "Paddy Power",
  "markets": [
    {
      "key": "h2h",
      "outcomes": [
        {"name": "Chelsea", "price": 1.85},
        {"name": "Arsenal", "price": 2.10},
        {"name": "Draw", "price": 3.40}
      ]
    }
  ]
}
```

## Data Processing Flow

### 1. API Request
- Makes HTTP GET request with 30-second timeout
- Logs request URL and response status
- Captures API usage headers if available
- Handles network errors gracefully

### 2. Team Mapping
- Loads all team mappings into memory cache for efficiency
- Maps API team names to database team IDs using `odds_api_name` field
- Case-insensitive matching (e.g., "chelsea" matches "Chelsea")
- Skips matches where teams aren't found in database

### 3. Fixture Linking  
- Attempts to link odds to specific fixtures
- Matches by: home_team_id, away_team_id, and kickoff_time
- Uses exact datetime matching between API and database
- Sets fixture_id to NULL if no match found

### 4. Bookmaker Processing
- Extracts bookmaker name from `title` field
- Converts to lowercase for consistency
- Auto-creates new bookmaker records if not exists
- Returns bookmaker_id for odds records

### 5. Odds Processing
- Processes only "h2h" (head-to-head) markets
- Maps outcome names to bet types:
  - Home team name → "home win"
  - Away team name → "away win" 
  - "Draw" → "draw"
- Validates price field exists and is not null
- Skips outcomes with missing prices

### 6. Database Operations
- Uses INSERT OR UPDATE logic for existing odds
- Matches existing records by: match_id, bet_type, bookmaker_id
- Updates existing records or inserts new ones
- Single transaction per API response for data integrity

### 7. Summary Generation
- Recalculates fixture_odds_summary after new data
- Averages odds across all bookmakers per fixture
- Updates bookmaker counts and timestamps
- Only includes records with valid fixture_id and price

## Error Handling

### Network Errors
- **Timeout**: 30-second limit prevents hanging
- **Connection Issues**: Catches RequestException 
- **API Errors**: Logs HTTP status codes and response text
- **Retry Logic**: Currently none (single attempt)

### Data Validation
- **Missing Teams**: Logs warning and skips match
- **Missing Prices**: Logs warning and skips outcome  
- **Invalid JSON**: Caught by exception handling
- **Database Errors**: Transaction rollback on failures

### Rate Limiting
- **API Limits**: Logs usage headers when available
- **Request Timing**: No built-in delays (single request per run)
- **Monitoring**: Check log files for API usage statistics

## Logging Details

### Request Logging
```
INFO - Fetching odds from API...
INFO - API Request URL: https://api.the-odds-api.com/v4/sports/...
INFO - Successfully retrieved 20 matches from API
INFO - API requests used: 1
INFO - API requests remaining: 499
```

### Processing Logging
```
INFO - Loading team mappings...
INFO - Loaded 23 team mappings  
INFO - Processing 20 matches...
WARNING - Skipping match Tottenham vs Liverpool - teams not found in database
INFO - Successfully processed 981 odds records
```

### Error Logging
```
ERROR - API request timed out after 30 seconds
ERROR - API request failed with status 401: Invalid API key
WARNING - Missing price for Chelsea in match Chelsea vs Arsenal
```

## Performance Optimizations

### Team Mapping Cache
- Single database query loads all team mappings
- In-memory dictionary lookup (O(1) complexity)
- Eliminates repeated database queries per match

### Batch Processing
- Single database connection for entire API response
- Transaction committed once at end
- Reduces database I/O overhead

### Efficient Queries  
- Uses parameterized queries to prevent SQL injection
- Optimized SELECT statements with proper indexes
- Minimal data transferred between application and database

## API Usage Monitoring

### Rate Limits
- The Odds API typically has monthly request limits
- Headers `x-requests-used` and `x-requests-remaining` show usage
- Monitor logs to track API consumption

### Best Practices
- Run script during off-peak hours if possible
- Use test mode for development to avoid API calls
- Monitor log files for usage patterns
- Consider implementing request delays for high-frequency usage