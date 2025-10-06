# Prediction League Script System

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-production-brightgreen.svg)]()

A comprehensive automated system for managing Fantasy Premier League predictions, data collection, and result processing. Built for hobby prediction leagues with friends and family.

## 🌟 Features

### 🔄 **Master Scheduler System**
- **Centralized Orchestration**: Single cron job manages all automation
- **Intelligent Timing**: Smart scheduling with delays and process management
- **Gameweek Validation**: Deadline-based validation with auto-refresh triggers
- **Process Isolation**: Individual script failures don't affect other components
- **Configuration-Driven**: Easy enable/disable and timing adjustments

### 🔄 **Automated Data Processing**
- **FPL API Integration**: Automatic fixtures, gameweeks, and results collection
- **Complete Historical Data**: 32 seasons of Premier League match data (1993-2025, 12,324+ matches, 100% coverage) from football-data.co.uk
- **Smart Change Detection**: Only updates database when data actually changes
- **Intelligent Timing**: Runs during match days and timing windows
- **Missing Results Detection**: Automatically fetches results for completed fixtures
- **Comprehensive Statistics**: Match results, team stats, betting odds, referee info

### 📱 **Intelligent Automated Predictions**
- **AI-Driven Strategy Selection**: Uses real-time season analysis to determine optimal prediction format (1-0 vs 2-1)
- **Adaptive Prediction Generation**: Automatically switches strategy based on current season's low-scoring percentage
- **OAuth2 Dropbox Integration**: Secure token management with auto-refresh
- **Dual-File Upload**: Automated predictions written to both odds-api and main gameweek files
- **Append/Create Logic**: Intelligent handling of existing gameweek predictions with content preservation
- **Deadline-Based Triggering**: Only runs when gameweek deadline is within 36 hours
- **UK Timezone Display**: Automatic BST/GMT conversion for deadline notifications
- **Fallback Protection**: Gracefully falls back to 2-1 strategy if recommendation system unavailable

### 🗄️ **Database Management**
- **SQLite Backend**: Lightweight, reliable data storage
- **Auto-Upload**: Automated uploads to PythonAnywhere hosting
- **Change Monitoring**: Real-time detection and immediate sync
- **Health Checks**: Regular uploads ensure system connectivity

### 🎯 **Intelligent Predictions Dashboard**
- **Adaptive Strategy Recommendations**: AI-driven strategy switching based on real-time season analysis
- **7 Prediction Strategies**: Fixed (2-1, 2-0, 1-0), Adaptive, Calibrated, Home/Away Bias, Poisson, Smart Goals, Custom
- **Season Pattern Analysis**: Monitors low-scoring match percentage to recommend optimal strategies
- **Strategy Switch Notifications**: Pushover alerts when optimal strategy changes (1-0 vs 2-1)
- **Historical Validation**: 32+ seasons of data (1993-2025) validate recommendation accuracy
- **Real-Time Performance**: Live strategy comparison with accuracy tracking and exact scores
- **Custom Testing**: Manual score input with instant validation and points calculation

### 🔍 **Prediction Verification System**
- **Automated Validation**: Compares database predictions against WhatsApp messages and text files
- **Name Alias Resolution**: Handles player name variations (Ed Fenna → Edward Fenna, Steven Harrison → Ste Harrison)
- **Team Order Preservation**: Text position-based extraction maintains correct home/away order
- **Multiple Data Sources**: Parses `.txt` files and WhatsApp `.zip` exports from Dropbox
- **Database Storage**: Results saved to queryable `prediction_verification` table
- **Verification Categories**: Matches, Score Mismatches, In Messages Only, In Database Only
- **CSV Backup**: Timestamped reports for historical tracking

