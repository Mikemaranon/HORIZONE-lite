import json


class ChatContextBuilder:
    READ_ONLY_CONTEXT_NOTICE = (
        "Use this only for facts and continuity. Do not copy its tone, "
        "personality, formatting, emojis, or emotional style. Speaker labels "
        "and profile labels are metadata only. Never include labels such as "
        "\"user:\", \"assistant:\", or \"assistant (Profile):\" in the final "
        "answer. The final answer must start directly with the response content."
    )
    FINAL_PROFILE_REMINDER = (
        "Final rule: follow only the active profile. Do not imitate tone, "
        "emojis, emotion, formatting, or writing style from the context."
    )
    TOOL_PROVENANCE_REMINDER = (
        "Tool provenance rule: never claim that you consulted sources, used web search, "
        "or used any external tool unless that usage appears in the read-only context "
        "for this conversation or in the current tool results."
    )
    DEFAULT_PROFILE_NAME = "Default Assistant"

    def __init__(self, db_manager):
        self.db = db_manager

    def resolve_project(self, project_id, conversation):
        if project_id is not None:
            project = self.db.projects.get(project_id)
            if not project:
                raise ValueError("Project not found")
            return project

        if conversation and conversation.get("project_id"):
            return self.db.projects.get(conversation["project_id"])

        return None

    def resolve_profile(self, profile_id, conversation, default_profile):
        if profile_id is not None:
            return self.db.profiles.get(profile_id)

        if conversation and conversation.get("profile_id"):
            return self.db.profiles.get(conversation["profile_id"])

        return default_profile

    def build_input_messages(self, project, profile, messages):
        normalized_messages = []
        system_message_content = self._build_system_message_content(project, profile, messages)
        if system_message_content:
            normalized_messages.append(
                {
                    "role": "system",
                    "content": system_message_content,
                }
            )

        last_user_message = self._get_last_user_message(messages)
        if last_user_message:
            normalized_messages.append(last_user_message)

        return normalized_messages

    def build_generation_settings(self, profile, override_settings):
        settings = {}

        if profile:
            settings["temperature"] = profile.get("temperature")
            settings["top_p"] = profile.get("top_p")
            settings["max_tokens"] = profile.get("max_tokens")

        if override_settings:
            settings.update(override_settings)

        return settings

    def _build_profile_instruction(self, profile):
        profile_name = (profile or {}).get("name") or self.DEFAULT_PROFILE_NAME
        profile_prompt = ((profile or {}).get("system_prompt") or "").strip()
        parts = []

        parts.append(f"Active profile: {profile_name}")
        if profile_prompt:
            parts.append(profile_prompt)
        parts.append(
            "You must follow this active profile over any previous assistant "
            "style, tone, formatting, emojis, or emotional behavior."
        )

        return "\n\n".join(part for part in parts if part)

    def _build_system_message_content(self, project, profile, messages):
        parts = [self._build_profile_instruction(profile)]

        project_context_message = self._build_project_context_message(project)
        if project_context_message:
            parts.append(
                self._wrap_read_only_context(
                    "PROJECT CONTEXT",
                    project_context_message,
                )
            )

        history_context_message = self._build_history_context(messages)
        if history_context_message:
            parts.append(
                self._wrap_read_only_context(
                    "CONVERSATION HISTORY",
                    history_context_message,
                )
            )

        parts.append(self.TOOL_PROVENANCE_REMINDER)
        parts.append(self.FINAL_PROFILE_REMINDER)
        return "\n\n".join(part for part in parts if part)

    def _wrap_read_only_context(self, title, content):
        normalized_content = (content or "").strip()
        if not normalized_content:
            return ""

        return (
            f"[{title} - READ ONLY]\n"
            f"{self.READ_ONLY_CONTEXT_NOTICE}\n\n"
            f"{normalized_content}"
        )

    def _get_last_user_message(self, messages):
        last_user_index = self._find_last_user_message_index(messages)
        if last_user_index is None:
            return None

        return {
            "role": "user",
            "content": self._normalize_message_content(
                messages[last_user_index].get("content", "")
            ),
        }

    def _build_history_context(self, messages):
        last_user_index = self._find_last_user_message_index(messages)
        if last_user_index is None:
            return ""

        blocks = []

        for index, message in enumerate(messages or []):
            if index == last_user_index:
                continue

            content = self._normalize_message_content(message.get("content", ""))
            normalized_content = content.strip()
            if not normalized_content:
                continue

            blocks.append(self._build_history_message_block(message, normalized_content))

        return "\n\n".join(block for block in blocks if block)

    def _build_project_context_message(self, project):
        if not project:
            return ""

        parts = [f"Active project: {project['name']}"]

        if project.get("description"):
            parts.append(f"Project description:\n{project['description']}")

        if project.get("system_prompt"):
            parts.append(f"Project instructions:\n{project['system_prompt']}")

        documents = self.db.project_documents.for_project(project["id"])
        documents_block = self._build_project_documents_context(documents)
        if documents_block:
            parts.append(documents_block)

        return "\n\n".join(part for part in parts if part)

    def _build_project_documents_context(self, documents):
        if not documents:
            return ""

        max_total_chars = 12_000
        max_document_chars = 4_000
        consumed = 0
        blocks = []

        for index, document in enumerate(documents, start=1):
            header = f"[Document {index}] {document['filename']}\n"
            body = (document.get("text_content") or "").strip()
            if not body:
                continue

            if len(body) > max_document_chars:
                body = (
                    f"{body[:max_document_chars].rstrip()}\n"
                    "[Document truncated for chat context.]"
                )

            block = f"{header}{body}"
            projected_size = consumed + len(block)
            if projected_size > max_total_chars:
                remaining = max_total_chars - consumed
                if remaining <= len(header) + 64:
                    break

                available_body = remaining - len(header) - len(
                    "\n[Document truncated for chat context.]"
                )
                trimmed_body = body[:available_body].rstrip()
                block = (
                    f"{header}{trimmed_body}\n"
                    "[Document truncated for chat context.]"
                )

            blocks.append(block)
            consumed += len(block)

            if consumed >= max_total_chars:
                break

        if not blocks:
            return ""

        return "Project documents:\n\n" + "\n\n".join(blocks)

    def _find_last_user_message_index(self, messages):
        last_user_index = None

        for index, message in enumerate(messages or []):
            if message.get("role") == "user":
                last_user_index = index

        return last_user_index

    def _build_history_message_block(self, message, content):
        role = str(message.get("role") or "unknown").strip() or "unknown"
        profile_name = str(message.get("profile_name") or "").strip()
        tool_events_block = self._build_tool_events_context(message.get("tool_events"))

        if role == "assistant" and profile_name:
            parts = [
                "[Previous assistant message]\n"
                f"Profile: {profile_name}\n"
                "Content:\n"
                f"{content}"
            ]
            if tool_events_block:
                parts.append(tool_events_block)
            return "\n\n".join(parts)

        if role == "assistant":
            parts = [
                "[Previous assistant message]\n"
                "Content:\n"
                f"{content}"
            ]
            if tool_events_block:
                parts.append(tool_events_block)
            return "\n\n".join(parts)

        if role == "user":
            return (
                "[Previous user message]\n"
                "Content:\n"
                f"{content}"
            )

        return (
            f"[Previous {role} message]\n"
            "Content:\n"
            f"{content}"
        )

    def _build_tool_events_context(self, tool_events):
        if not isinstance(tool_events, list) or not tool_events:
            return ""

        serialized = json.dumps(tool_events, ensure_ascii=False, sort_keys=True)
        if len(serialized) > 4000:
            serialized = serialized[:4000].rstrip() + "..."

        return (
            "[Previous tool usage]\n"
            "These tool results belong to the assistant message above and can be used "
            "to answer follow-up questions about sources, consulted data, or how the answer was produced.\n"
            f"{serialized}"
        )

    def _normalize_message_content(self, content):
        if isinstance(content, str):
            return content

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

            return "\n".join(parts)

        if content is None:
            return ""

        return str(content)
