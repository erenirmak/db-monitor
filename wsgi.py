import eventlet

eventlet.monkey_patch()

from backend import create_app, socketio  # noqa: E402
from backend.core.config import Config  # noqa: E402
from backend.services.monitor import start_monitor  # noqa: E402

app = create_app()
start_monitor(app, socketio, interval=Config.MONITOR_INTERVAL)

if __name__ == "__main__":
    # This file is intended to be run by Gunicorn:
    # gunicorn --worker-class eventlet -w 1 wsgi:app
    socketio.run(app)
