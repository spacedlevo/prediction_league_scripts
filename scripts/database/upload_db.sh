#!/bin/bash

# Local file to upload
LOCAL_FILE="/home/levo/Documents/projects/prediction_league_script/data/database.db"

# Remote connection details
REMOTE_USER="predictionleague"
REMOTE_HOST="192.168.0.150"
REMOTE_PATH="/home/predictionleague/projects/prediction_league_scripts/data/database.db"   # Change this if you want a specific destination directory

# Upload the file
scp "$LOCAL_FILE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"

# Check result
if [ $? -eq 0 ]; then
    echo "Upload completed successfully."
else
    echo "Upload failed." >&2
    exit 1
fi
