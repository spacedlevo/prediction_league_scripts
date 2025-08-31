# Proxmox VM Deployment Guide

Complete guide for setting up a Proxmox VM running Ubuntu Server and deploying the prediction league script system.

## Overview

This guide covers:
1. Creating and configuring a Proxmox VM
2. Installing Ubuntu Server
3. Setting up the system environment
4. Cloning and configuring the prediction league scripts
5. Setting up automated cron jobs
6. Testing and monitoring

## Prerequisites

- Proxmox VE host with available resources
- Ubuntu Server 22.04/24.04 ISO
- GitHub access to clone the repository
- API keys and credentials ready for configuration

## Part 1: Proxmox VM Setup

### 1.1 Create VM in Proxmox

**Access Proxmox Web Interface:**
1. Open Proxmox web interface (https://your-proxmox-ip:8006)
2. Login with root credentials

**Create New VM:**
1. Click **"Create VM"** button
2. **General Tab:**
   - VM ID: `101` (or next available)
   - Name: `prediction-league-server`
   - Resource Pool: (optional)

3. **OS Tab:**
   - Use CD/DVD disc image file (iso)
   - Storage: local
   - ISO image: `ubuntu-22.04-server-amd64.iso`

4. **System Tab:**
   - Graphic card: Default
   - Machine: Default (i440fx)
   - BIOS: Default (SeaBIOS)
   - SCSI Controller: VirtIO SCSI
   - Qemu Agent: ✅ **Enable**

5. **Hard Disk Tab:**
   - Bus/Device: VirtIO Block
   - Storage: local-lvm (or your preferred storage)
   - Disk size: **20 GB** minimum (32 GB recommended)
   - Cache: Default (No cache)

6. **CPU Tab:**
   - Sockets: 1
   - Cores: **2** (minimum for good performance)
   - Type: host

7. **Memory Tab:**
   - Memory: **2048 MB** (2GB minimum, 4GB recommended)
   - Minimum memory: 1024 MB

8. **Network Tab:**
   - Bridge: vmbr0 (default)
   - Model: VirtIO (paravirtualized)
   - Firewall: ✅ Enable if desired

9. **Confirm:**
   - Review settings
   - ✅ **Start after created**
   - Click **"Finish"**

### 1.2 VM Resource Recommendations

**Minimum Requirements:**
- **CPU:** 2 cores
- **RAM:** 2GB
- **Storage:** 20GB
- **Network:** 1 Gbps connection

**Recommended for Production:**
- **CPU:** 2-4 cores  
- **RAM:** 4GB
- **Storage:** 32GB SSD
- **Network:** 1 Gbps connection

## Part 2: Ubuntu Server Installation

### 2.1 Install Ubuntu Server

**Boot from ISO:**
1. VM should auto-start and boot from Ubuntu ISO
2. If not, start VM and ensure ISO is mounted

**Installation Steps:**
1. **Language:** English
2. **Keyboard:** Your layout
3. **Network:** Configure static IP (recommended) or DHCP
   - Static IP example: `192.168.1.100/24`
   - Gateway: `192.168.1.1`
   - DNS: `8.8.8.8,1.1.1.1`
4. **Proxy:** Usually blank
5. **Mirror:** Default Ubuntu archive mirror
6. **Storage:** Use entire disk (guided setup)
7. **Profile Setup:**
   - Name: `Prediction League Admin`
   - Server name: `prediction-league`
   - Username: `predleague` (or your preference)
   - Password: **Strong password**
8. **SSH:** ✅ **Install OpenSSH server**
   - Import SSH identity: From GitHub (optional)
9. **Snaps:** Skip or select desired snaps
10. **Installation:** Wait for completion
11. **Reboot:** Remove ISO and reboot

### 2.2 Post-Installation Setup

**SSH into the server:**
```bash
ssh predleague@192.168.1.100
```

**Update system:**
```bash
sudo apt update && sudo apt upgrade -y
```

**Install essential packages:**
```bash
sudo apt install -y git curl wget vim htop build-essential software-properties-common
```

**Install Python 3 and pip:**
```bash
sudo apt install -y python3 python3-pip python3-venv python3-dev
```

**Verify installations:**
```bash
python3 --version  # Should show Python 3.8+
git --version
```

## Part 3: System Environment Setup

### 3.1 Create System User and Directories

**Create dedicated user (optional but recommended):**
```bash
sudo adduser predictionleague --disabled-password --gecos ""
sudo usermod -aG sudo predictionleague
```

**Switch to prediction user:**
```bash
sudo su - predictionleague
```

**Create project directory structure:**
```bash
mkdir -p ~/ projects
cd ~/projects
```

### 3.2 Clone Repository from GitHub

**Clone the repository:**
```bash
git clone https://github.com/your-username/prediction_league_script.git
cd prediction_league_script
```

**Verify project structure:**
```bash
ls -la
# Should see: data/ docs/ legacy/ logs/ samples/ scripts/ venv/ keys.json etc.
```

## Part 4: Python Environment Setup

### 4.1 Create Virtual Environment

**Create and activate virtual environment:**
```bash
cd ~/projects/prediction_league_script
python3 -m venv venv
source venv/bin/activate
```

**Verify virtual environment:**
```bash
which python  # Should point to venv/bin/python
python --version
```

### 4.2 Install Python Dependencies

**Install required packages:**
```bash
# Core dependencies
pip install requests sqlite3
pip install paramiko  # For PythonAnywhere uploads
pip install tqdm      # For progress bars

# Additional dependencies (if needed)
pip install python-dateutil pytz

# Verify installations
pip list
```

**Test basic imports:**
```bash
python -c "import requests, sqlite3, paramiko, tqdm; print('All imports successful')"
```

## Part 5: Configuration Setup

### 5.1 Configure API Keys

**Create keys.json file:**
```bash
cd ~/projects/prediction_league_script
cp keys.json.template keys.json  # If template exists
# OR create from scratch:
vim keys.json
```

**keys.json structure:**
```json
{
  "odds_api_key": "your_odds_api_key_here",
  "dropbox_app_key": "your_dropbox_app_key",
  "dropbox_app_secret": "your_dropbox_app_secret",
  "dropbox_oath_token": "will_be_updated_by_oauth_setup",
  "PUSHOVER_USER": "your_pushover_user_key",
  "PUSHOVER_TOKEN": "your_pushover_app_token",
  "pythonanywhere_username": "your_pythonanywhere_username",
  "pythonanywhere_password": "your_pythonanywhere_password"
}
```

**Secure the keys file:**
```bash
chmod 600 keys.json
```

### 5.2 Setup Dropbox OAuth2

**Run OAuth2 setup (interactive):**
```bash
./venv/bin/python scripts/prediction_league/setup_dropbox_oauth.py
```

**Follow the prompts:**
1. Browser will open to Dropbox authorization
2. Click "Allow" 
3. Copy authorization code
4. Paste code in terminal
5. Tokens will be automatically saved

### 5.3 Database Setup

**Check if database exists:**
```bash
ls -la data/
# Should see database.db
```

**If database doesn't exist, you may need to:**
1. Copy database from backup
2. Initialize with schema
3. Run initial data population scripts

## Part 6: Test System Components

### 6.1 Test Individual Scripts

**Test FPL data fetching:**
```bash
./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py --test --dry-run
```

**Test FPL results processing:**
```bash
./venv/bin/python scripts/fpl/fetch_results.py --test --dry-run
```

**Test Dropbox connection:**
```bash
./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --dry-run
```

**Test database monitoring:**
```bash
./venv/bin/python scripts/database/monitor_and_upload.py --test --dry-run
```

### 6.2 Verify System Health

**Check log files:**
```bash
ls -la logs/
tail -f logs/fixtures_gameweeks_$(date +%Y%m%d).log
```

**Check database connectivity:**
```bash
./venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/database.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM teams')
print(f'Teams in database: {cursor.fetchone()[0]}')
conn.close()
"
```

## Part 7: Automation Setup

### 7.1 Create Cron Jobs

**Edit crontab:**
```bash
crontab -e
```

**Add cron jobs (example schedule):**
```bash
# Prediction League Scripts - All times in server timezone

# FPL Data Fetching (every 6 hours)
0 */6 * * * cd /home/predictionleague/projects/prediction_league_script && ./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py >/dev/null 2>&1

# FPL Results Processing (every 30 minutes during season)
*/30 * * * * cd /home/predictionleague/projects/prediction_league_script && ./venv/bin/python scripts/fpl/fetch_results.py >/dev/null 2>&1

# Dropbox Prediction Cleaning (every 15 minutes) 
*/15 * * * * cd /home/predictionleague/projects/prediction_league_script && ./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py >/dev/null 2>&1

# Database Monitoring & Upload (every minute)
* * * * * cd /home/predictionleague/projects/prediction_league_script && ./venv/bin/python scripts/database/monitor_and_upload.py >/dev/null 2>&1

# System maintenance - log cleanup (daily at 2 AM)
0 2 * * * find /home/predictionleague/projects/prediction_league_script/logs -name "*.log" -mtime +30 -delete
```

**Verify cron jobs:**
```bash
crontab -l
```

### 7.2 Create Systemd Services (Alternative)

For more robust service management, you can create systemd services:

**Create service file:**
```bash
sudo vim /etc/systemd/system/prediction-league-monitor.service
```

**Service file content:**
```ini
[Unit]
Description=Prediction League Database Monitor
After=network.target

[Service]
Type=simple
User=predictionleague
WorkingDirectory=/home/predictionleague/projects/prediction_league_script
ExecStart=/home/predictionleague/projects/prediction_league_script/venv/bin/python scripts/database/monitor_and_upload.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

**Enable and start service:**
```bash
sudo systemctl enable prediction-league-monitor.service
sudo systemctl start prediction-league-monitor.service
sudo systemctl status prediction-league-monitor.service
```

## Part 8: Monitoring and Maintenance

### 8.1 Log Monitoring

**Monitor logs in real-time:**
```bash
# Database monitoring
tail -f logs/database_monitor_$(date +%Y%m%d).log

# FPL results
tail -f logs/fetch_results_$(date +%Y%m%d).log

# Dropbox cleaning  
tail -f logs/clean_predictions_$(date +%Y%m%d).log
```

**Log rotation setup:**
```bash
sudo vim /etc/logrotate.d/prediction-league
```

**Logrotate config:**
```
/home/predictionleague/projects/prediction_league_script/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 predictionleague predictionleague
}
```

### 8.2 System Monitoring

**Create monitoring script:**
```bash
vim ~/monitor_system.sh
```

**Monitoring script content:**
```bash
#!/bin/bash
echo "=== Prediction League System Status ==="
echo "Date: $(date)"
echo

