import hashlib
import hmac
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .db import AUTH_MODE, get_conn
from .grants import GrantManager
from .roles import RoleManager


def _hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 + random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


class UserManager:
    @staticmethod
    def get_all_users() -> List[Dict[str, Any]]:
        """Return all users."""
        if AUTH_MODE != "local":
            return []
        with get_conn() as conn:
            rows = conn.execute("SELECT username, created_at, role FROM users ORDER BY username").fetchall()
            return [{"username": row[0], "created_at": row[1], "role": row[2]} for row in rows]

    @staticmethod
    def get_user(username: str) -> Optional[Dict[str, Any]]:
        """Return a specific user."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT username, created_at, role FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row:
                return None
            return {"username": row[0], "created_at": row[1], "role": row[2]}

    @staticmethod
    def create_user(username: str, password: str) -> Tuple[bool, str]:
        """Create a new user."""
        username = username.strip().lower()
        if not username:
            return False, "Username is required."
        if len(password) < 4:
            return False, "Password must be at least 4 characters."

        with get_conn() as conn:
            existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                return False, f'User "{username}" already exists.'

            hashed = _hash_password(password)

            # If this is the first user, make them an admin
            is_first = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
            role = "admin" if is_first else "viewer"

            conn.execute(
                "INSERT INTO users (username, password_hash, created_at, role) VALUES (?, ?, ?, ?)",
                (username, hashed, datetime.now().isoformat(), role),
            )
            return True, f'User "{username}" created successfully.'

    @staticmethod
    def update_user_role(username: str, new_role: str) -> Tuple[bool, str]:
        """Update an existing user's role."""
        username = username.strip().lower()
        if AUTH_MODE != "local":
            return False, "Role management is only supported in local mode."
        if new_role not in ("admin", "editor", "viewer"):
            return False, "Invalid role."

        with get_conn() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False, "User not found."

            # Prevent removing the last admin
            if new_role != "admin":
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                current_role = conn.execute(
                    "SELECT role FROM users WHERE username = ?", (username,)
                ).fetchone()[0]
                if current_role == "admin" and admin_count <= 1:
                    return False, "Cannot demote the last admin."

            conn.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, username))
            return True, f"Role updated to {new_role}."

    @staticmethod
    def delete_user(username: str) -> Tuple[bool, str]:
        """Delete a user."""
        username = username.strip().lower()
        if AUTH_MODE != "local":
            return False, "User deletion is only supported in local mode."

        with get_conn() as conn:
            row = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False, "User not found."

            # Prevent deleting the last admin
            if row[0] == "admin":
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admin_count <= 1:
                    return False, "Cannot delete the last admin."

            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            return True, "User deleted successfully."

    @staticmethod
    def admin_reset_password(username: str, new_password: str) -> Tuple[bool, str]:
        """Reset a user's password without knowing the old one."""
        username = username.strip().lower()
        if AUTH_MODE != "local":
            return False, "Password reset is only supported in local mode."
        if len(new_password) < 4:
            return False, "New password must be at least 4 characters."

        with get_conn() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False, "User not found."

            hashed = _hash_password(new_password)
            conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed, username))
            return True, "Password reset successfully."

    @staticmethod
    def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change a local user's password."""
        username = username.strip().lower()
        if AUTH_MODE != "local":
            return False, "Password change is only supported in local mode."

        if not username:
            return False, "Username is required."

        with get_conn() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False, "User not found."

            # Verify old password
            if not _verify_password(old_password, row[0]):
                return False, "Incorrect old password."

            if len(new_password) < 4:
                return False, "New password must be at least 4 characters."

            hashed = _hash_password(new_password)
            conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed, username))

        return True, "Password changed successfully."

    @staticmethod
    def any_users_exist() -> bool:
        """Check if any local user accounts have been created yet."""
        with get_conn() as conn:
            row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    @staticmethod
    def verify_password(username: str, password: str) -> bool:
        """Verify a user's password."""
        with get_conn() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False
            return _verify_password(password, row[0])

    @staticmethod
    def get_user_permissions(username: str, db_key: Optional[str] = None) -> List[str]:
        """Get all permissions for a user, optionally scoped to a specific database."""
        user = UserManager.get_user(username)
        if not user:
            return []

        # Get global role permissions
        global_role = RoleManager.get_role(user["role"])
        global_perms = global_role["permissions"] if global_role else []

        # If no db_key specified, return global permissions
        if not db_key:
            return global_perms

        # If db_key specified, check for specific grant
        grants = GrantManager.get_user_grants(username)
        for grant in grants:
            if grant["db_key"] == db_key:
                db_role = RoleManager.get_role(grant["role"])
                if db_role:
                    # Combine global and db-specific permissions
                    return list(set(global_perms + db_role["permissions"]))

        return global_perms
