#!/usr/bin/env python3
"""
Push database to local prediction league server via SCP.

Uploads database.db to predictionleague@predictions.local using SSH key auth.
"""

import subprocess
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database.db"
LOG_DIR = PROJECT_ROOT / "logs"

REMOTE_USER = "predictionleague"
REMOTE_HOST = "predictions.local"
REMOTE_PATH = "/home/predictionleague/projects/prediction_league_scripts/data/database.db"


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"push_local_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def push_database(logger, dry_run=False):
    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        return False

    db_size_mb = DB_PATH.stat().st_size / 1024 / 1024
    remote_dest = f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}"

    logger.info(f"Database: {DB_PATH.name} ({db_size_mb:.2f} MB)")
    logger.info(f"Destination: {remote_dest}")

    if dry_run:
        logger.info("DRY RUN - no file transferred")
        return True

    try:
        result = subprocess.run(
            ["scp", "-o", "ConnectTimeout=10", str(DB_PATH), remote_dest],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info("Database pushed successfully")
            return True
        else:
            logger.error(f"SCP failed (exit {result.returncode}): {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("SCP timed out after 120 seconds")
        return False
    except FileNotFoundError:
        logger.error("scp command not found")
        return False


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Push database to predictionleague@predictions.local'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would happen without transferring')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    logger = setup_logging()
    logger.info("Starting database push to predictions.local...")

    success = push_database(logger, dry_run=args.dry_run)
    if success:
        logger.info("Push completed successfully")
    else:
        logger.error("Push failed")
        sys.exit(1)
