"""SocketIO event handlers."""

from flask import session
from flask_socketio import emit

from backend import socketio
from backend.connection import DATABASES, db_status, check_db_status


@socketio.on("connect")
def handle_connect():
    emit("response", {"data": "Connected to server"})
    user_id = session.get("user_id", "")
    for db_key, config in DATABASES.items():
        if config.get("user_id", "") == user_id:
            emit("db_status_update", {"db_key": db_key, "status": db_status.get(db_key, {})})


@socketio.on("disconnect")
def handle_disconnect():
    pass


@socketio.on("check_status")
def handle_check_status(db_key):
    user_id = session.get("user_id", "")
    if db_key in DATABASES and DATABASES[db_key].get("user_id", "") == user_id:
        check_db_status(db_key)
        emit(
            "db_status_update",
            {"db_key": db_key, "status": db_status[db_key]},
        )
