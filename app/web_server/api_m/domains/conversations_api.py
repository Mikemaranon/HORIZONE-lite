from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import ChatContextBuilder, ChatExportService


class ConversationsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.chat_export_service = self.services.chat_export_service
            return

        context_builder = ChatContextBuilder(self.db)
        self.chat_export_service = ChatExportService(self.db, context_builder)

    def register(self):
        self.app.add_url_rule(
            "/api/conversations/export",
            view_func=self.handle_conversations_export_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/conversations",
            view_func=self.handle_conversations_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/conversations",
            view_func=self.handle_conversations_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/conversations",
            view_func=self.handle_conversations_patch,
            methods=["PATCH"],
        )
        self.app.add_url_rule(
            "/api/conversations",
            view_func=self.handle_conversations_delete,
            methods=["DELETE"],
        )

    def handle_conversations_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        conversation_id = request.args.get("id")
        if conversation_id:
            try:
                parsed_id = self.parse_int(conversation_id, "id")
            except ValueError as error:
                return self.error(str(error), 400)

            conversation = self.db.conversations.get(parsed_id)
            if not conversation:
                return self.error("Conversation not found", 404)

            include_messages = request.args.get("include_messages", "0") in {"1", "true", "yes"}
            payload = {"conversation": conversation}
            if include_messages:
                payload["messages"] = self.db.messages.for_conversation(parsed_id)
            return self.ok(payload)

        project_id = request.args.get("project_id")
        try:
            parsed_project_id = self.parse_int(project_id, "project_id")
        except ValueError as error:
            return self.error(str(error), 400)

        conversations = self.db.conversations.all(parsed_project_id)
        return self.ok({"conversations": conversations})

    def handle_conversations_export_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            conversation_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": conversation_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            export_payload = self.chat_export_service.build_conversation_export(conversation_id)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok({"export": export_payload})

    def handle_conversations_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        default_profile = self.get_default_profile()
        default_model = self.db.models.get_default()

        try:
            project_id = self.parse_int(data.get("project_id"), "project_id")
            project_model_id = self.parse_int(data.get("project_model_id"), "project_model_id")
            quick_project_model_ids = self._parse_quick_project_model_ids(
                data.get("quick_project_model_ids", []),
            )
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            project_model = self._resolve_project_model(project_model_id, project_id)
            effective_project_id = project_model["project_id"] if project_model else project_id
            self._validate_quick_project_model_ids(quick_project_model_ids, effective_project_id)
        except ValueError as error:
            return self.error(str(error), 400)

        if project_model:
            project_id = project_model["project_id"]
            profile_id = project_model["profile_id"]
            model_config_id = project_model["model_id"]
        else:
            try:
                profile_id = self.parse_int(
                    data.get("profile_id", default_profile["id"] if default_profile else None),
                    "profile_id",
                )
                model_config_id = self.parse_int(
                    data.get("model_config_id", default_model["id"] if default_model else None),
                    "model_config_id",
                )
            except ValueError as error:
                return self.error(str(error), 400)

        configured_model = self.db.models.get(model_config_id) if model_config_id else default_model
        provider = configured_model["provider"] if project_model and configured_model else data.get(
            "provider",
            configured_model["provider"] if configured_model else self.config_manager.providers.default_provider,
        )
        model = configured_model["name"] if project_model and configured_model else data.get(
            "model",
            configured_model["name"] if configured_model else "",
        )
        title = data.get("title", "New Chat")

        conversation_id = self.db.conversations.create(
            title=title,
            project_id=project_id,
            project_model_id=project_model_id,
            quick_project_model_ids=quick_project_model_ids,
            profile_id=profile_id,
            model_config_id=model_config_id,
            provider=provider,
            model=model,
        )
        return self.ok({"conversation": self.db.conversations.get(conversation_id)}, 201)

    def handle_conversations_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        try:
            conversation_id = self.parse_int(data.get("id"), "id")
            self.require_fields({"id": conversation_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            return self.error("Conversation not found", 404)

        try:
            project_id = self.parse_int(data.get("project_id", conversation["project_id"]), "project_id")
            raw_project_model_id = (
                data.get("project_model_id")
                if "project_model_id" in data
                else conversation.get("project_model_id")
            )
            project_model_id = self.parse_int(raw_project_model_id, "project_model_id")
            quick_project_model_ids = self._parse_quick_project_model_ids(
                data.get(
                    "quick_project_model_ids",
                    conversation.get("quick_project_model_ids", []),
                ),
            )
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            project_model = self._resolve_project_model(project_model_id, project_id)
            effective_project_id = project_model["project_id"] if project_model else project_id
            self._validate_quick_project_model_ids(quick_project_model_ids, effective_project_id)
        except ValueError as error:
            return self.error(str(error), 400)

        if project_model:
            project_id = project_model["project_id"]
            profile_id = project_model["profile_id"]
            model_config_id = project_model["model_id"]
        else:
            try:
                profile_id = self.parse_int(data.get("profile_id", conversation["profile_id"]), "profile_id")
                model_config_id = self.parse_int(
                    data.get("model_config_id", conversation.get("model_config_id")),
                    "model_config_id",
                )
            except ValueError as error:
                return self.error(str(error), 400)

        configured_model = self.db.models.get(model_config_id) if model_config_id else None
        self.db.conversations.update(
            conversation_id=conversation_id,
            title=data.get("title", conversation["title"]),
            project_id=project_id,
            project_model_id=project_model_id,
            quick_project_model_ids=quick_project_model_ids,
            profile_id=profile_id,
            model_config_id=model_config_id,
            provider=configured_model["provider"] if project_model and configured_model else data.get(
                "provider",
                configured_model["provider"] if configured_model else conversation["provider"],
            ),
            model=configured_model["name"] if project_model and configured_model else data.get(
                "model",
                configured_model["name"] if configured_model else conversation["model"],
            ),
        )
        return self.ok({"conversation": self.db.conversations.get(conversation_id)})

    def _resolve_project_model(self, project_model_id, project_id):
        if not project_model_id:
            return None

        project_model = self.db.project_models.get(project_model_id)
        if not project_model:
            raise ValueError("Project agent not found")

        if project_id and project_model["project_id"] != project_id:
            raise ValueError("Project agent does not belong to this project")

        return project_model

    def _parse_quick_project_model_ids(self, raw_value):
        if raw_value in (None, ""):
            return []

        if not isinstance(raw_value, list):
            raise ValueError("quick_project_model_ids must be a list")

        parsed_ids = []
        for raw_id in raw_value:
            project_model_id = self.parse_int(raw_id, "quick_project_model_ids")
            if project_model_id and project_model_id not in parsed_ids:
                parsed_ids.append(project_model_id)

        return parsed_ids

    def _validate_quick_project_model_ids(self, project_model_ids, project_id):
        if not project_model_ids:
            return

        if not project_id:
            raise ValueError("Quick agents require a project chat")

        for project_model_id in project_model_ids:
            self._resolve_project_model(project_model_id, project_id)

    def handle_conversations_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            conversation_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": conversation_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            return self.error("Conversation not found", 404)

        self.db.conversations.delete(conversation_id)
        return self.ok({"deleted": True, "conversation_id": conversation_id})
