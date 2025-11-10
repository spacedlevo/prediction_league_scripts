# Production Deployment Guide

Guidelines for deploying the prediction league project to production servers.

## Table of Contents

- [Critical Dependencies](#critical-dependencies-for-production)
- [Systemd Service Requirements](#systemd-service-requirements)
- [Keys.json Permission Configuration](#keysjson-permission-configuration)
- [Common Production Issues](#common-production-issues)

---

## Critical Dependencies for Production

When deploying to production servers (Ubuntu/systemd), ensure all dependencies are installed:

```bash
# Essential timezone dependency (service will fail without this)
pip install pytz

# Verify installation
python -c "import pytz; print('pytz installed successfully')"
```

### Key Dependencies

- `requests` - HTTP client for API calls
- `paramiko` - SSH/SFTP for PythonAnywhere uploads
- `tqdm` - Progress bars for long operations
- `pytz` - **REQUIRED** - Timezone handling for UK time display (BST/GMT conversion)

---

## Common Production Issues

### Service Fails with Exit Code 3

**Symptom**: Service fails to start with exit code 3

**Cause**: Usually indicates missing `pytz` dependency

**Solution**:

```bash
# Check logs for missing module errors
journalctl -u prediction-league.service --no-pager -l

# Test app import to verify all dependencies
python -c "import app"

# Install missing dependency
pip install pytz
```

### Import Errors on Service Start

**Symptom**: Service fails to start with import errors

**Cause**: Missing dependencies in virtual environment

**Solution**:

```bash
# Activate virtual environment
source venv/bin/activate

# Install all requirements
pip install -r requirements.txt

# Verify all imports work
python -c "import app"
```

---

## Systemd Service Requirements

### Service Configuration

Ensure your systemd service file includes:

- **Virtual environment path**: Use full path to venv Python interpreter
- **Working directory**: Must be set to webapp directory
- **Config.json**: Must be accessible with correct timezone setting
- **User/Group**: Appropriate user with access to all required files

### Example Service File

```ini
[Unit]
Description=Prediction League Web Application
After=network.target

[Service]
Type=simple
User=predictionleague
Group=predictionleague
WorkingDirectory=/path/to/project/webapp
Environment="PATH=/path/to/project/venv/bin"
ExecStart=/path/to/project/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Service Management Commands

```bash
# Reload systemd after changes
sudo systemctl daemon-reload

# Start service
sudo systemctl start prediction-league.service

# Enable service on boot
sudo systemctl enable prediction-league.service

# Check status
sudo systemctl status prediction-league.service

# View logs
journalctl -u prediction-league.service --no-pager -l

# Follow logs in real-time
journalctl -u prediction-league.service -f
```

---

## Keys.json Permission Configuration

Critical for multi-user production environments where scripts run under different users.

### Setting Permissions

```bash
# Set appropriate permissions for group access
chmod 640 keys.json                    # Owner read/write, group read
chgrp predictionleague keys.json       # Set group ownership

# Verify permissions
ls -la keys.json
# Should show: -rw-r----- 1 user predictionleague
```

### Permission Preservation

**Fixed September 2025**: Scripts now preserve original file permissions when updating Dropbox tokens.

- `clean_predictions_dropbox.py` (runs every 15 minutes) maintains group permissions
- `setup_dropbox_oauth.py` (manual setup) preserves permissions during token refresh
- Prevents automatic reset to 0600 (owner-only) permissions

### Multi-User Access

When multiple users or services need to access keys.json:

1. Create a shared group (e.g., `predictionleague`)
2. Add all users/services to the group
3. Set group ownership on keys.json
4. Use 640 permissions (owner read/write, group read)
5. Ensure scripts preserve permissions when updating file

---

## Virtual Environment Setup

### Creating Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Verify installation
python -c "import pytz; import requests; import paramiko; print('All dependencies installed')"
```

### Production Requirements

Ensure `requirements.txt` includes:

```
requests
paramiko
tqdm
pytz
dropbox
flask  # For webapp
# Add other dependencies as needed
```

---

## Scheduler Setup

### Cron Configuration

```bash
# Edit crontab
crontab -e

# Add single entry for master scheduler
* * * * * /path/to/project/scripts/scheduler/master_scheduler.sh

# Verify cron is running
systemctl status cron

# Check cron logs
grep CRON /var/log/syslog
```

### Scheduler Logs

```bash
# Monitor scheduler activity
tail -f logs/scheduler/master_scheduler_$(date +%Y%m%d).log

# Check for errors
grep ERROR logs/scheduler/master_scheduler_*.log

# View specific script logs
tail -f logs/database/monitor_and_upload_$(date +%Y%m%d).log
```

---

## Security Considerations

### File Permissions

- **keys.json**: 640 (owner read/write, group read)
- **database.db**: 660 (owner/group read/write)
- **scripts**: 755 (executable)
- **logs directory**: 775 (owner/group read/write/execute)

### Secret Management

- Store API keys and credentials in `keys.json`
- Never commit `keys.json` to version control
- Use environment-specific configuration files
- Rotate credentials regularly

### SSH/SFTP Access

For PythonAnywhere uploads:

- Use SSH key authentication when possible
- Store passwords securely in keys.json
- Restrict permissions on keys.json (640)
- Consider using SSH agent for key management

---

## Monitoring and Maintenance

### Log Management

```bash
# Create logs directory structure
mkdir -p logs/{scheduler,database,fpl,odds-api,pulse_api}

# Set up log rotation
sudo nano /etc/logrotate.d/prediction-league
```

Example logrotate configuration:

```
/path/to/project/logs/*/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

### Health Checks

```bash
# Check database upload status
./venv/bin/python scripts/database/monitor_and_upload.py --dry-run

# Verify scheduler is running
ps aux | grep master_scheduler

# Check recent uploads
sqlite3 data/database.db "SELECT table_name, timestamp FROM last_update ORDER BY timestamp DESC LIMIT 10;"
```

### Troubleshooting Commands

```bash
# Check service status
sudo systemctl status prediction-league.service

# View service logs
journalctl -u prediction-league.service --no-pager -l

# Check scheduler logs
tail -100 logs/scheduler/master_scheduler_$(date +%Y%m%d).log

# Verify cron is working
grep CRON /var/log/syslog | tail -20

# Test database connection
python -c "import sqlite3; conn = sqlite3.connect('data/database.db'); print('Database connection successful')"

# Test imports
python -c "import app; print('App import successful')"
```

---

## Deployment Checklist

Before deploying to production:

- [ ] Install all dependencies in virtual environment
- [ ] Verify pytz is installed
- [ ] Configure keys.json with correct permissions (640)
- [ ] Set up systemd service file
- [ ] Enable and start service
- [ ] Configure cron for master scheduler
- [ ] Set up log rotation
- [ ] Test database uploads
- [ ] Verify scheduler executes scripts correctly
- [ ] Monitor logs for errors
- [ ] Set up backup strategy for database
- [ ] Document any environment-specific configuration

---

## Backup and Recovery

### Database Backups

```bash
# Manual backup
cp data/database.db data/backups/database_$(date +%Y%m%d_%H%M%S).db

# Automated daily backups (add to crontab)
0 3 * * * /path/to/project/scripts/backup_database.sh
```

### Configuration Backups

```bash
# Backup keys.json (securely)
cp keys.json backups/keys_$(date +%Y%m%d).json
chmod 600 backups/keys_*.json

# Backup configuration
tar -czf backups/config_$(date +%Y%m%d).tar.gz keys.json config.json scripts/scheduler/scheduler_config.conf
```

### Recovery Process

1. Stop all services
2. Restore database from backup
3. Restore configuration files
4. Verify permissions
5. Restart services
6. Check logs for errors
7. Verify functionality

---

## Support and Resources

- **Main Documentation**: [CLAUDE.md](../CLAUDE.md)
- **Systems Documentation**: [SYSTEMS.md](SYSTEMS.md)
- **Fixes Changelog**: [FIXES_CHANGELOG.md](FIXES_CHANGELOG.md)
- **Project Repository**: Check README.md for repository information
