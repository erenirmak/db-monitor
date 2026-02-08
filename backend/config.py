"""Application configuration."""

import os
from pathlib import Path

# Base directory of the db-monitor project
BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "change-me-in-production-" + os.urandom(8).hex(),
    )
    MONITOR_INTERVAL = 5  # seconds between status checks

    # Directory where encrypted credentials DB + secret key are stored.
    # Override via the  DB_MONITOR_DATA_DIR  env var.
    DATA_DIR = os.environ.get(
        "DB_MONITOR_DATA_DIR", str(BASE_DIR / "data")
    )

    # Permanent session lifetime (seconds).  Default: 7 days.
    PERMANENT_SESSION_LIFETIME = int(
        os.environ.get("SESSION_LIFETIME", 7 * 24 * 3600)
    )
