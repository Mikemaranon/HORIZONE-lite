class ChatExportService:
    def __init__(self, db_manager, context_builder, tool_manager=None):
        self.db = db_manager
        self.context_builder = context_builder
        self.tool_manager = tool_manager

    def build_conversation_export(self, conversation_id):
        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            raise LookupError("Conversation not found")

        project = self._get_project_snapshot(conversation.get("project_id"))
        workspace = self._get_workspace_snapshot(project)
        profile = self._get_profile_snapshot(conversation.get("profile_id"))
        model = self._get_model_snapshot(conversation.get("model_config_id"))
        provider = self._get_provider_snapshot(model)
        messages = self.db.messages.for_conversation(conversation_id)
        tool_context = self._build_tool_context(conversation, project, workspace)
        active_tools = self._get_available_tools(tool_context)
        project_documents = self.db.project_documents.for_project(project["id"]) if project else []
        folder_paths = self.context_builder._build_folder_paths(project["id"]) if project else {}

        return {
            "conversation": conversation,
            "project": project,
            "workspace": workspace,
            "profile": profile,
            "model": model,
            "provider": provider,
            "active_tools": active_tools,
            "project_documents": [
                {
                    "id": document["id"],
                    "folder_id": document.get("folder_id"),
                    "filename": document["filename"],
                    "path": self._build_document_path(document, folder_paths),
                    "content_type": document["content_type"],
                    "size_bytes": document["size_bytes"],
                    "created_at": document["created_at"],
                    "updated_at": document["updated_at"],
                }
                for document in project_documents
            ],
            "messages": self._build_export_messages(
                messages,
                conversation=conversation,
                project=project,
                fallback_profile=profile,
                tool_context=tool_context,
            ),
            "summary": {
                "message_count": len(messages),
                "user_message_count": sum(1 for message in messages if message.get("role") == "user"),
                "assistant_message_count": sum(1 for message in messages if message.get("role") == "assistant"),
                "tool_enabled_count": len(active_tools),
            },
            "export_metadata": {
                "reconstructed_generation_context": True,
                "system_prompts_versioned_per_turn": False,
                "notes": [
                    (
                        "System prompts and per-turn settings are reconstructed using the "
                        "current project, profile, and associated document configuration."
                    ),
                    (
                        "Tool events are exported from the persisted history of each "
                        "assistant response."
                    ),
                ],
            },
        }

    def _build_export_messages(self, messages, *, conversation, project, fallback_profile, tool_context):
        export_messages = []

        for index, message in enumerate(messages):
            model = self._get_model_snapshot(message.get("model_config_id"))
            provider = self._get_provider_snapshot(model)
            profile = self._get_profile_snapshot(message.get("profile_id")) or fallback_profile

            export_message = {
                **message,
                "author_label": self._resolve_author_label(message, model),
                "model": model or self._fallback_model_snapshot(conversation),
                "provider": provider or self._fallback_provider_snapshot(conversation),
                "profile": profile,
            }

            if message.get("role") == "assistant":
                export_message["generation"] = self._build_generation_snapshot(
                    messages[:index],
                    project=project,
                    profile=profile,
                    conversation=conversation,
                    model=model,
                    provider=provider,
                    tool_context=tool_context,
                )

            export_messages.append(export_message)

        return export_messages

    def _build_generation_snapshot(
        self,
        history_messages,
        *,
        project,
        profile,
        conversation,
        model,
        provider,
        tool_context,
    ):
        settings = self.context_builder.build_generation_settings(profile, None)
        if model and model.get("id") is not None:
            settings["_model_config_id"] = model["id"]

        last_user_message = self._find_last_user_message(history_messages)
        input_messages = self.context_builder.build_input_messages(
            project,
            profile,
            history_messages,
        )
        tool_aware_messages = self._build_tool_aware_messages(
            input_messages,
            tool_context=tool_context,
        )

        return {
            "provider": provider or self._fallback_provider_snapshot(conversation),
            "model": model or self._fallback_model_snapshot(conversation),
            "profile": profile,
            "settings": settings,
            "input_messages": tool_aware_messages,
            "available_tools": self._get_available_tools(tool_context),
            "source_user_message_id": last_user_message.get("id") if last_user_message else None,
            "source_user_message_position": last_user_message.get("position") if last_user_message else None,
            "reconstructed": True,
        }

    def _get_available_tools(self, tool_context):
        if self.tool_manager:
            return self.tool_manager.list_available_tools(tool_context=tool_context)

        return self.db.tools.active()

    def _build_tool_aware_messages(self, messages, *, tool_context):
        if self.tool_manager:
            return self.tool_manager.build_tool_aware_messages(
                messages,
                tool_context=tool_context,
            )

        return messages

    def _build_tool_context(self, conversation, project, workspace):
        return {
            "conversation_id": conversation.get("id") if conversation else None,
            "project": project,
            "workspace": workspace,
        }

    def _get_workspace_snapshot(self, project):
        if not project:
            return None
        return self.db.project_workspaces.get_by_project(project["id"])

    def _resolve_author_label(self, message, model):
        role = str(message.get("role") or "").strip().lower()
        if role == "user":
            return "You"
        if role == "assistant":
            if model and model.get("display_name"):
                return model["display_name"]
            return message.get("model_name") or "Assistant"
        return role or "unknown"

    def _get_project_snapshot(self, project_id):
        if not project_id:
            return None
        return self.db.projects.get(project_id)

    def _get_profile_snapshot(self, profile_id):
        if not profile_id:
            return None
        return self.db.profiles.get(profile_id)

    def _get_model_snapshot(self, model_id):
        if not model_id:
            return None
        return self.db.models.get(model_id)

    def _get_provider_snapshot(self, model):
        if not model or not model.get("provider_config_id"):
            return None

        provider = self.db.providers.get(model["provider_config_id"])
        if not provider:
            return None

        return {
            "id": provider["id"],
            "name": provider["name"],
            "provider_type": provider["provider_type"],
            "endpoint": provider["endpoint"],
            "resolved_adapter": provider["resolved_adapter"],
            "resolved_metadata": provider["resolved_metadata"],
            "is_builtin": provider["is_builtin"],
            "builtin_key": provider["builtin_key"],
            "created_at": provider["created_at"],
            "updated_at": provider["updated_at"],
        }

    def _fallback_model_snapshot(self, conversation):
        if not conversation:
            return None

        return {
            "id": conversation.get("model_config_id"),
            "name": conversation.get("model") or "",
            "display_name": conversation.get("model") or "",
            "provider": conversation.get("provider") or "",
        }

    def _fallback_provider_snapshot(self, conversation):
        if not conversation:
            return None

        return {
            "provider_type": conversation.get("provider") or "",
            "name": conversation.get("provider") or "",
        }

    def _find_last_user_message(self, messages):
        for message in reversed(messages or []):
            if message.get("role") == "user":
                return message
        return None

    def _build_document_path(self, document, folder_paths):
        folder_path = folder_paths.get(document.get("folder_id"))
        if not folder_path:
            return document["filename"]
        return f"{folder_path}/{document['filename']}"
