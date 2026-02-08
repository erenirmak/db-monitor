"""
SQLite-backed persistent storage for saved database connections.

Every sensitive field (host, port, username, password, connection URL, and
the Extra-JSON blob) is stored encrypted.  Non-sensitive metadata
(display_name, engine type) is stored in plaintext.

Schema::

    saved_connections(
        db_key        TEXT PRIMARY KEY,
        display_name  TEXT NOT NULL,
        engine_type   TEXT NOT NULL,
        host_enc      TEXT,
        port_enc      TEXT,
        username_enc  TEXT,
        password_enc  TEXT,
        database_enc  TEXT,
        url_enc       TEXT NOT NULL,
        extra_json_enc TEXT,
        created_at    TEXT NOT NULL
    )
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.crypto import encrypt, decrypt

_db_path: Path | None = None

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS saved_connections (
    db_key          TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    engine_type     TEXT NOT NULL,
    host_enc        TEXT,
    port_enc        TEXT,
    username_enc    TEXT,
    password_enc    TEXT,
    database_enc    TEXT,
    file_path_enc   TEXT,
    url_enc         TEXT NOT NULL,
    extra_json_enc  TEXT,
    created_at      TEXT NOT NULL
)
"""


def init_storage(data_dir: str | Path) -> None:
    """Create the data directory and initialize the SQLite schema."""
    global _db_path
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "connections.db"

    with _get_conn() as conn:
        conn.execute(_CREATE_TABLE)

        # Migrate: add user_id column if missing (pre-existing DBs)
        try:
            conn.execute(
                "ALTER TABLE saved_connections ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
            )
            print("Migration: added user_id column to saved_connections")
        except sqlite3.OperationalError:
            pass  # column already exists


def _get_conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("Storage not initialised — call init_storage() first.")
    return sqlite3.connect(str(_db_path))


# ------------------------------------------------------------------
# Write operations
# ------------------------------------------------------------------

def save_connection(
    db_key: str,
    display_name: str,
    engine_type: str,
    fields: Dict[str, str],
    connection_url: str,
    extra_options: Optional[Dict[str, Any]] = None,
    user_id: str = "",
) -> None:
    """Encrypt sensitive fields and insert/replace into SQLite."""
    host_enc = encrypt(fields.get("host", "")) if fields.get("host") else None
    port_enc = encrypt(fields.get("port", "")) if fields.get("port") else None
    user_enc = encrypt(fields.get("username", "")) if fields.get("username") else None
    pass_enc = encrypt(fields.get("password", "")) if fields.get("password") else None
    db_enc = encrypt(fields.get("database", "")) if fields.get("database") else None
    fp_enc = encrypt(fields.get("filePath", "")) if fields.get("filePath") else None
    url_enc = encrypt(connection_url)
    extra_enc = encrypt(json.dumps(extra_options)) if extra_options else None

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO saved_connections
                (db_key, user_id, display_name, engine_type,
                 host_enc, port_enc, username_enc, password_enc,
                 database_enc, file_path_enc, url_enc, extra_json_enc, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                db_key,
                user_id,
                display_name,
                engine_type,
                host_enc,
                port_enc,
                user_enc,
                pass_enc,
                db_enc,
                fp_enc,
                url_enc,
                extra_enc,
                datetime.now().isoformat(),
            ),
        )


def delete_connection(db_key: str) -> bool:
    """Remove a saved connection.  Returns True if a row was deleted."""
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM saved_connections WHERE db_key = ?", (db_key,)
        )
        return cur.rowcount > 0


# ------------------------------------------------------------------
# Read operations
# ------------------------------------------------------------------

def load_all_connections(user_id: str = "") -> List[Dict[str, Any]]:
    """
    Read saved connections for a specific user, decrypt the sensitive fields,
    and return a list of dicts ready for ``connection.register_connection()``.

    Each dict has keys:
        db_key, display_name, engine_type, url, extra_options, fields, user_id
    """
    with _get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM saved_connections WHERE user_id = ?", (user_id,)
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            url = decrypt(row["url_enc"])
        except Exception:
            # If decryption fails (key changed?), skip this entry
            print(f"⚠ Skipping connection {row['db_key']}: decryption failed")
            continue

        extra: dict | None = None
        if row["extra_json_enc"]:
            try:
                extra = json.loads(decrypt(row["extra_json_enc"]))
            except Exception:
                extra = {}

        # Reconstruct fields (best-effort, used for display only)
        fields: dict[str, str] = {}
        for col, key in [
            ("host_enc", "host"),
            ("port_enc", "port"),
            ("username_enc", "username"),
            ("password_enc", "password"),
            ("database_enc", "database"),
            ("file_path_enc", "filePath"),
        ]:
            if row[col]:
                try:
                    fields[key] = decrypt(row[col])
                except Exception:
                    pass

        results.append(
            {
                "db_key": row["db_key"],
                "display_name": row["display_name"],
                "engine_type": row["engine_type"],
                "url": url,
                "extra_options": extra or {},
                "fields": fields,
                "user_id": row["user_id"] if "user_id" in row.keys() else "",
            }
        )

    return results
