from urllib.parse import urlparse


class SourceAttributionService:
    def __init__(self, db_manager):
        self.db = db_manager

    def build_follow_up_response(self, *, conversation_id, request_messages, provider, model):
        latest_user_message = self._get_latest_user_message_content(request_messages)
        if not self._is_source_follow_up(latest_user_message):
            return None

        if not conversation_id:
            return self._build_no_sources_response(
                provider,
                model,
                message=(
                    "I have not consulted external sources in this thread yet. "
                    "If you want, I can search now and cite specific results."
                ),
            )

        previous_assistant_message = self._get_previous_assistant_message(conversation_id)
        if not previous_assistant_message:
            return self._build_no_sources_response(
                provider,
                model,
                message=(
                    "There is no previous assistant response in this thread to attribute sources to. "
                    "If you want, I can perform the search now."
                ),
            )

        tool_events = previous_assistant_message.get("tool_events") or []
        if not tool_events:
            return self._build_no_sources_response(
                provider,
                model,
                message=(
                    "I did not consult external sources in the previous response. "
                    "That response was not backed by any tool or web search in this thread. "
                    "If you want, I can search now and give you real sources."
                ),
            )

        return self._build_sources_response(provider, model, tool_events)

    def _get_latest_user_message_content(self, messages):
        for message in reversed(messages or []):
            if message.get("role") != "user":
                continue
            return str(message.get("content") or "").strip()
        return ""

    def _is_source_follow_up(self, content):
        normalized = str(content or "").strip().lower()
        if not normalized:
            return False

        triggers = [
            "fuentes consultadas",
            "que fuentes has consultado",
            "qué fuentes has consultado",
            "dame las fuentes",
            "dime las fuentes",
            "sources consulted",
            "which sources did you use",
            "what sources did you use",
            "give me the sources",
            "tell me the sources",
            "show me the sources",
        ]
        return any(trigger in normalized for trigger in triggers)

    def _get_previous_assistant_message(self, conversation_id):
        messages = self.db.messages.for_conversation(conversation_id)
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message
        return None

    def _build_sources_response(self, provider, model, tool_events):
        source_lines = self._extract_tool_source_lines(tool_events)
        if source_lines:
            content = "The sources consulted in the previous response are:\n\n" + "\n".join(
                [f"- {line}" for line in source_lines]
            )
        else:
            tool_names = ", ".join(
                sorted(
                    {
                        str(tool_event.get("tool_name") or "").replace("_", " ")
                        for tool_event in tool_events
                        if tool_event.get("tool_name")
                    }
                )
            ) or "internal tools"
            content = (
                "The previous response did use tools, but there were no explicit URLs or web sources "
                f"left to cite. The tools used were: {tool_names}."
            )

        return {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "source_attribution": True,
                "tool_events": tool_events,
            },
        }

    def _build_no_sources_response(self, provider, model, message):
        return {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": message,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "source_attribution": True,
                "tool_events": [],
            },
        }

    def _extract_tool_source_lines(self, tool_events):
        seen = set()
        lines = []

        for tool_event in tool_events or []:
            result_payload = tool_event.get("result") or {}
            results = result_payload.get("results")
            if not isinstance(results, list):
                continue

            for item in results:
                if not isinstance(item, dict):
                    continue

                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not url:
                    continue

                parsed = urlparse(url)
                domain = parsed.netloc or url
                label = f"{title} - {domain}" if title else domain
                if url in seen:
                    continue
                seen.add(url)
                lines.append(label)

        return lines
