from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app() -> Flask:
    """Application factory — creates and configures the Flask app."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object("backend.config.Config")

    # Initialize extensions
    socketio.init_app(app, cors_allowed_origins="*")

    # ---- Encryption + persistent storage + auth --------------------
    from datetime import timedelta
    from backend.config import Config as _cfg
    from backend.crypto import init_crypto
    from backend.storage import init_storage
    from backend.auth import init_auth

    init_crypto(_cfg.DATA_DIR)
    init_storage(_cfg.DATA_DIR)
    init_auth(_cfg.DATA_DIR)
    # Connections are loaded per-user on login — no global load_saved_connections().

    # Make sessions permanent so the cookie survives browser restarts
    app.permanent_session_lifetime = timedelta(
        seconds=_cfg.PERMANENT_SESSION_LIFETIME
    )
    # -----------------------------------------------------------------

    # Register blueprints
    from backend.routes import register_blueprints
    register_blueprints(app)

    # Register SocketIO handlers
    from backend import sockets  # noqa: F401

    return app