### 🔧 **Production Ready**
- **Comprehensive Logging**: Daily log files with detailed operation tracking
- **Error Handling**: Graceful failure recovery and retry logic
- **Master Scheduler**: Advanced automation with lock files and health monitoring
- **Security**: API key protection and secure authentication

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Virtual environment support
- API access to Fantasy Premier League
- Dropbox App credentials (optional)
- PythonAnywhere hosting (optional)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/prediction_league_script.git
   cd prediction_league_script
   ```

2. **Set up Python environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure API keys:**
   ```bash
   cp keys.json.template keys.json
   # Edit keys.json with your API credentials
   ```

4. **Set up Dropbox OAuth2** (if using Dropbox features):
   ```bash
   python scripts/prediction_league/setup_dropbox_oauth.py
   ```

5. **Install the Master Scheduler:**
   ```bash
   ./scripts/scheduler/install_scheduler.sh --dry-run  # Test first
   ./scripts/scheduler/install_scheduler.sh            # Install
   ```

6. **Test the system:**
   ```bash
   python scripts/fpl/fetch_fixtures_gameweeks.py --test --dry-run
   python scripts/fpl/fetch_results.py --test --dry-run
   ./scripts/scheduler/scheduler_status.sh             # Check status
   ```

## 📖 Documentation

### Core Guides
- **[Master Scheduler Guide](scripts/scheduler/README.md)** - Complete automation system
- **[Proxmox Deployment Guide](docs/Proxmox_Deployment_Guide.md)** - Complete VM setup guide
- **[Usage Guide](docs/Usage_Guide.md)** - Comprehensive usage instructions
- **[API Integration](docs/API_Integration.md)** - API endpoints and authentication
- **[Database Schema](docs/Database_Schema.md)** - Database structure and relationships

### Reference
- **[Project Overview](docs/PROJECT_OVERVIEW.md)** - System architecture overview
- **[FPL Data Guide](docs/FPL_DATA_GUIDE.md)** - Fantasy Premier League data handling
- **[Troubleshooting](docs/Troubleshooting.md)** - Common issues and solutions
- **[Changelog](docs/CHANGELOG.md)** - Version history and updates

## 🔧 System Architecture

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   FPL API       │  │   Dropbox API   │  │ Football-Data   │  │  PythonAnywhere │
│   - Fixtures    │  │   - Predictions │  │ - Historical    │  │   - Database    │
│   - Gameweeks   │  │   - OAuth2      │  │ - Weekly Data   │  │   - Hosting     │
│   - Results     │  │   - File Sync   │  │ - Match Stats   │  │   - SSH Upload  │
└─────────┬───────┘  └─────────┬───────┘  └─────────┬───────┘  └─────────┬───────┘
          │                    │                    │                    │
          ▼                    ▼                    ▼                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        Master Scheduler System                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                Centralized Orchestration Engine                    │     │
│  │  - Timing Control      - Process Management    - Weekly Scheduling │     │
│  │  - Lock Files          - Gameweek Validation   - Historical Data   │     │
│  │  - Health Monitoring   - Configuration Management                   │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   FPL       │  │ Prediction  │  │  Football   │  │  Database   │         │
│  │ Processing  │  │ Processing  │  │    Data     │  │ Monitoring  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                        SQLite Database                              │     │
│  │  - Teams & Players      - Fixtures & Results    - Historical Stats │     │
│  │  - Predictions          - Gameweeks             - Betting Odds     │     │
│  │  - File Metadata        - Change Tracking       - Match Officials  │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────────────┘
```

## 🛠️ Core Components

### Master Scheduler System
- **`scripts/scheduler/master_scheduler.sh`** - Main orchestration engine
- **`scripts/scheduler/gameweek_validator.py`** - Deadline-based validation
- **`scripts/scheduler/scheduler_config.conf`** - Centralized configuration
- **`scripts/scheduler/install_scheduler.sh`** - Installation and setup
- **`scripts/scheduler/scheduler_status.sh`** - Health monitoring

### FPL Data Processing  
- **`scripts/fpl/fetch_fixtures_gameweeks.py`** - Manages fixtures and gameweeks with validation
- **`scripts/fpl/fetch_results.py`** - Processes match results with timezone handling
- **`scripts/fpl/fetch_fpl_data.py`** - Comprehensive player data collection

### Football-Data.co.uk Integration
- **`scripts/football_data/migrate_legacy_data.py`** - Historical data migration (1993-2025)
- **`scripts/football_data/fetch_football_data.py`** - Weekly current season data updates

