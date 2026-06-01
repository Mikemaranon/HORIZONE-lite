from dataclasses import dataclass

from .service_errors import RequestError, ResourceNotFoundError


class ConversationRequestError(RequestError):
    pass


class ConversationResourceNotFoundError(ResourceNotFoundError):
    pass


@dataclass(frozen=True)
class ConversationDefaults:
    profile: dict | None
    model: dict | None
    default_provider: str


@dataclass(frozen=True)
class ConversationSelection:
    project_id: int | None
    project_model_id: int | None
    quick_project_model_ids: list[int]
    profile_id: int | None
    model_config_id: int | None
    provider: str
    model: str


class ConversationService:
    def __init__(self, db_manager, config_manager, export_service=None):
        self.db = db_manager
        self.config_manager = config_manager
        self.export_service = export_service

    def list_conversations(self, project_id=None):
        parsed_project_id = self.parse_optional_int(project_id, "project_id")
        return self.db.conversations.all(parsed_project_id)

    def get_conversation(self, conversation_id, include_messages=False):
        parsed_id = self._parse_required_id(conversation_id, "id")
        conversation = self.db.conversations.get(parsed_id)
        if not conversation:
            raise ConversationResourceNotFoundError("Conversation not found")

        payload = {"conversation": conversation}
        if include_messages:
            payload["messages"] = self.db.messages.for_conversation(parsed_id)
        return payload

    def export_conversation(self, conversation_id):
        if not self.export_service:
            raise ConversationRequestError("Conversation export is unavailable")

        parsed_id = self._parse_required_id(conversation_id, "id")
        try:
            return self.export_service.build_conversation_export(parsed_id)
        except LookupError as error:
            raise ConversationResourceNotFoundError(str(error)) from error

    def create_conversation(self, data):
        defaults = self._get_defaults()
        selection = self._build_create_selection(data, defaults)
        conversation_id = self.db.conversations.create(
            title=data.get("title", "New Chat"),
            project_id=selection.project_id,
            project_model_id=selection.project_model_id,
            quick_project_model_ids=selection.quick_project_model_ids,
            profile_id=selection.profile_id,
            model_config_id=selection.model_config_id,
            provider=selection.provider,
            model=selection.model,
        )
        return self.db.conversations.get(conversation_id)

    def update_conversation(self, data):
        conversation_id = self._parse_required_id(data.get("id"), "id")
        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            raise ConversationResourceNotFoundError("Conversation not found")

        selection = self._build_update_selection(data, conversation)
        self.db.conversations.update(
            conversation_id=conversation_id,
            title=data.get("title", conversation["title"]),
            project_id=selection.project_id,
            project_model_id=selection.project_model_id,
            quick_project_model_ids=selection.quick_project_model_ids,
            profile_id=selection.profile_id,
            model_config_id=selection.model_config_id,
            provider=selection.provider,
            model=selection.model,
        )
        return self.db.conversations.get(conversation_id)

    def delete_conversation(self, conversation_id):
        parsed_id = self._parse_required_id(conversation_id, "id")
        conversation = self.db.conversations.get(parsed_id)
        if not conversation:
            raise ConversationResourceNotFoundError("Conversation not found")

        self.db.conversations.delete(parsed_id)
        return {"deleted": True, "conversation_id": parsed_id}

    def _build_create_selection(self, data, defaults):
        project_id = self.parse_optional_int(data.get("project_id"), "project_id")
        project_model_id = self.parse_optional_int(data.get("project_model_id"), "project_model_id")
        quick_ids = self.parse_quick_project_model_ids(data.get("quick_project_model_ids", []))
        project_model = self._resolve_project_model(project_model_id, project_id)
        effective_project_id = project_model["project_id"] if project_model else project_id
        self._validate_quick_project_model_ids(quick_ids, effective_project_id)

        if project_model:
            return self._selection_from_project_model(project_model, project_model_id, quick_ids)

        profile_id = self.parse_optional_int(
            data.get("profile_id", defaults.profile["id"] if defaults.profile else None),
            "profile_id",
        )
        model_config_id = self.parse_optional_int(
            data.get("model_config_id", defaults.model["id"] if defaults.model else None),
            "model_config_id",
        )
        configured_model = self.db.models.get(model_config_id) if model_config_id else defaults.model
        return ConversationSelection(
            project_id=project_id,
            project_model_id=project_model_id,
            quick_project_model_ids=quick_ids,
            profile_id=profile_id,
            model_config_id=model_config_id,
            provider=data.get(
                "provider",
                configured_model["provider"] if configured_model else defaults.default_provider,
            ),
            model=data.get("model", configured_model["name"] if configured_model else ""),
        )

    def _build_update_selection(self, data, conversation):
        project_id = self.parse_optional_int(
            data.get("project_id", conversation["project_id"]),
            "project_id",
        )
        raw_project_model_id = (
            data.get("project_model_id")
            if "project_model_id" in data
            else conversation.get("project_model_id")
        )
        project_model_id = self.parse_optional_int(raw_project_model_id, "project_model_id")
        quick_ids = self.parse_quick_project_model_ids(
            data.get("quick_project_model_ids", conversation.get("quick_project_model_ids", [])),
        )
        project_model = self._resolve_project_model(project_model_id, project_id)
        effective_project_id = project_model["project_id"] if project_model else project_id
        self._validate_quick_project_model_ids(quick_ids, effective_project_id)

        if project_model:
            return self._selection_from_project_model(project_model, project_model_id, quick_ids)

        profile_id = self.parse_optional_int(
            data.get("profile_id", conversation["profile_id"]),
            "profile_id",
        )
        model_config_id = self.parse_optional_int(
            data.get("model_config_id", conversation.get("model_config_id")),
            "model_config_id",
        )
        configured_model = self.db.models.get(model_config_id) if model_config_id else None
        return ConversationSelection(
            project_id=project_id,
            project_model_id=project_model_id,
            quick_project_model_ids=quick_ids,
            profile_id=profile_id,
            model_config_id=model_config_id,
            provider=data.get(
                "provider",
                configured_model["provider"] if configured_model else conversation["provider"],
            ),
            model=data.get(
                "model",
                configured_model["name"] if configured_model else conversation["model"],
            ),
        )

    def _selection_from_project_model(self, project_model, project_model_id, quick_ids):
        configured_model = self.db.models.get(project_model["model_id"])
        return ConversationSelection(
            project_id=project_model["project_id"],
            project_model_id=project_model_id,
            quick_project_model_ids=quick_ids,
            profile_id=project_model["profile_id"],
            model_config_id=project_model["model_id"],
            provider=configured_model["provider"] if configured_model else "",
            model=configured_model["name"] if configured_model else "",
        )

    def _resolve_project_model(self, project_model_id, project_id):
        if not project_model_id:
            return None

        project_model = self.db.project_models.get(project_model_id)
        if not project_model:
            raise ConversationRequestError("Project agent not found")

        if project_id and project_model["project_id"] != project_id:
            raise ConversationRequestError("Project agent does not belong to this project")

        return project_model

    def parse_quick_project_model_ids(self, raw_value):
        if raw_value in (None, ""):
            return []
        if not isinstance(raw_value, list):
            raise ConversationRequestError("quick_project_model_ids must be a list")

        parsed_ids = []
        for raw_id in raw_value:
            project_model_id = self.parse_optional_int(raw_id, "quick_project_model_ids")
            if project_model_id and project_model_id not in parsed_ids:
                parsed_ids.append(project_model_id)
        return parsed_ids

    def _validate_quick_project_model_ids(self, project_model_ids, project_id):
        if not project_model_ids:
            return
        if not project_id:
            raise ConversationRequestError("Quick agents require a project chat")

        for project_model_id in project_model_ids:
            self._resolve_project_model(project_model_id, project_id)

    def parse_optional_int(self, value, field_name):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ConversationRequestError(f"Invalid {field_name}")

    def _parse_required_id(self, value, field_name):
        parsed_id = self.parse_optional_int(value, field_name)
        if parsed_id is None:
            raise ConversationRequestError(f"Missing {field_name}")
        return parsed_id

    def _get_defaults(self):
        return ConversationDefaults(
            profile=self.db.profiles.get_default(),
            model=self.db.models.get_default(),
            default_provider=self.config_manager.providers.default_provider,
        )
