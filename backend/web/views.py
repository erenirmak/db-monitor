"""HTML page routes."""

from flask import Blueprint, render_template, session

from backend.auth import get_user_permissions, get_user_role, login_required

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
@login_required
def index():
    user_id = session.get("user_id", "")
    user_role = get_user_role(user_id) if user_id else "viewer"
    user_permissions = get_user_permissions(user_id) if user_id else []
    return render_template("index.html", user_role=user_role, user_permissions=user_permissions)
