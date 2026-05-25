from ..exceptions import ModelOperationError
from ..http_client import JsonHttpClient
from .base_provider import ModelProvider


class OllamaProvider(ModelProvider):
    provider_name = "ollama"

    def __init__(self, config, db_manager=None, http_client=None, settings_resolver=None):
        super().__init__(
            config,
            db_manager=db_manager,
            http_client=http_client,
            settings_resolver=settings_resolver,
        )
        self.http_client = http_client or JsonHttpClient(config.request_timeout_seconds)

    def list_models(self) -> list[dict]:
        base_url = self._get_base_url()
        response = self.http_client.get_json(
            f"{base_url}/tags",
            headers=self._build_headers(),
            provider_name=self.provider_name,
        )
        self._raise_if_error_response(response)

        models = []
        for item in response.get("models", []):
            model_id = item.get("model") or item.get("name")
            if not model_id:
                continue

            models.append(
                self.normalize_model_entry(
                    model_id=model_id,
                    display_name=item.get("name") or model_id,
                    source="ollama",
                    metadata={
                        "modified_at": item.get("modified_at"),
                        "size": item.get("size"),
                        "digest": item.get("digest"),
                        "details": item.get("details", {}),
                    },
                )
            )

        return models

    def chat(self, messages: list[dict], model: str, settings: dict | None = None) -> dict:
        payload = self._build_chat_payload(messages, model, settings, stream=False)
        base_url = self._get_base_url(settings=settings)

        response = self.http_client.post_json(
            f"{base_url}/chat",
            payload,
            headers=self._build_headers(),
            provider_name=self.provider_name,
        )
        self._raise_if_error_response(response, model=model)

        message = response.get("message", {})
        return self.normalize_chat_response(
            model=response.get("model", model),
            content=message.get("content", ""),
            usage={
                "prompt_tokens": response.get("prompt_eval_count"),
                "completion_tokens": response.get("eval_count"),
                "total_duration": response.get("total_duration"),
                "load_duration": response.get("load_duration"),
            },
            finish_reason=response.get("done_reason"),
            raw_response=response,
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        payload = self._build_chat_payload(messages, model, settings, stream=True)
        base_url = self._get_base_url(settings=settings)
        content_parts = []
        finish_reason = "stop"
        usage = {}
        response_model = model
        chunk_count = 0

        for chunk in self.http_client.stream_json_lines(
            f"{base_url}/chat",
            payload,
            headers=self._build_headers(),
            provider_name=self.provider_name,
        ):
            if self.is_stop_requested(should_stop):
                break

            chunk_count += 1
            self._raise_if_error_response(chunk, model=model)
            response_model = chunk.get("model", response_model)

            message = chunk.get("message") or {}
            text = message.get("content") or ""
            if text:
                content_parts.append(text)
                yield {
                    "type": "delta",
                    "delta": text,
                }

            if chunk.get("done"):
                finish_reason = chunk.get("done_reason") or finish_reason
                usage = {
                    "prompt_tokens": chunk.get("prompt_eval_count"),
                    "completion_tokens": chunk.get("eval_count"),
                    "total_duration": chunk.get("total_duration"),
                    "load_duration": chunk.get("load_duration"),
                }

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
            ),
        }

    def _build_chat_payload(self, messages, model, settings, *, stream):
        payload = {
            "model": model,
            "messages": self.normalize_messages(messages),
            "stream": stream,
        }

        options = self._build_options(settings)
        if options:
            payload["options"] = options

        return payload

    def _build_headers(self):
        api_key = self.settings_resolver.get_setting(
            "ollama_api_key",
            self.config.ollama_api_key,
        )
        if not api_key:
            return {}
        return {"Authorization": f"Bearer {api_key}"}

    def _get_base_url(self, settings=None):
        model_config_id = (settings or {}).get("_model_config_id")
        return self.settings_resolver.get_provider_endpoint(
            self.provider_name,
            self.config.ollama_base_url,
            model_config_id=model_config_id,
        )

    def _build_options(self, settings):
        common = self.get_common_generation_settings(settings)
        options = {}

        if common.get("temperature") is not None:
            options["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            options["top_p"] = common["top_p"]
        if common.get("max_tokens") is not None:
            options["num_predict"] = common["max_tokens"]
        if common.get("stop") is not None:
            options["stop"] = common["stop"]

        return options

    def _raise_if_error_response(self, response, model=None):
        if not isinstance(response, dict):
            return

        raw_error = response.get("error")
        if not raw_error:
            return

        message = str(raw_error)
        if "llama runner process has terminated" in message:
            resolved_model = f" for `{model}`" if model else ""
            message = (
                f"Ollama could find the model{resolved_model}, but its local runner stopped "
                "during generation. Restart Ollama and also try `ollama run <model>` "
                "outside the app to confirm the model works."
            )

        raise ModelOperationError(
            message,
            provider=self.provider_name,
            details={"raw_error": raw_error},
        )
