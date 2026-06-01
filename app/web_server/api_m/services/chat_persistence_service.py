class ChatPersistenceService:
    PLACEHOLDER_TITLES = {
        "new chat",
        "new conversation",
        "nueva conversación",
        "nueva conversacion",
    }

    def __init__(self, db_manager, model_manager):
        self.db = db_manager
        self.model_manager = model_manager

    def prepare_conversation(self, conversation, provider, model, request_messages):
        conversation_id = conversation["id"]
        with self.db.transaction():
            self.persist_request_messages(conversation_id, request_messages)
            self.db.conversations.touch(conversation_id)

    def finalize_response(self, conversation_id, response, assistant_message_meta=None):
        assistant_content = ((response.get("message") or {}).get("content") or "").strip()
        if not assistant_content:
            return

        with self.db.transaction():
            conversation = self.db.conversations.get(conversation_id)
            stored_messages = self.db.messages.for_conversation(conversation_id)
            self._apply_assistant_message_meta(response, assistant_message_meta)
            self.persist_assistant_message(conversation_id, response)
            self.db.conversations.touch(conversation_id)

        self._ensure_generated_conversation_title(
            conversation,
            stored_messages,
            response,
        )

    def persist_request_messages(self, conversation_id, request_messages):
        stored_messages = self.db.messages.for_conversation(conversation_id)
        stored_count = len(stored_messages)
        new_messages = request_messages[stored_count:]

        self.db.messages.append_many(conversation_id, new_messages)

    def persist_assistant_message(self, conversation_id, response):
        assistant_message = response.get("message", {})
        normalized_tool_events = self._normalize_tool_events(
            (response.get("raw") or {}).get("tool_events", [])
        )
        if response.get("raw") is not None:
            response["raw"]["tool_events"] = normalized_tool_events
        self.db.messages.create(
            conversation_id=conversation_id,
            role=assistant_message.get("role", "assistant"),
            content=assistant_message.get("content", ""),
            project_model_id=assistant_message.get("project_model_id"),
            project_model_name=assistant_message.get("project_model_name", ""),
            model_config_id=assistant_message.get("model_config_id"),
            model_name=assistant_message.get("model_name", ""),
            profile_id=assistant_message.get("profile_id"),
            profile_name=assistant_message.get("profile_name", ""),
            tool_events=normalized_tool_events,
            provider_message_id=response.get("message_id"),
        )

    def _apply_assistant_message_meta(self, response, assistant_message_meta=None):
        if not assistant_message_meta:
            return

        assistant_message = response.setdefault("message", {})
        assistant_message["project_model_id"] = assistant_message_meta.get("project_model_id")
        assistant_message["project_model_name"] = assistant_message_meta.get("project_model_name", "")
        assistant_message["model_config_id"] = assistant_message_meta.get("model_config_id")
        assistant_message["model_name"] = assistant_message_meta.get("model_name", "")
        assistant_message["profile_id"] = assistant_message_meta.get("profile_id")
        assistant_message["profile_name"] = assistant_message_meta.get("profile_name", "")

    def _ensure_generated_conversation_title(self, conversation, stored_messages, response):
        if not conversation:
            return

        if not self._should_replace_conversation_title(conversation):
            return

        if any(message.get("role") == "assistant" for message in stored_messages):
            return

        first_user_message = self._get_first_user_message_content(stored_messages)
        if not first_user_message:
            return

        assistant_content = ((response.get("message") or {}).get("content") or "").strip()
        if not assistant_content:
            return

        provider = response.get("provider") or conversation.get("provider")
        model = response.get("model") or conversation.get("model")
        generated_title = self._generate_title(
            provider,
            model,
            first_user_message,
            assistant_content,
        )
        title = generated_title or self._build_provisional_title(first_user_message)
        if not title:
            return

        latest_conversation = self.db.conversations.get(conversation["id"])
        if not self._should_replace_conversation_title(latest_conversation):
            return

        self.db.conversations.rename(conversation["id"], title)

    def _generate_title(self, provider, model, first_user_message, assistant_content):
        if not provider or not model:
            return ""

        try:
            return self.model_manager.generate_conversation_title(
                provider,
                model,
                [
                    {
                        "role": "user",
                        "content": first_user_message,
                    },
                    {
                        "role": "assistant",
                        "content": assistant_content,
                    },
                ],
            )
        except Exception:
            return ""

    def _get_first_user_message_content(self, messages):
        for message in messages:
            if message.get("role") != "user":
                continue

            content = message.get("content")
            if isinstance(content, str):
                normalized = " ".join(content.split())
                if normalized:
                    return normalized
                continue

            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str) and item.strip():
                        parts.append(item.strip())
                        continue

                    if isinstance(item, dict):
                        text = str(item.get("text", "")).strip()
                        if text:
                            parts.append(text)

                normalized = " ".join(parts)
                if normalized:
                    return normalized

        return ""

    def _should_replace_conversation_title(self, conversation):
        current_title = str((conversation or {}).get("title") or "").strip().lower()
        if current_title in self.PLACEHOLDER_TITLES:
            return True

        project_id = (conversation or {}).get("project_id")
        if not project_id:
            return False

        project = self.db.projects.get(project_id)
        project_chat_title = f"{(project or {}).get('name', '')} · chat".strip().lower()
        return bool(project_chat_title and current_title == project_chat_title)

    def _build_provisional_title(self, first_user_message):
        normalized = " ".join(str(first_user_message or "").split()).strip(" -–—:;,.!?")
        if not normalized:
            return ""

        first_line = normalized.split("\n", 1)[0].strip()
        if not first_line:
            return ""

        words = first_line.split()
        if len(words) > 6:
            first_line = " ".join(words[:6])

        if len(first_line) > 60:
            first_line = first_line[:60].rstrip()

        if first_line and first_line[0].islower():
            first_line = first_line[0].upper() + first_line[1:]

        return first_line.strip(" -–—:;,.!?")

    def _normalize_tool_events(self, tool_events):
        normalized_events = []

        for tool_event in tool_events if isinstance(tool_events, list) else []:
            if not isinstance(tool_event, dict):
                continue

            normalized_event = dict(tool_event)
            normalized_event["tool_summary"] = self._build_tool_summary(normalized_event)
            normalized_event["source_urls"] = self._extract_source_urls(normalized_event)
            normalized_event["source_titles"] = self._extract_source_titles(normalized_event)
            normalized_events.append(normalized_event)

        return normalized_events

    def _build_tool_summary(self, tool_event):
        tool_name = str(tool_event.get("tool_name") or "tool").strip()
        arguments = tool_event.get("arguments") or {}

        if not tool_event.get("ok"):
            error = str(tool_event.get("error") or "The tool could not complete.").strip()
            return f"{tool_name} failed: {error}"

        result = tool_event.get("result") or {}
        if tool_name == "web_search":
            query = str(arguments.get("query") or result.get("query") or "").strip()
            results = result.get("results") or []
            count = len(results) if isinstance(results, list) else 0
            if query:
                return f'{tool_name} searched for "{query}" and returned {count} result(s).'
            return f"{tool_name} returned {count} result(s)."

        if tool_name == "current_date":
            date = str(result.get("date") or "").strip()
            time = str(result.get("time") or "").strip()
            timezone = str(result.get("timezone") or "").strip()
            details = [value for value in [date, time, timezone] if value]
            if details:
                return f"{tool_name} returned {', '.join(details)}."
            return f"{tool_name} returned current date information."

        if tool_name == "workspace_write_file":
            file_payload = result.get("file") if isinstance(result, dict) else {}
            path = str((file_payload or {}).get("path") or arguments.get("path") or "").strip()
            action = "created" if (file_payload or {}).get("created") else "updated"
            if path:
                return f"{tool_name} {action} {path}."
            return f"{tool_name} wrote a file in the connected workspace."

        if tool_name == "workspace_append_file":
            file_payload = result.get("file") if isinstance(result, dict) else {}
            path = str((file_payload or {}).get("path") or arguments.get("path") or "").strip()
            if path:
                return f"{tool_name} appended to {path}."
            return f"{tool_name} appended text in the connected workspace."

        if tool_name == "workspace_read_file":
            file_payload = result.get("file") if isinstance(result, dict) else {}
            path = str((file_payload or {}).get("path") or arguments.get("path") or "").strip()
            if path:
                return f"{tool_name} read {path}."
            return f"{tool_name} read a file from the connected workspace."

        if tool_name == "workspace_search":
            matches = result.get("matches") if isinstance(result, dict) else []
            match_count = len(matches) if isinstance(matches, list) else 0
            query = str(arguments.get("query") or "").strip()
            if query:
                return f'{tool_name} searched for "{query}" and returned {match_count} match(es).'
            return f"{tool_name} returned {match_count} match(es)."

        compact_fields = []
        for key, value in result.items() if isinstance(result, dict) else []:
            if isinstance(value, (str, int, float, bool)) and str(value).strip():
                compact_fields.append(f"{key}: {value}")

        if compact_fields:
            return f"{tool_name} returned {'; '.join(compact_fields[:3])}."

        return f"{tool_name} completed successfully."

    def _extract_source_urls(self, tool_event):
        results = ((tool_event.get("result") or {}).get("results") or [])
        source_urls = []

        for item in results:
            if not isinstance(item, dict):
                continue

            url = str(item.get("url") or "").strip()
            if url and url not in source_urls:
                source_urls.append(url)

        return source_urls

    def _extract_source_titles(self, tool_event):
        results = ((tool_event.get("result") or {}).get("results") or [])
        source_titles = []

        for item in results:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip()
            if title and title not in source_titles:
                source_titles.append(title)

        return source_titles
