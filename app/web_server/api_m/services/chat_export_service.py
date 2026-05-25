class ChatExportService:
    def __init__(self, db_manager, context_builder):
        self.db = db_manager
        self.context_builder = context_builder

    def build_conversation_export(self, conversation_id):
        conversation = self.db.conversations.get(conversation_id)
        if not conversation:
            raise LookupError("Conversation not found")

        project = self._get_project_snapshot(conversation.get("project_id"))
        profile = self._get_profile_snapshot(conversation.get("profile_id"))
        model = self._get_model_snapshot(conversation.get("model_config_id"))
        provider = self._get_provider_snapshot(model)
        messages = self.db.messages.for_conversation(conversation_id)
        active_tools = self.db.tools.active()
        project_documents = self.db.project_documents.for_project(project["id"]) if project else []

        return {
            "conversation": conversation,
            "project": project,
            "profile": profile,
            "model": model,
            "provider": provider,
            "active_tools": active_tools,
            "project_documents": [
                {
                    "id": document["id"],
                    "filename": document["filename"],
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

    def _build_export_messages(self, messages, *, conversation, project, fallback_profile):
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
                )

            export_messages.append(export_message)

        return export_messages

    def _build_generation_snapshot(self, history_messages, *, project, profile, conversation, model, provider):
        settings = self.context_builder.build_generation_settings(profile, None)
        if model and model.get("id") is not None:
            settings["_model_config_id"] = model["id"]

        last_user_message = self._find_last_user_message(history_messages)

        return {
            "provider": provider or self._fallback_provider_snapshot(conversation),
            "model": model or self._fallback_model_snapshot(conversation),
            "profile": profile,
            "settings": settings,
            "input_messages": self.context_builder.build_input_messages(
                project,
                profile,
                history_messages,
            ),
            "source_user_message_id": last_user_message.get("id") if last_user_message else None,
            "source_user_message_position": last_user_message.get("position") if last_user_message else None,
            "reconstructed": True,
        }

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
