from model_m import ProviderError
from .chat_executor import ChatExecutor
from .chat_request_preparer import ChatRequestPreparer
from .reasoning_content_filter import sanitize_chat_response
from .source_attribution_service import SourceAttributionService


class ChatService:
    ALLOWED_MESSAGE_ROLES = ChatRequestPreparer.ALLOWED_MESSAGE_ROLES
    MAX_MESSAGES_PER_REQUEST = ChatRequestPreparer.MAX_MESSAGES_PER_REQUEST
    MAX_MESSAGE_CONTENT_CHARS = ChatRequestPreparer.MAX_MESSAGE_CONTENT_CHARS

    def __init__(
        self,
        db_manager,
        model_manager,
        context_builder,
        persistence_service,
        stream_service,
        tool_manager=None,
        source_attribution_service=None,
        request_preparer=None,
        executor=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.context_builder = context_builder
        self.persistence_service = persistence_service
        self.stream_service = stream_service
        self.tool_manager = tool_manager
        self.executor = executor or ChatExecutor(model_manager, tool_manager=tool_manager)
        self.source_attribution_service = source_attribution_service or SourceAttributionService(db_manager)
        self.request_preparer = request_preparer or ChatRequestPreparer(
            db_manager,
            context_builder,
            request_id_resolver=stream_service.resolve_request_id,
        )

    def handle_request(self, data, default_profile, default_provider, parse_int=None):
        prepared = self.request_preparer.prepare(
            data,
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
            return self._build_source_follow_up_payload(prepared, source_follow_up_response)

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

    def _build_source_follow_up_payload(self, prepared, source_follow_up_response):
        source_follow_up_response = sanitize_chat_response(source_follow_up_response)
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

    def _run_chat(self, prepared):
        try:
            response = self.executor.chat(
                prepared.provider,
                prepared.input_messages,
                prepared.model,
                prepared.generation_settings,
                tool_context=self._build_tool_context(prepared),
            )
        except ProviderError:
            raise

        response = sanitize_chat_response(response)
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
            "confirmed_tool_call": prepared.tool_confirmation,
            "confirmed_tool_calls": [prepared.tool_confirmation] if prepared.tool_confirmation else [],
        }
