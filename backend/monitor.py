"""Background thread that periodically checks every registered database."""

from __future__ import annotations

import time
import threading

from backend.connection import DATABASES, db_status, check_db_status


def monitor_databases(app, socketio, interval: int = 5) -> None:
    """
    Continuously ping every registered database and update status.

    Status updates are stored in ``db_status``.  Each connected client
    receives only its own databases' updates via the SocketIO ``connect``
    and ``check_status`` handlers — the monitor itself does **not** broadcast.
    """
    while True:
        try:
            for db_key in list(DATABASES.keys()):
                check_db_status(db_key)
            time.sleep(interval)
        except Exception as exc:
            print(f"Error in monitor_databases: {exc}")
            time.sleep(interval)


def start_monitor(app, socketio, interval: int = 5) -> threading.Thread:
    """Spawn the monitoring daemon thread and return it."""
    t = threading.Thread(
        target=monitor_databases,
        args=(app, socketio, interval),
        daemon=True,
    )
    t.start()
    return t
