import json

from flask import Response, stream_with_context


class ChatSSEPresenter:
    STREAM_HEADERS = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    def response_from_events(self, events):
        @stream_with_context
        def generate():
            for event in events:
                yield self.format_event(
                    event.get("event", ""),
                    event.get("data") or {},
                )

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers=dict(self.STREAM_HEADERS),
        )

    def format_event(self, event_name, payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        return f"event: {event_name}\ndata: {serialized}\n\n"
