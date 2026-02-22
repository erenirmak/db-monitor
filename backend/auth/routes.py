"""Authentication routes — login, logout, registration."""

from flask import Blueprint, redirect, render_template, request, session, url_for

from backend.auth import (
    AUTH_MODE,
    any_users_exist,
    authenticate,
    create_user,
)
from backend.core.audit import log_audit_event

auth_bp = Blueprint("auth_views", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Show login form / handle login POST."""
    if session.get("authenticated") and session.get("user_id"):
        return redirect(url_for("views.index"))

    # No users yet → send to register so they can create the first account
    if AUTH_MODE == "local" and not any_users_exist():
        return redirect(url_for("auth_views.register"))

    error = None
    success = request.args.get("success")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        ok, msg = authenticate(username, password)
        if ok:
            session.permanent = True
            session["authenticated"] = True
            session["user_id"] = username.lower()

            from backend.database.connection import load_saved_connections

            load_saved_connections(user_id=username.lower())

            log_audit_event(
                action="login",
                user_id=username.lower(),
                resource_type="system",
                details={"auth_mode": AUTH_MODE},
            )

            return redirect(url_for("views.index"))

        log_audit_event(
            action="failed_login",
            user_id=username.lower(),
            resource_type="system",
            status="failure",
            details={"reason": msg, "auth_mode": AUTH_MODE},
        )
        error = msg

    return render_template(
        "login.html",
        auth_mode=AUTH_MODE,
        error=error,
        success=success,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registration page — username + password + confirm password."""
    if AUTH_MODE == "ldap":
        return redirect(url_for("auth_views.login"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("password_confirm", "")

        if not username:
            error = "Username is required."
        elif len(password) < 4:
            error = "Password must be at least 4 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            ok, msg = create_user(username, password)
            if ok:
                return redirect(
                    url_for(
                        "auth_views.login",
                        success=f'Account "{username}" created! You can now sign in.',
                    )
                )
            error = msg

    return render_template("register.html", error=error)


@auth_bp.route("/logout")
def logout():
    """Clear the session and redirect to login."""
    user_id = session.get("user_id")
    if user_id:
        log_audit_event(action="logout", user_id=user_id, resource_type="system")
    session.clear()
    return redirect(url_for("auth_views.login"))
