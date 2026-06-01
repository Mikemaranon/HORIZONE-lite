from ....exceptions import ProviderUnavailableError

from .base import CloudAdapterBase


class MicrosoftFoundryCloudAdapter(CloudAdapterBase):
    adapter_name = "microsoft_foundry"

    def list_models(self, provider_config):
        raise ProviderUnavailableError(
            "Automatic model listing is not available for this Microsoft Foundry endpoint yet. "
            "Create the model entry manually and use the deployment name as the model.",
            provider="cloud",
        )

    def chat(self, provider_config, messages, model, settings):
        payload = {
            "model": model,
            "messages": self.owner.normalize_messages(messages),
        }
        common = self.owner.get_common_generation_settings(settings)
        if common.get("temperature") is not None:
            payload["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            payload["top_p"] = common["top_p"]
        if common.get("max_tokens") is not None:
            payload["max_tokens"] = common["max_tokens"]
        if common.get("stop") is not None:
            payload["stop"] = common["stop"]

        response = self.http_client.post_json(
            f"{self._get_base_url(provider_config)}/chat/completions?api-version=2024-05-01-preview",
            payload,
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )

        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return self.owner.normalize_chat_response(
            model=response.get("model", model),
            content=message.get("content", "") or "",
            usage=response.get("usage", {}),
            finish_reason=choice.get("finish_reason"),
            raw_response=self._build_common_metadata(provider_config),
        )

    def _build_headers(self, provider_config):
        api_key = str(
            provider_config.get("api_key")
            or self.owner.settings_resolver.get_cloud_api_key(
                self.adapter_name,
                self.owner.config.openai_api_key,
            )
            or ""
        ).strip()
        if not api_key:
            raise ProviderUnavailableError(
                "Cloud provider requires an API key for this endpoint.",
                provider="cloud",
            )
        return {
            "api-key": api_key,
            "extra-parameters": "pass-through",
        }
