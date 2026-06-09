from ..exceptions import ModelOperationError, ProviderUnavailableError
from ..http_client import JsonHttpClient
from .base_provider import ModelProvider


class LlamaCppProvider(ModelProvider):
    provider_name = "llama_cpp"

    def __init__(
        self,
        config,
        db_manager=None,
        http_client=None,
        settings_resolver=None,
        runtime_manager=None,
    ):
        super().__init__(
            config,
            db_manager=db_manager,
            http_client=http_client,
            settings_resolver=settings_resolver,
        )
        self.http_client = http_client or JsonHttpClient(config.request_timeout_seconds)
        self.runtime_manager = runtime_manager

    def list_models(self) -> list[dict]:
        self._ensure_runtime_ready()
        base_url = self._get_base_url()
        response = self.http_client.get_json(
            f"{base_url}/models",
            headers={},
            provider_name=self.provider_name,
        )
        self._raise_if_error_response(response)

        models = []
        for item in response.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue

            models.append(
                self.normalize_model_entry(
                    model_id=model_id,
                    display_name=item.get("display_name") or model_id,
                    source="horizone_runtime",
                    metadata={
                        "object": item.get("object"),
                        "owned_by": item.get("owned_by"),
                        "created": item.get("created"),
                        "meta": item.get("meta", {}),
                    },
                )
            )

        return models

    def chat(self, messages: list[dict], model: str, settings: dict | None = None) -> dict:
        self._ensure_runtime_ready(settings=settings, model=model)
        payload = self._build_chat_payload(messages, model, settings, stream=False)
        base_url = self._get_base_url(settings=settings)

        response = self.http_client.post_json(
            f"{base_url}/chat/completions",
            payload,
            headers={},
            provider_name=self.provider_name,
        )
        self._raise_if_error_response(response, model=model)

        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return self.normalize_chat_response(
            model=response.get("model", model),
            content=message.get("content", "") or "",
            usage=response.get("usage", {}),
            finish_reason=choice.get("finish_reason"),
            raw_response=response,
            message_id=response.get("id"),
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        self._ensure_runtime_ready(settings=settings, model=model)
        payload = self._build_chat_payload(messages, model, settings, stream=True)
        base_url = self._get_base_url(settings=settings)
        content_parts = []
        usage = {}
        finish_reason = None
        response_model = model
        message_id = None
        chunk_count = 0

        for chunk in self.http_client.stream_sse_json(
            f"{base_url}/chat/completions",
            payload,
            headers={},
            provider_name=self.provider_name,
        ):
            if self.is_stop_requested(should_stop):
                break

            chunk_count += 1
            self._raise_if_error_response(chunk, model=model)
            response_model = chunk.get("model", response_model)
            message_id = chunk.get("id") or message_id
            if chunk.get("usage"):
                usage = chunk["usage"]

            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            text = delta.get("content") or ""
            if text:
                content_parts.append(text)
                yield {
                    "type": "delta",
                    "delta": text,
                }

            if choice.get("finish_reason") is not None:
                finish_reason = choice.get("finish_reason")

        if self.is_stop_requested(should_stop):
            finish_reason = "cancelled"

        yield {
            "type": "response",
            "response": self.normalize_chat_response(
                model=response_model,
                content="".join(content_parts),
                usage=usage,
                finish_reason=finish_reason,
                raw_response={
                    "streamed": True,
                    "chunk_count": chunk_count,
                    "cancelled": finish_reason == "cancelled",
                },
                message_id=message_id,
            ),
        }

    def _build_chat_payload(self, messages, model, settings, *, stream):
        payload = {
            "model": model,
            "messages": self.normalize_messages(messages),
            "stream": stream,
        }

        if stream:
            payload["stream_options"] = {"include_usage": True}

        common = self.get_common_generation_settings(settings)
        if common.get("temperature") is not None:
            payload["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            payload["top_p"] = common["top_p"]
        if common.get("max_tokens") is not None:
            payload["max_tokens"] = common["max_tokens"]
        if common.get("stop") is not None:
            payload["stop"] = common["stop"]

        return payload

    def _get_base_url(self, settings=None):
        model_config_id = (settings or {}).get("_model_config_id")
        configured_endpoint = self.settings_resolver.get_provider_endpoint(
            self.provider_name,
            "",
            model_config_id=model_config_id,
        )
        if configured_endpoint:
            return str(configured_endpoint or "").rstrip("/")

        if self.runtime_manager:
            return f"{self.runtime_manager.base_url().rstrip('/')}/v1"

        base_url = self.settings_resolver.get_provider_endpoint(
            self.provider_name,
            self.config.llama_cpp_base_url,
            model_config_id=model_config_id,
        )
        return str(base_url or "").rstrip("/")

    def _ensure_runtime_ready(self, settings=None, model=None):
        if not self.runtime_manager:
            return

        snapshot = self.runtime_manager.start_if_available(
            model_config_id=(settings or {}).get("_model_config_id"),
            model_name=model,
        )
        if snapshot.get("status") == "ready":
            return

        message = snapshot.get("error_message") or "HORIZONE runtime is not ready."
        raise ProviderUnavailableError(
            message,
            provider=self.provider_name,
            details={
                "runtime_status": snapshot.get("status"),
                "active_model": snapshot.get("active_model"),
                "base_url": snapshot.get("base_url"),
            },
        )

    def _raise_if_error_response(self, response, model=None):
        if not isinstance(response, dict):
            return

        raw_error = response.get("error")
        if not raw_error:
            return

        if isinstance(raw_error, dict):
            message = raw_error.get("message") or str(raw_error)
        else:
            message = str(raw_error)

        raise ModelOperationError(
            message,
            provider=self.provider_name,
            details={"raw_error": raw_error, "model": model},
        )
