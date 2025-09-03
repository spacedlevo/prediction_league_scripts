# Prediction League Web Application

## Overview

Simple Flask-based web application for managing the prediction league database and running maintenance scripts. Built following the hobbyist development philosophy: simple, readable, maintainable.

## Philosophy

- **Single-file architecture** - Everything in `app.py` for easy maintenance
- **Server-side rendering** - HTML templates instead of complex frontend frameworks
- **Direct database access** - Simple sqlite3 module, no ORM complexity
- **Minimal dependencies** - Flask, basic web technologies
- **Self-documenting code** - Clear function names, logical structure

## Features

### 1. Dashboard
- Database overview and health check
- Player counts (active/inactive)
- Current gameweek status
- Prediction coverage statistics
- Last update timestamps

### 2. Admin Panel
- Add new players to the league
- Toggle player active/inactive status
- Update payment and league status
- Simple form validation

### 3. Scripts Management
- Execute existing Python scripts manually
- Real-time output display
- Status tracking for long-running operations

### 4. FPL Insights
- Player statistics from FPL data
- Basic filtering (team, position, price range)
- Simple charts for key metrics
- Export data functionality

## Development Plan

### Phase 1: Foundation (Days 1-2)
- [ ] Basic Flask app structure
- [ ] Database connection helpers
- [ ] HTML template layout
- [ ] Dashboard with basic stats

### Phase 2: Core Features (Days 3-5)
- [ ] Admin panel for player management
- [ ] Script execution system
- [ ] Basic authentication
- [ ] Error handling and logging

### Phase 3: FPL Features (Days 6-7)
- [ ] FPL data display
- [ ] Basic filtering and sorting
- [ ] Simple charts
- [ ] CSV export functionality

### Phase 4: Polish (Day 8)
- [ ] Styling improvements
- [ ] Mobile responsiveness
- [ ] Performance optimization
- [ ] Documentation

## File Structure

```
webapp/
├── README.md           # This file - development plan
├── app.py             # Main Flask application (single file)
├── config.json        # Configuration settings
├── requirements.txt   # Python dependencies
├── templates/         # HTML templates
│   ├── layout.html    # Base template
│   ├── dashboard.html # Database overview
│   ├── admin.html     # Player management
│   ├── scripts.html   # Script execution
│   └── fpl.html       # FPL insights
└── static/           # CSS, JS, assets
    ├── style.css     # Main stylesheet
    ├── script.js     # Basic JavaScript
    └── favicon.ico   # Site icon
```

## Technology Choices

### Backend
- **Flask** - Lightweight, simple to understand
- **sqlite3** - Direct database access, no ORM complexity
- **subprocess** - Execute existing Python scripts
- **sessions** - Simple authentication

### Frontend
- **Jinja2 templates** - Server-side rendering
- **TailwindCSS** - Simple utility classes
- **htmx** - Dynamic updates without JavaScript complexity
- **Chart.js** - Simple charts via CDN

### Deployment
- **Direct Python execution** - No Docker complexity
- **systemd service** - Auto-start on boot
- **nginx proxy** - Optional for production

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Configure settings
cp config.json.example config.json
# Edit config.json with your settings

# Run development server
python app.py

# Access at http://localhost:5000
```

## Configuration

Example `config.json`:
```json
{
  "secret_key": "your-secret-key-here",
  "database_path": "../data/database.db",
  "scripts_path": "../scripts",
  "admin_password": "admin123",
  "host": "0.0.0.0",
  "port": 5000,
  "debug": false
}
```

## Security Notes

- **Local network only** - Designed for private network use
- **Basic authentication** - Session-based, hardcoded password
- **Input validation** - Simple form validation
- **SQL injection protection** - Parameterized queries only

## Development Notes

### Code Style
- Functions should be small and focused
- Use descriptive variable names
- Minimal comments - let code explain itself
- Handle errors gracefully with user-friendly messages

### Database Access
- Direct sqlite3 connection
- Parameterized queries for safety
- Transaction handling for data modifications
- Connection pooling not needed for single-user app

### Script Integration
- Execute existing scripts via subprocess
- Capture output for display in UI
- Handle long-running operations gracefully
- Prevent concurrent script execution

## Future Enhancements

### Nice-to-have features (not required for MVP):
- [ ] User preferences/settings
- [ ] Data export to CSV/JSON
- [ ] Basic API endpoints
- [ ] Mobile app-like interface
- [ ] Automated backups
- [ ] Email notifications
- [ ] Advanced charting
- [ ] Custom dashboard widgets

## Maintenance

This application is designed to be maintained by a single hobbyist developer:
- Single file makes changes easy to track
- Simple technology stack
- Clear separation of concerns within the single file
- Minimal external dependencies
- Self-contained deployment