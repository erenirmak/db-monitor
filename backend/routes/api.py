"""REST API routes."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import Blueprint, jsonify, make_response, request, session
from sqlalchemy import inspect, text

from backend.auth import change_password, login_required
from backend.connection import (
    DATABASES,
    build_connection_string,
    db_status,
    get_db_connection,
    get_user_databases,
    load_saved_connections,
    register_connection,
    test_connection_string,
    unregister_connection,
    user_owns_db,
)

api_bp = Blueprint("api", __name__)


# ------------------------------------------------------------------
# Database listing
# ------------------------------------------------------------------


@api_bp.route("/databases")
@login_required
def get_databases():
    user_id = session.get("user_id", "")
    databases = []
    # Sort locally by custom sort order then by name?
    # Actually client side can sort, but server side sort is nicer.
    # However, user_databases returns dict.
    user_dbs = get_user_databases(user_id)

    for db_key, config in user_dbs.items():
        # Mask password in fields before sending to frontend
        safe_fields = config.get("fields", {}).copy()
        if "password" in safe_fields:
            safe_fields["password"] = ""  # Clear password for security

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

    # Optional: Sort by order then name
    databases.sort(key=lambda x: (x["order"], x["name"]))

    return jsonify(databases)


@api_bp.route("/reorder-databases", methods=["POST"])
@login_required
def reorder_databases():
    """Update group and order for a batch of connections."""
    user_id = session.get("user_id", "")
    updates = request.get_json().get("updates", [])
    if not updates or not isinstance(updates, list):
        return jsonify({"success": False, "error": "Invalid updates payload"}), 400

    from backend.connection import update_db_metadata

    for item in updates:
        db_key = item.get("key")
        if not db_key:
            continue

        # Security check
        if not user_owns_db(user_id, db_key):
            continue

        # Extract fields (allow partial updates)
        group_name = item.get("group")
        sort_order = item.get("order")

        update_db_metadata(db_key, group_name=group_name, sort_order=sort_order)

    return jsonify({"success": True})


# ------------------------------------------------------------------
# Schema / table introspection
# ------------------------------------------------------------------


@api_bp.route("/database/<db_key>/schemas")
@login_required
def get_schemas(db_key: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404
        return jsonify({"error": "Database not found"}), 404
    try:
        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500
        inspector = inspect(engine)
        return jsonify({"schemas": inspector.get_schema_names()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/database/<db_key>/schema/<schema>/tables")
@login_required
def get_tables(db_key: str, schema: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404
        return jsonify({"error": "Database not found"}), 404
    try:
        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500
        inspector = inspect(engine)
        db_config = DATABASES[db_key]

        if db_config["engine"] == "sqlite":
            tables = inspector.get_table_names()
            try:
                views = inspector.get_view_names()
            except Exception:
                views = []
        else:
            tables = inspector.get_table_names(schema=schema)
            try:
                views = inspector.get_view_names(schema=schema)
            except Exception:
                views = []

        return jsonify({"tables": tables, "views": views})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@api_bp.route("/database/<db_key>/schema/<schema>/table/<table>")
@login_required
def get_table_info(db_key: str, schema: str, table: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404
        return jsonify({"error": "Database not found"}), 404
    try:
        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500

        inspector = inspect(engine)
        columns_info = inspector.get_columns(table, schema=schema if schema != "default" else None)
        columns = [{"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]} for c in columns_info]

        with engine.connect() as conn:
            if schema and schema != "default":
                result = conn.execute(text(f"SELECT * FROM {schema}.{table} LIMIT 100"))
            else:
                result = conn.execute(text(f"SELECT * FROM {table} LIMIT 100"))
            rows = result.fetchall()
            data = [dict(row._mapping) for row in rows]

        return jsonify({"columns": columns, "data": data, "row_count": len(data)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ------------------------------------------------------------------
# SQL execution
# ------------------------------------------------------------------


@api_bp.route("/database/<db_key>/execute", methods=["POST"])
@login_required
def execute_sql(db_key: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404
        return jsonify({"error": "Database not found"}), 404
    try:
        data = request.json
        sql = (data.get("sql") or "").strip()
        if not sql:
            return jsonify({"error": "No SQL provided"}), 400

        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500

        with engine.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                rows = result.fetchall()
                data_out = [dict(row._mapping) for row in rows]
                return jsonify(
                    {
                        "success": True,
                        "data": data_out,
                        "row_count": len(data_out),
                        "columns": list(result.keys()) if result.keys() else [],
                    }
                )
            return jsonify(
                {
                    "success": True,
                    "rows_affected": result.rowcount,
                    "message": (f"Query executed successfully. Rows affected: {result.rowcount}"),
                }
            )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


# ------------------------------------------------------------------
# Connection management
# ------------------------------------------------------------------


@api_bp.route("/test-connection", methods=["POST"])
@login_required
def api_test_connection():
    """Test a database connection without saving it."""
    try:
        data = request.json
        db_type = (data.get("type") or "").lower()
        fields = data.get("fields", {})
        extra_json_str = data.get("extra_json", "")

        if not db_type or not fields:
            return jsonify({"success": False, "error": "Database type and fields are required"}), 400

        # Parse extra JSON
        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify({"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            return jsonify({"success": False, "error": f"Unsupported database type: {db_type}"}), 400

        success, message = test_connection_string(db_type, connection_string, extra_options or None)
        return jsonify(
            {
                "success": success,
                "error": message if not success else None,
                "message": message,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@api_bp.route("/save-connection", methods=["POST"])
@login_required
def api_save_connection():
    """Save and activate a new or existing database connection."""
    try:
        data = request.json
        name = (data.get("name") or "").strip()
        db_type = (data.get("type") or "").lower()
        fields = data.get("fields", {})
        extra_json_str = data.get("extra_json", "")
        group_name = (data.get("group") or "").strip()
        db_key_input = data.get("id") or None
        user_id = session.get("user_id", "")

        # For folder type, fields can be empty.
        if not name or not db_type:
            return jsonify({"success": False, "error": "Connection name and type are required"}), 400

        if db_type != "folder" and not fields:
            return jsonify({"success": False, "error": "Connection fields are required"}), 400

        # Auto-create folder if a group name is specified but the folder doesn't exist
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
                # Create the missing folder automatically
                print(f"Auto-creating folder '{group_name}' for user {user_id}")
                register_connection(
                    name=group_name,
                    db_type="folder",
                    connection_string="folder://",
                    extra_options={},
                    fields={},
                    user_id=user_id,
                    group_name=group_name,  # Self-reference or empty? Frontend expects group logic.
                    # Wait, if I set group_name=group_name, the folder item itself is in the group.
                    # Frontend logic:
                    # if (db.engine === 'folder') {
                    #    const groupName = db.group || db.name;
                    #    if (!groups[groupName]) groups[groupName] = [];
                    #    return;
                    # }
                    # So checking db.group is fine.
                )

        # Check ownership and preserve sort_order/passwords if updating
        sort_order = 0
        if db_key_input:
            if not user_owns_db(user_id, db_key_input):
                return jsonify({"success": False, "error": "Access denied or database not found."}), 403
            # Preserve existing sort order and FILL IN MISSING PASSWORDS
            existing_conf = DATABASES.get(db_key_input, {})
            sort_order = existing_conf.get("sort_order", 0)

            # If passwords are empty in the new fields, reuse the old fields
            existing_fields = existing_conf.get("fields", {})
            for key, val in fields.items():
                if key == "password" and not val:
                    # If user sent empty password, keep old one
                    fields[key] = existing_fields.get("password", "")
                elif (key == "host" or key == "username") and not val:
                    # Also keep host/username if empty? User might want to clear them?
                    # Let's assume for editing, if visible field is empty, it means empty.
                    # Password is special because we mask it.
                    pass

        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify({"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            # Special case for folder type connection (handled inside build_connection_string or bypass here)
            if db_type == "folder":
                connection_string = "folder://"
            else:
                return jsonify({"success": False, "error": f"Unsupported database type: {db_type}"}), 400

        # Test before saving (skip for folders)
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
        print(f"Database connection saved: {db_key} ({name})")

        return jsonify(
            {
                "success": True,
                "db_key": db_key,
                "message": f'Connection "{name}" saved successfully',
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@api_bp.route("/connections/reorder", methods=["POST"])
@login_required
def api_reorder_connections():
    """Update group and sort order for multiple connections."""
    user_id = session.get("user_id", "")
    try:
        # Payload: { "updates": [ { "key": "...", "group": "...", "order": 0 }, ... ] }
        data = request.json
        updates = data.get("updates", [])

        count = 0
        from backend.connection import update_db_metadata

        for item in updates:
            db_key = item.get("key")
            # Security check: must match current user
            if not db_key or not user_owns_db(user_id, db_key):
                continue

            group = item.get("group")
            order = item.get("order")

            # update_db_metadata handles None values by skipping updates,
            # so we ensure we pass what we have.
            if update_db_metadata(db_key, group_name=group, sort_order=order):
                count += 1

        return jsonify({"success": True, "message": f"Updated {count} connections"})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@api_bp.route("/delete-folder", methods=["POST"])
@login_required
def api_delete_folder():
    """Delete a folder and ungroup its contents."""
    user_id = session.get("user_id", "")
    data = request.json
    folder_name = (data.get("name") or "").strip()

    if not folder_name:
        return jsonify({"success": False, "error": "Folder name required"}), 400

    from backend.connection import get_user_databases, unregister_connection, update_db_metadata

    user_dbs = get_user_databases(user_id)
    folder_db_key = None

    count_moved = 0
    for key, conf in user_dbs.items():
        # Check if this is the folder record itself
        if conf.get("engine") == "folder" and conf.get("display_name") == folder_name:
            folder_db_key = key
            # continue explicitly not needed but good for clarity, though we might have duplicates?
            # actually we search for all contents first usually.

        # Check if this connection is INSIDE the folder
        if conf.get("group_name") == folder_name:
            # Ungroup it
            update_db_metadata(key, group_name="")
            count_moved += 1

    # Delete the folder record(s) - handle potential duplicates
    deleted = False
    if folder_db_key:
        unregister_connection(folder_db_key)
        deleted = True

    # If we didn't find a specific folder record but did move items, that's fine (legacy tag behavior)
    # If we found nothing, maybe return error? But success is safer UX.

    return jsonify({"success": True, "message": f"Folder deleted. {count_moved} connections moved to root."})


@api_bp.route("/disconnect/<db_key>", methods=["POST"])
@login_required
def api_disconnect(db_key: str):
    """Disconnect and remove a database connection."""
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"success": False, "error": "Database not found"}), 404

    name = unregister_connection(db_key)
    if name is None:
        return jsonify({"success": False, "error": "Database not found"}), 404

    print(f"Database connection removed: {db_key} ({name})")
    return jsonify({"success": True, "message": f'Connection "{name}" removed successfully'})


# ------------------------------------------------------------------
# User Profile & Backup
# ------------------------------------------------------------------


@api_bp.route("/profile/change-password", methods=["POST"])
@login_required
def api_change_password():
    """Change the current user's password."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    user_id = session.get("user_id", "")

    success, message = change_password(user_id, old_password, new_password)
    return jsonify({"success": success, "message": message})


