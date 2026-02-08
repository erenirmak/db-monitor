"""HTML page routes."""

from flask import Blueprint, render_template

from backend.auth import login_required

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
@login_required
def index():
    return render_template("index.html")
