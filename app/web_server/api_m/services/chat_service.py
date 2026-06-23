import time

from model_m import ProviderError
from .chat_executor import ChatExecutor
from .chat_request_preparer import ChatRequestError, ChatRequestPreparer
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
        response_started_at = time.perf_counter()
        prepared = self.request_preparer.prepare(
            data,
            default_profile=default_profile,
            default_provider=default_provider,
        )
        tool_context = self._build_tool_context(prepared)
        source_follow_up_response = None
        if not getattr(prepared, "tool_directives", []):
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
            return self._build_source_follow_up_payload(
                prepared,
                source_follow_up_response,
                response_started_at,
            )

        if prepared.stream_requested:
            return self.stream_service.build_stream_response(
                prepared.conversation_id,
                prepared.provider,
                prepared.input_messages,
                prepared.model,
                prepared.generation_settings,
                prepared.request_id,
                prepared.assistant_message_meta,
                tool_context,
            )

        response = self._run_chat(prepared, tool_context=tool_context)
        payload = {"response": response}
        if prepared.conversation_id:
            payload["conversation"] = self.db.conversations.get(prepared.conversation_id)
        return payload

    def _build_source_follow_up_payload(
        self,
        prepared,
        source_follow_up_response,
        response_started_at,
    ):
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
            self.persistence_service.persist_elapsed_seconds(
                source_follow_up_response,
                time.perf_counter() - response_started_at,
            )
        payload = {"response": source_follow_up_response}
        if prepared.conversation_id:
            payload["conversation"] = self.db.conversations.get(prepared.conversation_id)
        return payload

    def _run_chat(self, prepared, *, tool_context=None):
        response_started_at = time.perf_counter()
        try:
            response = self.executor.chat(
                prepared.provider,
                prepared.input_messages,
                prepared.model,
                prepared.generation_settings,
                tool_context=tool_context or self._build_tool_context(prepared),
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
            self.persistence_service.persist_elapsed_seconds(
                response,
                time.perf_counter() - response_started_at,
            )

        return response

    def _build_tool_context(self, prepared):
        workspace = None
        if prepared.project:
            workspace = self.db.project_workspaces.get_by_project(prepared.project["id"])

        tool_context = {
            "conversation_id": prepared.conversation_id,
            "project": prepared.project,
            "workspace": workspace,
            "confirmed_tool_call": prepared.tool_confirmation,
            "confirmed_tool_calls": [prepared.tool_confirmation] if prepared.tool_confirmation else [],
        }
        forced_resume = self._resolve_forced_tool_resume(prepared, tool_context)
        if forced_resume:
            tool_context["forced_tool_resume"] = forced_resume
        tool_directives = getattr(prepared, "tool_directives", [])
        if tool_directives:
            if not self.tool_manager:
                raise ChatRequestError("Tool commands are unavailable")
            try:
                tool_context["forced_tool_directives"] = self.tool_manager.validate_tool_directives(
                    tool_directives,
                    tool_context=tool_context,
                )
            except ValueError as error:
                raise ChatRequestError(str(error)) from error
        return tool_context

    def _resolve_forced_tool_resume(self, prepared, tool_context):
        confirmation = prepared.tool_confirmation or {}
        source_message_id = confirmation.get("source_message_id")
        source_event_index = confirmation.get("source_event_index")
        if source_message_id is None:
            return None

        source_message = self.db.messages.get(source_message_id)
        if not source_message:
            raise ChatRequestError("Tool confirmation source message was not found")
        if source_message.get("conversation_id") != prepared.conversation_id:
            raise ChatRequestError("Tool confirmation does not belong to this conversation")

        tool_events = source_message.get("tool_events") or []
        if source_event_index < 0 or source_event_index >= len(tool_events):
            raise ChatRequestError("Tool confirmation source event was not found")
        source_event = tool_events[source_event_index]
        if (
            source_event.get("tool_name") != confirmation.get("name")
            or (source_event.get("arguments") or {}) != confirmation.get("arguments")
        ):
            raise ChatRequestError("Tool confirmation does not match the stored request")
        source_status = str((source_event.get("policy") or {}).get("status") or "").strip()
        if source_status not in {"confirmation_required", "confirming"}:
            raise ChatRequestError("Tool confirmation is no longer pending")

        forced_chain = source_event.get("forced_chain")
        if not isinstance(forced_chain, dict):
            return None
        directives = forced_chain.get("directives")
        current_index = forced_chain.get("current_index")
        if (
            not isinstance(directives, list)
            or not isinstance(current_index, int)
            or current_index < 0
            or current_index >= len(directives)
            or directives[current_index].get("tool_name") != confirmation.get("name")
        ):
            raise ChatRequestError("Stored forced tool chain is invalid")
        try:
            directives = self.tool_manager.validate_tool_directives(
                directives,
                tool_context=tool_context,
            )
        except ValueError as error:
            raise ChatRequestError(str(error)) from error
        return {
            "directives": directives,
            "current_index": current_index,
            "completed_events": list(forced_chain.get("completed_events") or []),
        }
