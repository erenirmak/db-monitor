"""
Authentication module — supports two modes controlled by environment variables.

Modes
-----
- ``local``  (default) — username + password login, PBKDF2-hashed, stored in
  SQLite.  Multiple local accounts are supported.
- ``ldap``             — username + password verified against an LDAP / LLDAP
  server.

Environment variables
---------------------
AUTH_MODE              "local" | "ldap"  (default: "local")

LDAP-mode variables:
  LDAP_URL             e.g. ldap://localhost:3890
  LDAP_BASE_DN         e.g. dc=example,dc=com
  LDAP_USER_DN_TEMPLATE  e.g. uid={username},ou=people,dc=example,dc=com
                         Use ``{username}`` as placeholder.
  LDAP_BIND_DN         Admin bind DN for search-based auth (optional).
  LDAP_BIND_PASSWORD   Admin bind password (optional).
  LDAP_USER_FILTER     e.g. (&(objectClass=person)(uid={username}))
  LDAP_REQUIRE_GROUP   DN of a group the user must belong to (optional).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from functools import wraps
from pathlib import Path
from typing import List, Optional

from flask import redirect, request, session, url_for

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_db_path: Path | None = None

AUTH_MODE: str = "local"  # "local" or "ldap"

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
)
"""


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def init_auth(data_dir: str | Path) -> None:
    """Initialise the auth sub-system.  Must be called once at startup."""
    global _db_path, AUTH_MODE

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "auth.db"

    AUTH_MODE = os.environ.get("AUTH_MODE", "local").lower().strip()
    if AUTH_MODE not in ("local", "ldap"):
        AUTH_MODE = "local"

    with _get_conn() as conn:
        conn.execute(_CREATE_USERS_TABLE)

    # Migrate: if old single-password 'auth' table exists, drop it
    with _get_conn() as conn:
        try:
            conn.execute("DROP TABLE IF EXISTS auth")
        except Exception:
            pass


def _get_conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("Auth not initialised — call init_auth() first.")
    return sqlite3.connect(str(_db_path))


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 + random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User management (local mode)
# ---------------------------------------------------------------------------


def create_user(username: str, password: str) -> tuple[bool, str]:
    """Create a new local user.  Returns (ok, message)."""
    username = username.strip().lower()
    if not username:
        return False, "Username is required."
    if len(password) < 4:
        return False, "Password must be at least 4 characters."

    with _get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return False, f'User "{username}" already exists.'

        hashed = _hash_password(password)
        from datetime import datetime

        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hashed, datetime.now().isoformat()),
        )
    return True, f'User "{username}" created successfully.'


def any_users_exist() -> bool:
    """Check if any local user accounts have been created yet."""
    with _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Authentication logic
# ---------------------------------------------------------------------------


def authenticate_local(username: str, password: str) -> tuple[bool, str]:
    """Verify a local username + password.  Returns (success, message)."""
    username = username.strip().lower()
    if not username:
        return False, "Username is required."

    with _get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()

    if row is None:
        return False, "Invalid username or password."

    if _verify_password(password, row[0]):
        return True, "OK"
    return False, "Invalid username or password."


def authenticate_ldap(username: str, password: str) -> tuple[bool, str]:
    """Verify credentials against an LDAP / LLDAP server."""
    try:
        import ldap3
    except ImportError:
        return False, "ldap3 package is not installed.  Run:  uv add ldap3"

    ldap_url = os.environ.get("LDAP_URL", "").strip()
    base_dn = os.environ.get("LDAP_BASE_DN", "").strip()
    user_dn_template = os.environ.get("LDAP_USER_DN_TEMPLATE", "").strip()
    bind_dn = os.environ.get("LDAP_BIND_DN", "").strip()
    bind_pw = os.environ.get("LDAP_BIND_PASSWORD", "").strip()
    user_filter = os.environ.get("LDAP_USER_FILTER", "").strip()
    require_group = os.environ.get("LDAP_REQUIRE_GROUP", "").strip()

    if not ldap_url or not base_dn:
        return False, "LDAP_URL and LDAP_BASE_DN must be set."

    try:
        server = ldap3.Server(ldap_url, get_info=ldap3.NONE, connect_timeout=5)

        # --- Strategy 1: direct bind with DN template ---
        if user_dn_template:
            user_dn = user_dn_template.replace("{username}", username)
            conn = ldap3.Connection(server, user=user_dn, password=password)
            if not conn.bind():
                return False, "Invalid credentials."

        # --- Strategy 2: search-bind ---
        elif bind_dn and user_filter:
            admin_conn = ldap3.Connection(server, user=bind_dn, password=bind_pw)
            if not admin_conn.bind():
                return False, "LDAP admin bind failed — check LDAP_BIND_DN/PASSWORD."

            search_filter = user_filter.replace("{username}", username)
            admin_conn.search(base_dn, search_filter, attributes=["dn"])
            if not admin_conn.entries:
                return False, "User not found in LDAP directory."

            user_dn = str(admin_conn.entries[0].entry_dn)
            admin_conn.unbind()

            conn = ldap3.Connection(server, user=user_dn, password=password)
            if not conn.bind():
                return False, "Invalid credentials."
        else:
            return False, (
                "LDAP config incomplete — set either LDAP_USER_DN_TEMPLATE "
                "or both LDAP_BIND_DN + LDAP_USER_FILTER."
            )

        # --- Optional group membership check ---
        if require_group:
            conn.search(
                require_group,
                f"(member={user_dn})",
                search_scope=ldap3.BASE,
            )
            if not conn.entries:
                conn.unbind()
                return False, "User is not a member of the required group."

        conn.unbind()
        return True, "OK"

    except ldap3.core.exceptions.LDAPSocketOpenError:
        return False, f"Cannot reach LDAP server at {ldap_url}"
    except Exception as exc:
        return False, f"LDAP error: {exc}"


def authenticate(username: str, password: str) -> tuple[bool, str]:
    """Top-level dispatcher — picks the right backend."""
    if not username:
        return False, "Username is required."
    if AUTH_MODE == "ldap":
        return authenticate_ldap(username, password)
    return authenticate_local(username, password)


# ---------------------------------------------------------------------------
# Session helper
# ---------------------------------------------------------------------------


def get_current_user() -> Optional[str]:
    """Return the logged-in username from the Flask session, or None."""
    return session.get("user_id")


# ---------------------------------------------------------------------------
# Flask decorator / middleware
# ---------------------------------------------------------------------------


def login_required(f):
    """Decorator that protects a route — redirects to /login if not authed."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated") or not session.get("user_id"):
            if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                from flask import jsonify

                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth_views.login"))
        return f(*args, **kwargs)

    return decorated