### Prediction Management
- **`scripts/prediction_league/clean_predictions_dropbox.py`** - Dropbox integration
- **`scripts/prediction_league/automated_predictions.py`** - Automated prediction generation with dual-file upload
- **`scripts/prediction_league/setup_dropbox_oauth.py`** - OAuth2 setup helper

### Database Operations
- **`scripts/database/monitor_and_upload.py`** - Change monitoring and uploads

### Legacy Support
- **`legacy/`** - Previous system versions for reference

### Intelligent Strategy Recommendation System
- **`scripts/prediction_league/update_season_recommendations.py`** - Weekly season analysis and recommendations
- **`scripts/database/setup_season_recommendations.py`** - Database schema setup and historical data population
- **`scripts/database/create_season_recommendations_table.sql`** - SQL schema for recommendation tables
- **`webapp/app.py`** - Enhanced with adaptive strategy API endpoints
- **`webapp/templates/predictions.html`** - Recommendation dashboard widget and adaptive strategy

**Key Features:**
- **Real-Time Season Analysis**: Monitors low-scoring match percentage (≤2 goals)
- **Strategy Switch Recommendations**: Suggests optimal timing to switch between 1-0 and 2-1 strategies
- **Historical Pattern Matching**: Uses 32+ seasons of data to validate recommendations
- **Confidence Levels**: Early/Moderate/High confidence based on sample size
- **Automated Notifications**: Pushover alerts for strategy changes
- **Performance Tracking**: Expected points improvement calculations

**Recommendation Logic:**
- **>47% low-scoring matches**: Recommend 1-0 strategy
- **<47% low-scoring matches**: Continue 2-1 strategy
- **Sample size thresholds**: 40 matches (moderate), 80 matches (high confidence)
- **Historical validation**: Based on comprehensive analysis of 2019-2026 seasons

## ⚙️ Configuration

### API Keys Setup
Create `keys.json` from template and configure:

```json
{
  "odds_api_key": "your_odds_api_key",
  "dropbox_app_key": "your_dropbox_app_key", 
  "dropbox_app_secret": "your_dropbox_app_secret",
  "pythonanywhere_username": "your_username",
  "pythonanywhere_password": "your_password"
}
```

### Master Scheduler Configuration

**Single Cron Job (Recommended):**
```bash
# Master Scheduler - Manages all automation
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh
```

**Configuration File (`scripts/scheduler/scheduler_config.conf`):**
```bash
# Enable/disable individual components
ENABLE_FETCH_RESULTS=true
ENABLE_FETCH_FOOTBALL_DATA=true
ENABLE_MONITOR_UPLOAD=true
ENABLE_CLEAN_PREDICTIONS=true
ENABLE_FETCH_FIXTURES=true
ENABLE_AUTOMATED_PREDICTIONS=true
ENABLE_FETCH_FPL_DATA=true
ENABLE_FETCH_ODDS=true
ENABLE_UPDATE_RECOMMENDATIONS=true

# Timing controls
DELAY_BETWEEN_RESULTS_UPLOAD=30

# Seasonal adjustments
OFFSEASON_MODE=false
```

**Legacy Cron Jobs (Manual Setup):**
```bash
# FPL Data (every 30 minutes)
*/30 * * * * cd /path/to/project && ./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py

# Results Processing (every minute)  
* * * * * cd /path/to/project && ./venv/bin/python scripts/fpl/fetch_results.py

# Prediction Processing (every 15 minutes)
*/15 * * * * cd /path/to/project && ./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py

# Database Upload (every minute with delay)
* * * * * sleep 30; cd /path/to/project && ./venv/bin/python scripts/database/monitor_and_upload.py

# Automated Predictions (every hour)
0 * * * * cd /path/to/project && ./venv/bin/python scripts/prediction_league/automated_predictions.py

# Daily Data Refresh (7 AM)
0 7 * * * cd /path/to/project && ./venv/bin/python scripts/fpl/fetch_fpl_data.py

# Weekly Football Data (Sundays 9 AM)
0 9 * * 0 cd /path/to/project && ./venv/bin/python scripts/football_data/fetch_football_data.py

# Season Recommendations (Sundays 10 AM)
0 10 * * 0 cd /path/to/project && ./venv/bin/python scripts/prediction_league/update_season_recommendations.py
```

