import os
import unittest

from config_m import ConfigManager


class ConfigManagerTests(unittest.TestCase):
    def tearDown(self):
        for key in [
            "PORT",
            "HOST",
            "FLASK_DEBUG",
            "SECRET_KEY",
            "POLAR_SECRET_KEY",
            "POLAR_BOOTSTRAP_ADMIN_PASSWORD",
            "POLAR_ALLOW_INSECURE_DEFAULT_ADMIN",
            "POLAR_RETURN_TOKEN_IN_LOGIN_RESPONSE",
            "POLAR_ALLOW_PUBLIC_REGISTRATION",
            "DEFAULT_PROVIDER",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "GOOGLE_API_KEY",
            "GOOGLE_BASE_URL",
            "OLLAMA_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "MODEL_REQUEST_TIMEOUT",
            "MLX_MODEL_PATHS",
            "HUGGINGFACE_HUB_CACHE",
        ]:
            os.environ.pop(key, None)

    def test_loads_default_runtime_values(self):
        config = ConfigManager()

        self.assertEqual(config.runtime.port, 5050)
        self.assertEqual(config.runtime.host, "0.0.0.0")
        self.assertFalse(config.runtime.debug)
        self.assertTrue(config.runtime.secret_key)
        self.assertFalse(config.runtime.allow_insecure_default_admin)
        self.assertFalse(config.runtime.return_token_in_login_response)
        self.assertFalse(config.runtime.allow_public_registration)

    def test_runtime_values_can_be_overridden(self):
        os.environ["PORT"] = "9090"
        os.environ["HOST"] = "127.0.0.1"
        os.environ["FLASK_DEBUG"] = "true"
        os.environ["SECRET_KEY"] = "configured-secret"
        os.environ["POLAR_BOOTSTRAP_ADMIN_PASSWORD"] = "configured-password"
        os.environ["POLAR_ALLOW_INSECURE_DEFAULT_ADMIN"] = "true"
        os.environ["POLAR_RETURN_TOKEN_IN_LOGIN_RESPONSE"] = "true"
        os.environ["POLAR_ALLOW_PUBLIC_REGISTRATION"] = "true"

        config = ConfigManager()

        self.assertEqual(config.runtime.port, 9090)
        self.assertEqual(config.runtime.host, "127.0.0.1")
        self.assertTrue(config.runtime.debug)
        self.assertEqual(config.runtime.secret_key, "configured-secret")
        self.assertEqual(config.runtime.bootstrap_admin_password, "configured-password")
        self.assertTrue(config.runtime.allow_insecure_default_admin)
        self.assertTrue(config.runtime.return_token_in_login_response)
        self.assertTrue(config.runtime.allow_public_registration)

    def test_provider_values_can_be_overridden(self):
        os.environ["DEFAULT_PROVIDER"] = "ollama"
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
        os.environ["GOOGLE_API_KEY"] = "test-google-key"
        os.environ["MODEL_REQUEST_TIMEOUT"] = "30"
        os.environ["MLX_MODEL_PATHS"] = "/tmp/model-a, /tmp/model-b"

        config = ConfigManager()

        self.assertEqual(config.providers.default_provider, "ollama")
        self.assertEqual(config.providers.openai_api_key, "test-key")
        self.assertEqual(config.providers.anthropic_api_key, "test-anthropic-key")
        self.assertEqual(config.providers.google_api_key, "test-google-key")
        self.assertEqual(config.providers.request_timeout_seconds, 30)
        self.assertEqual(
            config.providers.mlx_model_paths,
            ("/tmp/model-a", "/tmp/model-b"),
        )
