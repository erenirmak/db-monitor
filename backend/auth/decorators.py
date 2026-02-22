from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def login_required(f):
    """Decorator that protects a route — redirects to /login if not authed."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated") or not session.get("user_id"):
            if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth_views.login"))
        return f(*args, **kwargs)

    return decorated


def require_permission(permission: str):
    """Decorator to require a specific permission."""

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            username = session.get("user_id")
            if not username:
                return jsonify({"error": "Authentication required"}), 401

            db_key = kwargs.get("db_key")
            if not db_key:
                db_key = request.args.get("db_key") or (request.json.get("db_key") if request.is_json else None)

            from .core import has_permission

            if not has_permission(username, permission, db_key):
                return jsonify({"error": f"Forbidden: Requires '{permission}' permission"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator
