from config_m import ConfigManager

from .provider_manager import ProviderManager


class ModelManager:
    def __init__(self, config_manager: ConfigManager, db_manager=None):
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.provider_manager = ProviderManager(config_manager, db_manager=db_manager)

    def list_models(self, provider_name: str | None = None) -> dict:
        return self.provider_manager.list_models(provider_name)

    def chat(
        self,
        provider_name: str,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
    ) -> dict:
        return self.provider_manager.chat(provider_name, messages, model, settings or {})

    def stream_chat(
        self,
        provider_name: str,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        return self.provider_manager.stream_chat(
            provider_name,
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
        return self.provider_manager.generate_conversation_title(
            provider_name,
            model,
            title_context,
            settings or {},
        )

    def resolve_provider_configuration(
        self,
        provider_type: str,
        endpoint: str = "",
        api_key: str = "",
        *,
        allow_probe: bool = True,
    ) -> dict:
        return self.provider_manager.resolve_provider_configuration(
            provider_type,
            endpoint,
            api_key,
            allow_probe=allow_probe,
        )
