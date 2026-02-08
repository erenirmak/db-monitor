"""REST API routes."""

from __future__ import annotations

import json
from flask import Blueprint, request, jsonify, session
from sqlalchemy import inspect, text

from backend.auth import login_required
from backend.connection import (
    DATABASES,
    db_status,
    build_connection_string,
    get_db_connection,
    test_connection_string,
    register_connection,
    unregister_connection,
    get_user_databases,
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
    for db_key, config in get_user_databases(user_id).items():
        databases.append(
            {
                "key": db_key,
                "name": config["display_name"],
                "engine": config["engine"],
                "status": db_status.get(db_key, {}),
            }
        )
    return jsonify(databases)


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
        columns_info = inspector.get_columns(
            table, schema=schema if schema != "default" else None
        )
        columns = [
            {"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]}
            for c in columns_info
        ]

        with engine.connect() as conn:
            if schema and schema != "default":
                result = conn.execute(
                    text(f"SELECT * FROM {schema}.{table} LIMIT 100")
                )
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
                    "message": (
                        f"Query executed successfully. "
                        f"Rows affected: {result.rowcount}"
                    ),
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
            return jsonify(
                {"success": False, "error": "Database type and fields are required"}
            ), 400

        # Parse extra JSON
        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify(
                {"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}
            ), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            return jsonify(
                {"success": False, "error": f"Unsupported database type: {db_type}"}
            ), 400

        success, message = test_connection_string(
            db_type, connection_string, extra_options or None
        )
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
    """Save and activate a new database connection."""
    try:
        data = request.json
        name = (data.get("name") or "").strip()
        db_type = (data.get("type") or "").lower()
        fields = data.get("fields", {})
        extra_json_str = data.get("extra_json", "")

        if not name or not db_type or not fields:
            return jsonify(
                {"success": False, "error": "Connection name, type, and fields are required"}
            ), 400

        extra_options = _parse_extra_json(extra_json_str)
        if extra_options is None:
            return jsonify(
                {"success": False, "error": "Invalid Extra JSON — must be valid JSON object"}
            ), 400

        connection_string = build_connection_string(db_type, fields)
        if not connection_string:
            return jsonify(
                {"success": False, "error": f"Unsupported database type: {db_type}"}
            ), 400

        # Test before saving
        success, message = test_connection_string(
            db_type, connection_string, extra_options or None
        )
        if not success:
            return jsonify(
                {"success": False, "error": f"Connection test failed: {message}"}
            ), 400

        db_key = register_connection(
            name, db_type, connection_string, extra_options or None,
            fields=fields,
            user_id=session.get("user_id", ""),
        )
        print(f"New database connection saved: {db_key} ({name})")

        return jsonify(
            {
                "success": True,
                "db_key": db_key,
                "message": f'Connection "{name}" saved successfully',
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


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
    return jsonify(
        {"success": True, "message": f'Connection "{name}" removed successfully'}
    )


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
