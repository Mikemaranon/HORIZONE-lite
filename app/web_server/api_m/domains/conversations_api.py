from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    ChatContextBuilder,
    ChatExportService,
    ConversationRequestError,
    ConversationResourceNotFoundError,
    ConversationService,
)


class ConversationsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.conversation_service = self.services.conversation_service
            return

        context_builder = ChatContextBuilder(self.db)
        export_service = ChatExportService(self.db, context_builder)
        self.conversation_service = ConversationService(
            self.db,
            self.config_manager,
            export_service=export_service,
        )

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

        try:
            if request.args.get("id"):
                payload = self.conversation_service.get_conversation(
                    request.args.get("id"),
                    include_messages=self._is_truthy(request.args.get("include_messages")),
                )
            else:
                payload = {
                    "conversations": self.conversation_service.list_conversations(
                        request.args.get("project_id"),
                    )
                }
        except ConversationRequestError as error:
            return self.error(str(error), 400)
        except ConversationResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_conversations_export_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            export_payload = self.conversation_service.export_conversation(request.args.get("id"))
        except ConversationRequestError as error:
            return self.error(str(error), 400)
        except ConversationResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok({"export": export_payload})

    def handle_conversations_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            conversation = self.conversation_service.create_conversation(
                self.get_request_json(request),
            )
        except ConversationRequestError as error:
            return self.error(str(error), 400)

        return self.ok({"conversation": conversation}, 201)

    def handle_conversations_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            conversation = self.conversation_service.update_conversation(
                self.get_request_json(request),
            )
        except ConversationRequestError as error:
            return self.error(str(error), 400)
        except ConversationResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok({"conversation": conversation})

    def handle_conversations_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.conversation_service.delete_conversation(request.args.get("id"))
        except ConversationRequestError as error:
            return self.error(str(error), 400)
        except ConversationResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def _is_truthy(self, value):
        return str(value or "").strip().lower() in {"1", "true", "yes"}