## 🔒 Security Features

- **API Key Protection**: Sensitive data never committed to repository
- **OAuth2 Authentication**: Modern token-based authentication with auto-refresh  
- **Secure File Handling**: Atomic file operations and proper permissions
- **Process Locking**: Prevents concurrent execution conflicts
- **Transaction Safety**: Database operations with rollback protection

## 📊 Monitoring & Logging

### Log Files
- **Daily Rotation**: `logs/script_name_YYYYMMDD.log`
- **Detailed Tracking**: All operations, errors, and timing information
- **Change Detection**: Only logs actual changes, not unnecessary operations

### Health Monitoring
- **Database Upload Tracking**: Monitors successful uploads to hosting
- **API Connectivity**: Tracks API response times and failures
- **Change Detection**: Reports on actual vs phantom updates

## 🚨 Common Issues & Solutions

### OAuth Token Expired
```bash
# Re-run OAuth setup
python scripts/prediction_league/setup_dropbox_oauth.py
```

### Database Connection Issues
```bash
# Test database connectivity
python -c "import sqlite3; sqlite3.connect('data/database.db').close(); print('✅ Database OK')"
```

### Timezone Errors (Fixed in v2025.08.31)
The system now properly handles timezone-aware datetime comparisons with robust error handling.

## 🤝 Contributing

This is a personal hobby project, but contributions are welcome:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit changes** (`git commit -m 'Add amazing feature'`)
4. **Push to branch** (`git push origin feature/amazing-feature`)  
5. **Open a Pull Request**

### Development Guidelines
- Follow the **[CLAUDE.md](CLAUDE.md)** development philosophy
- **Prioritize simplicity** over complexity
- **Write self-documenting code** with meaningful names
- **Test with sample data** to avoid wasting API calls
- **Handle errors gracefully** with proper logging

## 📋 Requirements

### System Requirements
- **Python**: 3.8 or higher
- **Storage**: 100MB minimum (500MB recommended)
- **Memory**: 512MB minimum (1GB recommended)  
- **Network**: Stable internet connection for API access

### Python Dependencies
- `requests` - HTTP client for API calls
- `paramiko` - SSH/SFTP for uploads
- `tqdm` - Progress bars for long operations
- `sqlite3` - Database operations (built-in)

## 🎯 Project Philosophy

This system is built with **hobby project principles**:

- **Simplicity over complexity** - Easy to understand and modify
- **Readability over performance** - Code should tell a story
- **Practical functionality** over academic perfection  
- **Self-documenting code** over extensive comments
- **Reliable operation** for personal use cases

## 📈 Version History

### Recent Major Updates
- **v2025.08.31**: Master Scheduler System & Major Improvements
  - **Master Scheduler System**: Centralized orchestration with single cron job
  - **Gameweek Validation**: Deadline-based validation with auto-refresh
  - **Enhanced Monitoring**: Process management, lock files, and health checks
  - **Database Improvements**: Change monitoring with PythonAnywhere uploads
  - **Dropbox OAuth2 System**: Automatic token refresh and secure authentication
  - **FPL Results Processing**: Timezone handling fixes and smart timing
  - **Configuration Management**: Easy enable/disable and timing controls

See **[CHANGELOG.md](docs/CHANGELOG.md)** for complete version history.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Fantasy Premier League** for providing comprehensive API access
- **Dropbox** for reliable file storage and OAuth2 implementation
- **PythonAnywhere** for affordable hosting solutions
- **Python Community** for excellent libraries and documentation

## 📞 Support

For issues and questions:

1. **Check Documentation**: Start with the [Usage Guide](docs/Usage_Guide.md)
2. **Review Troubleshooting**: See [Troubleshooting.md](docs/Troubleshooting.md)  
3. **Check Logs**: Review daily log files for specific error messages
4. **Open Issue**: Create a GitHub issue with logs and system details

---

**Built with ❤️ for hobby prediction leagues**

*This system has been designed and tested for personal use in managing prediction leagues with friends and family. While robust and production-ready, it prioritizes simplicity and maintainability over enterprise-scale features.*