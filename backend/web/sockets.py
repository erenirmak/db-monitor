"""SocketIO event handlers."""

from flask import session
from flask_socketio import emit

from backend import socketio
from backend.database.connection import DATABASES, check_db_status, db_status

# Track online users: {user_id: connection_count}
ONLINE_USERS: dict[str, int] = {}


@socketio.on("connect")
def handle_connect():
    emit("response", {"data": "Connected to server"})
    user_id = session.get("user_id", "")

    if user_id:
        ONLINE_USERS[user_id] = ONLINE_USERS.get(user_id, 0) + 1
        socketio.emit("online_users_update", {"online_users": list(ONLINE_USERS.keys())})

    for db_key, config in DATABASES.items():
        if config.get("user_id", "") == user_id:
            emit("db_status_update", {"db_key": db_key, "status": db_status.get(db_key, {})})


@socketio.on("disconnect")
def handle_disconnect():
    user_id = session.get("user_id", "")
    if user_id and user_id in ONLINE_USERS:
        ONLINE_USERS[user_id] -= 1
        if ONLINE_USERS[user_id] <= 0:
            del ONLINE_USERS[user_id]
        socketio.emit("online_users_update", {"online_users": list(ONLINE_USERS.keys())})


@socketio.on("check_status")
def handle_check_status(db_key):
    user_id = session.get("user_id", "")
    if db_key in DATABASES and DATABASES[db_key].get("user_id", "") == user_id:
        check_db_status(db_key)
        emit(
            "db_status_update",
            {"db_key": db_key, "status": db_status[db_key]},
        )
