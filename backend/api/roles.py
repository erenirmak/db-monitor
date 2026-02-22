from flask import Blueprint, jsonify, request

from backend.auth import (
    create_role,
    delete_role,
    get_all_roles,
    login_required,
    requires_permission,
)

roles_bp = Blueprint("roles", __name__)


@roles_bp.route("/roles", methods=["GET"])
@login_required
@requires_permission("manage_roles")
def api_get_roles():
    roles = get_all_roles()
    return jsonify({"roles": roles})


@roles_bp.route("/roles", methods=["POST"])
@login_required
@requires_permission("manage_roles")
def api_create_role():
    data = request.json or {}
    name = data.get("name", "")
    permissions = data.get("permissions", [])
    description = data.get("description", "")

    ok, msg = create_role(name, permissions, description)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})


@roles_bp.route("/roles/<name>", methods=["DELETE"])
@login_required
@requires_permission("manage_roles")
def api_delete_role(name: str):
    ok, msg = delete_role(name)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})
