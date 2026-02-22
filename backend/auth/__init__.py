from .core import (
    authenticate,
    authenticate_ldap,
    authenticate_local,
    get_current_user,
    get_user_permissions,
    get_user_role,
    has_permission,
)
from .db import AUTH_MODE, init_auth
from .decorators import login_required
from .decorators import require_permission as requires_permission
from .grants import GrantManager
from .roles import RoleManager
from .users import UserManager

# Expose functions to match the old auth.py interface
get_all_roles = RoleManager.get_all_roles
create_role = RoleManager.create_role
delete_role = RoleManager.delete_role

get_all_grants = GrantManager.get_all_grants
get_user_grants = GrantManager.get_user_grants
create_grant = GrantManager.create_grant
delete_grant = GrantManager.delete_grant

create_user = UserManager.create_user
get_all_users = UserManager.get_all_users
update_user_role = UserManager.update_user_role
delete_user = UserManager.delete_user
admin_reset_password = UserManager.admin_reset_password
change_password = UserManager.change_password
any_users_exist = UserManager.any_users_exist

__all__ = [
    "init_auth",
    "AUTH_MODE",
    "get_all_roles",
    "create_role",
    "delete_role",
    "get_all_grants",
    "get_user_grants",
    "create_grant",
    "delete_grant",
    "create_user",
    "get_all_users",
    "update_user_role",
    "delete_user",
    "admin_reset_password",
    "change_password",
    "any_users_exist",
    "authenticate",
    "authenticate_local",
    "authenticate_ldap",
    "get_current_user",
    "get_user_role",
    "get_user_permissions",
    "has_permission",
    "login_required",
    "requires_permission",
]
