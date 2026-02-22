from flask import Blueprint, jsonify, request

from backend.auth import (
    create_grant,
    delete_grant,
    get_all_grants,
    login_required,
    requires_permission,
)

grants_bp = Blueprint("grants", __name__)


@grants_bp.route("/grants", methods=["GET"])
@login_required
@requires_permission("manage_users")
def api_get_grants():
    grants = get_all_grants()
    return jsonify({"grants": grants})


@grants_bp.route("/grants", methods=["POST"])
@login_required
@requires_permission("manage_users")
def api_create_grant():
    data = request.json or {}
    username = data.get("username", "")
    db_key = data.get("db_key", "")
    role = data.get("role", "")

    ok, msg = create_grant(username, db_key, role)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})


@grants_bp.route("/grants/<username>/<db_key>", methods=["DELETE"])
@login_required
@requires_permission("manage_users")
def api_delete_grant(username: str, db_key: str):
    ok, msg = delete_grant(username, db_key)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})
