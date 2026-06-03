from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    ChatContextBuilder,
    ChatExecutor,
    ChatPersistenceService,
    ChatRequestPreparer,
    ChatRequestError,
    ChatResourceNotFoundError,
    ChatService,
    ChatStreamService,
)
from model_m import ProviderError


class ChatAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.chat_stream_service = self.services.chat_stream_service
            self.chat_service = self.services.chat_service
        else:
            context_builder = ChatContextBuilder(self.db)
            persistence_service = ChatPersistenceService(self.db, self.model_manager)
            executor = ChatExecutor(self.model_manager)
            self.chat_stream_service = ChatStreamService(
                self.db,
                self.model_manager,
                persistence_service,
                executor=executor,
            )
            request_preparer = ChatRequestPreparer(
                self.db,
                context_builder,
                request_id_resolver=self.chat_stream_service.resolve_request_id,
            )
            self.chat_service = ChatService(
                self.db,
                self.model_manager,
                context_builder,
                persistence_service,
                self.chat_stream_service,
                request_preparer=request_preparer,
                executor=executor,
            )
        self.__class__._active_streams = self.chat_stream_service._active_streams
        self.__class__._active_streams_lock = self.chat_stream_service._active_streams_lock

    def register(self):
        self.app.add_url_rule("/api/chat", view_func=self.chat, methods=["POST"])
        self.app.add_url_rule("/api/chat/cancel", view_func=self.cancel_chat, methods=["POST"])
        self.app.add_url_rule(
            "/api/chat/tool-confirmations",
            view_func=self.update_tool_confirmation,
            methods=["PATCH"],
        )

    def chat(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            response = self.chat_service.handle_request(
                data,
                default_profile=self.get_default_profile(),
                default_provider=self.config_manager.providers.default_provider,
            )
        except ProviderError as error:
            return self.provider_error(error)
        except (ChatResourceNotFoundError, ChatRequestError) as error:
            return self.error_from_exception(error)

        if hasattr(response, "mimetype"):
            return response

        return self.ok(response)

    def cancel_chat(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        request_id = str(data.get("request_id") or "").strip()
        if not request_id:
            return self.error("Missing request_id", 400)

        was_cancelled = self.chat_stream_service.cancel(request_id)
        return self.ok(
            {
                "request_id": request_id,
                "cancelled": was_cancelled,
            }
        )

    def update_tool_confirmation(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            message_id = self.parse_int(data.get("message_id"), "message_id")
            tool_event_index = self.parse_int(data.get("tool_event_index"), "tool_event_index")
            if message_id is None:
                raise ValueError("Missing message_id")
            if tool_event_index is None:
                raise ValueError("Missing tool_event_index")
            status = self._parse_tool_confirmation_status(data.get("status"))
            message = self.chat_service.persistence_service.update_tool_confirmation_status(
                message_id,
                tool_event_index,
                status,
            )
        except ValueError as error:
            if str(error) == "Message not found":
                return self.error(str(error), 404)
            return self.error_from_exception(error)

        return self.ok({"message": message})

    def _parse_tool_confirmation_status(self, raw_status):
        status = str(raw_status or "").strip()
        if status not in {"confirmation_required", "confirming", "confirmed", "cancelled"}:
            raise ValueError("Invalid status")
        return status
