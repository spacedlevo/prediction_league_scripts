# Prediction League Script Project - Comprehensive Overview

A comprehensive system for football predictions, fantasy football analysis, and betting odds management for hobby use.

## Project Purpose

This is a hobby project designed for personal use to analyze football data, make predictions, and track fantasy football performance. The system integrates multiple data sources and provides tools for:

- **Fantasy Premier League Analysis**: Player performance tracking and recommendations
- **Betting Odds Collection**: Automated odds gathering from multiple bookmakers
- **Match Predictions**: Data-driven prediction systems
- **Database Management**: Centralized SQLite database with proper relationships

## Project Structure

```
prediction_league_script/
├── data/
│   └── database.db         # Main SQLite database
├── docs/                   # Project documentation
│   ├── README.md          # Odds API specific documentation
│   ├── PROJECT_OVERVIEW.md # This comprehensive overview
│   ├── CHANGELOG.md       # Change history
│   └── *.md              # Additional documentation
├── legacy/                 # Legacy implementations
│   ├── odds-api/          # Original UEFA odds scraper
│   └── pick_player/       # Original FPL tools
├── logs/                   # Application logs
├── samples/                # Sample data for testing
│   ├── odds_api/          # Odds API response samples  
│   └── fantasypl/         # FPL API response samples
├── scripts/                # Main application scripts
│   ├── fpl/              # Fantasy Premier League tools
│   │   └── fetch_fpl_data.py # Modern FPL data fetcher
│   ├── odds-api/         # Modern odds collection
│   │   └── fetch_odds.py # Main odds fetcher
│   └── prediction_league/ # Prediction systems
├── Utility/               # Database migration utilities
├── keys.json             # API configuration (not in repo)
└── venv/                 # Python virtual environment
```

## System Components

### 1. Modern Odds API System (`scripts/odds-api/`)

