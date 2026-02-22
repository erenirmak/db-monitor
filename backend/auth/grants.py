from typing import Any, Dict, List, Tuple

from .db import get_conn


class GrantManager:
    @staticmethod
    def get_all_grants() -> List[Dict[str, Any]]:
        """Return all database grants."""
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT username, db_key, role FROM user_database_grants ORDER BY username, db_key"
            ).fetchall()
            return [{"username": row[0], "db_key": row[1], "role": row[2]} for row in rows]

    @staticmethod
    def get_user_grants(username: str) -> List[Dict[str, Any]]:
        """Return all database grants for a user."""
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT db_key, role FROM user_database_grants WHERE username = ?", (username,)
            ).fetchall()
            return [{"db_key": row[0], "role": row[1]} for row in rows]

    @staticmethod
    def create_grant(username: str, db_key: str, role: str) -> Tuple[bool, str]:
        """Create or update a database grant."""
        with get_conn() as conn:
            # Verify user exists
            if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                return False, "User not found"

            # Verify role exists
            if not conn.execute("SELECT 1 FROM roles WHERE name = ?", (role,)).fetchone():
                return False, "Role not found"

            try:
                conn.execute(
                    "INSERT INTO user_database_grants (username, db_key, role) VALUES (?, ?, ?)",
                    (username, db_key, role),
                )
                return True, "Grant created successfully"
            except Exception:
                # Update if exists
                conn.execute(
                    "UPDATE user_database_grants SET role = ? WHERE username = ? AND db_key = ?",
                    (role, username, db_key),
                )
                return True, "Grant updated successfully"

    @staticmethod
    def delete_grant(username: str, db_key: str) -> Tuple[bool, str]:
        """Delete a database grant."""
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM user_database_grants WHERE username = ? AND db_key = ?", (username, db_key)
            )
            return True, "Grant deleted successfully"
