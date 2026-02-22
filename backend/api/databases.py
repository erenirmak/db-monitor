from flask import Blueprint, jsonify, request, session

from backend.auth import login_required, requires_permission
from backend.core.audit import log_audit_event
from backend.database.connection import (
    DATABASES,
    build_connection_string,
    db_status,
    get_user_databases,
    register_connection,
    test_connection_string,
    unregister_connection,
    update_db_metadata,
    user_owns_db,
)

from .utils import _parse_extra_json

databases_bp = Blueprint("databases", __name__)


@databases_bp.route("/databases")
@login_required
def get_databases():
    user_id = session.get("user_id", "")
    databases = []
    user_dbs = get_user_databases(user_id)

    for db_key, config in user_dbs.items():
        safe_fields = config.get("fields", {}).copy()
        if "password" in safe_fields:
            safe_fields["password"] = ""

        databases.append(
            {
                "key": db_key,
                "name": config["display_name"],
                "engine": config["engine"],
                "fields": safe_fields,
                "extra_json": config.get("extra_options", {}),
                "status": db_status.get(db_key, {}),
                "group": config.get("group_name", ""),
                "order": config.get("sort_order", 0),
            }
        )

    databases.sort(key=lambda x: (x["order"], x["name"]))
    return jsonify(databases)


@databases_bp.route("/reorder-databases", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def reorder_databases():
    user_id = session.get("user_id", "")
    updates = request.get_json().get("updates", [])
    if not updates or not isinstance(updates, list):
        return jsonify({"success": False, "error": "Invalid updates payload"}), 400

    for item in updates:
        db_key = item.get("key")
        if not db_key or not user_owns_db(user_id, db_key):
            continue

        group_name = item.get("group")
        sort_order = item.get("order")
        update_db_metadata(db_key, group_name=group_name, sort_order=sort_order)

    return jsonify({"success": True})


@databases_bp.route("/test-connection", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_test_connection():
    try:
        data = request.json
        db_type = (data.get("type") or "").lower()
        fields = data.get("fields", {})
        extra_json_str = data.get("extra_json", "")

        if not db_type or not fields:
            return jsonify({"success": False, "error": "Database type and fields are required"}), 400

        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify({"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            return jsonify({"success": False, "error": f"Unsupported database type: {db_type}"}), 400

        success, message = test_connection_string(db_type, connection_string, extra_options or None)
        return jsonify({"success": success, "error": message if not success else None, "message": message})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@databases_bp.route("/save-connection", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_save_connection():
    try:
        data = request.json
        name = (data.get("name") or "").strip()
        db_type = (data.get("type") or "").lower()
        fields = data.get("fields", {})
        extra_json_str = data.get("extra_json", "")
        group_name = (data.get("group") or "").strip()
        db_key_input = data.get("id") or None
        user_id = session.get("user_id", "")

        if not name or not db_type:
            return jsonify({"success": False, "error": "Connection name and type are required"}), 400

        if db_type != "folder" and not fields:
            return jsonify({"success": False, "error": "Connection fields are required"}), 400

        if group_name:
            folder_exists = False
            for key, conf in DATABASES.items():
                if (
                    conf.get("user_id") == user_id
                    and conf.get("engine") == "folder"
                    and conf.get("display_name") == group_name
                ):
                    folder_exists = True
                    break

            if not folder_exists:
                register_connection(
                    name=group_name,
                    db_type="folder",
                    connection_string="folder://",
                    extra_options={},
                    fields={},
                    user_id=user_id,
                    group_name=group_name,
                )

        sort_order = 0
        if db_key_input:
            if not user_owns_db(user_id, db_key_input):
                return jsonify({"success": False, "error": "Access denied or database not found."}), 403
            existing_conf = DATABASES.get(db_key_input, {})
            sort_order = existing_conf.get("sort_order", 0)
            existing_fields = existing_conf.get("fields", {})
            for key, val in fields.items():
                if key == "password" and not val:
                    fields[key] = existing_fields.get("password", "")

        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify({"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            if db_type == "folder":
                connection_string = "folder://"
            else:
                return jsonify({"success": False, "error": f"Unsupported database type: {db_type}"}), 400

        if db_type != "folder":
            success, message = test_connection_string(db_type, connection_string, extra_options or None)
            if not success:
                return jsonify({"success": False, "error": f"Connection test failed: {message}"}), 400

        db_key = register_connection(
            name,
            db_type,
            connection_string,
            extra_options or None,
            fields=fields,
            user_id=user_id,
            group_name=group_name,
            sort_order=sort_order,
            db_key=db_key_input,
        )

        log_audit_event(
            action="update_connection" if db_key_input else "create_connection",
            user_id=user_id,
            resource_type="database",
            resource_id=db_key,
            details={"name": name, "type": db_type},
        )

        return jsonify(
            {"success": True, "db_key": db_key, "message": f'Connection "{name}" saved successfully'}
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@databases_bp.route("/connections/reorder", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_reorder_connections():
    user_id = session.get("user_id", "")
    try:
        data = request.json
        updates = data.get("updates", [])
        count = 0

        for item in updates:
            db_key = item.get("key")
            if not db_key or not user_owns_db(user_id, db_key):
                continue

            group = item.get("group")
            order = item.get("order")

            if update_db_metadata(db_key, group_name=group, sort_order=order):
                count += 1

        return jsonify({"success": True, "message": f"Updated {count} connections"})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@databases_bp.route("/delete-folder", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_delete_folder():
    user_id = session.get("user_id", "")
    data = request.json
    folder_name = (data.get("name") or "").strip()

    if not folder_name:
        return jsonify({"success": False, "error": "Folder name required"}), 400

    user_dbs = get_user_databases(user_id)
    folder_db_key = None
    count_moved = 0

    for key, conf in user_dbs.items():
        if conf.get("engine") == "folder" and conf.get("display_name") == folder_name:
            folder_db_key = key
        if conf.get("group_name") == folder_name:
            update_db_metadata(key, group_name="")
            count_moved += 1

    if folder_db_key:
        unregister_connection(folder_db_key)

    return jsonify({"success": True, "message": f"Folder deleted. {count_moved} connections moved to root."})


@databases_bp.route("/disconnect/<db_key>", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_disconnect(db_key: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"success": False, "error": "Database not found"}), 404

    name = unregister_connection(db_key)
    if name is None:
        return jsonify({"success": False, "error": "Database not found"}), 404

    log_audit_event(
        action="delete_connection",
        user_id=user_id,
        resource_type="database",
        resource_id=db_key,
        details={"name": name},
    )

    return jsonify({"success": True, "message": f'Connection "{name}" removed successfully'})
