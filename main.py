"""
Database Monitor — entry point.

All application logic lives inside the ``backend`` package.
Run with:  uv run python main.py
"""

from backend import create_app, socketio
from backend.config import Config
from backend.monitor import start_monitor

app = create_app()

if __name__ == "__main__":
    start_monitor(app, socketio, interval=Config.MONITOR_INTERVAL)
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
