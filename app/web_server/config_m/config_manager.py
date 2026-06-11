import os
import secrets
from pathlib import Path

from .app_config import ProviderConfig, RuntimeConfig


class ConfigManager:
    def __init__(self):
        self.runtime = self._load_runtime_config()
        self.providers = self._load_provider_config()

    def _load_runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(
            secret_key=self._load_secret_key(),
            host=os.environ.get("HOST", "127.0.0.1"),
            port=self._get_env_int("PORT", 5050),
            debug=self._get_env_bool("FLASK_DEBUG", False),
            llama_cpp_binary=os.environ.get("HORIZONE_LLAMA_CPP_BINARY", ""),
            llama_cpp_server_kind=self._load_llama_cpp_server_kind(),
            llama_cpp_port=self._get_env_int("HORIZONE_LLAMA_CPP_PORT", 8080),
            llama_cpp_port_max=self._get_env_int("HORIZONE_LLAMA_CPP_PORT_MAX", 9000),
            runtime_models_dir=self._load_runtime_models_dir(),
            runtime_disabled=self._get_env_bool("HORIZONE_RUNTIME_DISABLED", False),
            bootstrap_admin_password=os.environ.get("HORIZONE_BOOTSTRAP_ADMIN_PASSWORD"),
            allow_insecure_default_admin=self._get_env_bool(
                "HORIZONE_ALLOW_INSECURE_DEFAULT_ADMIN",
                False,
            ),
            return_token_in_login_response=self._get_env_bool(
                "HORIZONE_RETURN_TOKEN_IN_LOGIN_RESPONSE",
                False,
            ),
            allow_public_registration=self._get_env_bool(
                "HORIZONE_ALLOW_PUBLIC_REGISTRATION",
                False,
            ),
        )

    def _load_provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            default_provider=os.environ.get("DEFAULT_PROVIDER", "mlx"),
            ollama_base_url=os.environ.get(
                "OLLAMA_BASE_URL", "http://localhost:11434/api"
            ).rstrip("/"),
            ollama_api_key=os.environ.get("OLLAMA_API_KEY"),
            llama_cpp_base_url=self._load_llama_cpp_base_url(),
            openai_base_url=os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            anthropic_base_url=os.environ.get(
                "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
            ).rstrip("/"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            google_base_url=os.environ.get(
                "GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com"
            ).rstrip("/"),
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
            mlx_model_paths=self._get_env_list("MLX_MODEL_PATHS"),
            huggingface_cache_dir=os.environ.get("HUGGINGFACE_HUB_CACHE"),
            request_timeout_seconds=self._get_env_int("MODEL_REQUEST_TIMEOUT", 120),
        )

    def get_provider_config(self) -> ProviderConfig:
        return self.providers

    def to_dict(self) -> dict:
        return {
            "runtime": {
                "host": self.runtime.host,
                "port": self.runtime.port,
                "debug": self.runtime.debug,
                "allow_public_registration": self.runtime.allow_public_registration,
                "llama_cpp_port": self.runtime.llama_cpp_port,
                "llama_cpp_port_max": self.runtime.llama_cpp_port_max,
                "llama_cpp_server_kind": self.runtime.llama_cpp_server_kind,
                "runtime_models_dir": self.runtime.runtime_models_dir,
                "runtime_disabled": self.runtime.runtime_disabled,
            },
            "providers": {
                "default_provider": self.providers.default_provider,
                "ollama_base_url": self.providers.ollama_base_url,
                "llama_cpp_base_url": self.providers.llama_cpp_base_url,
                "openai_base_url": self.providers.openai_base_url,
                "anthropic_base_url": self.providers.anthropic_base_url,
                "google_base_url": self.providers.google_base_url,
                "mlx_model_paths": list(self.providers.mlx_model_paths),
                "huggingface_cache_dir": self.providers.huggingface_cache_dir,
                "request_timeout_seconds": self.providers.request_timeout_seconds,
            },
        }

    def _get_env_bool(self, key: str, default: bool) -> bool:
        raw_value = os.environ.get(key)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    def _get_env_int(self, key: str, default: int) -> int:
        raw_value = os.environ.get(key)
        if raw_value is None:
            return default

        try:
            return int(raw_value)
        except ValueError:
            return default

    def _get_env_list(self, key: str) -> tuple[str, ...]:
        raw_value = os.environ.get(key, "")
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        return tuple(values)

    def _load_llama_cpp_base_url(self) -> str:
        configured = os.environ.get("HORIZONE_LLAMA_CPP_BASE_URL")
        if configured:
            return configured.rstrip("/")

        port = self.runtime.llama_cpp_port if hasattr(self, "runtime") else self._get_env_int(
            "HORIZONE_LLAMA_CPP_PORT",
            8080,
        )
        return f"http://127.0.0.1:{port}/v1"

    def _load_runtime_models_dir(self) -> str:
        configured = os.environ.get("HORIZONE_RUNTIME_MODELS_DIR")
        if configured:
            return configured

        return str(Path.home() / ".horizone" / "runtime" / "models")

    def _load_llama_cpp_server_kind(self) -> str:
        configured = os.environ.get("HORIZONE_LLAMA_CPP_SERVER_KIND", "native")
        normalized = configured.strip().lower()
        if normalized in {"native", "python"}:
            return normalized
        return "native"

    def _load_secret_key(self) -> str:
        configured = os.environ.get("SECRET_KEY") or os.environ.get("HORIZONE_SECRET_KEY")
        if configured:
            return configured
        return secrets.token_urlsafe(48)
