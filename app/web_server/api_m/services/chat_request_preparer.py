from dataclasses import dataclass
import uuid

from tool_m import ToolCommandParser


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
    tool_confirmation: dict | None
    tool_directives: list[dict]


class ChatRequestPreparer:
    ALLOWED_MESSAGE_ROLES = {"system", "user", "assistant", "tool"}
    MAX_MESSAGES_PER_REQUEST = 100
    MAX_MESSAGE_CONTENT_CHARS = 20000

    MAX_TOOL_DIRECTIVES = 20

    def __init__(
        self,
        db_manager,
        context_builder,
        request_id_resolver=None,
        tool_command_parser=None,
    ):
        self.db = db_manager
        self.context_builder = context_builder
        self.request_id_resolver = request_id_resolver or self._resolve_request_id
        self.tool_command_parser = tool_command_parser or ToolCommandParser()

    def prepare(self, data, default_profile, default_provider):
        self._validate_messages(data)
        self._validate_context_messages(data)
        conversation_id = self._parse_conversation_id(data)
        conversation = self._get_conversation(conversation_id)
        project = self.context_builder.resolve_project(
            self._parse_optional_int(data.get("project_id"), "project_id"),
            conversation,
        )
        profile = self.context_builder.resolve_profile(
            self._parse_optional_int(data.get("profile_id"), "profile_id"),
            conversation,
            default_profile,
        )
        project_model_id = self._parse_optional_int(
            data.get("project_model_id", conversation["project_model_id"] if conversation else None),
            "project_model_id",
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
        if model_config:
            generation_settings["_reasoning_mode"] = model_config.get(
                "reasoning_mode",
                "auto",
            )

        request_messages = self._build_server_side_request_messages(
            conversation,
            data["messages"],
        )
        input_request_messages = self._build_input_request_messages(
            data,
            request_messages,
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
                input_request_messages,
                project_model=project_model,
            ),
            generation_settings=generation_settings,
            request_messages=request_messages,
            request_id=self.request_id_resolver(data.get("request_id")),
            stream_requested=self._is_stream_requested(data.get("stream")),
            assistant_message_meta=self._build_assistant_message_meta(
                model_config,
                profile,
                provider,
                model,
                project_model=project_model,
            ),
            tool_confirmation=self._parse_tool_confirmation(data.get("tool_confirmation")),
            tool_directives=self._parse_tool_directives(data, input_request_messages),
        )

    def _validate_messages(self, data):
        if "messages" not in data:
            raise ChatRequestError("Missing messages")

        if not isinstance(data.get("messages"), list):
            raise ChatRequestError("messages must be a list")

        if len(data["messages"]) > self.MAX_MESSAGES_PER_REQUEST:
            raise ChatRequestError(
                f"messages must include at most {self.MAX_MESSAGES_PER_REQUEST} items"
            )

        for index, message in enumerate(data["messages"]):
            if not isinstance(message, dict):
                raise ChatRequestError(f"messages[{index}] must be an object")

            role = str(message.get("role") or "").strip()
            if role not in self.ALLOWED_MESSAGE_ROLES:
                raise ChatRequestError(f"messages[{index}].role is not supported")

            content = self._normalize_message_content(message.get("content"))
            if len(content) > self.MAX_MESSAGE_CONTENT_CHARS:
                raise ChatRequestError(
                    f"messages[{index}].content must be at most "
                    f"{self.MAX_MESSAGE_CONTENT_CHARS} characters"
                )

    def _validate_context_messages(self, data):
        if "context_messages" not in data:
            return

        if not isinstance(data.get("context_messages"), list):
            raise ChatRequestError("context_messages must be a list")

        if len(data["context_messages"]) > self.MAX_MESSAGES_PER_REQUEST:
            raise ChatRequestError(
                f"context_messages must include at most {self.MAX_MESSAGES_PER_REQUEST} items"
            )

        for index, message in enumerate(data["context_messages"]):
            if not isinstance(message, dict):
                raise ChatRequestError(f"context_messages[{index}] must be an object")

            role = str(message.get("role") or "").strip()
            if role not in self.ALLOWED_MESSAGE_ROLES:
                raise ChatRequestError(f"context_messages[{index}].role is not supported")

            content = self._normalize_message_content(message.get("content"))
            if len(content) > self.MAX_MESSAGE_CONTENT_CHARS:
                raise ChatRequestError(
                    f"context_messages[{index}].content must be at most "
                    f"{self.MAX_MESSAGE_CONTENT_CHARS} characters"
                )

    def _parse_conversation_id(self, data):
        return self._parse_optional_int(
            data.get("conversation_id"),
            "conversation_id",
        )

    def _parse_optional_int(self, raw_value, field_name):
        if raw_value is None or raw_value == "":
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            raise ChatRequestError(f"Invalid {field_name}")

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

    def _build_input_request_messages(self, data, request_messages):
        if "context_messages" not in data:
            return request_messages

        return [
            self._normalize_request_message(message)
            for message in data.get("context_messages", [])
            if self._is_supported_context_message(message)
        ]

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

        return message.get("role") in self.ALLOWED_MESSAGE_ROLES

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

    def _resolve_request_id(self, raw_request_id):
        normalized = str(raw_request_id or "").strip()
        if normalized:
            return normalized

        return str(uuid.uuid4())

    def _parse_tool_confirmation(self, raw_confirmation):
        if raw_confirmation in (None, ""):
            return None

        if not isinstance(raw_confirmation, dict):
            raise ChatRequestError("tool_confirmation must be an object")

        name = str(
            raw_confirmation.get("name") or raw_confirmation.get("tool_name") or ""
        ).strip()
        if not name:
            raise ChatRequestError("tool_confirmation.name is required")

        arguments = raw_confirmation.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ChatRequestError("tool_confirmation.arguments must be an object")

        confirmation = {
            "name": name,
            "arguments": arguments,
            "reason": str(raw_confirmation.get("reason") or "").strip(),
        }
        source_message_id = self._parse_optional_int(
            raw_confirmation.get("source_message_id"),
            "tool_confirmation.source_message_id",
        )
        source_event_index = self._parse_optional_int(
            raw_confirmation.get("source_event_index"),
            "tool_confirmation.source_event_index",
        )
        if (source_message_id is None) != (source_event_index is None):
            raise ChatRequestError(
                "tool_confirmation source_message_id and source_event_index are required together"
            )
        if source_message_id is not None:
            confirmation["source_message_id"] = source_message_id
            confirmation["source_event_index"] = source_event_index
        return confirmation

    def _parse_tool_directives(self, data, input_request_messages):
        command_content = self._active_user_message_content(input_request_messages)
        parsed_directives = self.tool_command_parser.parse(command_content)
        if len(parsed_directives) > self.MAX_TOOL_DIRECTIVES:
            raise ChatRequestError(
                f"A message may contain at most {self.MAX_TOOL_DIRECTIVES} tool commands"
            )

        if "tool_directives" not in data:
            return parsed_directives

        raw_directives = data.get("tool_directives")
        if not isinstance(raw_directives, list):
            raise ChatRequestError("tool_directives must be a list")
        if len(raw_directives) > self.MAX_TOOL_DIRECTIVES:
            raise ChatRequestError(
                f"tool_directives may include at most {self.MAX_TOOL_DIRECTIVES} items"
            )

        normalized_directives = []
        for index, directive in enumerate(raw_directives):
            if not isinstance(directive, dict):
                raise ChatRequestError(f"tool_directives[{index}] must be an object")
            start = directive.get("start")
            end = directive.get("end")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
            ):
                raise ChatRequestError(
                    f"tool_directives[{index}].start and end must be integers"
                )
            normalized_directives.append(
                {
                    "tool_name": str(directive.get("tool_name") or "").strip().lower(),
                    "instruction": str(directive.get("instruction") or "").strip(),
                    "start": start,
                    "end": end,
                }
            )

        if normalized_directives != parsed_directives:
            raise ChatRequestError(
                "tool_directives do not match the tool commands in the active user message"
            )
        return parsed_directives

    def _active_user_message_content(self, messages):
        if messages and messages[-1].get("role") == "user":
            return self._normalize_message_content(messages[-1].get("content"))
        return ""

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
