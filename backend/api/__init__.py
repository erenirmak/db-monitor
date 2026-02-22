from flask import Blueprint, jsonify, request, session

from backend.auth import get_user_permissions

# Import and register all sub-blueprints
from .backup import backup_bp
from .databases import databases_bp
from .grants import grants_bp
from .introspection import introspection_bp
from .query import query_bp
from .roles import roles_bp
from .users import users_bp

api_bp = Blueprint("api", __name__)


@api_bp.before_request
def check_api_access():
    """Ensure the user has the base 'api_access' permission for any API route."""
    if request.method == "OPTIONS":
        return

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    perms = get_user_permissions(user_id)
    if "api_access" not in perms:
        return jsonify({"error": "API access denied. You do not have the 'api_access' permission."}), 403


api_bp.register_blueprint(databases_bp)
api_bp.register_blueprint(introspection_bp)
api_bp.register_blueprint(query_bp)
api_bp.register_blueprint(users_bp)
api_bp.register_blueprint(roles_bp)
api_bp.register_blueprint(grants_bp)
api_bp.register_blueprint(backup_bp)
