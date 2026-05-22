import os

from .app_config import ProviderConfig, RuntimeConfig


class ConfigManager:
    def __init__(self):
        self.runtime = self._load_runtime_config()
        self.providers = self._load_provider_config()

    def _load_runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(
            secret_key=os.environ.get(
                "SECRET_KEY",
                "horizone-studio-local-dev-secret-key-2026",
            ),
            host=os.environ.get("HOST", "0.0.0.0"),
            port=self._get_env_int("PORT", 5050),
            debug=self._get_env_bool("FLASK_DEBUG", True),
        )

    def _load_provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            default_provider=os.environ.get("DEFAULT_PROVIDER", "mlx"),
            ollama_base_url=os.environ.get(
                "OLLAMA_BASE_URL", "http://localhost:11434/api"
            ).rstrip("/"),
            ollama_api_key=os.environ.get("OLLAMA_API_KEY"),
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
            },
            "providers": {
                "default_provider": self.providers.default_provider,
                "ollama_base_url": self.providers.ollama_base_url,
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
