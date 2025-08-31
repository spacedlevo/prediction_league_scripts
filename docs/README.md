# Prediction League Data Systems

A hobby project for collecting football data including betting odds and Fantasy Premier League player performance data.

## Overview

This system includes two main data collection components:

1. **Odds Data System**: Fetches live betting odds from The Odds API, stores in SQLite database with proper team and fixture mappings, and calculates averaged odds across bookmakers.

2. **Fantasy Premier League System**: Collects player performance data from FPL API with intelligent upsert operations to track player statistics, expected goals, transfers, and ownership data.

## Quick Start

### Prerequisites
- Python 3.7+
- Virtual environment (recommended)
- API keys configured in `keys.json` (for odds data)
- SQLite database with teams and fixtures data

### Basic Usage

**Odds Data Collection:**
```bash
# Fetch live odds from API
python scripts/odds-api/fetch_odds.py

# Test with sample data
python scripts/odds-api/fetch_odds.py --test

# Custom cleanup count (keep only 3 sample files)
python scripts/odds-api/fetch_odds.py --cleanup-count 3
```

**Fantasy Premier League Data Collection:**
```bash
# Fetch live FPL player data
python scripts/fpl/fetch_fpl_data.py

# Test with sample data (no API calls)
python scripts/fpl/fetch_fpl_data.py --test

# Dry run to see what would change
python scripts/fpl/fetch_fpl_data.py --dry-run
```

## Key Features

### Odds Data System
- **Live API Integration**: Fetches real-time odds from The Odds API
- **Smart Team Mapping**: Automatically maps API team names to database team IDs
- **Fixture Linking**: Links odds to specific fixtures using team and kickoff time matching  
- **Odds Aggregation**: Calculates averaged odds across all bookmakers per fixture
- **Robust Error Handling**: 30-second timeouts, retry logic, comprehensive logging

### Fantasy Premier League System
- **Intelligent Updates**: Only processes records that have actually changed
- **Comprehensive Data**: 33 performance metrics per player per gameweek
- **Fixture Integration**: Proper mapping to database fixture references
- **API Management**: Rate limiting, timeout protection, and error recovery
- **Sample Data Support**: JSON caching for development and testing

### Shared Features
- **File Management**: Automatic cleanup of old sample files (configurable)
- **Efficient Processing**: Caching, optimized database operations
- **Comprehensive Logging**: Daily log files with detailed processing information
- **Test Modes**: Use sample data for development without API limits

## Database Tables

### Odds System Tables
- **`odds`**: Individual bookmaker odds with prices
- **`fixture_odds_summary`**: Aggregated average odds per fixture
- **`bookmakers`**: Bookmaker reference data

### Fantasy Premier League Tables
- **`fantasy_pl_scores`**: Player performance data (33 metrics per player per gameweek)
- **`fixtures`**: Match fixtures with FPL and database ID mapping
- **`teams`**: Team information with API mappings

### Key Relationships
- All tables link to `fixtures` via `fixture_id`
- FPL data maps through `fixtures.fpl_fixture_id` to `fixtures.fixture_id`
- Odds link to teams via `home_team_id` and `away_team_id`
- Odds link to bookmakers via `bookmaker_id`

## File Structure

```
├── scripts/
│   ├── odds-api/
│   │   └── fetch_odds.py          # Odds fetching script
│   └── fpl/
│       └── fetch_fpl_data.py      # FPL data fetching script
├── data/
│   └── database.db               # Main SQLite database
├── samples/
│   ├── odds_api/                 # Odds API backup files
│   └── fantasypl/                # FPL API backup files
├── logs/                         # Daily log files
├── docs/                     # Documentation
└── keys.json                 # API configuration
```

## Documentation

### System Guides
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - Comprehensive system architecture and components
- **[FPL_DATA_GUIDE.md](FPL_DATA_GUIDE.md)** - Detailed Fantasy Premier League data system guide
- **[CHANGELOG.md](CHANGELOG.md)** - Complete history of changes and updates

### Technical References  
- **[Usage_Guide.md](Usage_Guide.md)** - Detailed command options and workflows
- **[API_Integration.md](API_Integration.md)** - Technical API integration details
- **[Database_Schema.md](Database_Schema.md)** - Complete database table structures
- **[Troubleshooting.md](Troubleshooting.md)** - Common issues and solutions

### Development
- **[CLAUDE.md](../CLAUDE.md)** - Python development best practices for this hobby project

## Quick Reference

### Most Common Commands
```bash
# Update odds data
python scripts/odds-api/fetch_odds.py

# Update FPL player data  
python scripts/fpl/fetch_fpl_data.py

# Test both systems without API calls
python scripts/odds-api/fetch_odds.py --test
python scripts/fpl/fetch_fpl_data.py --test
```

### Log Monitoring
```bash
# View latest odds fetch log
tail -f logs/odds_fetch_$(date +%Y%m%d).log

# View latest FPL fetch log  
tail -f logs/fpl_fetch_$(date +%Y%m%d).log
```

This system provides a robust foundation for football data collection and analysis, designed for hobby use with emphasis on reliability, maintainability, and clear documentation.