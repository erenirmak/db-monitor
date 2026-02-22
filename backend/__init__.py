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
    app.config.from_object("backend.core.config.Config")

    # Initialize extensions
    socketio.init_app(app, cors_allowed_origins="*")

    # ---- Encryption + persistent storage + auth --------------------
    from datetime import timedelta

    from backend.auth import init_auth
    from backend.core.config import Config as _cfg
    from backend.core.crypto import init_crypto
    from backend.core.telemetry import init_telemetry
    from backend.database.storage import init_storage

    init_telemetry()
    init_crypto(_cfg.DATA_DIR)
    init_storage(_cfg.DATA_DIR)
    init_auth(_cfg.DATA_DIR)

    # Instrument Flask app for OpenTelemetry
    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    FlaskInstrumentor().instrument_app(app)

    # Connections are loaded per-user on login — no global load_saved_connections().

    # Make sessions permanent so the cookie survives browser restarts
    app.permanent_session_lifetime = timedelta(seconds=_cfg.PERMANENT_SESSION_LIFETIME)
    # -----------------------------------------------------------------

    # Register blueprints
    from backend.web.routes import register_blueprints

    register_blueprints(app)

    # Register SocketIO handlers
    from backend.web import sockets  # noqa: F401

    return app
