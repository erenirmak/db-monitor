import json


def _parse_extra_json(raw: str) -> dict | None:
    """
    Parse the Extra JSON string from the frontend.

    Returns ``{}`` if the string is empty/blank, the parsed dict if valid,
    or ``None`` if the JSON is malformed.
    """
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except (json.JSONDecodeError, TypeError):
        return None
