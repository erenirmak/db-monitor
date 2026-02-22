from flask import Blueprint, jsonify, session
from sqlalchemy import inspect, text

from backend.auth import login_required, requires_permission
from backend.database.connection import DATABASES, get_db_connection, user_owns_db

introspection_bp = Blueprint("introspection", __name__)


@introspection_bp.route("/database/<db_key>/schemas")
@login_required
@requires_permission("execute_sql_read")
def get_schemas(db_key: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404
    try:
        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500
        inspector = inspect(engine)
        return jsonify({"schemas": inspector.get_schema_names()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@introspection_bp.route("/database/<db_key>/schema/<schema>/tables")
@login_required
@requires_permission("execute_sql_read")
def get_tables(db_key: str, schema: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
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


@introspection_bp.route("/database/<db_key>/schema/<schema>/table/<table>")
@login_required
@requires_permission("execute_sql_read")
def get_table_info(db_key: str, schema: str, table: str):
    user_id = session.get("user_id", "")
    if not user_owns_db(user_id, db_key):
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
