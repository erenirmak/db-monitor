import re

from flask import Blueprint, jsonify, request, session
from sqlalchemy import text

from backend.auth import get_user_permissions, login_required
from backend.core.audit import log_audit_event
from backend.database.connection import get_db_connection, user_owns_db

query_bp = Blueprint("query", __name__)


def get_required_permissions_for_sql(sql: str) -> set:
    """A basic SQL parser to determine required permissions."""
    sql = sql.strip().upper()
    sql = re.sub(r"--.*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

    statements = [s.strip() for s in sql.split(";") if s.strip()]
    perms = set()
    for stmt in statements:
        if (
            stmt.startswith("SELECT")
            or stmt.startswith("EXPLAIN")
            or stmt.startswith("SHOW")
            or stmt.startswith("DESCRIBE")
            or stmt.startswith("PRAGMA")
        ):
            perms.add("execute_sql_read")
        elif (
            stmt.startswith("INSERT")
            or stmt.startswith("UPDATE")
            or stmt.startswith("DELETE")
            or stmt.startswith("REPLACE")
            or stmt.startswith("UPSERT")
        ):
            perms.add("execute_sql_write")
        elif (
            stmt.startswith("CREATE")
            or stmt.startswith("ALTER")
            or stmt.startswith("DROP")
            or stmt.startswith("TRUNCATE")
            or stmt.startswith("GRANT")
            or stmt.startswith("REVOKE")
        ):
            perms.add("execute_sql_ddl")
        else:
            perms.add("execute_sql_write")
    return perms


@query_bp.route("/database/<db_key>/execute", methods=["POST"])
@login_required
def execute_sql(db_key: str):
    user_id = session.get("user_id", "")
    username = session.get("username", "")

    if not user_owns_db(user_id, db_key):
        return jsonify({"error": "Database not found"}), 404

    try:
        data = request.json
        sql = (data.get("sql") or "").strip()
        if not sql:
            return jsonify({"error": "No SQL provided"}), 400

        required_perms = get_required_permissions_for_sql(sql)
        user_perms = get_user_permissions(username, db_key)

        for perm in required_perms:
            if perm not in user_perms:
                return jsonify({"error": f"Permission denied: requires {perm}"}), 403

        engine = get_db_connection(db_key)
        if not engine:
            return jsonify({"error": "Connection failed"}), 500

        with engine.connect() as conn:
            result = conn.execute(text(sql))

            log_audit_event(
                action="execute_sql",
                user_id=user_id,
                resource_type="database",
                resource_id=db_key,
                details={"query": sql},
            )

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
