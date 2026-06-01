from ....exceptions import ProviderUnavailableError

from .base import CloudAdapterBase


class AnthropicCloudAdapter(CloudAdapterBase):
    adapter_name = "anthropic"

    def list_models(self, provider_config):
        response = self.http_client.get_json(
            f"{self._get_base_url(provider_config)}/v1/models",
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )
        return [
            self.owner.normalize_model_entry(
                model_id=item["id"],
                display_name=item.get("display_name") or item["id"],
                source=provider_config.get("name") or "cloud",
                metadata=self._build_common_metadata(
                    provider_config,
                    {
                        "created_at": item.get("created_at"),
                        "type": item.get("type"),
                    },
                ),
            )
            for item in response.get("data", [])
            if item.get("id")
        ]

    def chat(self, provider_config, messages, model, settings):
        normalized_messages = self.owner.normalize_messages(messages)
        system_prompt, conversation_messages = self._split_system_messages(normalized_messages)
        common = self.owner.get_common_generation_settings(settings)

        payload = {
            "model": model,
            "messages": conversation_messages,
            "max_tokens": common.get("max_tokens", 1024),
        }
        if system_prompt:
            payload["system"] = system_prompt
        if common.get("temperature") is not None:
            payload["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            payload["top_p"] = common["top_p"]
        if common.get("stop") is not None:
            payload["stop_sequences"] = common["stop"]

        response = self.http_client.post_json(
            f"{self._get_base_url(provider_config)}/v1/messages",
            payload,
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )

        return self.owner.normalize_chat_response(
            model=response.get("model", model),
            content=self._extract_text_response(response),
            usage=response.get("usage", {}),
            finish_reason=response.get("stop_reason"),
            raw_response=self._build_common_metadata(
                provider_config,
                {
                    "adapter_response_id": response.get("id"),
                },
            ),
            message_id=response.get("id"),
        )

    def _build_headers(self, provider_config):
        api_key = str(
            provider_config.get("api_key")
            or self.owner.settings_resolver.get_cloud_api_key(
                self.adapter_name,
                self.owner.config.anthropic_api_key,
            )
            or ""
        ).strip()
        if not api_key:
            raise ProviderUnavailableError(
                "Cloud provider requires an API key for this endpoint.",
                provider="cloud",
            )
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    def _split_system_messages(self, messages):
        system_parts = []
        conversation_messages = []
        for message in messages:
            if message["role"] == "system":
                system_parts.append(message["content"])
                continue
            conversation_messages.append(message)
        return "\n\n".join(part for part in system_parts if part), conversation_messages

    def _extract_text_response(self, response):
        parts = []
        for item in response.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                parts.append(item["text"])
        return "\n".join(parts)


