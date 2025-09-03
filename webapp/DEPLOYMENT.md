# Deployment Guide

## Quick Start

1. **Install Dependencies**
   ```bash
   cd webapp
   pip install -r requirements.txt
   ```

2. **Configure Settings**
   ```bash
   # Edit config.json with your settings
   cp config.json.example config.json
   nano config.json
   ```

3. **Run Development Server**
   ```bash
   python app.py
   ```

4. **Access Application**
   - Open browser to `http://localhost:5000`
   - Login with password from config.json (default: `admin123`)

## Production Deployment on Proxmox Ubuntu VM

### Option 1: Direct Python (Simplest)

1. **Create Service User**
   ```bash
   sudo adduser --system --group --home /opt/prediction-league predleague
   ```

2. **Install Application**
   ```bash
   sudo mkdir -p /opt/prediction-league
   sudo cp -r webapp/* /opt/prediction-league/
   sudo chown -R predleague:predleague /opt/prediction-league
   ```

3. **Install Python Dependencies**
   ```bash
   sudo -u predleague pip3 install -r /opt/prediction-league/requirements.txt
   ```

4. **Configure Settings**
   ```bash
   sudo -u predleague cp /opt/prediction-league/config.json.example /opt/prediction-league/config.json
   sudo -u predleague nano /opt/prediction-league/config.json
   ```

5. **Create Systemd Service**
   ```bash
   sudo nano /etc/systemd/system/prediction-league.service
   ```
   
   ```ini
   [Unit]
   Description=Prediction League Web Application
   After=network.target

   [Service]
   Type=simple
   User=predleague
   Group=predleague
   WorkingDirectory=/opt/prediction-league
   Environment=PYTHONPATH=/opt/prediction-league
   ExecStart=/usr/bin/python3 app.py
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```

6. **Enable and Start Service**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable prediction-league
   sudo systemctl start prediction-league
   sudo systemctl status prediction-league
   ```

### Option 2: With Nginx Reverse Proxy (Recommended)

1. **Follow steps 1-6 from Option 1**

2. **Configure App for Reverse Proxy**
   ```json
   {
     "host": "127.0.0.1",
     "port": 5001,
     "debug": false
   }
   ```

3. **Install and Configure Nginx**
   ```bash
   sudo apt update
   sudo apt install nginx
   ```

4. **Create Nginx Site**
   ```bash
   sudo nano /etc/nginx/sites-available/prediction-league
   ```
   
   ```nginx
   server {
       listen 80;
       server_name YOUR_VM_IP_OR_DOMAIN;

       location / {
           proxy_pass http://127.0.0.1:5001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static/ {
           alias /opt/prediction-league/static/;
           expires 1d;
           add_header Cache-Control "public, immutable";
       }
   }
   ```

5. **Enable Site**
   ```bash
   sudo ln -s /etc/nginx/sites-available/prediction-league /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

### Option 3: Docker Container (Advanced)

1. **Create Dockerfile**
   ```dockerfile
   FROM python:3.11-slim

   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt

   COPY . .
   
   EXPOSE 5000
   CMD ["python", "app.py"]
   ```

2. **Build and Run**
   ```bash
   docker build -t prediction-league .
   docker run -d \
     --name prediction-league \
     -p 5000:5000 \
     -v /path/to/your/data:/app/data \
     -v /path/to/your/scripts:/app/scripts \
     prediction-league
   ```

## Configuration Reference

### config.json Settings

```json
{
  "secret_key": "CHANGE-THIS-IN-PRODUCTION",
  "database_path": "../data/database.db",
  "scripts_path": "../scripts", 
  "venv_path": "../venv/bin/python",
  "admin_password": "CHANGE-THIS-PASSWORD",
  "host": "0.0.0.0",
  "port": 5000,
  "debug": false,
  "timezone": "Europe/London",
  "script_timeout": 300
}
```

### Security Recommendations

1. **Change Default Password**
   - Update `admin_password` in config.json
   - Use a strong, unique password

2. **Network Security**
   - Configure firewall to restrict access
   - Consider VPN access for remote management

3. **File Permissions**
   ```bash
   sudo chmod 600 /opt/prediction-league/config.json
   sudo chown predleague:predleague /opt/prediction-league/config.json
   ```

4. **Database Backup**
   ```bash
   # Create daily backup cron job
   sudo crontab -u predleague -e
   # Add: 0 2 * * * cp /path/to/data/database.db /path/to/backups/database-$(date +\%Y\%m\%d).db
   ```

## Monitoring and Maintenance

### Service Management
```bash
# Check status
sudo systemctl status prediction-league

# View logs
sudo journalctl -u prediction-league -f

# Restart service
sudo systemctl restart prediction-league
```

### Log Files
- Application logs: Check systemd journal
- Nginx logs: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- Database: Monitor disk space in data directory

### Updates
```bash
# Update application code
sudo systemctl stop prediction-league
sudo cp -r new-webapp-files/* /opt/prediction-league/
sudo chown -R predleague:predleague /opt/prediction-league
sudo systemctl start prediction-league
```

## Firewall Configuration

### Allow HTTP access
```bash
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
```

### Restrict by IP (recommended)
```bash
sudo ufw delete allow 80/tcp
sudo ufw allow from YOUR_NETWORK_RANGE to any port 80
# e.g., sudo ufw allow from 192.168.1.0/24 to any port 80
```

## Troubleshooting

### Common Issues

1. **Permission Denied**
   - Check file ownership: `sudo chown -R predleague:predleague /opt/prediction-league`
   - Check file permissions: `sudo chmod -R 755 /opt/prediction-league`

2. **Database Not Found**
   - Verify database path in config.json
   - Check database file exists and is readable

3. **Scripts Not Running**
   - Verify scripts_path in config.json
   - Check Python virtual environment path
   - Ensure scripts are executable

4. **Port Already in Use**
   - Change port in config.json
   - Check for other services: `sudo netstat -tulpn | grep :5000`

### Log Analysis
```bash
# Recent application logs
sudo journalctl -u prediction-league --since "1 hour ago"

# Follow logs in real-time
sudo journalctl -u prediction-league -f

# Check database connectivity
sudo -u predleague python3 -c "import sqlite3; print(sqlite3.connect('/path/to/database.db').execute('SELECT 1').fetchone())"
```

## Performance Optimization

### For High Usage
- Consider using Gunicorn instead of Flask dev server
- Implement database connection pooling
- Add Redis for session storage
- Use nginx for static file serving

### Example Gunicorn Setup
```bash
pip install gunicorn

# Update systemd service ExecStart:
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5001 app:app
```

This deployment guide covers the essentials for running the prediction league web app on your Proxmox Ubuntu VM with proper security and monitoring.