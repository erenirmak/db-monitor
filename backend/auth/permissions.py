from typing import List

# Define all available permissions in the system
AVAILABLE_PERMISSIONS = [
    "api_access",  # Can use the API endpoints
    "manage_users",  # Can create/edit/delete users
    "manage_roles",  # Can create/edit/delete roles
    "manage_connections",  # Can add/edit/delete database connections
    "execute_sql_read",  # Can run SELECT queries
    "execute_sql_write",  # Can run INSERT/UPDATE/DELETE queries
    "execute_sql_ddl",  # Can run CREATE/DROP/ALTER queries
]


def get_available_permissions() -> List[str]:
    """Return a list of all available permissions."""
    return AVAILABLE_PERMISSIONS