echo "=== Disk Space ==="
df -h /home/predictionleague/projects/prediction_league_script

echo "=== Memory Usage ==="
free -h

echo "=== Recent Log Entries ==="
tail -n 5 /home/predictionleague/projects/prediction_league_script/logs/database_monitor_$(date +%Y%m%d).log 2>/dev/null || echo "No database monitor logs today"

echo "=== Cron Jobs ==="
crontab -l | grep -v "^#"

echo "=== Process Status ==="
ps aux | grep python | grep -v grep
```

**Make executable and run:**
```bash
chmod +x ~/monitor_system.sh
./monitor_system.sh
```

## Part 9: Security Hardening

### 9.1 Firewall Configuration

**Install and configure UFW:**
```bash
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw status
```

### 9.2 Secure SSH

**Edit SSH config:**
```bash
sudo vim /etc/ssh/sshd_config
```

**Recommended SSH settings:**
```
Port 22
PermitRootLogin no
PasswordAuthentication yes
PubkeyAuthentication yes
X11Forwarding no
```

**Restart SSH:**
```bash
sudo systemctl restart ssh
```

### 9.3 System Updates

**Set up automatic updates:**
```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Part 10: Backup Strategy

### 10.1 Database Backup Script

**Create backup script:**
```bash
vim ~/backup_database.sh
```

