"""Background thread that periodically checks every registered database."""

from __future__ import annotations

import logging
import threading
import time

from backend.core.telemetry import get_meter
from backend.database.connection import DATABASES, check_db_status

logger = logging.getLogger(__name__)

# OpenTelemetry Metrics
meter = get_meter()
db_ping_counter = meter.create_counter(
    "db_monitor.ping.count",
    description="Number of database pings performed",
)
db_failure_counter = meter.create_counter(
    "db_monitor.ping.failures",
    description="Number of database ping failures",
)


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
                is_up = check_db_status(db_key)

                # Record metrics
                db_type = DATABASES[db_key].get("engine", "unknown")
                labels = {"db_key": db_key, "db_type": db_type}
                db_ping_counter.add(1, labels)
                if not is_up:
                    db_failure_counter.add(1, labels)

            time.sleep(interval)
        except Exception:
            logger.error("Error in monitor_databases", exc_info=True)
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