@api_bp.route("/connections/export", methods=["POST"])
@login_required
def api_export_connections():
    """Reserved for encrypted export with password."""
    user_id = session.get("user_id", "")
    data = request.json
    password = data.get("password")

    if not password:
        return jsonify({"success": False, "error": "Encryption password required"}), 400

    import base64
    import os

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # 1. Gather Data
    user_dbs = get_user_databases(user_id)
    export_data = []
    for _, config in user_dbs.items():
        # Clean export format
        item = {
            "name": config.get("display_name", "Untitled"),
            "engine": config.get("engine", "unknown"),
            "url": config.get("url", ""),
            "options": config.get("extra_options", {}),
            "group": config.get("group_name", ""),
            "order": config.get("sort_order", 0),
            "fields": config.get("fields", {}),  # Include fields for easier restore
        }
        export_data.append(item)

    json_bytes = json.dumps(export_data).encode("utf-8")

    # 2. Derive Key
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    f = Fernet(key)

    # 3. Encrypt
    encrypted_data = f.encrypt(json_bytes)

    # 4. Return format: Salt (16 bytes) + Encrypted Data
    # We'll encode the whole thing as base64 for safe transport/storage as text file
    final_payload = base64.b64encode(salt + encrypted_data).decode("utf-8")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"db_monitor_backup_{timestamp}.enc"

    return jsonify({"success": True, "filename": filename, "data": final_payload})


