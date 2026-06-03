import logging
import re

from flask import jsonify

from model_m import ProviderError


LOGGER = logging.getLogger(__name__)


class BaseAPI:
    STATUS_ERROR_CODES = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        500: "internal_error",
        502: "model_operation_error",
        503: "service_unavailable",
    }
    SECRET_DETAIL_PATTERN = re.compile(
        r"(api[_-]?key|authorization|bearer|password|secret|token)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        app,
        user_manager=None,
        db=None,
        model_manager=None,
        services=None,
    ):
        self.app = app
        self.services = services

        if self.services:
            self.user_manager = self.services.user_manager
            self.db = self.services.db_manager
            self.model_manager = self.services.model_manager
            self.config_manager = self.services.config_manager
        else:
            self.user_manager = user_manager
            self.db = db
            self.model_manager = model_manager
            self.config_manager = getattr(model_manager, "config_manager", None)

    def ok(self, data, code=200):
        return jsonify(data), code

    def error(self, message, code=400, error_code=None, details=None):
        error = self._build_error_payload(
            message,
            code=code,
            error_code=error_code,
            details=details,
        )
        return jsonify({"error": error, "message": error["message"]}), code

    def provider_error(self, error):
        payload = error.to_dict()
        payload["details"] = self._redact_error_details(payload.get("details") or {})
        return jsonify({"error": payload, "message": payload["message"]}), error.status_code

    def error_from_exception(self, error):
        status_code = self._status_code_for_exception(error)
        if status_code >= 500:
            LOGGER.exception("Unhandled API error")
            return self.error("An internal server error occurred.", status_code)

        return self.error(str(error), status_code)

    def authenticate_request(self, request):
        token = self.user_manager.get_token_from_cookie(request)
        if not token:
            token = self.user_manager.get_request_token(request)
        if not token or not self.user_manager.validate_token(token):
            return self.error("Unauthorized", 401)
        return True

    def get_request_json(self, request):
        return request.get_json(silent=True) or {}

    def parse_int(self, value, field_name):
        if value is None or value == "":
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid {field_name}")

    def require_fields(self, data, *field_names):
        for field_name in field_names:
            value = data.get(field_name)
            if value is None or value == "":
                raise ValueError(f"Missing {field_name}")

    def get_default_profile(self):
        return self.db.profiles.get_default()

    def _build_error_payload(self, message, code=400, error_code=None, details=None):
        payload = {
            "code": error_code or self.STATUS_ERROR_CODES.get(code, "api_error"),
            "message": str(message or "Request failed."),
        }
        sanitized_details = self._redact_error_details(details or {})
        if sanitized_details:
            payload["details"] = sanitized_details
        return payload

    def _status_code_for_exception(self, error):
        if isinstance(error, ProviderError):
            return error.status_code
        if isinstance(error, PermissionError):
            return 403
        if isinstance(error, LookupError) or error.__class__.__name__.endswith("ResourceNotFoundError"):
            return 404
        if error.__class__.__name__.endswith("ConflictError"):
            return 409
        if error.__class__.__name__.endswith("UnavailableError"):
            return 503
        if isinstance(error, ValueError) or error.__class__.__name__.endswith("RequestError"):
            return 400
        return 500

    def _redact_error_details(self, details):
        if not isinstance(details, dict):
            return {}

        redacted = {}
        for key, value in details.items():
            if self.SECRET_DETAIL_PATTERN.search(str(key)):
                redacted[key] = "[REDACTED]"
                continue
            if isinstance(value, dict):
                redacted[key] = self._redact_error_details(value)
                continue
            redacted[key] = value
        return redacted
