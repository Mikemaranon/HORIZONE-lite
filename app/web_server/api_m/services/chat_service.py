from dataclasses import dataclass
from urllib.parse import urlparse

from model_m import ProviderError


class ChatRequestError(ValueError):
    pass


class ChatResourceNotFoundError(LookupError):
    pass


@dataclass
class PreparedChatRequest:
    conversation_id: int | None
    conversation: dict | None
    model_config_id: int | None
    provider: str
    model: str
    input_messages: list[dict]
    generation_settings: dict
    request_messages: list[dict]
    request_id: str
    stream_requested: bool
    assistant_message_meta: dict


class ChatService:
    def __init__(
        self,
        db_manager,
        model_manager,
        context_builder,
        persistence_service,
        stream_service,
        tool_manager=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.context_builder = context_builder
        self.persistence_service = persistence_service
        self.stream_service = stream_service
        self.tool_manager = tool_manager

    def handle_request(self, data, parse_int, default_profile, default_provider):
        prepared = self._prepare_request(
            data,
            parse_int=parse_int,
            default_profile=default_profile,
            default_provider=default_provider,
        )
        source_follow_up_response = self._build_source_follow_up_response(prepared)

        if prepared.conversation:
            self.persistence_service.prepare_conversation(
                prepared.conversation,
                prepared.provider,
                prepared.model,
                prepared.request_messages,
            )

        if source_follow_up_response:
            if prepared.stream_requested:
                return self.stream_service.build_static_stream_response(
                    prepared.conversation_id,
                    prepared.provider,
                    prepared.model,
                    prepared.request_id,
                    prepared.assistant_message_meta,
                    source_follow_up_response,
                )

            if prepared.conversation_id:
                self.persistence_service.finalize_response(
                    prepared.conversation_id,
                    source_follow_up_response,
                    prepared.assistant_message_meta,
                )
            payload = {"response": source_follow_up_response}
            if prepared.conversation_id:
                payload["conversation"] = self.db.conversations.get(prepared.conversation_id)
            return payload

        if prepared.stream_requested:
            return self.stream_service.build_stream_response(
                prepared.conversation_id,
                prepared.provider,
                prepared.input_messages,
                prepared.model,
                prepared.generation_settings,
                prepared.request_id,
                prepared.assistant_message_meta,
            )

        response = self._run_chat(prepared)
        payload = {"response": response}
        if prepared.conversation_id:
            payload["conversation"] = self.db.conversations.get(prepared.conversation_id)
        return payload

    def _prepare_request(self, data, parse_int, default_profile, default_provider):
        self._validate_messages(data)
        conversation_id = self._parse_conversation_id(data, parse_int)
        conversation = self._get_conversation(conversation_id)
        project = self.context_builder.resolve_project(
            self._parse_optional_int(data.get("project_id"), "project_id", parse_int),
            conversation,
        )
        profile = self.context_builder.resolve_profile(
            self._parse_optional_int(data.get("profile_id"), "profile_id", parse_int),
            conversation,
            default_profile,
        )
        model_config_id = self._parse_optional_int(
            data.get("model_config_id", conversation["model_config_id"] if conversation else None),
            "model_config_id",
            parse_int,
        )
        model_config = self.db.models.get(model_config_id) if model_config_id else None

        provider = data.get("provider") or (conversation["provider"] if conversation else None)
        model = data.get("model") or (conversation["model"] if conversation else None)

        if model_config:
            provider = provider or model_config["provider"]
            model = model or model_config["name"]

        if not provider:
            provider = default_provider
        if not model:
            raise ChatRequestError("Missing model")

        generation_settings = self.context_builder.build_generation_settings(
            profile,
            data.get("settings"),
        )
        if model_config_id:
            generation_settings["_model_config_id"] = model_config_id

        return PreparedChatRequest(
            conversation_id=conversation_id,
            conversation=conversation,
            model_config_id=model_config_id,
            provider=provider,
            model=model,
            input_messages=self.context_builder.build_input_messages(
                project,
                profile,
                data["messages"],
            ),
            generation_settings=generation_settings,
            request_messages=data["messages"],
            request_id=self.stream_service.resolve_request_id(data.get("request_id")),
            stream_requested=self._is_stream_requested(data.get("stream")),
            assistant_message_meta=self._build_assistant_message_meta(
                model_config,
                profile,
                provider,
                model,
            ),
        )

    def _run_chat(self, prepared):
        try:
            if self.tool_manager:
                response = self.tool_manager.chat(
                    prepared.provider,
                    prepared.input_messages,
                    prepared.model,
                    prepared.generation_settings,
                )
            else:
                response = self.model_manager.chat(
                    prepared.provider,
                    prepared.input_messages,
                    prepared.model,
                    prepared.generation_settings,
                )
        except ProviderError:
            raise

        if prepared.conversation_id:
            self.persistence_service.finalize_response(
                prepared.conversation_id,
                response,
                prepared.assistant_message_meta,
            )

        return response

    def _validate_messages(self, data):
        if "messages" not in data:
            raise ChatRequestError("Missing messages")

        if not isinstance(data.get("messages"), list):
            raise ChatRequestError("messages must be a list")

    def _parse_conversation_id(self, data, parse_int):
        return self._parse_optional_int(
            data.get("conversation_id"),
            "conversation_id",
            parse_int,
        )

    def _parse_optional_int(self, raw_value, field_name, parse_int):
        return parse_int(raw_value, field_name)

    def _get_conversation(self, conversation_id):
        if conversation_id is None:
            return None

        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            raise ChatResourceNotFoundError("Conversation not found")
        return conversation

    def _is_stream_requested(self, raw_value):
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}

        return bool(raw_value)

    def _build_assistant_message_meta(self, model_config, profile, provider, model):
        return {
            "model_config_id": model_config["id"] if model_config else None,
            "model_name": model_config["display_name"] if model_config else model,
            "profile_id": profile["id"] if profile else None,
            "profile_name": profile["name"] if profile else "",
            "provider": provider,
        }

    def _build_source_follow_up_response(self, prepared):
        latest_user_message = self._get_latest_user_message_content(prepared.request_messages)
        if not self._is_source_follow_up(latest_user_message):
            return None

        if not prepared.conversation_id:
            return self._build_no_sources_response(
                prepared.provider,
                prepared.model,
                message=(
                    "I have not consulted external sources in this thread yet. "
                    "If you want, I can search now and cite specific results."
                ),
            )

        previous_assistant_message = self._get_previous_assistant_message(prepared.conversation_id)
        if not previous_assistant_message:
            return self._build_no_sources_response(
                prepared.provider,
                prepared.model,
                message=(
                    "There is no previous assistant response in this thread to attribute sources to. "
                    "If you want, I can perform the search now."
                ),
            )

        tool_events = previous_assistant_message.get("tool_events") or []
        if not tool_events:
            return self._build_no_sources_response(
                prepared.provider,
                prepared.model,
                message=(
                    "I did not consult external sources in the previous response. "
                    "That response was not backed by any tool or web search in this thread. "
                    "If you want, I can search now and give you real sources."
                ),
            )

        return self._build_sources_response(
            prepared.provider,
            prepared.model,
            tool_events,
        )

    def _get_latest_user_message_content(self, messages):
        for message in reversed(messages or []):
            if message.get("role") != "user":
                continue
            return str(message.get("content") or "").strip()
        return ""

    def _is_source_follow_up(self, content):
        normalized = str(content or "").strip().lower()
        if not normalized:
            return False

        triggers = [
            "fuentes consultadas",
            "que fuentes has consultado",
            "qué fuentes has consultado",
            "dame las fuentes",
            "dime las fuentes",
            "sources consulted",
            "which sources did you use",
            "what sources did you use",
            "give me the sources",
            "tell me the sources",
            "show me the sources",
        ]
        return any(trigger in normalized for trigger in triggers)

    def _get_previous_assistant_message(self, conversation_id):
        messages = self.db.messages.for_conversation(conversation_id)
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message
        return None

    def _build_sources_response(self, provider, model, tool_events):
        source_lines = self._extract_tool_source_lines(tool_events)
        if source_lines:
            content = "The sources consulted in the previous response are:\n\n" + "\n".join(
                [f"- {line}" for line in source_lines]
            )
        else:
            tool_names = ", ".join(
                sorted(
                    {
                        str(tool_event.get("tool_name") or "").replace("_", " ")
                        for tool_event in tool_events
                        if tool_event.get("tool_name")
                    }
                )
            ) or "internal tools"
            content = (
                "The previous response did use tools, but there were no explicit URLs or web sources "
                f"left to cite. The tools used were: {tool_names}."
            )

        return {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "source_attribution": True,
                "tool_events": tool_events,
            },
        }

    def _build_no_sources_response(self, provider, model, message):
        return {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": message,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "source_attribution": True,
                "tool_events": [],
            },
        }

    def _extract_tool_source_lines(self, tool_events):
        seen = set()
        lines = []

        for tool_event in tool_events or []:
            result_payload = tool_event.get("result") or {}
            results = result_payload.get("results")
            if not isinstance(results, list):
                continue

            for item in results:
                if not isinstance(item, dict):
                    continue

                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not url:
                    continue

                parsed = urlparse(url)
                domain = parsed.netloc or url
                label = f"{title} — {domain}" if title else domain
                if url in seen:
                    continue
                seen.add(url)
                lines.append(label)

        return lines