@api_bp.route("/connections/import", methods=["POST"])
@login_required
def api_import_connections():
    """Import encrypted connections."""
    user_id = session.get("user_id", "")
    data = request.json
    password = data.get("password")
    payload = data.get("data")

    if not password or not payload:
        return jsonify({"success": False, "error": "Password and data required"}), 400

    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    try:
        # 1. Decode payload
        raw_bytes = base64.b64decode(payload)

        # 2. Extract Salt (first 16 bytes)
        salt = raw_bytes[:16]
        encrypted_data = raw_bytes[16:]

        # 3. Derive Key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        f = Fernet(key)

        # 4. Decrypt
        decrypted_json = f.decrypt(encrypted_data)
        connections = json.loads(decrypted_json)

        # 5. Restore
        count = 0
        from backend.connection import register_connection

        for item in connections:
            # Check if name exists? For now, we just add them as new or update by matching name?
            # Strategy: Just register. duplicates allowed?
            # Let's check for duplicates by name to avoid clutter

            # Simple approach: Register everything.
            register_connection(
                name=item.get("name"),
                db_type=item.get("engine"),
                connection_string=item.get("url"),
                extra_options=item.get("options"),
                fields=item.get("fields"),  # Critical for future edits
                user_id=user_id,
                group_name=item.get("group"),
                sort_order=item.get("order"),
            )
            count += 1

        return jsonify({"success": True, "message": f"Successfully imported {count} connections."})

    except Exception as e:
        print(f"Import error: {e}")
        return jsonify({"success": False, "error": "Failed to decrypt. Wrong password or corrupted file."}), 400


@api_bp.route("/connections/backup")
@login_required
def api_backup_connections():
    """Legacy backup - redirect or keep for now?"""
    # Redirecting logic handled by frontend removing the link.
    # We keep this for backward compat if needed, or remove.
    # Let's return error to force use of new system if accessed directly.
    return jsonify({"error": "Please use the 'Backup' button in the UI"}), 400


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_extra_json(raw: str) -> dict | None:
    """
    Parse the Extra JSON string from the frontend.

    Returns ``{}`` if the string is empty/blank, the parsed dict if valid,
    or ``None`` if the JSON is malformed.
    """
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except (json.JSONDecodeError, TypeError):
        return None
