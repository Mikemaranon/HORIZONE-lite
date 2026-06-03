import unittest

from flask import Flask

from api_m.domains.base_api import BaseAPI
from api_m.services import ConflictError, RequestError, ResourceNotFoundError
from model_m import ProviderUnavailableError


class ErrorResponseTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.api = BaseAPI(self.app)

    def test_error_returns_structured_payload_with_message_alias(self):
        with self.app.app_context():
            response, status_code = self.api.error("Missing model", 400)
            payload = response.get_json()

        self.assertEqual(status_code, 400)
        self.assertEqual(
            payload,
            {
                "error": {
                    "code": "bad_request",
                    "message": "Missing model",
                },
                "message": "Missing model",
            },
        )

    def test_error_from_exception_maps_service_exceptions(self):
        cases = [
            (RequestError("Invalid payload"), 400, "bad_request"),
            (ResourceNotFoundError("Conversation not found"), 404, "not_found"),
            (ConflictError("Provider is in use"), 409, "conflict"),
        ]

        with self.app.app_context():
            for error, expected_status, expected_code in cases:
                response, status_code = self.api.error_from_exception(error)
                payload = response.get_json()

                self.assertEqual(status_code, expected_status)
                self.assertEqual(payload["error"]["code"], expected_code)
                self.assertEqual(payload["error"]["message"], str(error))

    def test_provider_error_redacts_secret_details(self):
        with self.app.app_context():
            response, status_code = self.api.provider_error(
                ProviderUnavailableError(
                    "Provider unavailable",
                    provider="cloud",
                    details={
                        "api_key": "sk-test",
                        "endpoint": "https://api.openai.com/v1",
                    },
                )
            )
            payload = response.get_json()

        self.assertEqual(status_code, 503)
        self.assertEqual(payload["error"]["code"], "provider_unavailable")
        self.assertEqual(payload["error"]["details"]["api_key"], "[REDACTED]")
        self.assertEqual(payload["error"]["details"]["endpoint"], "https://api.openai.com/v1")


if __name__ == "__main__":
    unittest.main()
