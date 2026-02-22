"""
Audit logging module for tracking user activity and security events.
Outputs structured JSON logs for easy ingestion by SIEMs (Graylog, Splunk, etc.).
"""

import logging
import sys
from typing import Any, Dict, Optional

from pythonjsonlogger import jsonlogger

# Create a dedicated logger for audit events
audit_logger = logging.getLogger("db_monitor.audit")
audit_logger.setLevel(logging.INFO)

# Prevent audit logs from propagating to the root logger (to avoid duplication)
audit_logger.propagate = False

# Configure JSON formatting
log_handler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
)
log_handler.setFormatter(formatter)
audit_logger.addHandler(log_handler)


def log_audit_event(
    action: str,
    user_id: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    status: str = "success",
) -> None:
    """
    Log a structured audit event.

    :param action: The action performed (e.g., "execute_sql", "create_connection")
    :param user_id: The ID of the user performing the action
    :param resource_type: The type of resource affected (e.g., "database", "query")
    :param resource_id: The specific ID of the resource (e.g., db_key)
    :param details: Additional context (e.g., the SQL query string, masked if necessary)
    :param status: "success" or "failure"
    """
    event_data = {
        "event_type": "audit",
        "action": action,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "status": status,
        "details": details or {},
    }

    # The message is a human-readable summary, the extra dict contains the structured data
    message = f"User {user_id} performed {action} on {resource_type} {resource_id or ''}"
    audit_logger.info(message, extra=event_data)
