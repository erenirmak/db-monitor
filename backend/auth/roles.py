import json
from typing import Any, Dict, List, Optional

from .db import get_conn


class RoleManager:
    @staticmethod
    def get_all_roles() -> List[Dict[str, Any]]:
        """Return all roles."""
        with get_conn() as conn:
            rows = conn.execute("SELECT name, description, permissions, is_system FROM roles").fetchall()
            return [
                {
                    "name": row[0],
                    "description": row[1],
                    "permissions": json.loads(row[2]),
                    "is_system": bool(row[3]),
                }
                for row in rows
            ]

    @staticmethod
    def get_role(name: str) -> Optional[Dict[str, Any]]:
        """Return a specific role."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT name, description, permissions, is_system FROM roles WHERE name = ?", (name,)
            ).fetchone()
            if not row:
                return None
            return {
                "name": row[0],
                "description": row[1],
                "permissions": json.loads(row[2]),
                "is_system": bool(row[3]),
            }

    @staticmethod
    def create_role(name: str, description: str, permissions: List[str]) -> bool:
        """Create a new custom role."""
        with get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO roles (name, description, permissions, is_system) VALUES (?, ?, ?, 0)",
                    (name, description, json.dumps(permissions)),
                )
                return True
            except Exception:
                return False

    @staticmethod
    def update_role(name: str, description: str, permissions: List[str]) -> bool:
        """Update an existing custom role."""
        with get_conn() as conn:
            # Check if system role
            row = conn.execute("SELECT is_system FROM roles WHERE name = ?", (name,)).fetchone()
            if not row or row[0]:
                return False  # Cannot update system roles

            conn.execute(
                "UPDATE roles SET description = ?, permissions = ? WHERE name = ?",
                (description, json.dumps(permissions), name),
            )
            return True

    @staticmethod
    def delete_role(name: str) -> bool:
        """Delete a custom role."""
        with get_conn() as conn:
            # Check if system role
            row = conn.execute("SELECT is_system FROM roles WHERE name = ?", (name,)).fetchone()
            if not row or row[0]:
                return False  # Cannot delete system roles

            # Check if role is in use
            user_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (name,)).fetchone()[0]
            grant_count = conn.execute(
                "SELECT COUNT(*) FROM user_database_grants WHERE role = ?", (name,)
            ).fetchone()[0]

            if user_count > 0 or grant_count > 0:
                return False  # Cannot delete role in use

            conn.execute("DELETE FROM roles WHERE name = ?", (name,))
            return True
