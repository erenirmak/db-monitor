from flask import Blueprint, jsonify, request, session

from backend.auth import (
    admin_reset_password,
    change_password,
    create_user,
    delete_user,
    get_all_users,
    login_required,
    requires_permission,
    update_user_role,
)

users_bp = Blueprint("users", __name__)


@users_bp.route("/profile/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    user_id = session.get("user_id", "")

    success, message = change_password(user_id, old_password, new_password)
    return jsonify({"success": success, "message": message})


@users_bp.route("/users", methods=["GET"])
@login_required
@requires_permission("manage_users")
def api_get_users():
    users = get_all_users()
    return jsonify({"users": users})


@users_bp.route("/users", methods=["POST"])
@login_required
@requires_permission("manage_users")
def api_create_user():
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")
    role = data.get("role", "viewer")

    ok, msg = create_user(username, password)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400

    if role != "viewer":
        update_user_role(username, role)

    return jsonify({"success": True, "message": msg})


@users_bp.route("/users/<username>/role", methods=["PUT"])
@login_required
@requires_permission("manage_users")
def api_update_user_role(username: str):
    data = request.json or {}
    role = data.get("role", "")
    ok, msg = update_user_role(username, role)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})


@users_bp.route("/users/<username>/password", methods=["PUT"])
@login_required
@requires_permission("manage_users")
def api_admin_reset_password(username: str):
    data = request.json or {}
    password = data.get("password", "")
    ok, msg = admin_reset_password(username, password)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})


@users_bp.route("/users/<username>", methods=["DELETE"])
@login_required
@requires_permission("manage_users")
def api_delete_user(username: str):
    ok, msg = delete_user(username)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})
