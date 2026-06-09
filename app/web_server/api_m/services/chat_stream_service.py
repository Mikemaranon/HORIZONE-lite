import logging
import re
import threading
import time
import uuid

from model_m import ProviderError
from .chat_executor import ChatExecutor
from .reasoning_content_filter import ReasoningStreamFilter, sanitize_chat_response
from .chat_sse_presenter import ChatSSEPresenter


LOGGER = logging.getLogger(__name__)


class ChatStreamService:
    DISPLAY_DELTA_SPLIT_THRESHOLD = 48
    DISPLAY_DELTA_TARGET_CHARS = 24
    DISPLAY_DELTA_DELAY_SECONDS = 0.018
    INTERNAL_ERROR_PAYLOAD = {
        "code": "streaming_internal_error",
        "message": "Streaming failed unexpectedly.",
    }

    def __init__(
        self,
        db_manager,
        model_manager,
        persistence_service,
        tool_manager=None,
        executor=None,
        presenter=None,
        display_delta_delay_seconds=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.persistence_service = persistence_service
        self.tool_manager = tool_manager
        self.executor = executor or ChatExecutor(model_manager, tool_manager=tool_manager)
        self.presenter = presenter or ChatSSEPresenter()
        self.display_delta_delay_seconds = (
            self.DISPLAY_DELTA_DELAY_SECONDS
            if display_delta_delay_seconds is None
            else display_delta_delay_seconds
        )
        self._active_streams = {}
        self._active_streams_lock = threading.Lock()

    def resolve_request_id(self, raw_request_id):
        normalized = str(raw_request_id or "").strip()
        if normalized:
            return normalized

        return str(uuid.uuid4())

    def cancel(self, request_id):
        with self._active_streams_lock:
            cancel_event = self._active_streams.get(request_id)

        if not cancel_event:
            return False

        cancel_event.set()
        return True

    def build_stream_response(
        self,
        conversation_id,
        provider,
        input_messages,
        model,
        generation_settings,
        request_id,
        assistant_message_meta,
        tool_context=None,
    ):
        return self.presenter.response_from_events(
            self.iter_stream_events(
                conversation_id,
                provider,
                input_messages,
                model,
                generation_settings,
                request_id,
                assistant_message_meta,
                tool_context=tool_context,
            )
        )

    def iter_stream_events(
        self,
        conversation_id,
        provider,
        input_messages,
        model,
        generation_settings,
        request_id,
        assistant_message_meta,
        tool_context=None,
    ):
        cancel_event = self._register_stream(request_id)

        try:
            yield self._event(
                "start",
                {
                    "conversation_id": conversation_id,
                    "provider": provider,
                    "model": model,
                    "request_id": request_id,
                    "message_meta": assistant_message_meta,
                },
            )

            final_response = None
            streamed_text_parts = []
            reasoning_filter = ReasoningStreamFilter(
                hide_unopened_reasoning_prefix=self._may_emit_unopened_reasoning_prefix(model)
            )

            event_stream = self.executor.stream_chat(
                provider,
                input_messages,
                model,
                generation_settings,
                should_stop=cancel_event.is_set,
                tool_context=tool_context,
            )

            for event in event_stream:
                event_type = event.get("type")

                if event_type == "delta":
                    delta = event.get("delta") or ""
                    if delta:
                        visible_delta = reasoning_filter.feed(delta)
                        for reasoning_event in reasoning_filter.pop_events():
                            yield self._event(f"reasoning_{reasoning_event['type']}", {})
                        if visible_delta:
                            for display_delta in self._iter_display_deltas(visible_delta):
                                streamed_text_parts.append(display_delta)
                                yield self._event("delta", {"delta": display_delta})
                    continue

                if event_type == "tool_start":
                    yield self._event(
                        "tool_start",
                        {
                            "tool_name": event.get("tool_name", ""),
                            "display_name": event.get("display_name", ""),
                            "arguments": event.get("arguments") or {},
                        },
                    )
                    continue

                if event_type == "tool_result":
                    yield self._event(
                        "tool_result",
                        {
                            "tool_name": event.get("tool_name", ""),
                            "display_name": event.get("display_name", ""),
                            "ok": bool(event.get("ok")),
                        },
                    )
                    continue

                if event_type == "response":
                    final_response = event.get("response")

            remaining_delta = reasoning_filter.flush()
            for reasoning_event in reasoning_filter.pop_events():
                yield self._event(f"reasoning_{reasoning_event['type']}", {})
            if remaining_delta:
                for display_delta in self._iter_display_deltas(remaining_delta):
                    streamed_text_parts.append(display_delta)
                    yield self._event("delta", {"delta": display_delta})

            was_cancelled = cancel_event.is_set()
            final_response = self._resolve_final_response(
                final_response,
                streamed_text_parts,
                provider,
                model,
                was_cancelled,
                reasoning_filter.reasoning_content,
            )

            if conversation_id:
                self.persistence_service.finalize_response(
                    conversation_id,
                    final_response,
                    assistant_message_meta,
                )

            payload = {
                "response": final_response,
                "cancelled": was_cancelled,
                "request_id": request_id,
                "message_meta": assistant_message_meta,
            }
            if conversation_id:
                payload["conversation"] = self.db.conversations.get(conversation_id)

            yield self._event("end", payload)
        except GeneratorExit:
            cancel_event.set()
            raise
        except ProviderError as error:
            payload = error.to_dict()
            payload["request_id"] = request_id
            yield self._event("error", {"error": payload, "request_id": request_id})
        except Exception:
            LOGGER.exception("Unexpected chat stream error", extra={"request_id": request_id})
            error_payload = dict(self.INTERNAL_ERROR_PAYLOAD)
            error_payload["request_id"] = request_id
            yield self._event(
                "error",
                {"error": error_payload, "request_id": request_id},
            )
        finally:
            self._release_stream(request_id)

    def build_static_stream_response(
        self,
        conversation_id,
        provider,
        model,
        request_id,
        assistant_message_meta,
        response,
    ):
        return self.presenter.response_from_events(
            self.iter_static_stream_events(
                conversation_id,
                provider,
                model,
                request_id,
                assistant_message_meta,
                response,
            )
        )

    def iter_static_stream_events(
        self,
        conversation_id,
        provider,
        model,
        request_id,
        assistant_message_meta,
        response,
    ):
        yield self._event(
            "start",
            {
                "conversation_id": conversation_id,
                "provider": provider,
                "model": model,
                "request_id": request_id,
                "message_meta": assistant_message_meta,
            },
        )

        response = sanitize_chat_response(response)
        reasoning_content = ((response.get("message") or {}).get("reasoning_content") or "")
        if reasoning_content:
            yield self._event("reasoning_start", {})
            yield self._event("reasoning_end", {})
        content = ((response.get("message") or {}).get("content") or "")
        if content:
            for display_delta in self._iter_display_deltas(content):
                yield self._event("delta", {"delta": display_delta})

        if conversation_id:
            self.persistence_service.finalize_response(
                conversation_id,
                response,
                assistant_message_meta,
            )

        payload = {
            "response": response,
            "cancelled": False,
            "request_id": request_id,
            "message_meta": assistant_message_meta,
        }
        if conversation_id:
            payload["conversation"] = self.db.conversations.get(conversation_id)

        yield self._event("end", payload)

    def _resolve_final_response(
        self,
        final_response,
        streamed_text_parts,
        provider,
        model,
        was_cancelled,
        reasoning_content="",
    ):
        if not final_response:
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "".join(streamed_text_parts),
                    "reasoning_content": reasoning_content or "",
                },
                "usage": {},
                "finish_reason": "cancelled" if was_cancelled else None,
                "message_id": None,
                "raw": {
                    "streamed": True,
                    "reconstructed": True,
                    "cancelled": was_cancelled,
                },
            }

        final_response = sanitize_chat_response(final_response)
        if reasoning_content:
            message = final_response.setdefault("message", {})
            message.setdefault("reasoning_content", reasoning_content)
        if was_cancelled:
            final_response["finish_reason"] = "cancelled"
            raw_response = final_response.get("raw") or {}
            raw_response["cancelled"] = True
            final_response["raw"] = raw_response

        return final_response

    def _event(self, event_name, payload):
        return {"event": event_name, "data": payload}

    def _register_stream(self, request_id):
        cancel_event = threading.Event()
        with self._active_streams_lock:
            self._active_streams[request_id] = cancel_event
        return cancel_event

    def _release_stream(self, request_id):
        with self._active_streams_lock:
            self._active_streams.pop(request_id, None)

    def _iter_display_deltas(self, delta):
        if len(delta) <= self.DISPLAY_DELTA_SPLIT_THRESHOLD:
            yield delta
            return

        chunks = list(self._split_delta_for_display(delta))
        for index, chunk in enumerate(chunks):
            if not chunk:
                continue

            yield chunk
            if index < len(chunks) - 1:
                self._pause_between_display_deltas()

    def _split_delta_for_display(self, delta):
        current = ""
        for token in re.findall(r"\S+\s*|\s+", delta):
            if len(token) > self.DISPLAY_DELTA_TARGET_CHARS * 2:
                if current:
                    yield current
                    current = ""
                yield from self._split_long_token(token)
                continue

            if current and len(current) + len(token) > self.DISPLAY_DELTA_TARGET_CHARS:
                yield current
                current = token
            else:
                current += token

        if current:
            yield current

    def _split_long_token(self, token):
        size = self.DISPLAY_DELTA_TARGET_CHARS
        for index in range(0, len(token), size):
            yield token[index:index + size]

    def _pause_between_display_deltas(self):
        if self.display_delta_delay_seconds > 0:
            time.sleep(self.display_delta_delay_seconds)

    def _may_emit_unopened_reasoning_prefix(self, model):
        normalized_model = str(model or "").lower()
        return any(
            marker in normalized_model
            for marker in ("reasoning", "qwen", "qwq", "kimi")
        )
