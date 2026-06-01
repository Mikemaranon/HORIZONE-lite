from ....exceptions import ProviderUnavailableError

from .base import CloudAdapterBase


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


