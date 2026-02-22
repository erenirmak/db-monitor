from flask import Flask


def register_blueprints(app: Flask) -> None:
    from backend.api import api_bp
    from backend.auth.routes import auth_bp
    from backend.web.views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
