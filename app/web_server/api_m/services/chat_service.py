from dataclasses import dataclass

from model_m import ProviderError
from .source_attribution_service import SourceAttributionService


class ChatRequestError(ValueError):
    pass


class ChatResourceNotFoundError(LookupError):
    pass


@dataclass
class PreparedChatRequest:
    conversation_id: int | None
    conversation: dict | None
    project: dict | None
    project_model: dict | None
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
        source_attribution_service=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.context_builder = context_builder
        self.persistence_service = persistence_service
        self.stream_service = stream_service
        self.tool_manager = tool_manager
        self.source_attribution_service = source_attribution_service or SourceAttributionService(db_manager)

    def handle_request(self, data, parse_int, default_profile, default_provider):
        prepared = self._prepare_request(
            data,
            parse_int=parse_int,
            default_profile=default_profile,
            default_provider=default_provider,
        )
        source_follow_up_response = self.source_attribution_service.build_follow_up_response(
            conversation_id=prepared.conversation_id,
            request_messages=prepared.request_messages,
            provider=prepared.provider,
            model=prepared.model,
        )

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
                self._build_tool_context(prepared),
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
        project_model_id = self._parse_optional_int(
            data.get("project_model_id", conversation["project_model_id"] if conversation else None),
            "project_model_id",
            parse_int,
        )
        project_model = self._resolve_project_model(project_model_id, project)
        if project_model:
            profile = self.db.profiles.get(project_model["profile_id"])

        model_config_id = self._parse_optional_int(
            project_model["model_id"] if project_model else data.get(
                "model_config_id",
                conversation["model_config_id"] if conversation else None,
            ),
            "model_config_id",
            parse_int,
        )
        model_config = self.db.models.get(model_config_id) if model_config_id else None

        provider = data.get("provider") or (conversation["provider"] if conversation else None)
        model = data.get("model") or (conversation["model"] if conversation else None)

        if project_model and model_config:
            provider = model_config["provider"]
            model = model_config["name"]
        elif model_config:
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

        request_messages = self._build_server_side_request_messages(
            conversation,
            data["messages"],
        )

        return PreparedChatRequest(
            conversation_id=conversation_id,
            conversation=conversation,
            project=project,
            project_model=project_model,
            model_config_id=model_config_id,
            provider=provider,
            model=model,
            input_messages=self.context_builder.build_input_messages(
                project,
                profile,
                request_messages,
                project_model=project_model,
            ),
            generation_settings=generation_settings,
            request_messages=request_messages,
            request_id=self.stream_service.resolve_request_id(data.get("request_id")),
            stream_requested=self._is_stream_requested(data.get("stream")),
            assistant_message_meta=self._build_assistant_message_meta(
                model_config,
                profile,
                provider,
                model,
                project_model=project_model,
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
                    tool_context=self._build_tool_context(prepared),
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

    def _build_tool_context(self, prepared):
        workspace = None
        if prepared.project:
            workspace = self.db.project_workspaces.get_by_project(prepared.project["id"])

        return {
            "conversation_id": prepared.conversation_id,
            "project": prepared.project,
            "workspace": workspace,
        }

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

    def _resolve_project_model(self, project_model_id, project):
        if not project_model_id:
            return None

        project_model = self.db.project_models.get(project_model_id)
        if not project_model:
            raise ChatResourceNotFoundError("Project agent not found")

        if project and project_model.get("project_id") != project.get("id"):
            raise ChatRequestError("Project agent does not belong to this project")

        if not project:
            raise ChatRequestError("Project agent requires a project chat")

        return project_model

    def _build_server_side_request_messages(self, conversation, incoming_messages):
        normalized_incoming_messages = [
            self._normalize_request_message(message)
            for message in incoming_messages
            if self._is_supported_context_message(message)
        ]

        if not conversation:
            return normalized_incoming_messages

        stored_messages = [
            self._stored_message_to_request_message(message)
            for message in self.db.messages.for_conversation(conversation["id"])
        ]
        new_messages = self._extract_unpersisted_request_messages(
            stored_messages,
            normalized_incoming_messages,
        )
        return stored_messages + new_messages

    def _stored_message_to_request_message(self, message):
        return {
            "role": message.get("role"),
            "content": message.get("content", ""),
            "project_model_id": message.get("project_model_id"),
            "project_model_name": message.get("project_model_name", ""),
            "model_config_id": message.get("model_config_id"),
            "model_name": message.get("model_name", ""),
            "profile_id": message.get("profile_id"),
            "profile_name": message.get("profile_name", ""),
            "tool_events": message.get("tool_events") or [],
        }

    def _extract_unpersisted_request_messages(self, stored_messages, incoming_messages):
        if not stored_messages:
            return incoming_messages

        if not incoming_messages:
            return []

        stored_signatures = [
            self._message_signature(message)
            for message in stored_messages
        ]
        incoming_signatures = [
            self._message_signature(message)
            for message in incoming_messages
        ]

        if (
            len(incoming_signatures) >= len(stored_signatures)
            and incoming_signatures[: len(stored_signatures)] == stored_signatures
        ):
            return incoming_messages[len(stored_signatures):]

        if (
            len(incoming_signatures) <= len(stored_signatures)
            and stored_signatures[-len(incoming_signatures):] == incoming_signatures
        ):
            return []

        overlap_size = self._find_history_overlap_size(
            stored_signatures,
            incoming_signatures,
        )
        if overlap_size:
            return incoming_messages[overlap_size:]

        return incoming_messages

    def _find_history_overlap_size(self, stored_signatures, incoming_signatures):
        max_overlap = min(len(stored_signatures), len(incoming_signatures))

        for size in range(max_overlap, 0, -1):
            if stored_signatures[-size:] == incoming_signatures[:size]:
                return size

        return 0

    def _normalize_request_message(self, message):
        return {
            **message,
            "role": str(message.get("role") or "").strip(),
            "content": self._normalize_message_content(message.get("content")),
        }

    def _is_supported_context_message(self, message):
        if not isinstance(message, dict):
            return False

        return message.get("role") in {"system", "user", "assistant", "tool"}

    def _message_signature(self, message):
        return (
            str(message.get("role") or "").strip(),
            self._normalize_message_content(message.get("content")).strip(),
        )

    def _normalize_message_content(self, content):
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                    continue

                if isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        parts.append(text)

            return "\n".join(parts)

        if content is None:
            return ""

        return str(content)

    def _is_stream_requested(self, raw_value):
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}

        return bool(raw_value)

    def _build_assistant_message_meta(self, model_config, profile, provider, model, project_model=None):
        return {
            "project_model_id": project_model["id"] if project_model else None,
            "project_model_name": project_model["nickname"] if project_model else "",
            "model_config_id": model_config["id"] if model_config else None,
            "model_name": model_config["display_name"] if model_config else model,
            "profile_id": profile["id"] if profile else None,
            "profile_name": profile["name"] if profile else "",
            "provider": provider,
        }
