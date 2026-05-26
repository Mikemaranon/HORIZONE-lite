from config_m import ConfigManager

from .conversation_title_service import ConversationTitleService
from .model_catalog_service import ModelCatalogService
from .provider_registry import ProviderRegistry


class ProviderManager:
    def __init__(self, config_manager: ConfigManager, db_manager=None):
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.provider_registry = ProviderRegistry(config_manager, db_manager=db_manager)
        self.model_catalog_service = ModelCatalogService(db_manager=db_manager)
        self.conversation_title_service = ConversationTitleService()
        self.providers = self.provider_registry.providers

    def get_provider(self, provider_name: str):
        return self.provider_registry.get_provider(provider_name)

    def list_models(self, provider_name: str | None = None) -> dict:
        if provider_name:
            self.get_provider(provider_name)

        return self.model_catalog_service.list_models(
            provider_name=provider_name,
            providers=self.providers,
        )

    def chat(
        self,
        provider_name: str,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
    ) -> dict:
        provider = self.get_provider(provider_name)
        return provider.chat(messages, model, settings or {})

    def stream_chat(
        self,
        provider_name: str,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        provider = self.get_provider(provider_name)
        return provider.stream_chat(
            messages,
            model,
            settings or {},
            should_stop=should_stop,
        )

    def generate_conversation_title(
        self,
        provider_name: str,
        model: str,
        title_context,
        settings: dict | None = None,
    ) -> str:
        return self.conversation_title_service.generate_title(
            self.get_provider(provider_name),
            model,
            title_context,
            settings or {},
        )

    def get_registered_providers(self) -> list[str]:
        return self.provider_registry.get_registered_providers()

    def resolve_provider_configuration(
        self,
        provider_type: str,
        endpoint: str = "",
        api_key: str = "",
    ) -> dict:
        if provider_type != "cloud":
            return {
                "resolved_adapter": "",
                "resolved_metadata": {},
            }

        provider = self.get_provider("cloud")
        return provider.resolve_configuration(endpoint, api_key)
