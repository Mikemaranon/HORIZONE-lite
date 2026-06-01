from ....exceptions import ProviderUnavailableError

from .base import CloudAdapterBase


class OpenAICompatibleCloudAdapter(CloudAdapterBase):
    adapter_name = "openai_compatible"
    supports_streaming = True

    def list_models(self, provider_config):
        response = self.http_client.get_json(
            f"{self._get_base_url(provider_config)}/models",
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )

        models = []
        for item in response.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(
                self.owner.normalize_model_entry(
                    model_id=model_id,
                    display_name=model_id,
                    source=provider_config.get("name") or "cloud",
                    metadata=self._build_common_metadata(
                        provider_config,
                        {
                            "owned_by": item.get("owned_by"),
                            "created": item.get("created"),
                        },
                    ),
                )
            )

        return models

    def chat(self, provider_config, messages, model, settings):
        payload = self._build_chat_payload(messages, model, settings, stream=False)
        response = self.http_client.post_json(
            f"{self._get_base_url(provider_config)}/chat/completions",
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
            raw_response=self._build_common_metadata(
                provider_config,
                {
                    "adapter_response_id": response.get("id"),
                },
            ),
            message_id=response.get("id"),
        )

    def stream_chat(self, provider_config, messages, model, settings, should_stop=None):
        payload = self._build_chat_payload(messages, model, settings, stream=True)
        content_parts = []
        usage = {}
        finish_reason = None
        response_model = model
        message_id = None
        chunk_count = 0

        for chunk in self.http_client.stream_sse_json(
            f"{self._get_base_url(provider_config)}/chat/completions",
            payload,
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        ):
            if self.owner.is_stop_requested(should_stop):
                break

            chunk_count += 1
            response_model = chunk.get("model", response_model)
            message_id = chunk.get("id") or message_id
            if chunk.get("usage"):
                usage = chunk["usage"]

            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            text = delta.get("content") or ""
            if text:
                content_parts.append(text)
                yield {"type": "delta", "delta": text}

            if choice.get("finish_reason") is not None:
                finish_reason = choice.get("finish_reason")

        if self.owner.is_stop_requested(should_stop):
            finish_reason = "cancelled"

        yield {
            "type": "response",
            "response": self.owner.normalize_chat_response(
                model=response_model,
                content="".join(content_parts),
                usage=usage,
                finish_reason=finish_reason,
                raw_response=self._build_common_metadata(
                    provider_config,
                    {
                        "streamed": True,
                        "chunk_count": chunk_count,
                        "cancelled": finish_reason == "cancelled",
                    },
                ),
                message_id=message_id,
            ),
        }

    def _build_chat_payload(self, messages, model, settings, *, stream):
        payload = {
            "model": model,
            "messages": self.owner.normalize_messages(messages),
            "stream": stream,
        }

        if stream:
            payload["stream_options"] = {"include_usage": True}

        common = self.owner.get_common_generation_settings(settings)
        if common.get("temperature") is not None:
            payload["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            payload["top_p"] = common["top_p"]
        if common.get("max_tokens") is not None:
            payload["max_completion_tokens"] = common["max_tokens"]
        if common.get("stop") is not None:
            payload["stop"] = common["stop"]

        return payload

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
        return {"Authorization": f"Bearer {api_key}"}


