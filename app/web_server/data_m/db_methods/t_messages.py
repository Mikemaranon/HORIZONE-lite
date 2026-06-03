import json


class MessagesTable:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        conversation_id,
        role,
        content,
        position=None,
        project_model_id=None,
        project_model_name="",
        model_config_id=None,
        model_name="",
        profile_id=None,
        profile_name="",
        tool_events=None,
        provider_message_id=None,
    ):
        if position is None:
            position = self._next_position(conversation_id)
        model_name = self._normalize_model_name(model_config_id, model_name)

        _, message_id = self.db.execute(
            """
            INSERT INTO messages (
                conversation_id, role, content, position, project_model_id, project_model_name,
                model_config_id, model_name, profile_id, profile_name, tool_events, provider_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                position,
                project_model_id,
                project_model_name,
                model_config_id,
                model_name,
                profile_id,
                profile_name,
                self._serialize_tool_events(tool_events),
                provider_message_id,
            ),
            lastrowid=True
        )
        return message_id

    def append_many(self, conversation_id, messages):
        message_ids = []

        for message in messages:
            message_ids.append(
                self.create(
                    conversation_id=conversation_id,
                    role=message.get("role"),
                    content=message.get("content", ""),
                    project_model_id=message.get("project_model_id"),
                    project_model_name=message.get("project_model_name", ""),
                    model_config_id=message.get("model_config_id"),
                    model_name=message.get("model_name", ""),
                    profile_id=message.get("profile_id"),
                    profile_name=message.get("profile_name", ""),
                    tool_events=message.get("tool_events"),
                    provider_message_id=message.get("provider_message_id"),
                )
            )

        return message_ids

    def get(self, message_id):
        _, row = self.db.execute(
            """
            SELECT id, conversation_id, role, content, position,
                   project_model_id, project_model_name,
                   model_config_id, model_name, profile_id, profile_name,
                   tool_events, provider_message_id, created_at
            FROM messages
            WHERE id = ?
            """,
            (message_id,),
            fetchone=True
        )
        return self._serialize(row)

    def for_conversation(self, conversation_id):
        _, rows = self.db.execute(
            """
            SELECT id, conversation_id, role, content, position,
                   project_model_id, project_model_name,
                   model_config_id, model_name, profile_id, profile_name,
                   tool_events, provider_message_id, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY position ASC, id ASC
            """,
            (conversation_id,),
            fetchall=True
        )
        return [self._serialize(row) for row in rows]

    def delete(self, message_id):
        self.db.execute(
            "DELETE FROM messages WHERE id = ?",
            (message_id,)
        )

    def delete_for_conversation(self, conversation_id):
        self.db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )

    def update_tool_events(self, message_id, tool_events):
        self.db.execute(
            """
            UPDATE messages
            SET tool_events = ?
            WHERE id = ?
            """,
            (
                self._serialize_tool_events(tool_events),
                message_id,
            )
        )

    def _next_position(self, conversation_id):
        _, row = self.db.execute(
            """
            SELECT COALESCE(MAX(position), -1) + 1
            FROM messages
            WHERE conversation_id = ?
            """,
            (conversation_id,),
            fetchone=True
        )
        return row[0] if row else 0

    def _normalize_model_name(self, model_config_id, model_name):
        normalized = str(model_name or "").strip()
        if not model_config_id:
            return normalized

        _, row = self.db.execute(
            """
            SELECT name, display_name
            FROM models
            WHERE id = ?
            """,
            (model_config_id,),
            fetchone=True,
        )
        if not row:
            return normalized

        technical_name = row[0] or ""
        display_name = row[1] or technical_name
        if not normalized or normalized == technical_name:
            return display_name

        return normalized

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "conversation_id": row[1],
            "role": row[2],
            "content": row[3],
            "position": row[4],
            "project_model_id": row[5],
            "project_model_name": row[6] or "",
            "model_config_id": row[7],
            "model_name": row[8] or "",
            "profile_id": row[9],
            "profile_name": row[10] or "",
            "tool_events": self._parse_tool_events(row[11]),
            "provider_message_id": row[12],
            "created_at": row[13],
        }

    def _serialize_tool_events(self, tool_events):
        normalized = tool_events if isinstance(tool_events, list) else []
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)

    def _parse_tool_events(self, raw_value):
        if not raw_value:
            return []

        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            return []

        return value if isinstance(value, list) else []
