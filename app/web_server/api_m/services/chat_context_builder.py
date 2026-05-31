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

    def __init__(self, db_manager, project_context_retrieval_service=None):
        self.db = db_manager
        if project_context_retrieval_service is None:
            from .project_context_retrieval_service import ProjectContextRetrievalService

            project_context_retrieval_service = ProjectContextRetrievalService(db_manager)
        self.project_context_retrieval_service = project_context_retrieval_service

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

    def build_input_messages(self, project, profile, messages, project_model=None):
        normalized_messages = []
        system_message_content = self._build_system_message_content(
            project,
            profile,
            messages,
            project_model=project_model,
        )
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

    def _build_project_agent_instruction(self, project_model):
        if not project_model:
            return ""

        parts = [f"Active project agent: {project_model.get('nickname') or 'Agent'}"]
        agent_prompt = (project_model.get("system_prompt") or "").strip()
        if agent_prompt:
            parts.append(agent_prompt)

        return "\n\n".join(part for part in parts if part)

    def _build_system_message_content(self, project, profile, messages, project_model=None):
        parts = [self._build_profile_instruction(profile)]
        project_agent_instruction = self._build_project_agent_instruction(project_model)
        if project_agent_instruction:
            parts.append(project_agent_instruction)

        latest_user_message = self._get_last_user_message(messages)
        latest_user_content = latest_user_message["content"] if latest_user_message else ""
        project_context_message = self._build_project_context_message(
            project,
            latest_user_content,
        )
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

    def _build_project_context_message(self, project, latest_user_content=""):
        if not project:
            return ""

        parts = [f"Active project: {project['name']}"]

        if project.get("description"):
            parts.append(f"Project description:\n{project['description']}")

        if project.get("system_prompt"):
            parts.append(f"Project instructions:\n{project['system_prompt']}")

        documents_block = self._build_project_documents_context(
            project,
            latest_user_content,
        )
        if documents_block:
            parts.append(documents_block)

        return "\n\n".join(part for part in parts if part)

    def _build_project_documents_context(self, project, latest_user_content):
        if not project or not latest_user_content:
            return ""

        return self.project_context_retrieval_service.build_context(
            project["id"],
            latest_user_content,
        )

    def _build_folder_paths(self, project_id):
        folders = self.db.project_document_folders.for_project(project_id)
        folders_by_id = {folder["id"]: folder for folder in folders}
        paths = {}

        for folder in folders:
            self._resolve_folder_path(folder["id"], folders_by_id, paths)

        return paths

    def _resolve_folder_path(self, folder_id, folders_by_id, paths):
        if folder_id in paths:
            return paths[folder_id]

        folder = folders_by_id.get(folder_id)
        if not folder:
            return ""

        parent_id = folder.get("parent_folder_id")
        if parent_id:
            parent_path = self._resolve_folder_path(parent_id, folders_by_id, paths)
            path = f"{parent_path}/{folder['name']}" if parent_path else folder["name"]
        else:
            path = folder["name"]

        paths[folder_id] = path
        return path

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

        blocks = []
        for tool_event in tool_events[:5]:
            block = self._build_compact_tool_event_block(tool_event)
            if block:
                blocks.append(block)

        if not blocks:
            return ""

        return (
            "[Previous tool usage]\n"
            "These tool results belong to the assistant message above and can be used "
            "to answer follow-up questions about sources, consulted data, or how the answer was produced.\n"
            f"{chr(10).join(blocks)}"
        )

    def _build_compact_tool_event_block(self, tool_event):
        if not isinstance(tool_event, dict):
            return ""

        tool_name = str(tool_event.get("tool_name") or "tool").strip()
        tool_summary = str(tool_event.get("tool_summary") or "").strip()
        if not tool_summary:
            tool_summary = self._derive_tool_summary(tool_event)

        lines = [f"- {tool_name}: {tool_summary}"]
        source_urls = tool_event.get("source_urls")
        source_titles = tool_event.get("source_titles")

        if not isinstance(source_urls, list) or not source_urls:
            source_urls = self._extract_source_urls(tool_event)
        if not isinstance(source_titles, list):
            source_titles = []

        if source_urls:
            lines.append("  Sources:")
            for index, url in enumerate(source_urls[:5]):
                title = source_titles[index] if index < len(source_titles) else ""
                if title:
                    lines.append(f"  - {title}: {url}")
                else:
                    lines.append(f"  - {url}")

        return "\n".join(lines)

    def _derive_tool_summary(self, tool_event):
        tool_name = str(tool_event.get("tool_name") or "tool").strip()
        if not tool_event.get("ok"):
            error = str(tool_event.get("error") or "The tool could not complete.").strip()
            return f"{tool_name} failed: {error}"

        result = tool_event.get("result") or {}
        if tool_name == "web_search":
            query = str((tool_event.get("arguments") or {}).get("query") or result.get("query") or "").strip()
            count = len(result.get("results") or []) if isinstance(result, dict) else 0
            if query:
                return f'searched for "{query}" and returned {count} result(s).'
            return f"returned {count} result(s)."

        if tool_name == "current_date":
            details = [
                str(result.get("date") or "").strip(),
                str(result.get("time") or "").strip(),
                str(result.get("timezone") or "").strip(),
            ]
            details = [value for value in details if value]
            if details:
                return f"returned {', '.join(details)}."
            return "returned current date information."

        compact_fields = []
        for key, value in result.items() if isinstance(result, dict) else []:
            if isinstance(value, (str, int, float, bool)) and str(value).strip():
                compact_fields.append(f"{key}: {value}")

        if compact_fields:
            return f"returned {'; '.join(compact_fields[:3])}."

        return "completed successfully."

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
