#!/bin/bash

# === Configuration ===
REMOTE_USER="predictionleague"
REMOTE_HOST="192.168.0.150"
REMOTE_PATH="/home/predictionleague/projects/prediction_league_scripts/data/database.db"
LOCAL_BACKUP_DIR="/home/levo/Documents/projects/prediction_league_script/data/"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
LOCAL_COPY="${LOCAL_BACKUP_DIR}/database.db"

# === Ensure local directory exists ===
mkdir -p "$LOCAL_BACKUP_DIR"

# === Sync the file ===
rsync -avz --progress ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH} "$LOCAL_COPY"
