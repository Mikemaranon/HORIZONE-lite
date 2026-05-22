from config_m import ConfigManager

from .exceptions import UnsupportedProviderError
from .http_client import JsonHttpClient
from .provider_settings_resolver import ProviderSettingsResolver
from .providers import (
    CloudProvider,
    MLXProvider,
    OllamaProvider,
)


class ProviderRegistry:
    def __init__(self, config_manager: ConfigManager, db_manager=None):
        self.config_manager = config_manager
        self.db_manager = db_manager
        provider_config = self.config_manager.get_provider_config()
        self.http_client = JsonHttpClient(provider_config.request_timeout_seconds)
        self.settings_resolver = ProviderSettingsResolver(db_manager)
        self.providers = self._build_providers(provider_config)

    def get_provider(self, provider_name):
        provider = self.providers.get(provider_name)
        if not provider:
            raise UnsupportedProviderError(
                f"Unsupported provider '{provider_name}'.",
                provider=provider_name,
            )
        return provider

    def get_registered_providers(self):
        return list(self.providers.keys())

    def _build_providers(self, provider_config):
        return {
            "mlx": MLXProvider(
                provider_config,
                db_manager=self.db_manager,
                settings_resolver=self.settings_resolver,
            ),
            "ollama": OllamaProvider(
                provider_config,
                db_manager=self.db_manager,
                http_client=self.http_client,
                settings_resolver=self.settings_resolver,
            ),
            "cloud": CloudProvider(
                provider_config,
                db_manager=self.db_manager,
                http_client=self.http_client,
                settings_resolver=self.settings_resolver,
            ),
        }
