"""Register all route blueprints on the app."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from backend.routes.views import views_bp
    from backend.routes.api import api_bp
    from backend.routes.auth_routes import auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
