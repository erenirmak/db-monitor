import base64
import json
import os
from datetime import datetime

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import Blueprint, jsonify, request, session

from backend.auth import login_required, requires_permission
from backend.database.connection import get_user_databases, register_connection

backup_bp = Blueprint("backup", __name__)


@backup_bp.route("/connections/export", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_export_connections():
    user_id = session.get("user_id", "")
    data = request.json
    password = data.get("password")

    if not password:
        return jsonify({"success": False, "error": "Encryption password required"}), 400

    user_dbs = get_user_databases(user_id)
    export_data = []
    for _, config in user_dbs.items():
        item = {
            "name": config.get("display_name", "Untitled"),
            "engine": config.get("engine", "unknown"),
            "url": config.get("url", ""),
            "options": config.get("extra_options", {}),
            "group": config.get("group_name", ""),
            "order": config.get("sort_order", 0),
            "fields": config.get("fields", {}),
        }
        export_data.append(item)

    json_bytes = json.dumps(export_data).encode("utf-8")

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    f = Fernet(key)

    encrypted_data = f.encrypt(json_bytes)
    final_payload = base64.b64encode(salt + encrypted_data).decode("utf-8")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"db_monitor_backup_{timestamp}.enc"

    return jsonify({"success": True, "filename": filename, "data": final_payload})


@backup_bp.route("/connections/import", methods=["POST"])
@login_required
@requires_permission("manage_connections")
def api_import_connections():
    user_id = session.get("user_id", "")
    data = request.json
    password = data.get("password")
    payload = data.get("data")

    if not password or not payload:
        return jsonify({"success": False, "error": "Password and data required"}), 400

    try:
        raw_bytes = base64.b64decode(payload)
        salt = raw_bytes[:16]
        encrypted_data = raw_bytes[16:]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        f = Fernet(key)

        decrypted_json = f.decrypt(encrypted_data)
        connections = json.loads(decrypted_json)

        count = 0
        for item in connections:
            register_connection(
                name=item.get("name"),
                db_type=item.get("engine"),
                connection_string=item.get("url"),
                extra_options=item.get("options"),
                fields=item.get("fields"),
                user_id=user_id,
                group_name=item.get("group"),
                sort_order=item.get("order"),
            )
            count += 1

        return jsonify({"success": True, "message": f"Successfully imported {count} connections."})

    except Exception as e:
        print(f"Import error: {e}")
        return jsonify({"success": False, "error": "Failed to decrypt. Wrong password or corrupted file."}), 400


@backup_bp.route("/connections/backup")
@login_required
def api_backup_connections():
    return jsonify({"error": "Please use the 'Backup' button in the UI"}), 400