**Purpose**: Robust system for collecting Premier League betting odds
- **Data Source**: The Odds API (https://the-odds-api.com/)
- **Main Script**: `fetch_odds.py`
- **Key Features**:
  - Automated daily odds collection with proper error handling
  - Database integration with intelligent team mapping
  - Fixture linking using team IDs and kickoff times
  - Comprehensive logging with daily log files
  - Sample data backup with configurable cleanup
  - Odds aggregation across multiple bookmakers

**Technical Highlights**:
- 30-second API timeout with retry logic
- Team mapping cache for efficient lookups
- Atomic database transactions with rollback support
- Configurable file cleanup (default: keep 5 most recent)

### 2. Fantasy Premier League System (`scripts/fpl/`)

**Purpose**: Comprehensive FPL player performance tracking and analysis
- **Data Source**: Fantasy Premier League API (https://fantasy.premierleague.com/api/)
- **Main Script**: `fetch_fpl_data.py`
- **Database Table**: `fantasy_pl_scores`

**Key Features**:
- **Intelligent Upserts**: Only updates records that have actually changed
- **Fixture Mapping**: Converts FPL fixture IDs to database fixture_id references
- **API Management**: Rate limiting, timeout protection, and error recovery
- **Progress Tracking**: Visual progress indication for ~700 players
- **JSON Caching**: Backup of API responses with configurable cleanup
- **Test Mode**: Use cached data for development without API calls

**Database Schema** (33 performance metrics):
- **Basic stats**: points, minutes, goals, assists, clean sheets
- **Advanced metrics**: expected goals/assists, ICT index, BPS
- **Transfer data**: value, transfers in/out, ownership percentage

**Technical Highlights**:
- Efficient upsert using `INSERT OR REPLACE` with change detection
- Season-aware fixture mapping (currently 2025/2026)
- Individual player error handling - failures don't stop entire process
- Comprehensive logging with daily log files

### 3. Database Architecture (`data/database.db`)

**Core Tables**:
- **`fixtures`**: Match fixtures (2,280 records across 6 seasons)
  - Maps FPL fixture IDs to internal fixture IDs
  - Contains kickoff times, team IDs, season information
- **`teams`**: Team information with API mappings
- **`odds`**: Individual bookmaker odds records
- **`bookmakers`**: Bookmaker reference data
- **`fantasy_pl_scores`**: Player performance data
- **`fixture_odds_summary`**: Aggregated odds for analysis

**Key Relationships**:
```
fixtures.fpl_fixture_id → FPL API reference
fixtures.fixture_id → Primary key used throughout system
fantasy_pl_scores.fixture_id → fixtures.fixture_id
odds.fixture_id → fixtures.fixture_id
```

### 4. Legacy Systems (`legacy/`)

**Legacy Odds API** (`legacy/odds-api/`):
- Original UEFA Championships odds scraper
- Simple CSV output format
- Basic API integration without database storage
- Kept for reference and historical context

**Legacy FPL Tools** (`legacy/pick_player/`):
- Original Fantasy Premier League analysis tools
- Local SQLite database (`fpl_players.db`)
- Player recommendation algorithms
- Data successfully migrated to main system
- Replaced by modern `fetch_fpl_data.py` script

## Development Workflow

### Data Collection Process

**Odds Collection**:
1. **Odds Fetching**: `fetch_odds.py` retrieves latest odds from API
2. **Team Mapping**: Automatic mapping of API team names to database IDs
3. **Fixture Linking**: Match odds to fixtures using teams and kickoff times
4. **Database Storage**: Atomic insertion/update of odds records
5. **Aggregation**: Calculate average odds across bookmakers
6. **Logging**: Comprehensive logging of all operations

**FPL Data Collection**:
1. **Bootstrap Fetch**: Get all player list from FPL API
2. **Player History**: Fetch individual performance data for ~700 players
3. **Fixture Mapping**: Convert FPL fixture IDs to database fixture_id
4. **Change Detection**: Compare with existing data to identify updates needed
5. **Upsert Operations**: Insert new records or update changed data only
6. **Sample Backup**: Save JSON responses for testing and debugging

### Database Evolution
1. **Legacy Phase**: Separate databases for different components
2. **Migration Phase**: Data consolidated into main database
3. **Current Phase**: Unified database with proper relationships
4. **Future**: Continued evolution tracked in `CHANGELOG.md`

## Configuration

### API Keys (`keys.json`)
```json
{
  "odds_api_key": "your_odds_api_key_here"
}
```

### Environment Setup
```bash
# Virtual environment
python -m venv venv
source venv/bin/activate

# Dependencies
pip install -r requirements.txt
```

## Usage Examples

### Odds Collection
```bash
# Fetch live odds
python scripts/odds-api/fetch_odds.py

# Test with sample data
python scripts/odds-api/fetch_odds.py --test

# Custom file management
python scripts/odds-api/fetch_odds.py --cleanup-count 3
```

### FPL Data Collection
```bash
# Fetch live FPL data
python scripts/fpl/fetch_fpl_data.py

# Test with sample data (no API calls)
python scripts/fpl/fetch_fpl_data.py --test

# Dry run to see what would change
python scripts/fpl/fetch_fpl_data.py --dry-run

# Custom sample file management
python scripts/fpl/fetch_fpl_data.py --cleanup-count 3
```

### Database Queries
```sql
-- View latest odds summary
SELECT * FROM fixture_odds_summary 
ORDER BY last_updated DESC LIMIT 10;

-- Fantasy player performance
SELECT player_name, total_points, expected_goals 
FROM fantasy_pl_scores 
WHERE gameweek = 1 
ORDER BY total_points DESC LIMIT 10;
```

## Data Quality & Reliability

### Error Handling
- API timeout protection (30 seconds)
- Database transaction rollbacks on errors
- Comprehensive error logging
- Graceful handling of missing data

### Data Validation
- Team mapping validation before processing
- Fixture matching using multiple criteria
- Price validation for odds records
- Foreign key constraints in database

### Monitoring
- Daily log files with detailed operations
- API usage tracking (requests used/remaining)
- Processing statistics (records processed/skipped)
- Sample data backup for debugging

## Future Development

### Planned Enhancements
- Additional sports/leagues support
- Enhanced prediction algorithms
- Web interface for data visualization
- Automated daily execution scheduling

### Architectural Improvements
- Database optimization for larger datasets
- API rate limiting improvements
- Enhanced error recovery mechanisms
- Real-time data processing capabilities

## Troubleshooting

### Common Issues
- **API Rate Limits**: Monitor request counts in logs
- **Team Mapping Failures**: Update team mappings in database
- **Database Locks**: Ensure single-threaded database access
- **Missing Fixtures**: Verify fixture data is current

### Debugging Tools
- Test mode with sample data (`--test` flag)
- Detailed logging in `logs/` directory
- Sample JSON files for API response analysis
- Database query tools for data investigation

## Project Philosophy

This hobby project follows these principles:
- **Simplicity**: Keep code readable and maintainable
- **Reliability**: Proper error handling and logging
- **Modularity**: Separate concerns into focused components
- **Testability**: Sample data and test modes available
- **Documentation**: Self-documenting code with comprehensive docs

The system is designed for personal use and learning, with emphasis on understanding football data rather than commercial-grade performance.