import json
import threading
import uuid

from flask import Response, stream_with_context

from model_m import ProviderError


class ChatStreamService:
    def __init__(self, db_manager, model_manager, persistence_service, tool_manager=None):
        self.db = db_manager
        self.model_manager = model_manager
        self.persistence_service = persistence_service
        self.tool_manager = tool_manager
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

                stream_source = self.tool_manager or self.model_manager
                for event in stream_source.stream_chat(
                    provider,
                    input_messages,
                    model,
                    generation_settings,
                    should_stop=cancel_event.is_set,
                ):
                    event_type = event.get("type")

                    if event_type == "delta":
                        delta = event.get("delta") or ""
                        if delta:
                            streamed_text_parts.append(delta)
                            yield self._format_sse("delta", {"delta": delta})
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
            except Exception as error:
                yield self._format_sse(
                    "error",
                    {
                        "error": {
                            "code": "streaming_internal_error",
                            "message": str(error) or "Streaming failed unexpectedly.",
                        }
                    },
                )
            finally:
                self._release_stream(request_id)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
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
                yield self._format_sse("delta", {"delta": content})

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
