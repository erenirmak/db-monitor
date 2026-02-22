"""Application configuration."""

import os
from pathlib import Path

# Base directory of the db-monitor project
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "change-me-in-production-" + os.urandom(8).hex(),
    )
    MONITOR_INTERVAL = 5  # seconds between status checks

    # Directory where encrypted credentials DB + secret key are stored.
    # Override via the  DB_MONITOR_DATA_DIR  env var.
    DATA_DIR = os.environ.get("DB_MONITOR_DATA_DIR", str(BASE_DIR / "data"))

    # Permanent session lifetime (seconds).  Default: 7 days.
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME", 7 * 24 * 3600))

    # -----------------------------------------------------------------------
    # Enterprise Readiness Scaffolding (Phase 1-5)
    # -----------------------------------------------------------------------

    # Phase 1: External Secrets
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

    # Phase 2: SSO Integration (OIDC) & Network Security
    OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID")
    OIDC_AUTHORITY = os.environ.get("OIDC_AUTHORITY")
    SSL_CA_BUNDLE = os.environ.get("SSL_CA_BUNDLE")  # Path to custom internal CA certificate
    ENFORCE_DB_SSL = os.environ.get("ENFORCE_DB_SSL", "false").lower() == "true"

    # Phase 3: Scalability & High Availability
    CONTROL_PLANE_DB_URI = os.environ.get("CONTROL_PLANE_DB_URI")  # e.g., postgresql://user:pass@host/db
    REDIS_URL = os.environ.get("REDIS_URL")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL")

    # Phase 5: AI & Automation
    AI_BASE_URL = os.environ.get("AI_BASE_URL")  # e.g., http://internal-vllm:8000/v1
    AI_API_KEY = os.environ.get("AI_API_KEY")
    STRICT_PRIVACY_MODE = os.environ.get("STRICT_PRIVACY_MODE", "false").lower() == "true"
    ALLOWED_AI_ENDPOINTS = os.environ.get("ALLOWED_AI_ENDPOINTS", "")  # Comma-separated list
