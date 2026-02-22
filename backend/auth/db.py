import os
import sqlite3
from pathlib import Path

_db_path: Path | None = None
AUTH_MODE: str = "local"

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer'
)
"""

_CREATE_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS roles (
    name          TEXT PRIMARY KEY,
    description   TEXT,
    permissions   TEXT NOT NULL, -- JSON array of permission strings
    is_system     INTEGER NOT NULL DEFAULT 0 -- 1 for built-in roles (admin, editor, viewer)
)
"""

_CREATE_DB_GRANTS_TABLE = """
CREATE TABLE IF NOT EXISTS user_database_grants (
    username      TEXT NOT NULL,
    db_key        TEXT NOT NULL,
    role          TEXT NOT NULL,
    PRIMARY KEY (username, db_key),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (role) REFERENCES roles(name) ON DELETE CASCADE
)
"""


def get_conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("Auth not initialised — call init_auth() first.")
    return sqlite3.connect(str(_db_path))


def init_auth(data_dir: str | Path) -> None:
    """Initialise the auth sub-system.  Must be called once at startup."""
    global _db_path, AUTH_MODE

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "auth.db"

    AUTH_MODE = os.environ.get("AUTH_MODE", "local").lower().strip()
    if AUTH_MODE not in ("local", "ldap"):
        AUTH_MODE = "local"

    with get_conn() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(_CREATE_USERS_TABLE)
        conn.execute(_CREATE_ROLES_TABLE)
        conn.execute(_CREATE_DB_GRANTS_TABLE)

        # Seed default roles if they don't exist
        import json

        admin_perms = json.dumps(
            [
                "api_access",
                "manage_users",
                "manage_roles",
                "manage_connections",
                "execute_sql_read",
                "execute_sql_write",
                "execute_sql_ddl",
            ]
        )
        editor_perms = json.dumps(["api_access", "manage_connections", "execute_sql_read", "execute_sql_write"])
        viewer_perms = json.dumps(["api_access", "execute_sql_read"])

        conn.execute(
            "INSERT OR IGNORE INTO roles (name, description, permissions, is_system) VALUES (?, ?, ?, ?)",
            ("admin", "Full system access", admin_perms, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO roles (name, description, permissions, is_system) VALUES (?, ?, ?, ?)",
            ("editor", "Can manage connections and write data", editor_perms, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO roles (name, description, permissions, is_system) VALUES (?, ?, ?, ?)",
            ("viewer", "Read-only access", viewer_perms, 1),
        )

        # Migration: Add api_access to existing roles if missing
        rows = conn.execute("SELECT name, permissions FROM roles").fetchall()
        for name, perms_json in rows:
            perms = json.loads(perms_json)
            if "api_access" not in perms:
                perms.append("api_access")
                conn.execute("UPDATE roles SET permissions = ? WHERE name = ?", (json.dumps(perms), name))

        # Migration: Add role column if it doesn't exist
        try:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'")
            # If this succeeds, it means the column was just added.
            # Let's make the first user an admin if they exist.
            conn.execute(
                "UPDATE users SET role = 'admin' "
                "WHERE rowid = (SELECT rowid FROM users ORDER BY created_at ASC LIMIT 1)"
            )
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # Migrate: if old single-password 'auth' table exists, drop it
    with get_conn() as conn:
        try:
            conn.execute("DROP TABLE IF EXISTS auth")
        except Exception:
            pass