**Backup script content:**
```bash
#!/bin/bash
PROJECT_DIR="/home/predictionleague/projects/prediction_league_script"
BACKUP_DIR="/home/predictionleague/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
cp $PROJECT_DIR/data/database.db $BACKUP_DIR/database_backup_$DATE.db

# Backup keys.json
cp $PROJECT_DIR/keys.json $BACKUP_DIR/keys_backup_$DATE.json

# Keep only last 7 days of backups
find $BACKUP_DIR -name "database_backup_*.db" -mtime +7 -delete
find $BACKUP_DIR -name "keys_backup_*.json" -mtime +7 -delete

echo "Backup completed: $DATE"
```

**Add to cron:**
```bash
# Daily backup at 1 AM
0 1 * * * /home/predictionleague/backup_database.sh
```

## Part 11: Troubleshooting

### 11.1 Common Issues

**Python Import Errors:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate
pip install missing_package
```

**Permission Errors:**
```bash
# Fix file permissions
chmod 755 ~/projects/prediction_league_script/scripts/**/*.py
chmod 600 ~/projects/prediction_league_script/keys.json
```

**Database Lock Errors:**
```bash
# Check for running processes
ps aux | grep python
# Kill if necessary
pkill -f "python.*prediction_league"
```

**Network/API Issues:**
```bash
# Test connectivity
curl -I https://fantasy.premierleague.com/api/
ping google.com
```

### 11.2 Service Health Checks

**Create health check script:**
```bash
vim ~/health_check.sh
```

**Health check content:**
```bash
#!/bin/bash
PROJECT_DIR="/home/predictionleague/projects/prediction_league_script"

