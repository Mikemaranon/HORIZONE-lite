SECRET_FIELD_KEYWORDS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
)

REDACTED_VALUE = "[REDACTED]"


def redact_query_params(query, params):
    lowered_query = str(query or "").lower()
    if any(keyword in lowered_query for keyword in SECRET_FIELD_KEYWORDS):
        return _redact_value(params)
    return params


def _redact_value(value):
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if _is_secret_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(item) for item in value)
    return REDACTED_VALUE if isinstance(value, str) else value


def _is_secret_key(key):
    lowered_key = str(key or "").lower()
    return any(keyword in lowered_key for keyword in SECRET_FIELD_KEYWORDS)
