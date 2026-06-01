import json


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


