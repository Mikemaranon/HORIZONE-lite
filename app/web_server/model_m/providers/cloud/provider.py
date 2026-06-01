from ...exceptions import ProviderUnavailableError
from ...http_client import JsonHttpClient
from ..base_provider import ModelProvider

from .adapters import (
    AnthropicCloudAdapter,
    GoogleCloudAdapter,
    MicrosoftFoundryCloudAdapter,
    OpenAICompatibleCloudAdapter,
)
from .detector import CloudAdapterDetector


class CloudProvider(ModelProvider):
    provider_name = "cloud"

    def __init__(self, config, db_manager=None, http_client=None, settings_resolver=None):
        super().__init__(
            config,
            db_manager=db_manager,
            http_client=http_client,
            settings_resolver=settings_resolver,
        )
        self.http_client = http_client or JsonHttpClient(config.request_timeout_seconds)
        self.detector = CloudAdapterDetector(self.http_client)
        self.adapters = self._build_adapters()

    def is_available(self) -> bool:
        return self._get_default_cloud_provider_config() is not None

    def get_availability_error(self):
        if self.is_available():
            return None

        return ProviderUnavailableError(
            "Cloud provider requires at least one configured cloud provider.",
            provider=self.provider_name,
        )

    def resolve_configuration(self, endpoint, api_key="", *, allow_probe=True):
        return self.detector.resolve(
            endpoint=endpoint,
            api_key=api_key,
            allow_probe=allow_probe,
        )

    def list_models(self) -> list[dict]:
        provider_config, adapter = self._resolve_runtime_provider()
        return adapter.list_models(provider_config)

    def chat(self, messages: list[dict], model: str, settings: dict | None = None) -> dict:
        provider_config, adapter = self._resolve_runtime_provider(settings=settings)
        return adapter.chat(
            provider_config,
            messages,
            model,
            settings or {},
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        provider_config, adapter = self._resolve_runtime_provider(settings=settings)
        yield from adapter.stream_chat(
            provider_config,
            messages,
            model,
            settings or {},
            should_stop=should_stop,
        )

    def _build_adapters(self):
        return {
            "openai_compatible": OpenAICompatibleCloudAdapter(self, self.http_client),
            "anthropic": AnthropicCloudAdapter(self, self.http_client),
            "google": GoogleCloudAdapter(self, self.http_client),
            "microsoft_foundry": MicrosoftFoundryCloudAdapter(self, self.http_client),
        }

    def _resolve_runtime_provider(self, settings=None):
        provider_config = self._resolve_provider_config(settings=settings)
        adapter_name = str(provider_config.get("resolved_adapter") or "").strip().lower()
        if not adapter_name:
            try:
                resolved = self.resolve_configuration(
                    provider_config.get("endpoint", ""),
                    provider_config.get("api_key", ""),
                    allow_probe=True,
                )
            except ValueError as error:
                raise ProviderUnavailableError(
                    f"Cloud provider is not fully configured: {error}",
                    provider=self.provider_name,
                ) from error

            provider_config = {
                **provider_config,
                "resolved_adapter": resolved["resolved_adapter"],
                "resolved_metadata": resolved["resolved_metadata"],
            }
            adapter_name = provider_config["resolved_adapter"]

        adapter = self.adapters.get(adapter_name)
        if not adapter:
            raise ProviderUnavailableError(
                f"Unsupported cloud adapter '{adapter_name}'.",
                provider=self.provider_name,
            )

        return provider_config, adapter

    def _resolve_provider_config(self, settings=None):
        model_config_id = (settings or {}).get("_model_config_id")
        provider_config = None
        if model_config_id:
            provider_config = self.settings_resolver.get_provider_config(
                model_config_id=model_config_id,
            )

        if provider_config:
            return provider_config

        provider_config = self._get_default_cloud_provider_config()
        if provider_config:
            return provider_config

        raise ProviderUnavailableError(
            "Cloud provider requires at least one configured cloud provider.",
            provider=self.provider_name,
        )

    def _get_default_cloud_provider_config(self):
        return self.settings_resolver.get_provider_config(provider_name=self.provider_name)