echo "=== Health Check $(date) ==="

# Test database connectivity
echo "Testing database..."
cd $PROJECT_DIR
./venv/bin/python -c "
import sqlite3
try:
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM teams')
    print(f'✅ Database OK: {cursor.fetchone()[0]} teams')
    conn.close()
except Exception as e:
    print(f'❌ Database Error: {e}')
"

# Test API connectivity
echo "Testing APIs..."
curl -s -I https://fantasy.premierleague.com/api/ | head -n 1

# Check disk space
echo "Checking disk space..."
df -h $PROJECT_DIR | tail -n 1

# Check recent logs for errors
echo "Recent errors:"
tail -n 50 logs/*$(date +%Y%m%d).log 2>/dev/null | grep -i error | tail -n 5 || echo "No recent errors"
```

## Part 12: Final Deployment Checklist

### 12.1 Pre-Production Checklist

- [ ] VM created with adequate resources
- [ ] Ubuntu Server installed and updated
- [ ] SSH access configured and tested
- [ ] Git repository cloned successfully
- [ ] Python virtual environment created
- [ ] All dependencies installed
- [ ] keys.json configured with all API keys
- [ ] Dropbox OAuth2 setup completed
- [ ] All scripts tested individually
- [ ] Database connectivity verified
- [ ] Cron jobs configured and tested
- [ ] Log monitoring setup
- [ ] Firewall configured
- [ ] Backup strategy implemented

### 12.2 Go-Live Steps

1. **Final Testing:**
   ```bash
   # Test all systems end-to-end
   cd ~/projects/prediction_league_script
   ./venv/bin/python scripts/fpl/fetch_fixtures_gameweeks.py --test
   ./venv/bin/python scripts/fpl/fetch_results.py --test --dry-run  
   ./venv/bin/python scripts/prediction_league/clean_predictions_dropbox.py --dry-run
   ./venv/bin/python scripts/database/monitor_and_upload.py --test
   ```

2. **Enable Production Cron Jobs:**
   ```bash
   crontab -e
   # Remove --dry-run flags and enable all jobs
   ```

3. **Monitor Initial Operation:**
   ```bash
   # Watch logs for first few hours
   tail -f logs/database_monitor_$(date +%Y%m%d).log
   ```

4. **Set Up Monitoring Alerts** (optional):
   - Configure Pushover notifications for errors
   - Set up email alerts for system issues
   - Monitor disk space and memory usage

### 12.3 Success Validation

**Verify the following are working:**
- [ ] FPL data updates automatically
- [ ] Results processing works during match days
- [ ] Dropbox predictions are cleaned and processed
- [ ] Database uploads to PythonAnywhere successfully
- [ ] All logs are being generated properly
- [ ] No permission or connectivity errors
- [ ] Backup system is working

## Conclusion

This guide provides a complete deployment setup for the prediction league script system on Proxmox VM infrastructure. The system will run automatically with minimal manual intervention while providing comprehensive logging and monitoring capabilities.

For ongoing maintenance, monitor the logs regularly and ensure the system stays updated with security patches. The automated backup system ensures data safety, while the health check scripts help identify issues early.

**Key Benefits of This Setup:**
- ✅ Isolated VM environment
- ✅ Automated data processing
- ✅ Comprehensive error handling
- ✅ Secure configuration
- ✅ Easy backup and recovery
- ✅ Scalable resource allocation
- ✅ Production-ready monitoring