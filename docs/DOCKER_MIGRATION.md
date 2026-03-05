# Docker Migration Plan: Consolidating to One Server

## Table of Contents

- [Current Setup](#current-setup)
- [Target Architecture](#target-architecture)
- [Why Docker?](#why-docker)
- [Step-by-Step Migration Plan](#step-by-step-migration-plan)
  - [Phase 1: Prepare the New VM](#phase-1-prepare-the-new-vm)
  - [Phase 2: PostgreSQL Data Warehouse](#phase-2-postgresql-data-warehouse)
  - [Phase 3: Create Dockerfiles](#phase-3-create-dockerfiles)
  - [Phase 4: Docker Compose](#phase-4-docker-compose)
  - [Phase 5: Code Changes Required](#phase-5-code-changes-required)
  - [Phase 6: Data Migration](#phase-6-data-migration)
  - [Phase 7: DNS and Network Updates](#phase-7-dns-and-network-updates)
  - [Phase 8: Verification Checklist](#phase-8-verification-checklist)
- [Key Considerations](#key-considerations)
- [Maintenance Commands Quick Reference](#maintenance-commands-quick-reference)
- [Estimated Effort](#estimated-effort)
- [If Starting From Scratch](#if-starting-from-scratch)

---

## Current Setup

Three projects across two Proxmox VMs plus PythonAnywhere:

| | VM 1: Prediction League Scripts | VM 2: Betting Syndicate | PythonAnywhere: Predictions League v2 |
|---|---|---|---|
| **Purpose** | Data collection, automation, processing | Betting syndicate web app | Public predictions league website |
| **Python** | 3.12.3 | 3.12 | 3.x (PA managed) |
| **Framework** | Scripts + Flask webapp | FastAPI + Uvicorn + Nginx | Flask (Gunicorn/WSGI) |
| **Database** | SQLite (27 MB, `data/database.db`) | SQLite (`database/betting_syndicate.db`) | SQLite (`site/data/database.db`) |
| **Scheduling** | Cron + master_scheduler.sh (every minute) | None | None |
| **External APIs** | FPL, Odds API, Pulse, Football-Data, Dropbox | None | FPL API (read-only) |
| **Network** | Outbound (APIs, SFTP to PythonAnywhere) | Inbound HTTP (LAN + Tailscale) | Public internet |
| **Data Flow** | Collects data → writes to SQLite → SFTP uploads entire .db to PythonAnywhere | Standalone | Receives .db file from prediction league scripts |

**Current data flow problem:** The prediction league scripts collect all the data (fixtures, results, predictions, odds, FPL data) into a large SQLite database, then upload the entire 27 MB file to PythonAnywhere via SFTP. The predictions_league_v2 webapp on PythonAnywhere only needs a subset of that data (teams, fixtures, predictions, players, results). This is inefficient and tightly couples the two systems via a raw file copy.

---

## Target Architecture

One Proxmox VM running Docker with five containers, plus a PostgreSQL data warehouse as the central hub:

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Single Proxmox VM                              │
│                      (projects-server)                               │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      Docker Engine                             │  │
│  │                                                                │  │
│  │  ┌─────────────────┐     ┌──────────────────────────────────┐ │  │
│  │  │  postgres        │     │  prediction-league               │ │  │
│  │  │  (data warehouse)│     │  (scheduler + scripts)           │ │  │
│  │  │                  │◄────│                                  │ │  │
│  │  │  Port 5432       │     │  Collects from APIs              │ │  │
│  │  │                  │     │  Writes to PostgreSQL             │ │  │
│  │  │  Volume:         │     │  Volume: pl_keys, pl_logs        │ │  │
│  │  │   pg_data        │     └──────────────────────────────────┘ │  │
│  │  │                  │                                          │  │
│  │  │                  │     ┌──────────────────────────────────┐ │  │
│  │  │                  │     │  db-sync                         │ │  │
│  │  │                  │────►│  (PostgreSQL → PythonAnywhere)   │ │  │
│  │  │                  │     │                                  │ │  │
│  │  │                  │     │  Extracts relevant tables         │ │  │
│  │  │                  │     │  Builds SQLite for PA             │ │  │
│  │  │                  │     │  Uploads via SFTP                │ │  │
│  │  └─────────────────┘     └──────────────────────────────────┘ │  │
│  │                                                                │  │
│  │  ┌──────────────────────┐  ┌────────────────────────────────┐ │  │
│  │  │  betting-syndicate   │  │  nginx                         │ │  │
│  │  │  FastAPI + Uvicorn   │  │  (reverse proxy)               │ │  │
│  │  │  Port 8001 internal  │  │  Port 80 → host                │ │  │
│  │  │                      │  │                                │ │  │
│  │  │  Volume:             │  │  betting.local → :8001         │ │  │
│  │  │   betting_data       │  │  predictions.local → :5000     │ │  │
│  │  │   betting_uploads    │  │  (optional Flask webapp)        │ │  │
│  │  └──────────────────────┘  └────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Tailscale (on host VM)                                              │
└──────────────────────────────────────────────────────────────────────┘

                              │
                              │ SFTP (subset SQLite)
                              ▼
                    ┌──────────────────┐
                    │  PythonAnywhere   │
                    │  predictions_     │
                    │  league_v2        │
                    │  (Flask webapp)   │
                    └──────────────────┘
```

### Data Flow (New)

```
External APIs (FPL, Odds, Pulse, Football-Data, Dropbox)
        │
        ▼
  prediction-league container
  (collects & processes data)
        │
        ▼
  PostgreSQL container (data warehouse)
  ┌─────────────────────────────────────┐
  │  All raw + processed data           │
  │  - fixtures, results, teams         │
  │  - predictions, players             │
  │  - odds, FPL data, pulse data       │
  │  - football_stats (historical)      │
  │  - betting syndicate (future?)      │
  └─────────────────────────────────────┘
        │
        ▼
  db-sync container (runs periodically)
  ┌─────────────────────────────────────┐
  │  1. Query PostgreSQL for relevant   │
  │     tables (teams, fixtures,        │
  │     predictions, players, results)  │
  │  2. Build minimal SQLite file       │
  │  3. Upload to PythonAnywhere        │
  └─────────────────────────────────────┘
        │
        ▼
  PythonAnywhere (predictions_league_v2)
  Serves the public predictions website
  using the synced SQLite database
```

---

## Why Docker?

- **Resource efficiency** — One VM instead of two, lower memory and CPU overhead
- **Isolation** — Each project in its own container, independent dependencies
- **Reproducibility** — `docker compose up` rebuilds the entire stack
- **Easier backups** — Named volumes in one place
- **Simpler updates** — Rebuild a single container without touching the other
- **No venv management** — Dependencies baked into images
- **PostgreSQL as central hub** — Proper database with concurrent access, migrations, and future extensibility

---

## Step-by-Step Migration Plan

### Phase 1: Prepare the New VM

#### 1.1 Create a New Proxmox VM

| Setting | Value |
|---------|-------|
| Name | `projects-server` |
| OS | Ubuntu Server 24.04 LTS |
| CPU | 2 cores (4 recommended) |
| RAM | 4 GB (combines both VMs, PostgreSQL needs ~256 MB) |
| Disk | 40 GB |
| Network | Bridge `vmbr0` |

#### 1.2 Install Docker on the VM

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

#### 1.3 Install Tailscale (for remote access)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

#### 1.4 Create Project Directory Structure

```bash
sudo mkdir -p /opt/projects
cd /opt/projects

mkdir -p prediction-league/keys
mkdir -p betting-syndicate/database
mkdir -p betting-syndicate/uploads/screenshots
mkdir -p db-sync
mkdir -p nginx/conf.d
mkdir -p postgres/init
mkdir -p backups
```

---

### Phase 2: PostgreSQL Data Warehouse

This is the biggest architectural change. Instead of SQLite files being passed around, PostgreSQL becomes the single source of truth for all collected data.

#### 2.1 Why PostgreSQL Instead of Keeping SQLite

| SQLite (current) | PostgreSQL (proposed) |
|---|---|
| Single-writer, file-level locking | Multiple concurrent connections |
| No network access — must copy entire file | Containers connect over Docker network |
| 27 MB file uploaded to PythonAnywhere every change | Only changed data synced |
| No schema migrations tooling | Built-in with alembic or plain SQL |
| Each project has its own copy of overlapping data | Single source of truth |
| No access control | Role-based access per container |

#### 2.2 Database Schema Design

The PostgreSQL warehouse mirrors the existing prediction_league_script tables, organised into schemas:

```sql
-- Schema for prediction league data (the core data collection)
CREATE SCHEMA predictions;

-- Core reference tables
CREATE TABLE predictions.teams (
    team_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    fpl_code INTEGER,
    odds_api_name TEXT,
    pulse_id INTEGER
);

CREATE TABLE predictions.fixtures (
    fixture_id INTEGER PRIMARY KEY,
    gameweek INTEGER NOT NULL,
    season TEXT NOT NULL,
    home_teamid INTEGER REFERENCES predictions.teams(team_id),
    away_teamid INTEGER REFERENCES predictions.teams(team_id),
    kickoff_dttm TIMESTAMP,
    home_score INTEGER,
    away_score INTEGER,
    result_code TEXT,
    fpl_fixture_id INTEGER
);

CREATE TABLE predictions.players (
    player_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    active BOOLEAN DEFAULT true
);

CREATE TABLE predictions.predictions (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES predictions.players(player_id),
    fixture_id INTEGER REFERENCES predictions.fixtures(fixture_id),
    home_pred INTEGER,
    away_pred INTEGER,
    points INTEGER DEFAULT 0,
    submitted_dttm TIMESTAMP,
    UNIQUE(player_id, fixture_id)
);

CREATE TABLE predictions.gameweeks (
    id SERIAL PRIMARY KEY,
    gameweek INTEGER NOT NULL,
    season TEXT NOT NULL,
    deadline_dttm TIMESTAMP,
    is_current BOOLEAN DEFAULT false,
    UNIQUE(gameweek, season)
);

-- Odds and analysis data
CREATE TABLE predictions.odds (
    id SERIAL PRIMARY KEY,
    fixture_id INTEGER REFERENCES predictions.fixtures(fixture_id),
    bookmaker TEXT,
    market TEXT,
    home_odds NUMERIC,
    draw_odds NUMERIC,
    away_odds NUMERIC,
    last_updated TIMESTAMP
);

CREATE TABLE predictions.fixture_odds_summary (
    fixture_id INTEGER PRIMARY KEY REFERENCES predictions.fixtures(fixture_id),
    avg_home_odds NUMERIC,
    avg_draw_odds NUMERIC,
    avg_away_odds NUMERIC,
    num_bookmakers INTEGER,
    last_updated TIMESTAMP
);

-- FPL data (large tables, kept for analysis)
CREATE TABLE predictions.fpl_players_bootstrap (
    id INTEGER PRIMARY KEY,
    season TEXT NOT NULL,
    data JSONB  -- Store the 94-column FPL data as JSONB for flexibility
);

CREATE TABLE predictions.football_stats (
    id SERIAL PRIMARY KEY,
    season TEXT,
    date DATE,
    home_team TEXT,
    away_team TEXT,
    home_score INTEGER,
    away_score INTEGER,
    data JSONB  -- Flexible storage for 30+ years of varied CSV columns
);

-- Tracking table
CREATE TABLE predictions.last_update (
    table_name TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    updated_by TEXT
);

-- Future: betting syndicate could also use schemas
-- CREATE SCHEMA betting;
-- (tables for ledger, bets, seasons, players, etc.)
```

#### 2.3 Initialisation Script

Create `/opt/projects/postgres/init/01-init.sql`:

This file runs automatically when the PostgreSQL container starts for the first time. It creates the schemas and tables above.

#### 2.4 PostgreSQL Configuration

The PostgreSQL container uses environment variables for setup:

```yaml
environment:
  POSTGRES_USER: projects
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # Set in .env file
  POSTGRES_DB: datawarehouse
```

Credentials stored in `/opt/projects/.env` (never committed):
```bash
POSTGRES_PASSWORD=your-secure-password-here
```

---

### Phase 3: Create Dockerfiles

#### 3.1 Prediction League Dockerfile

Create `/opt/projects/prediction-league/Dockerfile`:

```dockerfile
FROM python:3.12-slim

# Install cron and system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
COPY webapp/requirements.txt ./webapp_requirements.txt
# Add psycopg2 for PostgreSQL connectivity
RUN pip install --no-cache-dir -r requirements.txt -r webapp_requirements.txt psycopg2-binary

# Copy application code
COPY . .

# Remove venv (not needed in container)
RUN rm -rf venv/

# Create log directories
RUN mkdir -p /app/logs/scheduler

# Copy the crontab file
COPY docker/crontab /etc/cron.d/prediction-league
RUN chmod 0644 /etc/cron.d/prediction-league && crontab /etc/cron.d/prediction-league

# Expose Flask port
EXPOSE 5000

# Start cron and Flask
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
```

#### 3.2 Prediction League Entrypoint Script

Create `/opt/projects/prediction-league/docker/entrypoint.sh`:

```bash
#!/bin/bash
set -e

# Export env vars for cron (cron doesn't inherit environment)
printenv | grep -v "no_proxy" >> /etc/environment

# Start cron daemon in background
cron

# Start the Flask webapp (or just keep container alive if webapp not needed)
cd /app
exec python -m flask --app webapp/app.py run --host 0.0.0.0 --port 5000
```

#### 3.3 Prediction League Crontab

Create `/opt/projects/prediction-league/docker/crontab`:

```cron
# Master scheduler - runs every minute
* * * * * /bin/bash /app/scripts/scheduler/master_scheduler.sh >> /app/logs/scheduler/cron_output.log 2>&1
```

> **Note:** The master_scheduler.sh references `venv/bin/python` in several places. These paths need updating. See [Phase 5: Code Changes](#phase-5-code-changes-required).

#### 3.4 Betting Syndicate Dockerfile

Create `/opt/projects/betting-syndicate/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Remove venv
RUN rm -rf venv/

# Create required directories
RUN mkdir -p /app/uploads/screenshots /app/database

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

#### 3.5 Database Sync Container

This is a new lightweight container that reads from PostgreSQL and syncs a subset to PythonAnywhere.

Create `/opt/projects/db-sync/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
```

Create `/opt/projects/db-sync/requirements.txt`:

```
psycopg2-binary>=2.9.0
paramiko>=2.9.0
```

Create `/opt/projects/db-sync/entrypoint.sh`:

```bash
#!/bin/bash
# Run sync every 2 minutes
while true; do
    python /app/sync.py
    sleep 120
done
```

Create `/opt/projects/db-sync/sync.py`:

```python
"""
Sync relevant data from PostgreSQL warehouse to PythonAnywhere SQLite.

This replaces the old monitor_and_upload.py approach of uploading the
entire 27 MB SQLite file. Instead it:
1. Queries PostgreSQL for only the tables predictions_league_v2 needs
2. Builds a minimal SQLite file
3. Compares checksums to detect changes
4. Uploads only when data has changed
"""

import os
import json
import sqlite3
import hashlib
import logging
import tempfile
from datetime import datetime

import psycopg2
import psycopg2.extras
import paramiko

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config from environment
PG_HOST = os.environ.get("POSTGRES_HOST", "postgres")
PG_DB = os.environ.get("POSTGRES_DB", "datawarehouse")
PG_USER = os.environ.get("POSTGRES_USER", "projects")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "")

PA_HOST = os.environ.get("PA_HOST", "ssh.pythonanywhere.com")
PA_USER = os.environ.get("PA_USERNAME", "")
PA_PASS = os.environ.get("PA_PASSWORD", "")
PA_REMOTE_PATH = os.environ.get("PA_REMOTE_DB_PATH", "")

CHECKSUM_FILE = "/app/last_checksum.txt"


def get_pg_connection():
    return psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASS)


def build_sqlite(output_path):
    """Build a SQLite database with only the tables predictions_league_v2 needs."""
    conn_pg = get_pg_connection()
    conn_sqlite = sqlite3.connect(output_path)

    try:
        pg_cur = conn_pg.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sq_cur = conn_sqlite.cursor()

        # Teams
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                short_name TEXT, code TEXT
            )
        """)
        pg_cur.execute("SELECT team_id, name, short_name, fpl_code FROM predictions.teams")
        for row in pg_cur.fetchall():
            sq_cur.execute("INSERT OR REPLACE INTO teams VALUES (?,?,?,?)",
                           (row['team_id'], row['name'], row['short_name'], str(row['fpl_code'] or '')))

        # Fixtures
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                id INTEGER PRIMARY KEY, gameweek INTEGER NOT NULL,
                season TEXT NOT NULL, home_team_id INTEGER, away_team_id INTEGER,
                kickoff TEXT, home_score INTEGER, away_score INTEGER, status TEXT
            )
        """)
        pg_cur.execute("""
            SELECT fixture_id, gameweek, season, home_teamid, away_teamid,
                   kickoff_dttm, home_score, away_score, result_code
            FROM predictions.fixtures
        """)
        for row in pg_cur.fetchall():
            status = 'finished' if row['home_score'] is not None else 'scheduled'
            sq_cur.execute("INSERT OR REPLACE INTO fixtures VALUES (?,?,?,?,?,?,?,?,?)",
                           (row['fixture_id'], row['gameweek'], row['season'],
                            row['home_teamid'], row['away_teamid'],
                            str(row['kickoff_dttm']) if row['kickoff_dttm'] else None,
                            row['home_score'], row['away_score'], status))

        # Players
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                active INTEGER DEFAULT 1
            )
        """)
        pg_cur.execute("SELECT player_id, name, active FROM predictions.players")
        for row in pg_cur.fetchall():
            sq_cur.execute("INSERT OR REPLACE INTO players VALUES (?,?,?)",
                           (row['player_id'], row['name'], 1 if row['active'] else 0))

        # Predictions
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY, player_id INTEGER, fixture_id INTEGER,
                home_prediction INTEGER, away_prediction INTEGER, points INTEGER DEFAULT 0,
                submitted_date TEXT,
                UNIQUE(player_id, fixture_id)
            )
        """)
        pg_cur.execute("""
            SELECT id, player_id, fixture_id, home_pred, away_pred, points, submitted_dttm
            FROM predictions.predictions
        """)
        for row in pg_cur.fetchall():
            sq_cur.execute("INSERT OR REPLACE INTO predictions VALUES (?,?,?,?,?,?,?)",
                           (row['id'], row['player_id'], row['fixture_id'],
                            row['home_pred'], row['away_pred'], row['points'],
                            str(row['submitted_dttm']) if row['submitted_dttm'] else None))

        # Last update
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS last_update (
                id INTEGER PRIMARY KEY, table_name TEXT UNIQUE,
                last_updated TEXT, updated_by TEXT
            )
        """)
        sq_cur.execute("INSERT OR REPLACE INTO last_update (table_name, last_updated, updated_by) VALUES (?,?,?)",
                       ("database", datetime.now().isoformat(), "db-sync"))

        # Indexes
        sq_cur.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_gw_season ON fixtures(gameweek, season)")
        sq_cur.execute("CREATE INDEX IF NOT EXISTS idx_pred_player_fixture ON predictions(player_id, fixture_id)")
        sq_cur.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_season ON fixtures(season)")

        conn_sqlite.commit()
    finally:
        conn_pg.close()
        conn_sqlite.close()


def file_checksum(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_to_pythonanywhere(local_path):
    transport = paramiko.Transport((PA_HOST, 22))
    transport.connect(username=PA_USER, password=PA_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        sftp.put(local_path, PA_REMOTE_PATH)
        logger.info(f"Uploaded to PythonAnywhere: {PA_REMOTE_PATH}")
    finally:
        sftp.close()
        transport.close()


def main():
    if not PA_USER or not PA_PASS:
        logger.warning("PythonAnywhere credentials not set, skipping sync")
        return

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        build_sqlite(tmp_path)
        new_checksum = file_checksum(tmp_path)

        old_checksum = ""
        if os.path.exists(CHECKSUM_FILE):
            with open(CHECKSUM_FILE) as f:
                old_checksum = f.read().strip()

        if new_checksum != old_checksum:
            logger.info(f"Data changed (checksum {old_checksum[:8]}... → {new_checksum[:8]}...), uploading")
            upload_to_pythonanywhere(tmp_path)
            with open(CHECKSUM_FILE, "w") as f:
                f.write(new_checksum)
        else:
            logger.debug("No data changes detected, skipping upload")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()
```

#### 3.6 Nginx Configuration

Create `/opt/projects/nginx/conf.d/default.conf`:

```nginx
# Betting Syndicate - primary web app
server {
    listen 80;
    server_name betting.local;

    client_max_body_size 10M;

    location / {
        proxy_pass http://betting-syndicate:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Prediction League webapp (optional, if you want local web access)
server {
    listen 80;
    server_name predictions.local;

    location / {
        proxy_pass http://prediction-league:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### Phase 4: Docker Compose

Create `/opt/projects/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: projects
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: datawarehouse
      TZ: Europe/London
    volumes:
      - pg-data:/var/lib/postgresql/data
      - ./postgres/init:/docker-entrypoint-initdb.d:ro
    ports:
      - "127.0.0.1:5432:5432"  # Only accessible from host, not LAN
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U projects -d datawarehouse"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  prediction-league:
    build:
      context: ./prediction-league
      dockerfile: Dockerfile
    container_name: prediction-league
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - pl-logs:/app/logs
      - pl-samples:/app/samples
      # Mount keys file from host (sensitive, not baked into image)
      - ./prediction-league/keys/keys.json:/app/keys.json:rw
    environment:
      - TZ=Europe/London
      - PYTHONUNBUFFERED=1
      - PYTHON_CMD=python
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=datawarehouse
      - POSTGRES_USER=projects
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    networks:
      - app-network

  db-sync:
    build:
      context: ./db-sync
      dockerfile: Dockerfile
    container_name: db-sync
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./prediction-league/keys/keys.json:/app/keys.json:ro
    environment:
      - TZ=Europe/London
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=datawarehouse
      - POSTGRES_USER=projects
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - PA_USERNAME=${PA_USERNAME}
      - PA_PASSWORD=${PA_PASSWORD}
      - PA_REMOTE_DB_PATH=${PA_REMOTE_DB_PATH}
    networks:
      - app-network

  betting-syndicate:
    build:
      context: ./betting-syndicate
      dockerfile: Dockerfile
    container_name: betting-syndicate
    restart: unless-stopped
    volumes:
      - betting-data:/app/database
      - betting-uploads:/app/uploads
    environment:
      - TZ=Europe/London
      - PYTHONUNBUFFERED=1
    networks:
      - app-network

  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - betting-uploads:/opt/uploads:ro
    depends_on:
      - betting-syndicate
      - prediction-league
    networks:
      - app-network

volumes:
  pg-data:
  pl-logs:
  pl-samples:
  betting-data:
  betting-uploads:

networks:
  app-network:
    driver: bridge
```

Create `/opt/projects/.env`:

```bash
# PostgreSQL
POSTGRES_PASSWORD=change-this-to-a-secure-password

# PythonAnywhere (for db-sync container)
PA_USERNAME=your-pythonanywhere-username
PA_PASSWORD=your-pythonanywhere-password
PA_REMOTE_DB_PATH=/home/yourusername/mysite/site/data/database.db
```

---

### Phase 5: Code Changes Required

#### 5.1 Prediction League: Remove venv Path References

The `master_scheduler.sh` script uses `./venv/bin/python` to run scripts. In Docker, Python is the system Python.

**Approach:** Use an environment variable so it works both locally and in Docker:

```bash
# Add near the top of master_scheduler.sh
PYTHON_CMD="${PYTHON_CMD:-./venv/bin/python}"
```

Then replace all `./venv/bin/python` with `$PYTHON_CMD` throughout the file.

The Docker entrypoint already sets `PYTHON_CMD=python` via the environment.

#### 5.2 Prediction League: Migrate Scripts to Write to PostgreSQL

This is the most significant code change. Each data collection script currently writes to SQLite — they need adapting to write to PostgreSQL instead.

**Migration approach (incremental, not big-bang):**

1. Create a shared database utility module `scripts/db.py`:

```python
"""
Database connection factory.
Supports both SQLite (local dev) and PostgreSQL (Docker).
"""
import os
import sqlite3

def get_connection():
    pg_host = os.environ.get("POSTGRES_HOST")
    if pg_host:
        import psycopg2
        return psycopg2.connect(
            host=pg_host,
            dbname=os.environ.get("POSTGRES_DB", "datawarehouse"),
            user=os.environ.get("POSTGRES_USER", "projects"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
        )
    else:
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "data" / "database.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
```

2. Update scripts one at a time to use `from scripts.db import get_connection` instead of direct `sqlite3.connect(...)` calls.

3. Handle SQL dialect differences:
   - SQLite uses `?` for placeholders, PostgreSQL uses `%s`
   - SQLite uses `datetime()`, PostgreSQL uses `TIMESTAMP`
   - SQLite has `INSERT OR REPLACE`, PostgreSQL uses `INSERT ... ON CONFLICT DO UPDATE`

**Recommended phased approach:**
- **Phase A:** Run prediction-league container with SQLite as-is (no PostgreSQL dependency)
- **Phase B:** Add PostgreSQL, create a separate migration script that copies SQLite → PostgreSQL nightly
- **Phase C:** Gradually convert scripts to write directly to PostgreSQL
- **Phase D:** Remove SQLite dependency from prediction-league container

Phase A gets you running on Docker quickly. Phases B-D can happen over weeks/months.

#### 5.3 Prediction League: Remove PythonAnywhere Upload from monitor_and_upload.py

Once the db-sync container handles PythonAnywhere uploads, the SFTP logic in `monitor_and_upload.py` becomes redundant. You can either:
- Disable the upload portion (keep the monitoring for local database health)
- Remove the script entirely and rely on db-sync

#### 5.4 Prediction League: keys.json and Dropbox OAuth

`clean_predictions_dropbox.py` reads/writes tokens to `keys.json`. The file is mounted read-write in docker-compose so this works. **No change needed.**

#### 5.5 Betting Syndicate: Database Path

The database path in `app/database.py` resolves to `/app/database/` in the container, which is the mounted volume. **No change needed.**

#### 5.6 Betting Syndicate: fetch_db.sh / push_db.sh

Replace with `docker cp` commands:

```bash
# Fetch database from container
docker cp betting-syndicate:/app/database/betting_syndicate.db ./database/

# Push database to container
docker cp ./database/betting_syndicate.db betting-syndicate:/app/database/
docker compose restart betting-syndicate
```

---

### Phase 6: Data Migration

#### 6.1 Backup Everything First

```bash
# On Prediction League VM
cp data/database.db data/database_pre_migration.db
cp keys.json keys_pre_migration.json

# On Betting Syndicate VM
cp /opt/betting-syndicate/database/betting_syndicate.db ~/betting_syndicate_pre_migration.db

# On PythonAnywhere (via SSH)
cp ~/mysite/site/data/database.db ~/database_pre_migration.db
```

#### 6.2 Transfer Code and Data to New VM

```bash
# Prediction League
scp -r prediction-league-vm:~/prediction_league_script/* projects-server:/opt/projects/prediction-league/
ssh projects-server "rm -rf /opt/projects/prediction-league/venv"
scp prediction-league-vm:~/prediction_league_script/keys.json projects-server:/opt/projects/prediction-league/keys/

# Betting Syndicate
scp -r betting-vm:/opt/betting-syndicate/* projects-server:/opt/projects/betting-syndicate/
ssh projects-server "rm -rf /opt/projects/betting-syndicate/venv"
```

#### 6.3 Migrate SQLite Data into PostgreSQL

After starting the stack for the first time, load the existing SQLite data into PostgreSQL:

```bash
# Copy the SQLite database into the prediction-league container
docker cp /opt/projects/prediction-league/data/database.db prediction-league:/tmp/old_database.db

# Run migration script inside the container
docker exec prediction-league python /app/scripts/database/migrate_to_postgres.py
```

You'll need to write `migrate_to_postgres.py` — a one-time script that reads the SQLite tables and inserts into PostgreSQL. This is straightforward since the schemas are similar.

#### 6.4 Verify PythonAnywhere Sync

```bash
# Check db-sync logs
docker logs db-sync

# Verify the SQLite on PythonAnywhere has data
# (SSH to PythonAnywhere)
sqlite3 ~/mysite/site/data/database.db "SELECT COUNT(*) FROM fixtures WHERE season='2025/2026';"
```

---

### Phase 7: DNS and Network Updates

#### 7.1 Update Local DNS

Update your router/hosts file to point to the new VM:
```
192.168.1.60  betting.local
192.168.1.60  predictions.local
```

#### 7.2 Update Tailscale

Install and authenticate on the new VM. Update bookmarks and MagicDNS entries.

#### 7.3 Firewall

```bash
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp
sudo ufw allow in on tailscale0
sudo ufw enable
```

Note: PostgreSQL port 5432 is bound to `127.0.0.1` only — not exposed to the network.

---

### Phase 8: Verification Checklist

#### PostgreSQL
- [ ] Database is running: `docker exec postgres pg_isready`
- [ ] Schemas created: `docker exec postgres psql -U projects -d datawarehouse -c "\dn"`
- [ ] Data migrated: check row counts in key tables

#### Prediction League
- [ ] Scheduler is running (`docker logs prediction-league`)
- [ ] `fetch_results.py` executes every minute
- [ ] Scripts are writing to PostgreSQL (or SQLite during Phase A)
- [ ] Dropbox predictions sync works
- [ ] Flask webapp loads at `http://predictions.local` (if enabled)

#### Database Sync
- [ ] db-sync container is running (`docker logs db-sync`)
- [ ] SQLite is being built from PostgreSQL
- [ ] Changes are detected and uploaded to PythonAnywhere
- [ ] predictions_league_v2 on PythonAnywhere shows correct data

#### Betting Syndicate
- [ ] Dashboard loads at `http://betting.local`
- [ ] Can create/edit bets with screenshot uploads
- [ ] Ledger entries preserved from migration
- [ ] Season data intact

#### General
- [ ] All containers restart after VM reboot (`docker compose up -d` in systemd or cron `@reboot`)
- [ ] Tailscale access works from external devices
- [ ] Logs are persisting in volumes
- [ ] Backups are running

---

## Key Considerations

### 1. PostgreSQL and Docker Volumes

- PostgreSQL data lives in the `pg-data` named volume
- **Backup strategy:**

```bash
# Add to host crontab — daily PostgreSQL dump
0 3 * * * docker exec postgres pg_dump -U projects datawarehouse | gzip > /opt/backups/postgres_$(date +\%Y\%m\%d).sql.gz

# Keep 14 days of backups
0 4 * * * find /opt/backups -name "postgres_*.sql.gz" -mtime +14 -delete
```

### 2. Cron Inside Docker

Running cron inside a container has quirks:
- Cron doesn't inherit environment variables — the entrypoint exports them to `/etc/environment`
- If cron fails silently, check `docker logs prediction-league`

**Alternative:** Run cron on the **host VM** and use `docker exec`:
```cron
* * * * * docker exec prediction-league bash /app/scripts/scheduler/master_scheduler.sh
```
Simpler and more visible, but couples the host to the container.

### 3. Timezone

All containers set `TZ=Europe/London` for correct BST/GMT handling. PostgreSQL also respects this for `TIMESTAMP WITH TIME ZONE` columns.

### 4. Container Resource Limits

Optional but recommended:

```yaml
# Add to each service in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '1.0'
```

PostgreSQL is fine with 256 MB for this workload. The prediction-league container spikes briefly during API calls. Betting-syndicate is lightweight.

### 5. Secrets Management

- `.env` file on host holds PostgreSQL password and PythonAnywhere credentials
- `keys.json` mounted from host filesystem
- Add both to `.dockerignore`
- Set file permissions: `chmod 600 /opt/projects/.env`

### 6. Updating Code

```bash
cd /opt/projects

# Pull latest (if using git)
cd prediction-league && git pull && cd ..
cd betting-syndicate && git pull && cd ..

# Rebuild and restart
docker compose build
docker compose up -d
```

### 7. Log Management

```json
// /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

App-level logs persist in the `pl-logs` volume with the existing 30-day retention.

### 8. SQLite for Betting Syndicate

The betting-syndicate stays on SQLite — it's a standalone single-user app and doesn't need PostgreSQL. If you wanted to centralise it later, you could add a `betting` schema to PostgreSQL and adapt the FastAPI app to use SQLAlchemy's PostgreSQL dialect (it already uses SQLAlchemy, so the change would be minimal — just swap the connection string).

### 9. What Happens to the Old VMs

1. Keep old VMs powered off for 2-4 weeks as a safety net
2. Take Proxmox snapshots before deleting
3. Delete when confident everything works

---

## Maintenance Commands Quick Reference

```bash
# Start everything
cd /opt/projects && docker compose up -d

# Stop everything
docker compose down

# View logs
docker logs -f prediction-league
docker logs -f db-sync
docker logs -f betting-syndicate

# Restart a single service
docker compose restart betting-syndicate

# Rebuild after code change
docker compose build && docker compose up -d

# Shell into a container
docker exec -it prediction-league bash
docker exec -it betting-syndicate bash

# PostgreSQL shell
docker exec -it postgres psql -U projects -d datawarehouse

# Check PostgreSQL data
docker exec postgres psql -U projects -d datawarehouse -c "SELECT table_name FROM predictions.last_update ORDER BY timestamp DESC;"

# Backup PostgreSQL
docker exec postgres pg_dump -U projects datawarehouse > backup.sql

# Backup betting syndicate SQLite
docker cp betting-syndicate:/app/database/betting_syndicate.db ./backups/

# Check disk usage
docker system df

# View all container status
docker compose ps
```

---

## Estimated Effort

| Task | Time |
|------|------|
| VM setup + Docker install | 30 min |
| PostgreSQL schema + init scripts | 1-2 hours |
| Write Dockerfiles + compose + db-sync | 2-3 hours |
| Code changes (venv paths, PYTHON_CMD) | 30 min |
| Data migration (SQLite → PostgreSQL) | 1-2 hours |
| Testing + verification | 2-3 hours |
| DNS/network updates | 15 min |
| **Total (Phase A — Docker with SQLite as-is)** | **~4-5 hours** |
| **Total (Full — including PostgreSQL migration)** | **~8-12 hours** |

**Recommended approach:** Do Phase A first (Docker without PostgreSQL), get everything stable, then migrate to PostgreSQL over the following weeks.

---

## If Starting From Scratch

If this were a greenfield project with the benefit of hindsight, here's what I'd do differently across the entire stack.

### 1. PostgreSQL From Day One, No SQLite

SQLite was a good starting point for simplicity, but it became a bottleneck once multiple systems needed the same data. Starting with PostgreSQL means:
- No file-level locking issues
- No need to SFTP entire database files around
- Proper concurrent access from multiple scripts
- Real schema migrations with Alembic
- JSONB columns for semi-structured API data (FPL player data with 94 columns is a perfect JSONB use case)
- PythonAnywhere could connect to a hosted PostgreSQL instance (e.g. Supabase free tier, or Railway) instead of receiving SQLite files

### 2. One Repository, Monorepo Structure

Instead of three separate projects (`prediction_league_script`, `betting_syndicate`, `predictions_league_v2`), a single monorepo:

```
football-projects/
├── docker-compose.yml
├── services/
│   ├── data-collector/        # What prediction_league_script is now
│   │   ├── Dockerfile
│   │   ├── scripts/
│   │   └── requirements.txt
│   ├── predictions-web/       # What predictions_league_v2 is now
│   │   ├── Dockerfile
│   │   ├── app/
│   │   └── requirements.txt
│   ├── betting-syndicate/     # What betting_syndicate is now
│   │   ├── Dockerfile
│   │   ├── app/
│   │   └── requirements.txt
│   └── db-sync/               # Sync service
├── shared/
│   ├── models.py              # Shared SQLAlchemy models
│   ├── db.py                  # Shared database connection
│   └── config.py              # Shared configuration
├── migrations/                # Alembic migrations for PostgreSQL
├── .env.example
└── docs/
```

Benefits:
- Shared database models — define a table once, use everywhere
- Single `docker compose up` for the entire stack
- Coordinated releases and schema changes
- One CI/CD pipeline

### 3. Proper ORM Everywhere (SQLAlchemy)

The prediction_league_script uses raw `sqlite3` queries with string manipulation. The betting_syndicate already uses SQLAlchemy. I'd standardise on SQLAlchemy for everything:
- Shared model definitions across services
- Database-agnostic code (works with SQLite in dev, PostgreSQL in prod)
- Alembic for schema migrations instead of ad-hoc migration scripts
- No more hand-written `CREATE TABLE` statements scattered across files

### 4. Environment-Based Configuration, Not keys.json

Replace `keys.json` with environment variables everywhere:
- Docker Compose `.env` file for local dev
- Environment variables in production
- No file-based secrets to mount, copy, or chmod
- Works naturally with Docker, CI/CD, and cloud platforms

### 5. Proper Task Queue Instead of Cron + Shell Scripts

Replace the master_scheduler.sh + cron approach with a lightweight task scheduler:

**Option A: Celery + Redis** (heavier but battle-tested)
```python
@celery.task
def fetch_results():
    ...

celery.conf.beat_schedule = {
    'fetch-results': {'task': 'fetch_results', 'schedule': 60.0},
    'fetch-fixtures': {'task': 'fetch_fixtures', 'schedule': 1800.0},
}
```

**Option B: APScheduler** (lightweight, no Redis dependency)
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_results, 'interval', seconds=60)
scheduler.add_job(fetch_fixtures, 'interval', minutes=30)
scheduler.start()
```

Benefits over cron:
- No shell scripts, lock files, or sleep delays
- Built-in retry and error handling
- Visible job status and history
- Runs inside the Python process, no cron environment issues in Docker

### 6. API-First Architecture for Data Access

Instead of each webapp directly querying the database, expose a lightweight REST API from the data layer:

```
data-collector → PostgreSQL ← data-api (FastAPI)
                                  ↑
                    predictions-web queries this
                    betting-syndicate queries this (optionally)
```

This means:
- predictions_league_v2 on PythonAnywhere could call the API instead of needing a local database
- Any new project can access the data without knowing the schema
- Rate limiting, caching, and auth in one place

### 7. Containerised From the Start

No virtual environments, no `venv/bin/python` paths, no system-level cron. Everything in Docker from the beginning:
- `docker compose up` to run locally
- Same containers deploy to production
- No "works on my machine" issues
- Easy to add new services later

### 8. Self-Hosted predictions_league_v2 Instead of PythonAnywhere

PythonAnywhere is convenient but adds complexity:
- SFTP file transfers
- Limited Python version control
- Can't run background tasks
- SQLite file size limits

Self-hosting predictions_league_v2 in Docker on the same VM would mean:
- Direct PostgreSQL connection (no file sync needed)
- Full control over Python version and dependencies
- Tailscale for remote access instead of public hosting
- The db-sync container becomes unnecessary entirely

If public internet access is needed, a Cloudflare Tunnel or Tailscale Funnel can expose the service without port forwarding.

### 9. Structured Logging (JSON)

Instead of daily log files with `logging.basicConfig`:

```python
import structlog
logger = structlog.get_logger()
logger.info("fetch_complete", fixtures_count=380, duration_ms=1200)
```

JSON logs can be aggregated across containers with `docker compose logs` and searched easily. No more `tail -f logs/fetch_results_20260219.log`.

### 10. Tests for Data Pipelines

The current scripts have no automated tests — they're tested manually with `--test` flags and sample data. From scratch, I'd add:
- Unit tests for data transformation functions
- Integration tests that spin up a test PostgreSQL container
- A CI pipeline that runs tests on every push
- Sample data fixtures in the repo (not gitignored)

### Summary: Greenfield Stack

| Layer | Current | From Scratch |
|-------|---------|-------------|
| Database | 3x SQLite files, SFTP sync | PostgreSQL (single instance) |
| Repository | 3 separate repos | Monorepo |
| ORM | Raw sqlite3 + SQLAlchemy (mixed) | SQLAlchemy everywhere |
| Configuration | keys.json + .env (mixed) | Environment variables only |
| Scheduling | Cron + bash + lock files | APScheduler or Celery |
| Data access | Direct DB queries per app | REST API layer |
| Deployment | VMs + venv + systemd | Docker from day one |
| Hosting | PythonAnywhere + Proxmox VMs | Single Docker host + Tailscale |
| Logging | Daily text files | Structured JSON logs |
| Testing | Manual --test flags | Automated pytest + CI |

The current system works and is reliable — these are optimisations for a theoretical restart, not criticisms. The pragmatic approach is to migrate to Docker first (Phase A), then adopt PostgreSQL, and gradually improve from there.
