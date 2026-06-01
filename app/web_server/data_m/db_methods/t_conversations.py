import json


class ConversationsTable:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        title="New Chat",
        project_id=None,
        project_model_id=None,
        quick_project_model_ids=None,
        profile_id=None,
        model_config_id=None,
        provider="mlx",
        model="",
    ):
        _, conversation_id = self.db.execute(
            """
            INSERT INTO conversations (
                title, project_id, project_model_id, quick_project_model_ids,
                profile_id, model_config_id, provider, model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                project_id,
                project_model_id,
                self._serialize_quick_project_model_ids(quick_project_model_ids),
                profile_id,
                model_config_id,
                provider,
                model,
            ),
            lastrowid=True
        )
        return conversation_id

    def get(self, conversation_id):
        _, row = self.db.execute(
            """
            SELECT id, title, project_id, project_model_id, quick_project_model_ids,
                   profile_id, model_config_id, provider, model, created_at, updated_at
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
            fetchone=True
        )
        return self._serialize(row)

    def all(self, project_id=None):
        query = """
            SELECT id, title, project_id, project_model_id, quick_project_model_ids,
                   profile_id, model_config_id, provider, model, created_at, updated_at
            FROM conversations
        """
        params = ()

        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (project_id,)

        query += " ORDER BY updated_at DESC, id DESC"
        _, rows = self.db.execute(query, params, fetchall=True)
        return [self._serialize(row) for row in rows]

    def update(
        self,
        conversation_id,
        title,
        project_id,
        project_model_id,
        quick_project_model_ids,
        profile_id,
        model_config_id,
        provider,
        model,
    ):
        self.db.execute(
            """
            UPDATE conversations
            SET title = ?,
                project_id = ?,
                project_model_id = ?,
                quick_project_model_ids = ?,
                profile_id = ?,
                model_config_id = ?,
                provider = ?,
                model = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                title,
                project_id,
                project_model_id,
                self._serialize_quick_project_model_ids(quick_project_model_ids),
                profile_id,
                model_config_id,
                provider,
                model,
                conversation_id,
            )
        )

    def touch(self, conversation_id):
        self.db.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (conversation_id,)
        )

    def rename(self, conversation_id, title):
        self.db.execute(
            """
            UPDATE conversations
            SET title = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, conversation_id)
        )

    def delete(self, conversation_id):
        self.db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,)
        )

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "title": row[1],
            "project_id": row[2],
            "project_model_id": row[3],
            "quick_project_model_ids": self._parse_quick_project_model_ids(row[4]),
            "profile_id": row[5],
            "model_config_id": row[6],
            "provider": row[7],
            "model": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def _serialize_quick_project_model_ids(self, project_model_ids):
        if not project_model_ids:
            return ""

        normalized_ids = []
        for project_model_id in project_model_ids:
            try:
                normalized_id = int(project_model_id)
            except (TypeError, ValueError):
                continue

            if normalized_id > 0 and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        return json.dumps(normalized_ids) if normalized_ids else ""

    def _parse_quick_project_model_ids(self, raw_value):
        if not raw_value:
            return []

        try:
            values = json.loads(raw_value)
        except (TypeError, ValueError):
            return []

        if not isinstance(values, list):
            return []

        normalized_ids = []
        for value in values:
            try:
                normalized_id = int(value)
            except (TypeError, ValueError):
                continue

            if normalized_id > 0 and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        return normalized_ids
