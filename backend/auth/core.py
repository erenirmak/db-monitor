import os
from typing import Optional, Tuple

from flask import session

from .db import AUTH_MODE
from .users import UserManager


def authenticate_local(username: str, password: str) -> Tuple[bool, str]:
    """Verify a local username + password.  Returns (success, message)."""
    username = username.strip().lower()
    if not username:
        return False, "Username is required."

    if UserManager.verify_password(username, password):
        return True, "OK"
    return False, "Invalid username or password."


def authenticate_ldap(username: str, password: str) -> Tuple[bool, str]:
    """Verify credentials against an LDAP / LLDAP server."""
    try:
        import ldap3
    except ImportError:
        return False, "ldap3 package is not installed.  Run:  uv add ldap3"

    ldap_url = os.environ.get("LDAP_URL", "").strip()
    base_dn = os.environ.get("LDAP_BASE_DN", "").strip()
    user_dn_template = os.environ.get("LDAP_USER_DN_TEMPLATE", "").strip()
    bind_dn = os.environ.get("LDAP_BIND_DN", "").strip()
    bind_pw = os.environ.get("LDAP_BIND_PASSWORD", "").strip()
    user_filter = os.environ.get("LDAP_USER_FILTER", "").strip()
    require_group = os.environ.get("LDAP_REQUIRE_GROUP", "").strip()

    if not ldap_url or not base_dn:
        return False, "LDAP_URL and LDAP_BASE_DN must be set."

    try:
        server = ldap3.Server(ldap_url, get_info=ldap3.NONE, connect_timeout=5)

        # --- Strategy 1: direct bind with DN template ---
        if user_dn_template:
            user_dn = user_dn_template.replace("{username}", username)
            conn = ldap3.Connection(server, user=user_dn, password=password)
            if not conn.bind():
                return False, "Invalid credentials."

        # --- Strategy 2: search-bind ---
        elif bind_dn and user_filter:
            admin_conn = ldap3.Connection(server, user=bind_dn, password=bind_pw)
            if not admin_conn.bind():
                return False, "LDAP admin bind failed — check LDAP_BIND_DN/PASSWORD."

            search_filter = user_filter.replace("{username}", username)
            admin_conn.search(base_dn, search_filter, attributes=["dn"])
            if not admin_conn.entries:
                return False, "User not found in LDAP directory."

            user_dn = str(admin_conn.entries[0].entry_dn)
            admin_conn.unbind()

            conn = ldap3.Connection(server, user=user_dn, password=password)
            if not conn.bind():
                return False, "Invalid credentials."
        else:
            return False, (
                "LDAP config incomplete — set either LDAP_USER_DN_TEMPLATE "
                "or both LDAP_BIND_DN + LDAP_USER_FILTER."
            )

        # --- Optional group membership check ---
        if require_group:
            conn.search(
                require_group,
                f"(member={user_dn})",
                search_scope=ldap3.BASE,
            )
            if not conn.entries:
                conn.unbind()
                return False, "User is not a member of the required group."

        conn.unbind()
        return True, "OK"

    except ldap3.core.exceptions.LDAPSocketOpenError:
        return False, f"Cannot reach LDAP server at {ldap_url}"
    except Exception as exc:
        return False, f"LDAP error: {exc}"


def authenticate(username: str, password: str) -> Tuple[bool, str]:
    """Top-level dispatcher — picks the right backend."""
    if not username:
        return False, "Username is required."
    if AUTH_MODE == "ldap":
        return authenticate_ldap(username, password)
    return authenticate_local(username, password)


def get_current_user() -> Optional[str]:
    """Return the logged-in username from the Flask session, or None."""
    return session.get("user_id")


def get_user_role(username: str) -> str:
    """Return the global role of a user. Defaults to 'viewer' if not found or in LDAP mode."""
    if AUTH_MODE == "ldap":
        return "viewer"

    user = UserManager.get_user(username)
    if user:
        return user["role"]
    return "viewer"


def get_user_permissions(username: str, db_key: Optional[str] = None) -> list[str]:
    """
    Get all permissions for a user.
    If db_key is provided, it checks for specific database grants first,
    then falls back to the global role permissions.
    """
    if AUTH_MODE == "ldap":
        return ["api_access", "execute_sql_read"]

    # 0. Check if user owns the database
    if db_key:
        from backend.database.connection import DATABASES

        entry = DATABASES.get(db_key)
        if entry and entry.get("user_id", "") == username:
            # Owner has all permissions
            return [
                "api_access",
                "manage_users",
                "manage_roles",
                "manage_connections",
                "execute_sql_read",
                "execute_sql_write",
                "execute_sql_ddl",
            ]

    return UserManager.get_user_permissions(username, db_key)


def has_permission(username: str, permission: str, db_key: Optional[str] = None) -> bool:
    """Check if a user has a specific permission."""
    perms = get_user_permissions(username, db_key)
    return permission in perms
