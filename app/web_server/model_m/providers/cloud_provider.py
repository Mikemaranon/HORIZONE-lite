import json
from urllib.parse import urlparse

from ..exceptions import ProviderUnavailableError
from ..http_client import JsonHttpClient
from .base_provider import ModelProvider


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

    def resolve_configuration(self, endpoint, api_key=""):
        return self.detector.resolve(endpoint=endpoint, api_key=api_key)

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


class CloudAdapterDetector:
    def __init__(self, http_client):
        self.http_client = http_client

    def resolve(self, endpoint, api_key=""):
        normalized_endpoint = self._normalize_endpoint(endpoint)
        parsed = urlparse(normalized_endpoint)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")

        candidates = [
            self._resolve_by_host(hostname, normalized_endpoint, path),
            self._resolve_by_path(hostname, normalized_endpoint, path),
        ]
        for candidate in candidates:
            if candidate:
                return candidate

        probed = self._probe_candidates(normalized_endpoint, api_key)
        if probed:
            return probed

        raise ValueError(
            "The cloud adapter could not be detected automatically. "
            "Use a known endpoint or a URL that exposes compatible routes."
        )

    def _resolve_by_host(self, hostname, endpoint, path):
        if hostname == "api.openai.com":
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("api.anthropic.com"):
            return self._build_resolution(
                "anthropic",
                self._normalize_anthropic_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("generativelanguage.googleapis.com"):
            return self._build_resolution(
                "google",
                self._normalize_google_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("openai.azure.com"):
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("services.ai.azure.com"):
            if "/openai/" in path or path.endswith("/openai/v1"):
                return self._build_resolution(
                    "openai_compatible",
                    self._normalize_openai_base_url(endpoint),
                    "hostname",
                )
            if path.endswith("/models") or not path:
                return self._build_resolution(
                    "microsoft_foundry",
                    self._normalize_foundry_base_url(endpoint),
                    "hostname",
                )

        return None

    def _resolve_by_path(self, hostname, endpoint, path):
        if path.endswith("/v1/messages"):
            return self._build_resolution(
                "anthropic",
                self._normalize_anthropic_base_url(endpoint),
                "path",
            )

        if "/v1beta/models" in path:
            return self._build_resolution(
                "google",
                self._normalize_google_base_url(endpoint),
                "path",
            )

        if path.endswith("/chat/completions") and hostname.endswith("services.ai.azure.com"):
            return self._build_resolution(
                "microsoft_foundry",
                self._normalize_foundry_base_url(endpoint),
                "path",
            )

        if path.endswith("/chat/completions") or path.endswith("/models") or "/openai/v1" in path:
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "path",
            )

        return None

    def _probe_candidates(self, endpoint, api_key):
        for probe in (
            self._probe_openai_compatible,
            self._probe_anthropic,
            self._probe_google,
        ):
            try:
                resolved = probe(endpoint, api_key)
            except Exception:
                resolved = None
            if resolved:
                return resolved
        return None

    def _probe_openai_compatible(self, endpoint, api_key):
        base_url = self._normalize_openai_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return self._build_resolution("openai_compatible", base_url, "probe")
        return None

    def _probe_anthropic(self, endpoint, api_key):
        base_url = self._normalize_anthropic_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/v1/models",
            headers=self._anthropic_headers(api_key),
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return self._build_resolution("anthropic", base_url, "probe")
        return None

    def _probe_google(self, endpoint, api_key):
        base_url = self._normalize_google_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/v1beta/models",
            headers={"x-goog-api-key": api_key} if api_key else {},
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("models"), list):
            return self._build_resolution("google", base_url, "probe")
        return None

    def _build_resolution(self, adapter_name, base_url, detected_from):
        return {
            "resolved_adapter": adapter_name,
            "resolved_metadata": {
                "base_url": base_url,
                "detected_from": detected_from,
            },
        }

    def _normalize_endpoint(self, endpoint):
        normalized = str(endpoint or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("Cloud providers need an endpoint.")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Cloud provider endpoint must be a valid http(s) URL.")
        return normalized

    def _normalize_openai_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models"):
            return normalized[: -len("/models")]
        if normalized == "https://api.openai.com":
            return f"{normalized}/v1"
        if normalized.endswith(".openai.azure.com") or normalized.endswith(".services.ai.azure.com/openai"):
            return f"{normalized}/v1"
        return normalized

    def _normalize_anthropic_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/v1/messages"):
            return normalized[: -len("/v1/messages")]
        if normalized.endswith("/v1/models"):
            return normalized[: -len("/v1/models")]
        if normalized.endswith("/v1"):
            return normalized[: -len("/v1")]
        return normalized

    def _normalize_google_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        for suffix in (
            "/v1beta/models",
            "/v1beta",
        ):
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]
        return normalized

    def _normalize_foundry_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models"):
            return normalized
        return f"{normalized}/models"

    def _anthropic_headers(self, api_key):
        headers = {"anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        return headers


class CloudAdapterBase:
    adapter_name = "base"
    supports_streaming = False

    def __init__(self, owner, http_client):
        self.owner = owner
        self.http_client = http_client

    def list_models(self, provider_config):
        raise NotImplementedError

    def chat(self, provider_config, messages, model, settings):
        raise NotImplementedError

    def stream_chat(
        self,
        provider_config,
        messages,
        model,
        settings,
        should_stop=None,
    ):
        if self.owner.is_stop_requested(should_stop):
            yield {
                "type": "response",
                "response": self.owner.normalize_chat_response(
                    model=model,
                    content="",
                    finish_reason="cancelled",
                    raw_response={"cancelled": True, "adapter": self.adapter_name},
                ),
            }
            return

        response = self.chat(provider_config, messages, model, settings)
        content = (response.get("message") or {}).get("content", "")
        if content:
            yield {"type": "delta", "delta": content}
        yield {"type": "response", "response": response}

    def _get_metadata(self, provider_config):
        metadata = provider_config.get("resolved_metadata")
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                parsed = json.loads(metadata)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _get_base_url(self, provider_config):
        metadata = self._get_metadata(provider_config)
        return metadata.get("base_url") or str(provider_config.get("endpoint") or "").rstrip("/")

    def _build_common_metadata(self, provider_config, extra=None):
        metadata = {
            "adapter": self.adapter_name,
            "provider_id": provider_config.get("id"),
            "provider_name": provider_config.get("name"),
        }
        if extra:
            metadata.update(extra)
        return metadata


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


class GoogleCloudAdapter(CloudAdapterBase):
    adapter_name = "google"

    def list_models(self, provider_config):
        response = self.http_client.get_json(
            f"{self._get_base_url(provider_config)}/v1beta/models",
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )

        discovered = {}
        for item in response.get("models", []):
            supported_methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in supported_methods:
                continue

            model_id = item.get("baseModelId") or self._strip_model_name(item.get("name"))
            if not model_id:
                continue

            discovered[model_id] = self.owner.normalize_model_entry(
                model_id=model_id,
                display_name=item.get("displayName") or model_id,
                source=provider_config.get("name") or "cloud",
                metadata=self._build_common_metadata(
                    provider_config,
                    {
                        "resource_name": item.get("name"),
                        "version": item.get("version"),
                        "input_token_limit": item.get("inputTokenLimit"),
                        "output_token_limit": item.get("outputTokenLimit"),
                    },
                ),
            )

        return sorted(discovered.values(), key=lambda item: item["id"])

    def chat(self, provider_config, messages, model, settings):
        normalized_messages = self.owner.normalize_messages(messages)
        system_prompt, conversation_messages = self._split_system_messages(normalized_messages)
        payload = {
            "contents": [self._to_google_content(message) for message in conversation_messages],
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        generation_config = self._build_generation_config(settings)
        if generation_config:
            payload["generationConfig"] = generation_config

        response = self.http_client.post_json(
            f"{self._get_base_url(provider_config)}/v1beta/models/{model}:generateContent",
            payload,
            headers=self._build_headers(provider_config),
            provider_name="cloud",
        )

        candidate = (response.get("candidates") or [{}])[0]
        candidate_content = candidate.get("content", {})
        return self.owner.normalize_chat_response(
            model=model,
            content=self._extract_text_parts(candidate_content.get("parts", [])),
            usage=response.get("usageMetadata", {}),
            finish_reason=candidate.get("finishReason"),
            raw_response=self._build_common_metadata(provider_config),
        )

    def _build_headers(self, provider_config):
        api_key = str(
            provider_config.get("api_key")
            or self.owner.settings_resolver.get_cloud_api_key(
                self.adapter_name,
                self.owner.config.google_api_key,
            )
            or ""
        ).strip()
        if not api_key:
            raise ProviderUnavailableError(
                "Cloud provider requires an API key for this endpoint.",
                provider="cloud",
            )
        return {"x-goog-api-key": api_key}

    def _strip_model_name(self, resource_name):
        if not resource_name:
            return None
        return resource_name.replace("models/", "", 1)

    def _split_system_messages(self, messages):
        system_parts = []
        conversation_messages = []
        for message in messages:
            if message["role"] == "system":
                system_parts.append(message["content"])
                continue
            conversation_messages.append(message)
        return "\n\n".join(part for part in system_parts if part), conversation_messages

    def _to_google_content(self, message):
        role = "model" if message["role"] == "assistant" else "user"
        return {
            "role": role,
            "parts": [{"text": message["content"]}],
        }

    def _build_generation_config(self, settings):
        common = self.owner.get_common_generation_settings(settings)
        config = {}
        if common.get("temperature") is not None:
            config["temperature"] = common["temperature"]
        if common.get("top_p") is not None:
            config["topP"] = common["top_p"]
        if common.get("max_tokens") is not None:
            config["maxOutputTokens"] = common["max_tokens"]
        if common.get("stop") is not None:
            config["stopSequences"] = common["stop"]
        return config

    def _extract_text_parts(self, parts):
        values = []
        for item in parts:
            text = item.get("text")
            if text:
                values.append(text)
        return "\n".join(values)


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
