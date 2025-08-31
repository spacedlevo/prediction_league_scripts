# Prediction League Script System

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-production-brightgreen.svg)]()

A comprehensive automated system for managing Fantasy Premier League predictions, data collection, and result processing. Built for hobby prediction leagues with friends and family.

## 🌟 Features

### 🔄 **Automated Data Processing**
- **FPL API Integration**: Automatic fixtures, gameweeks, and results collection
- **Smart Change Detection**: Only updates database when data actually changes
- **Intelligent Timing**: Runs during match days and timing windows
- **Missing Results Detection**: Automatically fetches results for completed fixtures

### 📱 **Dropbox Integration**
- **OAuth2 Authentication**: Secure token management with auto-refresh
- **Prediction Processing**: Automatic cleaning and processing of prediction files
- **File Monitoring**: Change detection and processing of updated predictions
- **Multiple Format Support**: Text file parsing with team name recognition

### 🗄️ **Database Management**
- **SQLite Backend**: Lightweight, reliable data storage
- **Auto-Upload**: Automated uploads to PythonAnywhere hosting
- **Change Monitoring**: Real-time detection and immediate sync
- **Health Checks**: Regular uploads ensure system connectivity

### 🔧 **Production Ready**
- **Comprehensive Logging**: Daily log files with detailed operation tracking
- **Error Handling**: Graceful failure recovery and retry logic
- **Cron Integration**: Designed for automated scheduling
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

5. **Test the system:**
   ```bash
   python scripts/fpl/fetch_fixtures_gameweeks.py --test --dry-run
   python scripts/fpl/fetch_results.py --test --dry-run
   ```

## 📖 Documentation

### Core Guides
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
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FPL API       │    │   Dropbox API   │    │  PythonAnywhere │
│   - Fixtures    │    │   - Predictions │    │   - Database    │
│   - Gameweeks   │    │   - OAuth2      │    │   - Hosting     │
│   - Results     │    │   - File Sync   │    │   - SSH Upload  │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Processing Engine                       │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   FPL       │  │ Prediction  │  │  Database   │             │
│  │ Processing  │  │ Processing  │  │ Monitoring  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                SQLite Database                          │   │
│  │  - Teams & Players    - Fixtures & Results            │   │
│  │  - Predictions        - Gameweeks                     │   │
│  │  - File Metadata      - Change Tracking               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 🛠️ Core Components

### FPL Data Processing
- **`scripts/fpl/fetch_fixtures_gameweeks.py`** - Manages fixtures and gameweeks
- **`scripts/fpl/fetch_results.py`** - Processes match results with timezone handling
- **`scripts/fpl/fetch_fpl_data.py`** - Comprehensive player data collection

### Prediction Management
- **`scripts/prediction_league/clean_predictions_dropbox.py`** - Dropbox integration
- **`scripts/prediction_league/setup_dropbox_oauth.py`** - OAuth2 setup helper

### Database Operations
- **`scripts/database/monitor_and_upload.py`** - Change monitoring and uploads

### Legacy Support
- **`legacy/`** - Previous system versions for reference

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

### Automation Setup

**Cron Jobs Example:**
```bash
# FPL Data (every 6 hours)
0 */6 * * * cd /path/to/project && ./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py

# Results Processing (every 30 minutes during season)  
*/30 * * * * cd /path/to/project && ./venv/bin/python scripts/fpl/fetch_results.py

# Prediction Processing (every 15 minutes)
*/15 * * * * cd /path/to/project && ./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py

# Database Upload (every minute)
* * * * * cd /path/to/project && ./venv/bin/python scripts/database/monitor_and_upload.py
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
- **v2025.08.31**: Major system improvements and fixes
  - Database change monitoring with PythonAnywhere uploads
  - Dropbox OAuth2 system with automatic token refresh
  - FPL results processing fixes (timezone handling)
  - Fixtures update optimization (eliminated phantom updates)
  - Comprehensive deployment documentation

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