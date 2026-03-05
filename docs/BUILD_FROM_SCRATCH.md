# Build From Scratch: Docker + PostgreSQL Platform

An actionable, step-by-step guide to building the football data platform from scratch on a single Docker-hosted VM with PostgreSQL as the central data warehouse.

This follows the greenfield architecture outlined in [DOCKER_MIGRATION.md](DOCKER_MIGRATION.md) and consolidates everything currently spread across 2 Proxmox VMs + PythonAnywhere into one machine.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Phase 0 — Prerequisites](#phase-0--prerequisites)
- [Phase 1 — VM & Docker Setup](#phase-1--vm--docker-setup)
- [Phase 2 — Monorepo Scaffold](#phase-2--monorepo-scaffold)
- [Phase 3 — PostgreSQL Container](#phase-3--postgresql-container)
- [Phase 4 — Data Migration](#phase-4--data-migration)
- [Phase 5 — Data-Collector Container](#phase-5--data-collector-container)
- [Phase 6 — Predictions League App](#phase-6--predictions-league-app)
- [Phase 7 — Betting-Syndicate Container](#phase-7--betting-syndicate-container)
- [Phase 8 — Nginx Reverse Proxy](#phase-8--nginx-reverse-proxy)
- [Phase 9 — Networking & DNS](#phase-9--networking--dns)
- [Phase 10 — Hardening](#phase-10--hardening)
- [Phase 11 — Verification & Cutover](#phase-11--verification--cutover)
- [Phase 12 — Production Deployment to PythonAnywhere](#phase-12--production-deployment-to-pythonanywhere)
- [Appendix A — Complete `.env.example`](#appendix-a--complete-envexample)
- [Appendix B — Maintenance Quick Reference](#appendix-b--maintenance-quick-reference)

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          Single Proxmox VM                                │
│                         (projects-server)                                 │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                         Docker Engine                               │  │
│  │                                                                     │  │
│  │  ┌─────────────────┐     ┌───────────────────────────────────────┐ │  │
│  │  │  postgres        │     │  data-collector                      │ │  │
│  │  │  (data warehouse)│     │  (APScheduler + scripts)             │ │  │
│  │  │                  │◄────│  Collects from APIs                  │ │  │
│  │  │  Port 5432       │     │  Writes to PostgreSQL                │ │  │
│  │  │                  │     └───────────────────────────────────────┘ │  │
│  │  │  Volume:         │                                              │  │
│  │  │   pg_data        │     ┌───────────────────────────────────────┐ │  │
│  │  │                  │     │  predictions-league                   │ │  │
│  │  │                  │◄────│  Flask + SQLAlchemy                   │ │  │
│  │  │                  │     │  Reads from PostgreSQL (read-only)    │ │  │
│  │  │                  │     │  Port 5000 internal                   │ │  │
│  │  └─────────────────┘     └───────────────────────────────────────┘ │  │
│  │                                                                     │  │
│  │  ┌───────────────────────┐  ┌──────────────────────────────────┐   │  │
│  │  │  betting-syndicate    │  │  nginx                           │   │  │
│  │  │  FastAPI + Uvicorn    │  │  (reverse proxy)                 │   │  │
│  │  │  Port 8001 internal   │  │  Port 80 → host                 │   │  │
│  │  │                       │  │                                  │   │  │
│  │  │  Volume:              │  │  betting.local → :8001           │   │  │
│  │  │   betting_data        │  │  predictions.local → :5000      │   │  │
│  │  │   betting_uploads     │  │                                  │   │  │
│  │  └───────────────────────┘  └──────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  Tailscale (on host VM)                                                   │
└───────────────────────────────────────────────────────────────────────────┘

          When ready for production (Phase 12):
          ┌──────────────┐           ┌──────────────────┐
          │  db-sync      │──────────►│  PythonAnywhere   │
          │  (PostgreSQL  │  MySQL    │  predictions_     │
          │   → MySQL)    │  sync     │  league (prod)    │
          └──────────────┘           └──────────────────┘
```

**Estimated total effort:** 12-15 hours across all phases.

---

## Phase 0 — Prerequisites

**Goal:** Gather every credential and secret before touching any infrastructure.

### Credentials Inventory

Collect all of the following. Every one of these becomes an environment variable in the new setup.

| # | Credential | Current location | Env var name |
|---|-----------|-----------------|-------------|
| 1 | Odds API key | `keys.json` → `odds_api_key` | `ODDS_API_KEY` |
| 2 | Pushover API token | `keys.json` → `PUSHOVER_TOKEN` | `PUSHOVER_TOKEN` |
| 3 | Pushover user key | `keys.json` → `PUSHOVER_USER` | `PUSHOVER_USER` |
| 4 | PythonAnywhere MySQL host | PythonAnywhere Databases tab (Phase 12) | `PA_MYSQL_HOST` |
| 5 | PythonAnywhere MySQL username | PythonAnywhere Databases tab (Phase 12) | `PA_MYSQL_USER` |
| 6 | Dropbox app key | `keys.json` → `dropbox_app_key` | `DROPBOX_APP_KEY` |
| 7 | Dropbox app secret | `keys.json` → `dropbox_app_secret` | `DROPBOX_APP_SECRET` |
| 8 | Dropbox refresh token | `keys.json` → `dropbox_refresh_token` | `DROPBOX_REFRESH_TOKEN` |
| 9 | Dropbox access token | `keys.json` → `dropbox_oath_token` | `DROPBOX_ACCESS_TOKEN` |
| 10 | Dropbox token expiry | `keys.json` → `dropbox_token_expires_at` | `DROPBOX_TOKEN_EXPIRES_AT` |
| 11 | Dropbox backup token | `keys.json` → `dropbox_oath_token_backup` | `DROPBOX_ACCESS_TOKEN_BACKUP` |
| 12 | FPL team ID | `keys.json` → `fpl_team_id` | `FPL_TEAM_ID` |
| 13 | PostgreSQL password | New (you choose) | `POSTGRES_PASSWORD` |
| 14 | PythonAnywhere MySQL password | PythonAnywhere Databases tab (Phase 12) | `PA_MYSQL_PASSWORD` |
| 15 | PythonAnywhere MySQL database name | PythonAnywhere Databases tab (Phase 12) | `PA_MYSQL_DB` |
| 16 | Tailscale auth key | Tailscale admin console | Used once during setup |

### Backups

Before doing anything:

```bash
# On current Prediction League VM
cp data/database.db data/database_pre_migration_$(date +%Y%m%d).db
cp keys.json keys_pre_migration.json

# On current Betting Syndicate VM
cp /opt/betting-syndicate/database/betting_syndicate.db ~/betting_syndicate_pre_migration.db

# On PythonAnywhere (via SSH)
cp ~/mysite/site/data/database.db ~/database_pre_migration.db
```

### VM Sizing Decision

| Setting | Value |
|---------|-------|
| Name | `projects-server` |
| OS | Ubuntu Server 24.04 LTS |
| CPU | 2 cores (4 recommended) |
| RAM | 4 GB |
| Disk | 40 GB |
| Network | Bridge `vmbr0` |

**Checkpoint:** You have all 16 credentials documented and all 3 databases backed up.

---

## Phase 1 — VM & Docker Setup

**Goal:** A working Docker host with Tailscale for remote access.

### 1.1 Create Proxmox VM

Create the VM using the specs from Phase 0. Install Ubuntu Server 24.04 LTS with SSH enabled.

### 1.2 Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add your user to docker group (log out and back in after)
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

### 1.3 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 1.4 Configure Firewall

```bash
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP (Nginx)
sudo ufw allow in on tailscale0  # Tailscale traffic
sudo ufw enable
```

PostgreSQL port 5432 is never exposed — it's bound to `127.0.0.1` only within Docker's internal network.

**Checkpoint:** `docker compose version` returns a version number. Tailscale shows the VM in your network.

---

## Phase 2 — Monorepo Scaffold

**Goal:** A complete directory tree with git initialised.

### 2.1 Create Directory Structure

```bash
sudo mkdir -p /opt/projects/football-platform
cd /opt/projects/football-platform

mkdir -p services/data-collector/scripts
mkdir -p services/data-collector/samples
mkdir -p services/data-collector/logs
mkdir -p services/predictions-league/app
mkdir -p services/predictions-league/templates
mkdir -p services/predictions-league/static
mkdir -p services/betting-syndicate
mkdir -p services/db-sync
mkdir -p shared
mkdir -p postgres/init
mkdir -p nginx/conf.d
mkdir -p backups
mkdir -p migrations
mkdir -p docs
```

The final structure:

```
/opt/projects/football-platform/
├── docker-compose.yml
├── .env                          # Secrets (never committed)
├── .env.example                  # Template (committed)
├── .gitignore
├── services/
│   ├── data-collector/           # prediction_league_script code
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── scheduler.py          # APScheduler replacing cron
│   │   ├── scripts/              # All collection scripts
│   │   │   ├── fpl/
│   │   │   ├── odds-api/
│   │   │   ├── prediction_league/
│   │   │   ├── pulse_api/
│   │   │   ├── football_data/
│   │   │   ├── analysis/
│   │   │   ├── database/
│   │   │   └── config.py
│   │   ├── samples/              # API response samples
│   │   └── logs/                 # Application logs
│   ├── predictions-league/       # New predictions league webapp
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/                  # Flask + SQLAlchemy
│   │   ├── templates/
│   │   └── static/
│   ├── betting-syndicate/        # betting_syndicate code
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   ├── database/             # SQLite (stays as-is)
│   │   └── uploads/
│   └── db-sync/                  # Phase 12: PostgreSQL → PythonAnywhere MySQL
│       ├── Dockerfile
│       ├── requirements.txt
│       └── sync.py
├── shared/
│   ├── db.py                     # Database connection factory
│   └── config.py                 # Shared constants
├── postgres/
│   └── init/
│       └── 01_schema.sql         # Full PostgreSQL schema
├── nginx/
│   └── conf.d/
│       └── default.conf
├── migrations/                   # Alembic migrations (Phase 10)
├── backups/                      # pg_dump outputs
└── docs/
```

### 2.2 Initialise Git

```bash
cd /opt/projects/football-platform
git init
```

### 2.3 Create `.gitignore`

```gitignore
# Secrets
.env
keys.json
*.pem

# Data
*.db
*.db-journal
*.db-wal
backups/
services/data-collector/samples/
services/data-collector/logs/
services/betting-syndicate/database/
services/betting-syndicate/uploads/

# Python
__pycache__/
*.pyc
venv/
.venv/

# Docker
*.tar
```

**Checkpoint:** `tree -L 3 /opt/projects/football-platform/` shows the expected structure. Git repo initialised.

---

## Phase 3 — PostgreSQL Container

**Goal:** PostgreSQL running with all 24 tables created.

### 3.1 Create Schema Init Script

Create `postgres/init/01_schema.sql`. This runs automatically when the PostgreSQL container starts for the first time.

```sql
-- ============================================================================
-- Football Platform - PostgreSQL Schema
-- ============================================================================
-- This file creates all tables for the football data platform.
-- It runs once on first container start via docker-entrypoint-initdb.d.
--
-- Source: Database_Schema.md from prediction_league_script
-- Tables: 24 total
-- ============================================================================

-- Use a dedicated schema to keep things tidy
CREATE SCHEMA IF NOT EXISTS pl;

-- ============================================================================
-- CORE REFERENCE TABLES
-- ============================================================================

CREATE TABLE pl.teams (
    team_id SERIAL PRIMARY KEY,
    fpl_id INTEGER,
    team_name TEXT,
    available BOOLEAN DEFAULT false,
    strength INTEGER,
    strength_overall_home INTEGER,
    strength_overall_away INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    pulse_id INTEGER,
    football_data_name TEXT,
    odds_api_name TEXT
);

CREATE TABLE pl.fixtures (
    fpl_fixture_id INTEGER NOT NULL,
    fixture_id SERIAL PRIMARY KEY,
    kickoff_dttm TIMESTAMP,
    home_teamid INTEGER NOT NULL REFERENCES pl.teams(team_id),
    away_teamid INTEGER NOT NULL REFERENCES pl.teams(team_id),
    finished BOOLEAN DEFAULT true,
    season TEXT,
    home_win_odds REAL,
    draw_odds REAL,
    away_win_odds REAL,
    pulse_id INTEGER,
    gameweek INTEGER,
    started BOOLEAN DEFAULT false,
    provisional_finished BOOLEAN DEFAULT false
);

CREATE TABLE pl.bookmakers (
    bookmaker_id SERIAL PRIMARY KEY,
    bookmaker_name TEXT UNIQUE NOT NULL
);

-- ============================================================================
-- ODDS TABLES
-- ============================================================================

CREATE TABLE pl.odds (
    odd_id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES pl.teams(team_id),
    away_team_id INTEGER NOT NULL REFERENCES pl.teams(team_id),
    bet_type TEXT NOT NULL,
    fixture_id INTEGER REFERENCES pl.fixtures(fixture_id),
    bookmaker_id INTEGER NOT NULL REFERENCES pl.bookmakers(bookmaker_id),
    price REAL
);

CREATE TABLE pl.fixture_odds_summary (
    fixture_id INTEGER PRIMARY KEY REFERENCES pl.fixtures(fixture_id),
    home_team_id INTEGER NOT NULL REFERENCES pl.teams(team_id),
    away_team_id INTEGER NOT NULL REFERENCES pl.teams(team_id),
    avg_home_win_odds REAL,
    avg_draw_odds REAL,
    avg_away_win_odds REAL,
    bookmaker_count INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PREDICTION LEAGUE TABLES
-- ============================================================================

CREATE TABLE pl.players (
    player_id SERIAL PRIMARY KEY,
    player_name TEXT,
    paid INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 0,
    mini_league INTEGER NOT NULL DEFAULT 0,
    mini_league_paid INTEGER NOT NULL DEFAULT 0,
    pundit INTEGER NOT NULL DEFAULT 0,
    web_name TEXT
);

CREATE TABLE pl.predictions (
    prediction_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES pl.players(player_id),
    fixture_id INTEGER NOT NULL REFERENCES pl.fixtures(fixture_id),
    fpl_fixture_id INTEGER,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    predicted_result TEXT NOT NULL
);

CREATE TABLE pl.results (
    result_id SERIAL PRIMARY KEY,
    fpl_fixture_id INTEGER NOT NULL,
    fixture_id INTEGER REFERENCES pl.fixtures(fixture_id),
    home_goals INTEGER,
    away_goals INTEGER,
    result TEXT
);

CREATE TABLE pl.prediction_verification (
    verification_id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    player_id INTEGER REFERENCES pl.players(player_id),
    fixture_id INTEGER REFERENCES pl.fixtures(fixture_id),
    db_home_goals INTEGER,
    db_away_goals INTEGER,
    message_home_goals INTEGER,
    message_away_goals INTEGER,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged INTEGER DEFAULT 0
);

-- ============================================================================
-- FPL (FANTASY PREMIER LEAGUE) TABLES
-- ============================================================================

CREATE TABLE pl.gameweeks (
    gameweek INTEGER PRIMARY KEY,
    deadline_dttm TIMESTAMP,
    deadline_date DATE,
    deadline_time TIME,
    current_gameweek BOOLEAN,
    next_gameweek BOOLEAN,
    finished BOOLEAN
);

CREATE TABLE pl.fantasy_pl_scores (
    id SERIAL PRIMARY KEY,
    player_name TEXT,
    gameweek INTEGER,
    player_id INTEGER,
    total_points INTEGER,
    fixture_id INTEGER REFERENCES pl.fixtures(fixture_id),
    team_id INTEGER REFERENCES pl.teams(team_id),
    was_home BOOLEAN,
    season TEXT DEFAULT '2025/2026',
    -- Additional performance metrics stored as needed
    minutes INTEGER,
    goals_scored INTEGER,
    assists INTEGER,
    clean_sheets INTEGER,
    goals_conceded INTEGER,
    own_goals INTEGER,
    penalties_saved INTEGER,
    penalties_missed INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    saves INTEGER,
    bonus INTEGER,
    bps INTEGER,
    influence REAL,
    creativity REAL,
    threat REAL,
    ict_index REAL,
    starts INTEGER,
    expected_goals REAL,
    expected_assists REAL,
    expected_goal_involvements REAL,
    expected_goals_conceded REAL,
    value INTEGER,
    transfers_balance INTEGER,
    selected INTEGER,
    transfers_in INTEGER,
    transfers_out INTEGER
);

CREATE TABLE pl.fpl_players_bootstrap (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL,
    team_id INTEGER,
    db_team_id INTEGER REFERENCES pl.teams(team_id),
    position TEXT,
    minutes INTEGER,
    total_points INTEGER,
    ict_index REAL,
    goals_scored INTEGER,
    assists INTEGER,
    clean_sheets INTEGER,
    saves INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    bonus INTEGER,
    bps INTEGER,
    influence REAL,
    creativity REAL,
    threat REAL,
    starts INTEGER,
    expected_goals REAL,
    expected_assists REAL,
    value INTEGER,
    transfers_in INTEGER,
    transfers_out INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    season TEXT DEFAULT '2025/2026'
);

CREATE TABLE pl.fpl_team_picks (
    season TEXT NOT NULL,
    gameweek INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    is_captain BOOLEAN DEFAULT false,
    is_vice_captain BOOLEAN DEFAULT false,
    multiplier INTEGER DEFAULT 1,
    PRIMARY KEY (season, gameweek, player_id)
);

CREATE TABLE pl.fpl_team_gameweek_summary (
    season TEXT NOT NULL,
    gameweek INTEGER NOT NULL,
    total_points INTEGER,
    gameweek_rank INTEGER,
    overall_rank INTEGER,
    bank INTEGER,
    squad_value INTEGER,
    points_on_bench INTEGER,
    transfers_made INTEGER,
    transfers_cost INTEGER,
    chip_used TEXT,
    PRIMARY KEY (season, gameweek)
);

-- ============================================================================
-- PULSE API TABLES (Match Details)
-- ============================================================================

CREATE TABLE pl.match_officials (
    id SERIAL PRIMARY KEY,
    matchOfficialID INTEGER NOT NULL,
    pulseid INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT
);

CREATE TABLE pl.team_list (
    id SERIAL PRIMARY KEY,
    pulseid INTEGER NOT NULL,
    team_id INTEGER REFERENCES pl.teams(team_id),
    person_id INTEGER,
    player_name TEXT NOT NULL,
    match_shirt_number INTEGER,
    is_captain BOOLEAN,
    position TEXT NOT NULL,
    is_starting BOOLEAN
);

CREATE TABLE pl.match_events (
    id SERIAL PRIMARY KEY,
    pulseid INTEGER NOT NULL,
    person_id INTEGER,
    team_id INTEGER,
    assist_id INTEGER,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL
);

-- ============================================================================
-- FOOTBALL-DATA HISTORICAL TABLE
-- ============================================================================

-- Stores 30+ years of Premier League match data from football-data.co.uk
-- Uses flexible column set to accommodate varying CSV formats across seasons
CREATE TABLE pl.football_stats (
    id SERIAL PRIMARY KEY,
    season TEXT,
    match_date DATE,
    home_team TEXT,
    away_team TEXT,
    fthg INTEGER,           -- Full time home goals
    ftag INTEGER,           -- Full time away goals
    ftr TEXT,               -- Full time result (H/D/A)
    hthg INTEGER,           -- Half time home goals
    htag INTEGER,           -- Half time away goals
    htr TEXT,               -- Half time result
    referee TEXT,
    hs INTEGER,             -- Home shots
    as_col INTEGER,         -- Away shots (as is reserved in SQL)
    hst INTEGER,            -- Home shots on target
    ast INTEGER,            -- Away shots on target
    hf INTEGER,             -- Home fouls
    af INTEGER,             -- Away fouls
    hc INTEGER,             -- Home corners
    ac INTEGER,             -- Away corners
    hy INTEGER,             -- Home yellow cards
    ay INTEGER,             -- Away yellow cards
    hr INTEGER,             -- Home red cards
    ar INTEGER,             -- Away red cards
    home_team_id INTEGER REFERENCES pl.teams(team_id),
    away_team_id INTEGER REFERENCES pl.teams(team_id),
    -- Betting odds (varies by season availability)
    b365h REAL, b365d REAL, b365a REAL,
    bwh REAL, bwd REAL, bwa REAL,
    iwh REAL, iwd REAL, iwa REAL,
    psh REAL, psd REAL, psa REAL,
    whh REAL, whd REAL, wha REAL,
    vch REAL, vcd REAL, vca REAL,
    avgh REAL, avgd REAL, avga REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SEASON ANALYSIS & RECOMMENDATIONS
-- ============================================================================

CREATE TABLE pl.season_recommendations (
    id SERIAL PRIMARY KEY,
    season TEXT NOT NULL,
    current_gameweek INTEGER NOT NULL,
    total_matches INTEGER NOT NULL,
    low_scoring_matches INTEGER NOT NULL,
    low_scoring_percentage REAL NOT NULL,
    goals_per_game_avg REAL NOT NULL,
    recommended_strategy TEXT NOT NULL,
    confidence_level TEXT NOT NULL,
    recommendation_reason TEXT NOT NULL,
    historical_precedents TEXT,
    expected_points_improvement REAL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, current_gameweek)
);

CREATE TABLE pl.strategy_season_performance (
    id SERIAL PRIMARY KEY,
    season TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    total_points INTEGER NOT NULL,
    total_matches INTEGER NOT NULL,
    correct_results INTEGER NOT NULL,
    exact_scores INTEGER NOT NULL,
    accuracy_percentage REAL NOT NULL,
    avg_points_per_game REAL NOT NULL,
    season_type TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season, strategy_name)
);

CREATE TABLE pl.historical_season_patterns (
    id SERIAL PRIMARY KEY,
    season TEXT NOT NULL UNIQUE,
    total_matches INTEGER NOT NULL,
    low_scoring_matches INTEGER NOT NULL,
    low_scoring_percentage REAL NOT NULL,
    goals_per_game_avg REAL NOT NULL,
    optimal_strategy TEXT NOT NULL,
    strategy_advantage REAL NOT NULL,
    season_classification TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TRACKING & METADATA TABLES
-- ============================================================================

CREATE TABLE pl.file_metadata (
    filename TEXT PRIMARY KEY,
    last_modified TIMESTAMP
);

CREATE TABLE pl.gameweek_cache (
    current_gw INTEGER PRIMARY KEY,
    next_gw_deadline_time TEXT
);

CREATE TABLE pl.last_update (
    table_name TEXT PRIMARY KEY,
    updated TEXT,
    timestamp NUMERIC
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Core lookups
CREATE INDEX idx_teams_odds_api_name ON pl.teams(odds_api_name);
CREATE INDEX idx_fixtures_teams_kickoff ON pl.fixtures(home_teamid, away_teamid, kickoff_dttm);
CREATE INDEX idx_fixtures_season ON pl.fixtures(season);
CREATE INDEX idx_fixtures_gameweek ON pl.fixtures(gameweek);
CREATE INDEX idx_fixtures_fpl_id ON pl.fixtures(fpl_fixture_id);
CREATE INDEX idx_fixtures_pulse_id ON pl.fixtures(pulse_id);

-- Odds
CREATE INDEX idx_odds_match_id ON pl.odds(match_id);
CREATE INDEX idx_odds_fixture_id ON pl.odds(fixture_id);

-- Predictions
CREATE INDEX idx_predictions_player_fixture ON pl.predictions(player_id, fixture_id);
CREATE INDEX idx_predictions_fixture_id ON pl.predictions(fixture_id);
CREATE INDEX idx_predictions_player_id ON pl.predictions(player_id);

-- Verification
CREATE INDEX idx_verification_category ON pl.prediction_verification(category);
CREATE INDEX idx_verification_player ON pl.prediction_verification(player_id);
CREATE INDEX idx_verification_fixture ON pl.prediction_verification(fixture_id);

-- FPL
CREATE INDEX idx_player_scores_fixture_id ON pl.fantasy_pl_scores(fixture_id);
CREATE INDEX idx_player_scores_player_id ON pl.fantasy_pl_scores(player_id);
CREATE INDEX idx_player_scores_gameweek ON pl.fantasy_pl_scores(gameweek);
CREATE INDEX idx_player_scores_team_id ON pl.fantasy_pl_scores(team_id);
CREATE INDEX idx_player_scores_season_player_gw ON pl.fantasy_pl_scores(season, player_id, gameweek);
CREATE INDEX idx_bootstrap_player_season ON pl.fpl_players_bootstrap(player_id, season);
CREATE INDEX idx_fpl_picks_season_gw ON pl.fpl_team_picks(season, gameweek);
CREATE INDEX idx_gameweeks_current ON pl.gameweeks(current_gameweek);
CREATE INDEX idx_gameweeks_finished ON pl.gameweeks(finished);

-- Pulse API
CREATE INDEX idx_match_officials_pulseid ON pl.match_officials(pulseid);
CREATE INDEX idx_team_list_pulseid ON pl.team_list(pulseid);
CREATE INDEX idx_team_list_team_id ON pl.team_list(team_id);
CREATE INDEX idx_match_events_pulseid ON pl.match_events(pulseid);
CREATE INDEX idx_match_events_event_type ON pl.match_events(event_type);

-- Football data
CREATE INDEX idx_football_stats_season ON pl.football_stats(season);
CREATE INDEX idx_football_stats_date ON pl.football_stats(match_date);
CREATE INDEX idx_football_stats_home_team ON pl.football_stats(home_team_id);
CREATE INDEX idx_football_stats_away_team ON pl.football_stats(away_team_id);
CREATE INDEX idx_football_stats_result ON pl.football_stats(ftr);

-- Season analysis
CREATE INDEX idx_season_recommendations_season ON pl.season_recommendations(season);
CREATE INDEX idx_strategy_performance_season ON pl.strategy_season_performance(season);
CREATE INDEX idx_historical_patterns_season ON pl.historical_season_patterns(season);
CREATE INDEX idx_historical_patterns_class ON pl.historical_season_patterns(season_classification);

-- File metadata
CREATE INDEX idx_file_metadata_filename ON pl.file_metadata(filename);
```

### 3.2 Create Standalone Compose Test

Create a temporary `docker-compose.postgres-only.yml` to test PostgreSQL in isolation:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      POSTGRES_USER: projects
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: datawarehouse
      TZ: Europe/London
    volumes:
      - pg-data:/var/lib/postgresql/data
      - ./postgres/init:/docker-entrypoint-initdb.d:ro
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U projects -d datawarehouse"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pg-data:
```

### 3.3 Start and Verify

```bash
# Create .env with your password
echo "POSTGRES_PASSWORD=your-secure-password-here" > .env
chmod 600 .env

# Start PostgreSQL
docker compose -f docker-compose.postgres-only.yml up -d

# Wait for healthy
docker compose -f docker-compose.postgres-only.yml ps

# Verify all tables were created
docker exec postgres psql -U projects -d datawarehouse -c "\dt pl.*"
```

Expected output: 24 tables listed under the `pl` schema.

### 3.4 Quick Verification Queries

```bash
# Count tables
docker exec postgres psql -U projects -d datawarehouse -c \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'pl';"

# List all tables
docker exec postgres psql -U projects -d datawarehouse -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema = 'pl' ORDER BY table_name;"

# Count indexes
docker exec postgres psql -U projects -d datawarehouse -c \
  "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'pl';"
```

**Checkpoint:** `\dt pl.*` shows 24 tables. All indexes created. Stop here and validate before proceeding.

---

## Phase 4 — Data Migration

**Goal:** All existing SQLite data loaded into PostgreSQL with row counts matching.

### 4.1 Copy SQLite Database to VM

```bash
# From your current prediction league VM
scp prediction-league-vm:~/prediction_league_script/data/database.db \
    /opt/projects/football-platform/backups/source_database.db
```

### 4.2 Create Migration Script

Create `services/data-collector/scripts/database/migrate_sqlite_to_postgres.py`:

```python
"""
One-time migration: SQLite → PostgreSQL.

Reads every table from the existing SQLite database and inserts
into the corresponding PostgreSQL table under the pl schema.

Usage:
    python migrate_sqlite_to_postgres.py /path/to/database.db

Requires: psycopg2-binary
"""

import os
import sys
import sqlite3
import logging

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tables in dependency order (referenced tables first)
MIGRATION_ORDER = [
    # Core reference
    ("teams", "pl.teams", [
        "team_id", "fpl_id", "team_name", "available", "strength",
        "strength_overall_home", "strength_overall_away",
        "strength_attack_home", "strength_attack_away",
        "strength_defence_home", "strength_defence_away",
        "pulse_id", "football_data_name", "odds_api_name"
    ]),
    ("fixtures", "pl.fixtures", [
        "fpl_fixture_id", "fixture_id", "kickoff_dttm", "home_teamid", "away_teamid",
        "finished", "season", "home_win_odds", "draw_odds", "away_win_odds",
        "pulse_id", "gameweek", "started", "provisional_finished"
    ]),
    ("bookmakers", "pl.bookmakers", [
        "bookmaker_id", "bookmaker_name"
    ]),

    # Odds
    ("odds", "pl.odds", [
        "odd_id", "match_id", "home_team_id", "away_team_id",
        "bet_type", "fixture_id", "bookmaker_id", "price"
    ]),
    ("fixture_odds_summary", "pl.fixture_odds_summary", [
        "fixture_id", "home_team_id", "away_team_id",
        "avg_home_win_odds", "avg_draw_odds", "avg_away_win_odds",
        "bookmaker_count", "last_updated"
    ]),

    # Prediction league
    ("players", "pl.players", [
        "player_id", "player_name", "paid", "active",
        "mini_league", "mini_league_paid", "pundit", "web_name"
    ]),
    ("predictions", "pl.predictions", [
        "prediction_id", "player_id", "fixture_id", "fpl_fixture_id",
        "home_goals", "away_goals", "predicted_result"
    ]),
    ("results", "pl.results", [
        "result_id", "fpl_fixture_id", "fixture_id",
        "home_goals", "away_goals", "result"
    ]),
    ("prediction_verification", "pl.prediction_verification", [
        "verification_id", "category", "player_id", "fixture_id",
        "db_home_goals", "db_away_goals", "message_home_goals", "message_away_goals",
        "verified_at", "acknowledged"
    ]),

    # FPL
    ("gameweeks", "pl.gameweeks", [
        "gameweek", "deadline_dttm", "deadline_date", "deadline_time",
        "current_gameweek", "next_gameweek", "finished"
    ]),
    ("fpl_players_bootstrap", "pl.fpl_players_bootstrap", [
        "player_id", "player_name", "team_id", "db_team_id", "position",
        "minutes", "total_points", "ict_index", "goals_scored", "assists",
        "clean_sheets", "saves", "yellow_cards", "red_cards", "bonus", "bps",
        "influence", "creativity", "threat", "starts",
        "expected_goals", "expected_assists", "value",
        "transfers_in", "transfers_out", "last_updated", "season"
    ]),
    ("fpl_team_picks", "pl.fpl_team_picks", [
        "season", "gameweek", "player_id", "position",
        "is_captain", "is_vice_captain", "multiplier"
    ]),
    ("fpl_team_gameweek_summary", "pl.fpl_team_gameweek_summary", [
        "season", "gameweek", "total_points", "gameweek_rank", "overall_rank",
        "bank", "squad_value", "points_on_bench",
        "transfers_made", "transfers_cost", "chip_used"
    ]),

    # Pulse API
    ("match_officials", "pl.match_officials", [
        "id", "matchOfficialID", "pulseid", "name", "role"
    ]),
    ("team_list", "pl.team_list", [
        "id", "pulseid", "team_id", "person_id", "player_name",
        "match_shirt_number", "is_captain", "position", "is_starting"
    ]),
    ("match_events", "pl.match_events", [
        "id", "pulseid", "person_id", "team_id", "assist_id",
        "event_type", "event_time"
    ]),

    # Tracking
    ("file_metadata", "pl.file_metadata", ["filename", "last_modified"]),
    ("gameweek_cache", "pl.gameweek_cache", ["current_gw", "next_gw_deadline_time"]),
    ("last_update", "pl.last_update", ["table_name", "updated", "timestamp"]),

    # Season analysis
    ("season_recommendations", "pl.season_recommendations", [
        "id", "season", "current_gameweek", "total_matches",
        "low_scoring_matches", "low_scoring_percentage", "goals_per_game_avg",
        "recommended_strategy", "confidence_level", "recommendation_reason",
        "historical_precedents", "expected_points_improvement",
        "last_updated", "created_at"
    ]),
    ("strategy_season_performance", "pl.strategy_season_performance", [
        "id", "season", "strategy_name", "total_points", "total_matches",
        "correct_results", "exact_scores", "accuracy_percentage",
        "avg_points_per_game", "season_type", "last_updated"
    ]),
    ("historical_season_patterns", "pl.historical_season_patterns", [
        "id", "season", "total_matches", "low_scoring_matches",
        "low_scoring_percentage", "goals_per_game_avg",
        "optimal_strategy", "strategy_advantage", "season_classification",
        "created_at"
    ]),
]


def get_boolean_columns(table_name):
    """Get list of boolean columns that need conversion from integer"""
    boolean_columns = {
        'teams': ['available'],
        'gameweeks': ['current_gameweek', 'next_gameweek', 'finished'],
        'fixtures': ['finished', 'started', 'provisional_finished'],
        'fantasy_pl_scores': ['was_home'],
        'fpl_team_picks': ['is_captain', 'is_vice_captain'],
        'players': ['paid', 'active', 'mini_league', 'mini_league_paid', 'pundit'],
        'team_list': ['is_captain', 'is_starting'],
    }
    return boolean_columns.get(table_name, [])

def convert_boolean_value(value):
    """Convert SQLite integer boolean to PostgreSQL boolean"""
    if value is None:
        return None
    return bool(value)

def migrate_table(sqlite_cur, pg_cur, sqlite_table, pg_table, columns):
    """Migrate a single table from SQLite to PostgreSQL."""
    # Check if SQLite table exists
    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (sqlite_table,)
    )
    if not sqlite_cur.fetchone():
        logger.warning(f"  Skipping {sqlite_table} — does not exist in SQLite")
        return 0

    # Get available columns in SQLite table
    sqlite_cur.execute(f"PRAGMA table_info({sqlite_table})")
    sqlite_columns = {row[1] for row in sqlite_cur.fetchall()}

    # Only migrate columns that exist in both
    common_columns = [c for c in columns if c in sqlite_columns]
    if not common_columns:
        logger.warning(f"  Skipping {sqlite_table} — no matching columns")
        return 0

    # Get boolean columns for this table
    boolean_columns = get_boolean_columns(sqlite_table)

    # Read from SQLite
    col_list = ", ".join(common_columns)
    sqlite_cur.execute(f"SELECT {col_list} FROM {sqlite_table}")
    rows = sqlite_cur.fetchall()

    if not rows:
        logger.info(f"  {sqlite_table} → {pg_table}: 0 rows (empty)")
        return 0

    # Convert boolean columns from integer to boolean
    converted_rows = []
    for row in rows:
        converted_row = []
        for i, (value, col) in enumerate(zip(row, common_columns)):
            if col in boolean_columns:
                value = convert_boolean_value(value)
            converted_row.append(value)
        converted_rows.append(tuple(converted_row))

    # Insert into PostgreSQL
    placeholders = ", ".join(["%s"] * len(common_columns))
    pg_col_list = ", ".join(f'"{c}"' if c in ('matchOfficialID',) else c for c in common_columns)
    insert_sql = f"INSERT INTO {pg_table} ({pg_col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    psycopg2.extras.execute_batch(pg_cur, insert_sql, converted_rows, page_size=1000)

    logger.info(f"  {sqlite_table} → {pg_table}: {len(converted_rows)} rows")
    return len(converted_rows)


def reset_sequences(pg_cur):
    """Reset PostgreSQL sequences to match migrated data."""
    sequences = [
        ("pl.teams", "team_id"),
        ("pl.fixtures", "fixture_id"),
        ("pl.bookmakers", "bookmaker_id"),
        ("pl.odds", "odd_id"),
        ("pl.players", "player_id"),
        ("pl.predictions", "prediction_id"),
        ("pl.results", "result_id"),
        ("pl.prediction_verification", "verification_id"),
        ("pl.match_officials", "id"),
        ("pl.team_list", "id"),
        ("pl.match_events", "id"),
        ("pl.football_stats", "id"),
        ("pl.season_recommendations", "id"),
        ("pl.strategy_season_performance", "id"),
        ("pl.historical_season_patterns", "id"),
        ("pl.fantasy_pl_scores", "id"),
    ]
    for table, col in sequences:
        pg_cur.execute(f"""
            SELECT setval(pg_get_serial_sequence('{table}', '{col}'),
                          COALESCE((SELECT MAX({col}) FROM {table}), 0) + 1, false)
        """)
    logger.info("Reset all sequences")


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_sqlite_to_postgres.py /path/to/database.db")
        sys.exit(1)

    sqlite_path = sys.argv[1]
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_db = os.environ.get("POSTGRES_DB", "datawarehouse")
    pg_user = os.environ.get("POSTGRES_USER", "projects")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "")

    logger.info(f"Migrating from {sqlite_path} to {pg_host}/{pg_db}")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(host=pg_host, dbname=pg_db, user=pg_user, password=pg_pass)
    pg_cur = pg_conn.cursor()

    total_rows = 0
    try:
        for sqlite_table, pg_table, columns in MIGRATION_ORDER:
            total_rows += migrate_table(sqlite_cur, pg_cur, sqlite_table, pg_table, columns)

        reset_sequences(pg_cur)
        pg_conn.commit()
        logger.info(f"Migration complete: {total_rows} total rows migrated")
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
```

**Note:** The `football_stats` table migration is not included above because the source SQLite uses different column names (e.g., `HomeTeam`, `AwayTeam`, `Date`) than our normalised PostgreSQL schema. Write a separate migration for that table that maps the columns. The `fantasy_pl_scores` table similarly has 30+ columns that need individual mapping — extend the migration script to include those columns once you've confirmed the exact set in your SQLite database.

### 4.3 Run the Migration

```bash
# Install psycopg2 on the host (or run inside a container)
pip install psycopg2-binary

# Run migration
POSTGRES_HOST=localhost \
POSTGRES_PASSWORD=your-secure-password-here \
python services/data-collector/scripts/database/migrate_sqlite_to_postgres.py \
    backups/source_database.db
```

### 4.4 Validate Row Counts

```bash
# Compare key tables
echo "=== SQLite counts ==="
sqlite3 backups/source_database.db "
SELECT 'teams', COUNT(*) FROM teams
UNION ALL SELECT 'fixtures', COUNT(*) FROM fixtures
UNION ALL SELECT 'players', COUNT(*) FROM players
UNION ALL SELECT 'predictions', COUNT(*) FROM predictions
UNION ALL SELECT 'results', COUNT(*) FROM results
UNION ALL SELECT 'odds', COUNT(*) FROM odds
UNION ALL SELECT 'gameweeks', COUNT(*) FROM gameweeks
UNION ALL SELECT 'fpl_players_bootstrap', COUNT(*) FROM fpl_players_bootstrap;
"

echo "=== PostgreSQL counts ==="
docker exec postgres psql -U projects -d datawarehouse -c "
SELECT 'teams', COUNT(*) FROM pl.teams
UNION ALL SELECT 'fixtures', COUNT(*) FROM pl.fixtures
UNION ALL SELECT 'players', COUNT(*) FROM pl.players
UNION ALL SELECT 'predictions', COUNT(*) FROM pl.predictions
UNION ALL SELECT 'results', COUNT(*) FROM pl.results
UNION ALL SELECT 'odds', COUNT(*) FROM pl.odds
UNION ALL SELECT 'gameweeks', COUNT(*) FROM pl.gameweeks
UNION ALL SELECT 'fpl_players_bootstrap', COUNT(*) FROM pl.fpl_players_bootstrap;
"
```

Every count should match.

**Checkpoint:** All row counts match between SQLite and PostgreSQL. Stop and fix any discrepancies before proceeding.

---

## Phase 5 — Data-Collector Container

**Goal:** All 14 scheduled jobs running via APScheduler inside a single container, writing to PostgreSQL.

### 5.1 Shared Database Abstraction

Create `shared/db.py`:

```python
"""
Database connection factory.

Supports both PostgreSQL (production/Docker) and SQLite (local dev).
When POSTGRES_HOST is set, connects to PostgreSQL.
Otherwise falls back to SQLite at data/database.db.
"""

import os
import sqlite3
from pathlib import Path


def get_connection():
    """Return a database connection (PostgreSQL or SQLite)."""
    pg_host = os.environ.get("POSTGRES_HOST")
    if pg_host:
        import psycopg2
        return psycopg2.connect(
            host=pg_host,
            dbname=os.environ.get("POSTGRES_DB", "datawarehouse"),
            user=os.environ.get("POSTGRES_USER", "projects"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
            options="-c search_path=pl,public",
        )
    else:
        db_path = Path(__file__).parent.parent / "data" / "database.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def placeholder():
    """Return the correct SQL placeholder for the active backend."""
    if os.environ.get("POSTGRES_HOST"):
        return "%s"
    return "?"


def upsert_sql(table, columns, conflict_columns):
    """
    Generate an upsert statement for the active backend.

    SQLite:  INSERT OR REPLACE INTO ...
    PostgreSQL: INSERT INTO ... ON CONFLICT (...) DO UPDATE SET ...
    """
    col_list = ", ".join(columns)
    ph = placeholder()
    placeholders = ", ".join([ph] * len(columns))

    if os.environ.get("POSTGRES_HOST"):
        conflict = ", ".join(conflict_columns)
        update_cols = [c for c in columns if c not in conflict_columns]
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        if update_set:
            return (
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict}) DO UPDATE SET {update_set}"
            )
        else:
            return (
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict}) DO NOTHING"
            )
    else:
        return f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
```

### 5.2 APScheduler Configuration

Create `services/data-collector/scheduler.py`:

This replaces the entire `master_scheduler.sh` + cron approach. Every job from the current scheduler is mapped here with identical timing.

```python
"""
APScheduler-based job scheduler.

Replaces master_scheduler.sh + cron with a Python-native scheduler
that runs inside the Docker container. No cron, no lock files,
no shell scripts.

Job schedule (matches master_scheduler.sh exactly):
  - fetch_results:              every 1 minute
  - monitor_and_upload:         every 1 minute (10s offset)
  - clean_predictions_dropbox:  every 15 minutes
  - fetch_fixtures_gameweeks:   every 30 minutes
  - gameweek_validator:         every 5 minutes
  - automated_predictions:      every hour (at :00)
  - fetch_fpl_data:             daily at 07:00
  - fetch_fpl_picks:            daily at 07:05
  - fetch_odds:                 daily at 07:00
  - fetch_pulse_data:           daily at 08:00
  - fetch_football_data:        Sundays at 09:00
  - update_recommendations:     Sundays at 10:00
  - verify_predictions:         daily at 11:00
  - daily_cleanup:              daily at 02:00
"""

import os
import sys
import logging
import subprocess
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scheduler")

PROJECT_DIR = Path(__file__).parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"


def run_script(script_path, name, args=None):
    """Run a Python script as a subprocess."""
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    logger.info(f"Starting {name}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode == 0:
            logger.info(f"Completed {name}")
        else:
            logger.error(f"Failed {name} (exit {result.returncode}): {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout {name} (>3600s)")
    except Exception as e:
        logger.error(f"Error running {name}: {e}")


def is_enabled(name):
    """Check if a job is enabled via environment variable."""
    return os.environ.get(f"ENABLE_{name.upper()}", "true").lower() == "true"


def setup_scheduler():
    scheduler = BlockingScheduler(timezone="Europe/London")

    # === Every minute ===
    if is_enabled("fetch_results"):
        scheduler.add_job(
            run_script,
            IntervalTrigger(minutes=1),
            args=[SCRIPTS_DIR / "fpl" / "fetch_results.py", "fetch_results"],
            id="fetch_results",
            max_instances=1,
        )

    if is_enabled("monitor_upload"):
        scheduler.add_job(
            run_script,
            IntervalTrigger(minutes=1, start_date="2025-01-01 00:00:10"),  # 10s offset
            args=[SCRIPTS_DIR / "database" / "monitor_and_upload.py", "monitor_and_upload"],
            id="monitor_and_upload",
            max_instances=1,
        )

    # === Every 5 minutes ===
    scheduler.add_job(
        run_script,
        CronTrigger(minute="*/5"),
        args=[SCRIPTS_DIR / "fpl" / "gameweek_validator.py", "gameweek_validator", ["--check-refresh"]],
        id="gameweek_validator",
        max_instances=1,
    )

    # === Every 15 minutes ===
    if is_enabled("clean_predictions"):
        scheduler.add_job(
            run_script,
            CronTrigger(minute="0,15,30,45"),
            args=[SCRIPTS_DIR / "prediction_league" / "clean_predictions_dropbox.py", "clean_predictions"],
            id="clean_predictions",
            max_instances=1,
        )

    # === Every 30 minutes ===
    if is_enabled("fetch_fixtures"):
        scheduler.add_job(
            run_script,
            CronTrigger(minute="0,30"),
            args=[SCRIPTS_DIR / "fpl" / "fetch_fixtures_gameweeks.py", "fetch_fixtures"],
            id="fetch_fixtures",
            max_instances=1,
        )

    # === Every hour ===
    if is_enabled("automated_predictions"):
        scheduler.add_job(
            run_script,
            CronTrigger(minute=0),
            args=[SCRIPTS_DIR / "prediction_league" / "automated_predictions.py", "automated_predictions"],
            id="automated_predictions",
            max_instances=1,
        )

    # === Daily at 07:00 ===
    if is_enabled("fetch_fpl_data"):
        scheduler.add_job(
            run_script,
            CronTrigger(hour=7, minute=0),
            args=[SCRIPTS_DIR / "fpl" / "fetch_fpl_data.py", "fetch_fpl_data"],
            id="fetch_fpl_data",
            max_instances=1,
        )

    if is_enabled("fetch_odds"):
        scheduler.add_job(
            run_script,
            CronTrigger(hour=7, minute=0),
            args=[SCRIPTS_DIR / "odds-api" / "fetch_odds.py", "fetch_odds"],
            id="fetch_odds",
            max_instances=1,
        )

    # === Daily at 07:05 ===
    if is_enabled("fetch_fpl_picks"):
        scheduler.add_job(
            run_script,
            CronTrigger(hour=7, minute=5),
            args=[SCRIPTS_DIR / "fpl" / "fetch_fpl_picks.py", "fetch_fpl_picks"],
            id="fetch_fpl_picks",
            max_instances=1,
        )

    # === Daily at 08:00 ===
    if is_enabled("fetch_pulse_data"):
        scheduler.add_job(
            run_script,
            CronTrigger(hour=8, minute=0),
            args=[SCRIPTS_DIR / "pulse_api" / "fetch_pulse_data.py", "fetch_pulse_data"],
            id="fetch_pulse_data",
            max_instances=1,
        )

    # === Weekly: Sundays at 09:00 ===
    if is_enabled("fetch_football_data"):
        scheduler.add_job(
            run_script,
            CronTrigger(day_of_week="sun", hour=9, minute=0),
            args=[SCRIPTS_DIR / "football_data" / "fetch_football_data.py", "fetch_football_data"],
            id="fetch_football_data",
            max_instances=1,
        )

    # === Weekly: Sundays at 10:00 ===
    if is_enabled("update_recommendations"):
        scheduler.add_job(
            run_script,
            CronTrigger(day_of_week="sun", hour=10, minute=0),
            args=[SCRIPTS_DIR / "prediction_league" / "update_season_recommendations.py", "update_recommendations"],
            id="update_recommendations",
            max_instances=1,
        )

    # === Daily at 11:00 ===
    if is_enabled("verify_predictions"):
        scheduler.add_job(
            run_script,
            CronTrigger(hour=11, minute=0),
            args=[SCRIPTS_DIR / "analysis" / "verify_predictions_from_messages.py", "verify_predictions"],
            id="verify_predictions",
            max_instances=1,
        )

    # === Daily at 02:00: cleanup ===
    scheduler.add_job(
        lambda: logger.info("Daily cleanup — old logs handled by Docker log rotation"),
        CronTrigger(hour=2, minute=0),
        id="daily_cleanup",
    )

    return scheduler


if __name__ == "__main__":
    logger.info("Starting APScheduler with 14 jobs")
    scheduler = setup_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
```

### 5.3 Dockerfile

Create `services/data-collector/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY ../../shared /app/shared

# Copy application code
COPY . .

# Create log directory
RUN mkdir -p /app/logs

EXPOSE 5000

# Run scheduler (replaces cron + master_scheduler.sh)
CMD ["python", "scheduler.py"]
```

### 5.4 Requirements

Create `services/data-collector/requirements.txt`:

```
requests>=2.31.0
tqdm>=4.65.0
pytz>=2023.3
psycopg2-binary>=2.9.0
apscheduler>=3.10.0
flask>=3.0.0
```

### 5.5 Script Update Pattern

Each existing script currently does `sqlite3.connect(db_path)`. The migration path for each script is:

**Before (SQLite):**
```python
import sqlite3 as sql
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "data" / "database.db"
conn = sql.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("INSERT OR REPLACE INTO teams (team_id, team_name) VALUES (?, ?)", (1, "Arsenal"))
```

**After (dual-mode):**
```python
from shared.db import get_connection, placeholder, upsert_sql

conn = get_connection()
cursor = conn.cursor()
ph = placeholder()
cursor.execute(f"INSERT INTO pl.teams (team_id, team_name) VALUES ({ph}, {ph})", (1, "Arsenal"))
```

**Scripts to update (15 total):**

| Script | Path | Key changes |
|--------|------|-------------|
| fetch_results | `scripts/fpl/fetch_results.py` | `?` → `%s`, table prefix `pl.` |
| fetch_fixtures_gameweeks | `scripts/fpl/fetch_fixtures_gameweeks.py` | Same pattern |
| fetch_fpl_data | `scripts/fpl/fetch_fpl_data.py` | Same pattern |
| fetch_fpl_picks | `scripts/fpl/fetch_fpl_picks.py` | Same pattern |
| gameweek_validator | `scripts/fpl/gameweek_validator.py` | Same pattern |
| fetch_odds | `scripts/odds-api/fetch_odds.py` | Same pattern |
| clean_predictions_dropbox | `scripts/prediction_league/clean_predictions_dropbox.py` | Same + Dropbox token write |
| automated_predictions | `scripts/prediction_league/automated_predictions.py` | Same pattern |
| update_season_recommendations | `scripts/prediction_league/update_season_recommendations.py` | Same pattern |
| fetch_pulse_data | `scripts/pulse_api/fetch_pulse_data.py` | Same pattern |
| fetch_football_data | `scripts/football_data/fetch_football_data.py` | Same pattern |
| monitor_and_upload | `scripts/database/monitor_and_upload.py` | Reads `last_update` from PG |
| verify_predictions | `scripts/analysis/verify_predictions_from_messages.py` | Same pattern |
| webapp/app.py | `webapp/app.py` | Same pattern |
| config.py | `scripts/config.py` | No DB changes needed |

**Key SQL dialect differences to handle:**

| SQLite | PostgreSQL |
|--------|-----------|
| `?` placeholder | `%s` placeholder |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| `datetime('now')` | `NOW()` or `CURRENT_TIMESTAMP` |
| `AUTOINCREMENT` | `SERIAL` (already handled in schema) |
| `BOOLEAN` (0/1 integers) | `BOOLEAN` (true/false, but accepts 0/1) |
| No schema prefix | `pl.` schema prefix |

### 5.6 Dropbox Token Refresh

The `clean_predictions_dropbox.py` script writes refreshed OAuth tokens back to `keys.json`. In Docker, this file must be writable.

**Solution:** Mount `keys.json` as a read-write volume:

```yaml
volumes:
  - ./keys/keys.json:/app/keys.json:rw
```

Copy `keys.json` to the host once:
```bash
mkdir -p /opt/projects/football-platform/keys
cp keys.json /opt/projects/football-platform/keys/keys.json
chmod 640 /opt/projects/football-platform/keys/keys.json
```

### 5.7 Environment Variable Mapping

Instead of reading from `keys.json`, scripts can optionally read from environment variables. The migration can be gradual — `keys.json` continues to work, and env vars are the long-term target.

```python
# In each script, replace:
#   config = json.load(open("keys.json"))
#   api_key = config["odds_api_key"]
# With:
api_key = os.environ.get("ODDS_API_KEY") or config.get("odds_api_key")
```

**Checkpoint:** Container starts, `scheduler.py` logs show jobs being registered. At least `fetch_results` completes one cycle successfully. Stop here and validate before adding more containers.

---

## Phase 6 — Predictions League App

**Goal:** A new Flask + SQLAlchemy webapp running in Docker that reads directly from the PostgreSQL data warehouse. Built so it can later be deployed to PythonAnywhere with just a `DATABASE_URL` change.

### 6.1 Why SQLAlchemy

The key design decision: use **SQLAlchemy** as the ORM so the app is database-agnostic. The same code runs against:

- **PostgreSQL** in development (reads from the data warehouse directly — no sync needed)
- **MySQL** in production on PythonAnywhere (reads from a synced copy)

You never write raw SQL with `?` vs `%s` differences. SQLAlchemy handles all dialect translation.

### 6.2 Dockerfile

Create `services/predictions-league/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["flask", "run", "--host", "0.0.0.0", "--port", "5000"]
```

### 6.3 Requirements

Create `services/predictions-league/requirements.txt`:

```
flask>=3.0.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pymysql>=1.1.0
pytz>=2023.3
```

Both `psycopg2-binary` (PostgreSQL) and `pymysql` (MySQL) are included so the same image works in both environments. Only the one matching `DATABASE_URL` is actually used at runtime.

### 6.4 Database Connection

The app connects via a single `DATABASE_URL` environment variable:

```python
# services/predictions-league/app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://projects:password@postgres:5432/datawarehouse"
)

# SQLAlchemy handles the dialect automatically based on the URL scheme:
#   postgresql://  → uses psycopg2
#   mysql+pymysql:// → uses pymysql
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,          # Reconnect on stale connections
    pool_recycle=280,            # Recycle before PythonAnywhere's 300s timeout
    echo=False,
)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency for Flask routes — yields a session, closes on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 6.5 SQLAlchemy Models

Define models once — they work with both PostgreSQL and MySQL:

```python
# services/predictions-league/app/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "pl"}  # Ignored by MySQL, used by PostgreSQL

    team_id = Column(Integer, primary_key=True)
    fpl_id = Column(Integer)
    team_name = Column(String(100))
    odds_api_name = Column(String(100))
    pulse_id = Column(Integer)


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = {"schema": "pl"}

    fixture_id = Column(Integer, primary_key=True)
    fpl_fixture_id = Column(Integer, nullable=False)
    kickoff_dttm = Column(DateTime)
    home_teamid = Column(Integer, ForeignKey("pl.teams.team_id"), nullable=False)
    away_teamid = Column(Integer, ForeignKey("pl.teams.team_id"), nullable=False)
    finished = Column(Boolean, default=True)
    season = Column(String(20))
    gameweek = Column(Integer)

    home_team = relationship("Team", foreign_keys=[home_teamid])
    away_team = relationship("Team", foreign_keys=[away_teamid])


class Player(Base):
    __tablename__ = "players"
    __table_args__ = {"schema": "pl"}

    player_id = Column(Integer, primary_key=True)
    player_name = Column(String(100))
    active = Column(Integer, default=0)
    web_name = Column(String(100))


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = {"schema": "pl"}

    prediction_id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("pl.players.player_id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("pl.fixtures.fixture_id"), nullable=False)
    home_goals = Column(Integer, nullable=False)
    away_goals = Column(Integer, nullable=False)
    predicted_result = Column(String(5), nullable=False)

    player = relationship("Player")
    fixture = relationship("Fixture")


class Result(Base):
    __tablename__ = "results"
    __table_args__ = {"schema": "pl"}

    result_id = Column(Integer, primary_key=True, autoincrement=True)
    fpl_fixture_id = Column(Integer, nullable=False)
    fixture_id = Column(Integer, ForeignKey("pl.fixtures.fixture_id"))
    home_goals = Column(Integer)
    away_goals = Column(Integer)
    result = Column(String(5))


class Gameweek(Base):
    __tablename__ = "gameweeks"
    __table_args__ = {"schema": "pl"}

    gameweek = Column(Integer, primary_key=True)
    deadline_dttm = Column(DateTime)
    current_gameweek = Column(Boolean)
    finished = Column(Boolean)
```

> **Note on `__table_args__ = {"schema": "pl"}`:** PostgreSQL uses the `pl` schema. When deploying to MySQL (which doesn't have schemas in the same way), you have two options:
> 1. Remove the schema arg and set `search_path=pl` in the PostgreSQL connection string (recommended)
> 2. Use a conditional: `{"schema": "pl"} if "postgresql" in DATABASE_URL else {}`
>
> Option 1 is cleaner — set `options="-c search_path=pl,public"` in the PostgreSQL `DATABASE_URL` and omit `schema` from the models entirely. The models then work identically on both backends.

### 6.6 Switching Environments

The only difference between dev and prod is the `DATABASE_URL`:

```bash
# Development — reads directly from the PostgreSQL data warehouse
DATABASE_URL=postgresql://projects:password@postgres:5432/datawarehouse?options=-c%20search_path%3Dpl,public

# Production on PythonAnywhere — reads from the synced MySQL copy
DATABASE_URL=mysql+pymysql://user:pass@user.mysql.pythonanywhere-services.com/user$predictions
```

No code changes, no feature flags, no if/else. Just swap the URL.

### 6.7 Development Workflow

In dev, the predictions-league app reads live data directly from the warehouse:

```
data-collector → writes to PostgreSQL
                         ↑
predictions-league app → reads from PostgreSQL (same Docker network)
```

No sync container needed. The data is always fresh — you see real-time updates as the data-collector writes them.

When you're ready to go to production, Phase 12 covers setting up the db-sync container and deploying the same app to PythonAnywhere.

**Checkpoint:** `http://predictions.local` loads the webapp. Queries return live data from the warehouse. The app works with the same models whether pointed at PostgreSQL or MySQL.

---

## Phase 7 — Betting-Syndicate Container

**Goal:** Betting syndicate dashboard running in Docker, still using its own SQLite database.

The betting syndicate stays on SQLite — it's a standalone single-user app with no need for PostgreSQL. The existing code and SQLite database are containerised as-is.

### 7.1 Transfer Code

```bash
scp -r betting-vm:/opt/betting-syndicate/* \
    /opt/projects/football-platform/services/betting-syndicate/

# Remove venv (not needed in container)
rm -rf /opt/projects/football-platform/services/betting-syndicate/venv
```

### 7.2 Dockerfile

Create `services/betting-syndicate/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN rm -rf venv/

RUN mkdir -p /app/uploads/screenshots /app/database

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 7.3 Database Volume

The SQLite database is stored in a named Docker volume so it persists across container rebuilds:

```yaml
volumes:
  - betting-data:/app/database
  - betting-uploads:/app/uploads
```

To import the existing database:

```bash
# Start the container first to create the volume
docker compose up -d betting-syndicate

# Copy database into the volume
docker cp /opt/projects/football-platform/services/betting-syndicate/database/betting_syndicate.db \
    betting-syndicate:/app/database/
```

**Checkpoint:** `http://betting.local` loads the dashboard (after Nginx is set up in Phase 8). Ledger entries and season data are intact.

---

## Phase 8 — Nginx Reverse Proxy

**Goal:** Both web apps accessible via hostnames.

### 8.1 Create Nginx Config

Create `nginx/conf.d/default.conf`:

```nginx
# Betting Syndicate
server {
    listen 80;
    server_name betting.local;

    client_max_body_size 10M;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://betting-syndicate:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Predictions League webapp
server {
    listen 80;
    server_name predictions.local;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://predictions-league:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Checkpoint:** `curl -H "Host: betting.local" http://localhost` returns HTML.

---

## Phase 9 — Networking & DNS

**Goal:** Services survive VM reboot, accessible via Tailscale.

### 9.1 Full Docker Compose

Create `docker-compose.yml`:

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
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U projects -d datawarehouse"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'
    networks:
      - app-network

  data-collector:
    build:
      context: ./services/data-collector
      dockerfile: Dockerfile
    container_name: data-collector
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - collector-logs:/app/logs
      - collector-samples:/app/samples
      - ./keys/keys.json:/app/keys.json:rw
    environment:
      TZ: Europe/London
      PYTHONUNBUFFERED: "1"
      POSTGRES_HOST: postgres
      POSTGRES_DB: datawarehouse
      POSTGRES_USER: projects
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      ODDS_API_KEY: ${ODDS_API_KEY}
      PUSHOVER_TOKEN: ${PUSHOVER_TOKEN}
      PUSHOVER_USER: ${PUSHOVER_USER}
      DROPBOX_APP_KEY: ${DROPBOX_APP_KEY}
      DROPBOX_APP_SECRET: ${DROPBOX_APP_SECRET}
      DROPBOX_REFRESH_TOKEN: ${DROPBOX_REFRESH_TOKEN}
      FPL_TEAM_ID: ${FPL_TEAM_ID}
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'
    networks:
      - app-network

  predictions-league:
    build:
      context: ./services/predictions-league
      dockerfile: Dockerfile
    container_name: predictions-league
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      TZ: Europe/London
      PYTHONUNBUFFERED: "1"
      FLASK_APP: app
      DATABASE_URL: postgresql://projects:${POSTGRES_PASSWORD}@postgres:5432/datawarehouse?options=-c%20search_path%3Dpl,public
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
    networks:
      - app-network

  # db-sync is not needed until Phase 12 (production deployment to PythonAnywhere).
  # Uncomment when ready:
  #
  # db-sync:
  #   build:
  #     context: ./services/db-sync
  #     dockerfile: Dockerfile
  #   container_name: db-sync
  #   restart: unless-stopped
  #   depends_on:
  #     postgres:
  #       condition: service_healthy
  #   environment:
  #     TZ: Europe/London
  #     POSTGRES_HOST: postgres
  #     POSTGRES_DB: datawarehouse
  #     POSTGRES_USER: projects
  #     POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  #     PA_MYSQL_HOST: ${PA_MYSQL_HOST}
  #     PA_MYSQL_USER: ${PA_MYSQL_USER}
  #     PA_MYSQL_PASSWORD: ${PA_MYSQL_PASSWORD}
  #     PA_MYSQL_DB: ${PA_MYSQL_DB}
  #   deploy:
  #     resources:
  #       limits:
  #         memory: 256M
  #         cpus: '0.5'
  #   networks:
  #     - app-network

  betting-syndicate:
    build:
      context: ./services/betting-syndicate
      dockerfile: Dockerfile
    container_name: betting-syndicate
    restart: unless-stopped
    volumes:
      - betting-data:/app/database
      - betting-uploads:/app/uploads
    environment:
      TZ: Europe/London
      PYTHONUNBUFFERED: "1"
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
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
    depends_on:
      - betting-syndicate
      - predictions-league
    networks:
      - app-network

volumes:
  pg-data:
  collector-logs:
  collector-samples:
  betting-data:
  betting-uploads:

networks:
  app-network:
    driver: bridge
```

### 9.2 Local DNS

Add to your router's DNS or each client's `/etc/hosts`:

```
<VM-IP-ADDRESS>  betting.local
<VM-IP-ADDRESS>  predictions.local
```

### 9.3 Tailscale MagicDNS

Once Tailscale is running on the VM, the machine is accessible as `projects-server` on your Tailnet. You can also use Tailscale's MagicDNS to access `betting.local` and `predictions.local` from anywhere.

### 9.4 Auto-Start on Boot

Create a systemd service so Docker Compose starts on boot:

```bash
sudo tee /etc/systemd/system/football-platform.service << 'EOF'
[Unit]
Description=Football Platform Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/projects/football-platform
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable football-platform
```

### 9.5 Docker Log Rotation

Create `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Restart Docker: `sudo systemctl restart docker`

**Checkpoint:** `sudo reboot` the VM, wait 2 minutes, verify `docker compose ps` shows all containers running. Tailscale shows the VM online.

---

## Phase 10 — Hardening

**Goal:** Automated backups, monitoring, and Alembic initialised for future schema changes.

### 10.1 Automated PostgreSQL Backups

Add to the host's crontab (`crontab -e`):

```cron
# Daily PostgreSQL backup at 3 AM
0 3 * * * docker exec postgres pg_dump -U projects datawarehouse | gzip > /opt/projects/football-platform/backups/postgres_$(date +\%Y\%m\%d).sql.gz

# Weekly betting syndicate SQLite backup
0 4 * * 0 docker cp betting-syndicate:/app/database/betting_syndicate.db /opt/projects/football-platform/backups/betting_syndicate_$(date +\%Y\%m\%d).db

# Prune backups older than 14 days
0 5 * * * find /opt/projects/football-platform/backups -mtime +14 -delete
```

### 10.2 Resource Monitoring

Quick health check script — create `scripts/healthcheck.sh`:

```bash
#!/bin/bash
echo "=== Container Status ==="
docker compose ps

echo ""
echo "=== PostgreSQL ==="
docker exec postgres pg_isready -U projects -d datawarehouse

echo ""
echo "=== Disk Usage ==="
docker system df

echo ""
echo "=== Volume Sizes ==="
docker system df -v | grep -A 50 "VOLUME NAME"

echo ""
echo "=== Recent Errors (last hour) ==="
docker compose logs --since 1h 2>&1 | grep -i "error" | tail -20
```

### 10.3 Alembic Init (for future migrations)

```bash
cd /opt/projects/football-platform
pip install alembic psycopg2-binary
alembic init migrations
```

Update `migrations/env.py` to point at your PostgreSQL instance. This gives you proper schema migration tooling for any future table changes instead of ad-hoc SQL scripts.

### 10.4 Backup Verification

Test restoring from a backup periodically:

```bash
# Restore to a test database
gunzip -c backups/postgres_20260219.sql.gz | \
    docker exec -i postgres psql -U projects -d postgres -c "CREATE DATABASE test_restore;"
gunzip -c backups/postgres_20260219.sql.gz | \
    docker exec -i postgres psql -U projects -d test_restore

# Verify
docker exec postgres psql -U projects -d test_restore -c "SELECT COUNT(*) FROM pl.fixtures;"

# Cleanup
docker exec postgres psql -U projects -d postgres -c "DROP DATABASE test_restore;"
```

**Checkpoint:** Backup cron jobs are installed. `healthcheck.sh` runs without errors. At least one backup file exists in `/opt/projects/football-platform/backups/`.

---

## Phase 11 — Verification & Cutover

**Goal:** Full confidence that the new platform works, then power off old VMs.

### Verification Checklist

#### PostgreSQL
- [ ] Database running: `docker exec postgres pg_isready`
- [ ] Schema created: `docker exec postgres psql -U projects -d datawarehouse -c "\dt pl.*"` shows 24 tables
- [ ] Data migrated: row counts match SQLite source for all key tables
- [ ] Indexes created: `SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'pl';`

#### Data Collector (Scheduler)
- [ ] Container running: `docker compose ps data-collector`
- [ ] APScheduler started: `docker logs data-collector | grep "Starting APScheduler"`
- [ ] `fetch_results` runs every minute: check logs for "Completed fetch_results"
- [ ] `monitor_and_upload` runs every minute
- [ ] `clean_predictions_dropbox` runs at :00/:15/:30/:45
- [ ] `fetch_fixtures_gameweeks` runs at :00/:30
- [ ] `automated_predictions` runs at :00 each hour
- [ ] `fetch_fpl_data` runs at 07:00
- [ ] `fetch_odds` runs at 07:00
- [ ] `fetch_fpl_picks` runs at 07:05
- [ ] `fetch_pulse_data` runs at 08:00
- [ ] `fetch_football_data` runs Sunday 09:00
- [ ] `update_recommendations` runs Sunday 10:00
- [ ] `verify_predictions` runs at 11:00
- [ ] Dropbox OAuth token refresh works (check keys.json modification time)
- [ ] Scripts writing to PostgreSQL (query `pl.last_update` for recent timestamps)

#### Predictions League App

- [ ] Container running: `docker compose ps predictions-league`
- [ ] Webapp loads at `http://predictions.local`
- [ ] Querying live data from PostgreSQL warehouse (not stale/cached)
- [ ] Leaderboard, fixtures, and predictions pages all rendering correctly

#### Betting Syndicate
- [ ] Dashboard loads at `http://betting.local`
- [ ] Can create/edit bets with screenshot uploads
- [ ] Ledger entries preserved from migration
- [ ] Season data intact

#### Infrastructure
- [ ] All containers restart after VM reboot
- [ ] Tailscale access works from external devices
- [ ] Docker logs rotating (not filling disk)
- [ ] PostgreSQL backups running daily at 03:00
- [ ] Betting syndicate backups running weekly
- [ ] Firewall configured (only 22, 80, tailscale0)

### Rollback Plan

If something goes wrong:

1. **Immediate:** Power the old VMs back on — they still have everything running
2. **DNS:** Point `betting.local` back to the old betting VM IP
3. **PythonAnywhere:** The old predictions_league_v2 on PythonAnywhere continues to work with the old `monitor_and_upload.py` on the old VM
4. **Data:** Old SQLite databases are backed up and untouched

### Decommission Timeline

| Week | Action |
|------|--------|
| 0 | New platform live, old VMs powered off but preserved |
| 1 | Monitor new platform, check logs daily |
| 2 | Take Proxmox snapshots of old VMs |
| 3 | If everything stable, delete old VMs |
| 4 | Remove Proxmox snapshots (or keep one for archive) |

**Checkpoint:** All checklist items are ticked. Old VMs powered off. You're running on one VM.

---

## Phase 12 — Production Deployment to PythonAnywhere

**Goal:** Deploy the predictions league app to PythonAnywhere backed by MySQL, with the db-sync container keeping data in sync from the warehouse.

This phase is **deferred** — do it when the local platform (Phases 0-11) is stable and the new predictions league app is feature-complete. Until then, the old predictions_league_v2 on PythonAnywhere continues to work.

### 12.1 Set Up MySQL on PythonAnywhere

1. Go to **PythonAnywhere** → **Databases** tab
2. Set a MySQL password (if not already set)
3. Create a new database — PythonAnywhere prefixes it with your username, e.g. `yourusername$predictions`
4. Note your credentials:
   - **Host:** `yourusername.mysql.pythonanywhere-services.com`
   - **Username:** `yourusername`
   - **Password:** (the one you just set)
   - **Database:** `yourusername$predictions`

### 12.2 Create MySQL Tables

Open a MySQL console from the PythonAnywhere Databases tab:

```sql
-- Only the tables the predictions league webapp needs
-- These mirror the pl schema in the PostgreSQL warehouse

CREATE TABLE teams (
    team_id INT PRIMARY KEY,
    fpl_id INT,
    team_name VARCHAR(100),
    available TINYINT(1) DEFAULT 0,
    strength INT,
    strength_overall_home INT,
    strength_overall_away INT,
    strength_attack_home INT,
    strength_attack_away INT,
    strength_defence_home INT,
    strength_defence_away INT,
    pulse_id INT,
    football_data_name VARCHAR(100),
    odds_api_name VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fixtures (
    fpl_fixture_id INT NOT NULL,
    fixture_id INT PRIMARY KEY,
    kickoff_dttm DATETIME,
    home_teamid INT NOT NULL,
    away_teamid INT NOT NULL,
    finished TINYINT(1) DEFAULT 1,
    season VARCHAR(20),
    home_win_odds FLOAT,
    draw_odds FLOAT,
    away_win_odds FLOAT,
    pulse_id INT,
    gameweek INT,
    started TINYINT(1) DEFAULT 0,
    provisional_finished TINYINT(1) DEFAULT 0,
    FOREIGN KEY (home_teamid) REFERENCES teams(team_id),
    FOREIGN KEY (away_teamid) REFERENCES teams(team_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE players (
    player_id INT PRIMARY KEY,
    player_name VARCHAR(100),
    paid INT NOT NULL DEFAULT 0,
    active INT NOT NULL DEFAULT 0,
    mini_league INT NOT NULL DEFAULT 0,
    mini_league_paid INT NOT NULL DEFAULT 0,
    pundit INT NOT NULL DEFAULT 0,
    web_name VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE predictions (
    prediction_id INT PRIMARY KEY AUTO_INCREMENT,
    player_id INT NOT NULL,
    fixture_id INT NOT NULL,
    fpl_fixture_id INT,
    home_goals INT NOT NULL,
    away_goals INT NOT NULL,
    predicted_result VARCHAR(5) NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE results (
    result_id INT PRIMARY KEY AUTO_INCREMENT,
    fpl_fixture_id INT NOT NULL,
    fixture_id INT,
    home_goals INT,
    away_goals INT,
    result VARCHAR(5),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE gameweeks (
    gameweek INT PRIMARY KEY,
    deadline_dttm DATETIME,
    deadline_date DATE,
    deadline_time TIME,
    current_gameweek TINYINT(1),
    next_gameweek TINYINT(1),
    finished TINYINT(1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fixture_odds_summary (
    fixture_id INT PRIMARY KEY,
    home_team_id INT NOT NULL,
    away_team_id INT NOT NULL,
    avg_home_win_odds FLOAT,
    avg_draw_odds FLOAT,
    avg_away_win_odds FLOAT,
    bookmaker_count INT,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id),
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE last_update (
    table_name VARCHAR(100) PRIMARY KEY,
    updated VARCHAR(100),
    timestamp DOUBLE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
CREATE INDEX idx_fixtures_season ON fixtures(season);
CREATE INDEX idx_fixtures_gameweek ON fixtures(gameweek);
CREATE INDEX idx_predictions_player_fixture ON predictions(player_id, fixture_id);
CREATE INDEX idx_predictions_fixture_id ON predictions(fixture_id);
CREATE INDEX idx_gameweeks_current ON gameweeks(current_gameweek);
```

### 12.3 Enable the DB-Sync Container

Uncomment the `db-sync` service in `docker-compose.yml` and add the PythonAnywhere MySQL credentials to `.env`:

```bash
# Add to .env
PA_MYSQL_HOST=yourusername.mysql.pythonanywhere-services.com
PA_MYSQL_USER=yourusername
PA_MYSQL_PASSWORD=your-mysql-password
PA_MYSQL_DB=yourusername$predictions
```

The `services/db-sync/sync.py` script reads from PostgreSQL and writes to PythonAnywhere MySQL every 2 minutes, using `last_update` timestamps for change detection.

Create `services/db-sync/sync.py`, `services/db-sync/Dockerfile`, and `services/db-sync/requirements.txt` — see the [db-sync directory](#phase-2--monorepo-scaffold) in the scaffold for the files. The sync script should:

1. Connect to PostgreSQL (source) and MySQL (target)
2. Check `pl.last_update` for changes since last sync
3. Full-replace small tables (teams, players, gameweeks, fixtures, results, fixture_odds_summary)
4. Upsert large tables (predictions)
5. Update `last_update` on MySQL
6. Run in a `while true; sleep 120` loop

The `services/db-sync/requirements.txt`:

```
psycopg2-binary>=2.9.0
pymysql>=1.1.0
```

> **PythonAnywhere MySQL access:** Paid accounts ($5/month) can access MySQL from external IPs. Free accounts cannot — you'd need to run the sync as a PythonAnywhere scheduled task instead.

### 12.4 Deploy the Predictions League App

Deploy the **same app** from Phase 6 to PythonAnywhere. The only change is `DATABASE_URL`:

```python
# On PythonAnywhere, set in the WSGI configuration or .env:
DATABASE_URL=mysql+pymysql://user:pass@user.mysql.pythonanywhere-services.com/user$predictions
```

Since the app uses SQLAlchemy, no code changes are needed. The models, queries, and templates all work identically on MySQL.

**Note:** If your SQLAlchemy models use `schema="pl"`, remove that for the production deployment (MySQL doesn't use schemas the same way). The recommended approach from Phase 6.5 is to omit `schema` from models and set `search_path=pl` in the PostgreSQL connection string only.

### 12.5 Verification

- [ ] db-sync container running: `docker logs db-sync`
- [ ] MySQL on PythonAnywhere has data: `SELECT COUNT(*) FROM fixtures WHERE season='2025/2026';`
- [ ] Predictions league app on PythonAnywhere loads and shows correct data
- [ ] Data updates within 2-3 minutes of changes in the warehouse
- [ ] Old predictions_league_v2 decommissioned

**Checkpoint:** The predictions league is live on PythonAnywhere, backed by MySQL, synced from the warehouse.

---

## Appendix A — Complete `.env.example`

Create `.env.example` (committed to git as a template):

```bash
# ============================================================================
# Football Platform Environment Variables
# ============================================================================
# Copy this file to .env and fill in the values:
#   cp .env.example .env && chmod 600 .env
# ============================================================================

# --- PostgreSQL ---
POSTGRES_PASSWORD=change-this-to-a-secure-password

# --- Odds API ---
ODDS_API_KEY=your-odds-api-key

# --- Pushover Notifications ---
PUSHOVER_TOKEN=your-pushover-app-token
PUSHOVER_USER=your-pushover-user-key

# --- Dropbox OAuth2 ---
DROPBOX_APP_KEY=your-dropbox-app-key
DROPBOX_APP_SECRET=your-dropbox-app-secret
DROPBOX_REFRESH_TOKEN=your-dropbox-refresh-token
# Note: access token and expiry are managed automatically via keys.json

# --- FPL ---
FPL_TEAM_ID=your-fpl-team-id

# --- PythonAnywhere MySQL (Phase 12 — uncomment when ready) ---
# PA_MYSQL_HOST=yourusername.mysql.pythonanywhere-services.com
# PA_MYSQL_USER=yourusername
# PA_MYSQL_PASSWORD=your-pythonanywhere-mysql-password
# PA_MYSQL_DB=yourusername$predictions
```

---

## Appendix B — Maintenance Quick Reference

```bash
# ===== Starting & Stopping =====
cd /opt/projects/football-platform
docker compose up -d                  # Start everything
docker compose down                   # Stop everything
docker compose restart data-collector # Restart one service

# ===== Logs =====
docker logs -f data-collector         # Follow scheduler logs
docker logs -f predictions-league      # Follow predictions app logs
docker logs -f betting-syndicate      # Follow betting logs
docker compose logs --since 1h        # All logs from last hour
docker compose logs --since 1h 2>&1 | grep -i error  # Errors only

# ===== PostgreSQL =====
docker exec -it postgres psql -U projects -d datawarehouse
# Inside psql:
#   \dt pl.*                          -- List all tables
#   SELECT * FROM pl.last_update ORDER BY timestamp DESC LIMIT 5;
#   SELECT COUNT(*) FROM pl.fixtures WHERE season='2025/2026';
#   SELECT COUNT(*) FROM pl.predictions;

# ===== Backups =====
# Manual PostgreSQL backup
docker exec postgres pg_dump -U projects datawarehouse > backups/manual_backup.sql

# Manual betting syndicate backup
docker cp betting-syndicate:/app/database/betting_syndicate.db backups/

# Restore PostgreSQL from backup
cat backups/manual_backup.sql | docker exec -i postgres psql -U projects -d datawarehouse

# ===== Rebuilding =====
docker compose build                  # Rebuild all images
docker compose build data-collector   # Rebuild one image
docker compose up -d --build          # Rebuild and restart

# ===== Shell Access =====
docker exec -it data-collector bash
docker exec -it betting-syndicate bash
docker exec -it postgres bash

# ===== Disk & Resources =====
docker system df                      # Disk usage summary
docker stats --no-stream              # CPU/memory per container
docker system prune -f                # Clean unused images/containers

# ===== Debugging =====
docker compose ps                     # Container status
docker inspect data-collector         # Full container details
docker exec data-collector python -c "from shared.db import get_connection; print('DB OK')"
```
