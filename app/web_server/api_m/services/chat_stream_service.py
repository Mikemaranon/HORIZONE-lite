import json
import re
import threading
import time
import uuid

from flask import Response, stream_with_context

from model_m import ProviderError
from .chat_executor import ChatExecutor


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
        display_delta_delay_seconds=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.persistence_service = persistence_service
        self.tool_manager = tool_manager
        self.executor = executor or ChatExecutor(model_manager, tool_manager=tool_manager)
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
        cancel_event = self._register_stream(request_id)

        @stream_with_context
        def generate():
            try:
                yield self._format_sse(
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
                            for display_delta in self._iter_display_deltas(delta):
                                streamed_text_parts.append(display_delta)
                                yield self._format_sse("delta", {"delta": display_delta})
                        continue

                    if event_type == "tool_start":
                        yield self._format_sse(
                            "tool_start",
                            {
                                "tool_name": event.get("tool_name", ""),
                                "display_name": event.get("display_name", ""),
                                "arguments": event.get("arguments") or {},
                            },
                        )
                        continue

                    if event_type == "tool_result":
                        yield self._format_sse(
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

                was_cancelled = cancel_event.is_set()
                if not final_response:
                    final_response = {
                        "provider": provider,
                        "model": model,
                        "message": {
                            "role": "assistant",
                            "content": "".join(streamed_text_parts),
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
                elif was_cancelled:
                    final_response["finish_reason"] = "cancelled"
                    raw_response = final_response.get("raw") or {}
                    raw_response["cancelled"] = True
                    final_response["raw"] = raw_response

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

                yield self._format_sse("end", payload)
            except GeneratorExit:
                cancel_event.set()
                raise
            except ProviderError as error:
                yield self._format_sse("error", {"error": error.to_dict()})
            except Exception:
                yield self._format_sse(
                    "error",
                    {"error": dict(self.INTERNAL_ERROR_PAYLOAD)},
                )
            finally:
                self._release_stream(request_id)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def build_static_stream_response(
        self,
        conversation_id,
        provider,
        model,
        request_id,
        assistant_message_meta,
        response,
    ):
        @stream_with_context
        def generate():
            yield self._format_sse(
                "start",
                {
                    "conversation_id": conversation_id,
                    "provider": provider,
                    "model": model,
                    "request_id": request_id,
                    "message_meta": assistant_message_meta,
                },
            )

            content = ((response.get("message") or {}).get("content") or "")
            if content:
                for display_delta in self._iter_display_deltas(content):
                    yield self._format_sse("delta", {"delta": display_delta})

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

            yield self._format_sse("end", payload)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def _register_stream(self, request_id):
        cancel_event = threading.Event()
        with self._active_streams_lock:
            self._active_streams[request_id] = cancel_event
        return cancel_event

    def _release_stream(self, request_id):
        with self._active_streams_lock:
            self._active_streams.pop(request_id, None)

    def _format_sse(self, event_name, payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        return f"event: {event_name}\ndata: {serialized}\n\n"

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
