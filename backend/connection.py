"""
Database connection management.

Handles building connection strings, creating engines, testing connections,
and maintaining runtime state (registry, connection cache, status tracking).
"""

from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Runtime stores  (populated from SQLite on startup via load_saved_connections)
# ---------------------------------------------------------------------------

# { db_key: { engine, url, display_name, extra_options } }
DATABASES: Dict[str, Dict[str, Any]] = {}

# Cached SQLAlchemy Engine instances
db_connections: Dict[str, Any] = {}

# { db_key: { connected, last_check, error } }
db_status: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_db_key() -> str:
    """Generate a random 12-char key for a new connection."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


def build_connection_string(db_type: str, fields: Dict[str, str]) -> Optional[str]:
    """
    Build a SQLAlchemy connection URL from the form fields.

    Returns *None* for unsupported / non-SQLAlchemy types (mongodb, opensearch,
    elasticsearch).
    """
    try:
        user = fields.get("username", "")
        password = fields.get("password", "")
        host = fields.get("host", "localhost")
        database = fields.get("database", "")
        credentials = f"{user}:{password}@" if user else ""

        if db_type == "postgresql":
            port = fields.get("port", "5432")
            return f"postgresql://{credentials}{host}:{port}/{database}"

        if db_type == "mysql":
            port = fields.get("port", "3306")
            return f"mysql+pymysql://{credentials}{host}:{port}/{database}"

        if db_type == "mssql":
            port = fields.get("port", "1433")
            driver = fields.get("driver", "ODBC+Driver+17+for+SQL+Server")
            return f"mssql+pyodbc://{credentials}{host}:{port}/{database}?driver={driver}"

        if db_type == "oracle":
            port = fields.get("port", "1521")
            return f"oracle+cx_oracle://{credentials}{host}:{port}/{database}"

        if db_type == "sqlite":
            file_path = fields.get("filePath", "database.db")
            return f"sqlite:///{file_path}"

        if db_type == "folder":
            return "folder://"

        return None  # mongodb, opensearch, elasticsearch, etc.
    except Exception as exc:
        print(f"Error building connection string: {exc}")
        return None


def _parse_extra_options(extra_options: Optional[Dict[str, Any]]) -> dict:
    """
    Split the user-provided Extra JSON into ``engine_kwargs`` and
    ``connect_args``.

    The Extra JSON may contain:
    - ``connect_args``:  dict passed directly to the DBAPI ``connect()``.
    - anything else:     forwarded as keyword args to ``create_engine()``.

    Example Extra JSON::

        {
            "connect_args": {"connect_timeout": 10, "sslmode": "require"},
            "pool_size": 5,
            "pool_pre_ping": true
        }
    """
    if not extra_options:
        return {"engine_kwargs": {}, "connect_args": {}}

    opts = dict(extra_options)  # shallow copy
    connect_args = opts.pop("connect_args", {})
    return {"engine_kwargs": opts, "connect_args": connect_args}


def _create_engine_from_url(
    url: str,
    extra_options: Optional[Dict[str, Any]] = None,
    *,
    use_null_pool: bool = True,
) -> Any:
    """Create a SQLAlchemy engine merging user-provided extra options."""
    parsed = _parse_extra_options(extra_options)

    kwargs: dict = {"echo": False}
    if use_null_pool:
        kwargs["poolclass"] = NullPool

    # Merge engine-level options (pool_size, pool_pre_ping, …)
    kwargs.update(parsed["engine_kwargs"])

    # Merge connect_args (timeout, sslmode, …)
    if parsed["connect_args"]:
        kwargs["connect_args"] = parsed["connect_args"]

    return create_engine(url, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def test_connection_string(
    db_type: str,
    connection_string: str,
    extra_options: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Test whether a connection URL is reachable.  Returns (ok, message)."""
    if db_type == "folder":
        return True, "Folder created"

    try:
        engine = _create_engine_from_url(connection_string, extra_options, use_null_pool=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True, "Connection successful"
    except Exception as exc:
        return False, str(exc)


def get_db_connection(db_key: str) -> Any:
    """Return (or lazily create) the cached engine for *db_key*."""
    if db_key not in db_connections:
        db_config = DATABASES.get(db_key)
        if db_config is None:
            return None

        # Skip creating engine for folders
        if db_config.get("engine") == "folder":
            return None

        try:
            engine = _create_engine_from_url(
                db_config["url"],
                db_config.get("extra_options"),
                use_null_pool=True,
            )
            db_connections[db_key] = engine
        except Exception as exc:
            # Only log errors for real database types, suppress for known virtual types if any
            print(f"Error creating connection for {db_key}: {exc}")
            return None
    return db_connections[db_key]


def check_db_status(db_key: str) -> bool:
    """Ping the database and update ``db_status``."""
    db_config = DATABASES.get(db_key)
    if db_config and db_config.get("engine") == "folder":
        # Always return "connected" for folders so they don't show errors
        db_status[db_key] = {
            "connected": True,
            "error": None,
            "last_check": datetime.now().isoformat(),
        }
        return True

    try:
        engine = get_db_connection(db_key)
        if engine is None:
            db_status[db_key] = {
                "connected": False,
                "error": "Connection failed",
                "last_check": datetime.now().isoformat(),
            }
            return False

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        db_status[db_key] = {
            "connected": True,
            "error": None,
            "last_check": datetime.now().isoformat(),
        }
        return True
    except Exception as exc:
        db_status[db_key] = {
            "connected": False,
            "error": str(exc),
            "last_check": datetime.now().isoformat(),
        }
        return False


def register_connection(
    name: str,
    db_type: str,
    connection_string: str,
    extra_options: Optional[Dict[str, Any]] = None,
    fields: Optional[Dict[str, str]] = None,
    *,
    user_id: str = "",
    persist: bool = True,
    group_name: str = "",
    sort_order: int = 0,
    db_key: Optional[str] = None,
) -> str:
    """
    Add a new connection to the runtime registry **and** persist it
    (encrypted) to the SQLite store.

    If *db_key* is provided (e.g. update), uses it. Otherwise generates new.
    Returns the db_key.
    """
    if not db_key:
        db_key = generate_db_key()

    DATABASES[db_key] = {
        "engine": db_type,
        "url": connection_string,
        "display_name": name,
        "extra_options": extra_options or {},
        "fields": fields or {},
        "user_id": user_id,
        "group_name": group_name,
        "sort_order": sort_order,
    }
    db_status[db_key] = {"connected": False, "last_check": None, "error": None}

    # Persist to encrypted SQLite storage
    if persist:
        try:
            from backend.storage import save_connection

            save_connection(
                db_key=db_key,
                display_name=name,
                engine_type=db_type,
                fields=fields or {},
                connection_url=connection_string,
                extra_options=extra_options,
                user_id=user_id,
                group_name=group_name,
                sort_order=sort_order,
            )
        except Exception as exc:
            print(f"Warning: failed to persist connection {db_key}: {exc}")

    check_db_status(db_key)
    return db_key


def unregister_connection(db_key: str) -> Optional[str]:
    """
    Remove a connection from the registry **and** from persistent storage.

    Returns the display name if found, else *None*.
    """
    if db_key not in DATABASES:
        return None

    name = DATABASES[db_key].get("display_name", db_key)
    del DATABASES[db_key]

    db_status.pop(db_key, None)

    engine = db_connections.pop(db_key, None)
    if engine is not None:
        try:
            engine.dispose()
        except Exception:
            pass

    # Remove from encrypted SQLite storage
    try:
        from backend.storage import delete_connection

        delete_connection(db_key)
    except Exception as exc:
        print(f"Warning: failed to delete persisted connection {db_key}: {exc}")

    return name


def load_saved_connections(user_id: str = "") -> int:
    """
    Load connections for a specific user from the encrypted SQLite store
    into the runtime registry.  Can be called at startup or on user login.

    Returns the number of connections loaded.
    """
    from backend.storage import load_all_connections

    rows = load_all_connections(user_id=user_id)
    count = 0
    # DATABASES stores connections for ALL users. Do not clear globally.

    for row in rows:
        db_key = row["db_key"]
        # Update or insert the connection config
        DATABASES[db_key] = {
            "engine": row["engine_type"],
            "url": row["url"],
            "display_name": row["display_name"],
            "extra_options": row.get("extra_options", {}),
            "fields": row.get("fields", {}),
            "user_id": row.get("user_id", ""),
            "group_name": row.get("group_name", ""),
            "sort_order": row.get("sort_order", 0),
        }
        if db_key not in db_status:
            db_status[db_key] = {"connected": False, "last_check": None, "error": None}
        count += 1

    if count:
        print(f"Loaded/Updated {count} saved connection(s) for user '{user_id}'.")
    return count


def get_user_databases(user_id: str) -> Dict[str, Dict[str, Any]]:
    """Return only the DATABASES entries belonging to *user_id*."""
    return {k: v for k, v in DATABASES.items() if v.get("user_id", "") == user_id}


def user_owns_db(user_id: str, db_key: str) -> bool:
    """Check if a db_key belongs to the given user."""
    entry = DATABASES.get(db_key)
    if entry is None:
        return False
    return entry.get("user_id", "") == user_id


def update_db_metadata(db_key: str, group_name: Optional[str] = None, sort_order: Optional[int] = None) -> bool:
    """Update runtime and persistent metadata for a connection."""
    if db_key not in DATABASES:
        return False

    # Update runtime
    if group_name is not None:
        DATABASES[db_key]["group_name"] = group_name
    if sort_order is not None:
        DATABASES[db_key]["sort_order"] = sort_order

    # Update persistence
    try:
        from backend.storage import update_connection_metadata

        return update_connection_metadata(db_key, group_name, sort_order)
    except Exception as exc:
        print(f"Warning: failed to persist metadata update for {db_key}: {exc}")
        return False
