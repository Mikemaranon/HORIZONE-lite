from abc import ABC, abstractmethod

from config_m import ProviderConfig

from ..exceptions import ModelOperationError
from ..provider_settings_resolver import ProviderSettingsResolver

class ModelProvider(ABC):
    provider_name = "base"

    def __init__(
        self,
        config: ProviderConfig,
        db_manager=None,
        http_client=None,
        settings_resolver=None,
    ):
        self.config = config
        self.http_client = http_client
        self.settings_resolver = settings_resolver or ProviderSettingsResolver(db_manager)

    def is_available(self) -> bool:
        return True

    def get_availability_error(self):
        return None

    def cancel_stream(self) -> bool:
        return False

    @abstractmethod
    def list_models(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages: list[dict], model: str, settings: dict | None = None) -> dict:
        raise NotImplementedError

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        if self.is_stop_requested(should_stop):
            yield {
                "type": "response",
                "response": self.normalize_chat_response(
                    model=model,
                    content="",
                    finish_reason="cancelled",
                    raw_response={"cancelled": True},
                ),
            }
            return

        response = self.chat(messages, model, settings)
        content = (response.get("message") or {}).get("content", "")

        if content:
            yield {
                "type": "delta",
                "delta": content,
            }

        yield {
            "type": "response",
            "response": response,
        }

    def normalize_messages(self, messages: list[dict]) -> list[dict]:
        normalized_messages = []

        for raw_message in messages or []:
            role = raw_message.get("role")
            if not role:
                raise ModelOperationError(
                    "Each message must define a role.",
                    provider=self.provider_name,
                )

            content = self._normalize_content(raw_message.get("content", ""))
            normalized_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return normalized_messages

    def normalize_model_entry(
        self,
        *,
        model_id: str,
        display_name: str | None = None,
        source=None,
        metadata=None,
    ) -> dict:
        return {
            "id": model_id,
            "provider": self.provider_name,
            "display_name": display_name or model_id,
            "source": source,
            "metadata": metadata or {},
        }

    def normalize_chat_response(
        self,
        *,
        model: str,
        content: str,
        usage=None,
        finish_reason=None,
        raw_response=None,
        message_id=None,
        reasoning_content="",
    ) -> dict:
        response = {
            "provider": self.provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": usage or {},
            "finish_reason": finish_reason,
            "message_id": message_id,
            "raw": raw_response or {},
        }
        if reasoning_content:
            response["message"]["reasoning_content"] = reasoning_content
        return response

    def build_catalog(self, models: list[dict], error=None) -> dict:
        return {
            "provider": self.provider_name,
            "available": error is None and self.is_available(),
            "models": models,
            "error": error.to_dict() if error else None,
        }

    def get_common_generation_settings(self, settings: dict | None = None) -> dict:
        settings = settings or {}
        normalized = {}

        if settings.get("temperature") is not None:
            normalized["temperature"] = float(settings["temperature"])
        if settings.get("top_p") is not None:
            normalized["top_p"] = float(settings["top_p"])
        if settings.get("max_tokens") is not None:
            normalized["max_tokens"] = int(settings["max_tokens"])
        if settings.get("stop") is not None:
            normalized["stop"] = settings["stop"]

        return normalized

    def is_stop_requested(self, should_stop=None) -> bool:
        return bool(should_stop and should_stop())

    def _normalize_content(self, content) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(text)
            return "\n".join(parts)

        if content is None:
            return ""

        return str(content)
