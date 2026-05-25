import json


class WorkspaceEventsTable:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        workspace_id,
        project_id,
        event_type,
        summary,
        payload=None,
        conversation_id=None,
        message_id=None,
    ):
        _, event_id = self.db.execute(
            """
            INSERT INTO workspace_events (
                workspace_id, project_id, conversation_id, message_id, event_type, summary, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                project_id,
                conversation_id,
                message_id,
                event_type,
                summary,
                json.dumps(payload or {}),
            ),
            lastrowid=True,
        )
        return event_id

    def recent_for_workspace(self, workspace_id, limit=50):
        _, rows = self.db.execute(
            """
            SELECT id, workspace_id, project_id, conversation_id, message_id, event_type, summary, payload_json, created_at
            FROM workspace_events
            WHERE workspace_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (workspace_id, limit),
            fetchall=True,
        )
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row):
        return {
            "id": row[0],
            "workspace_id": row[1],
            "project_id": row[2],
            "conversation_id": row[3],
            "message_id": row[4],
            "event_type": row[5],
            "summary": row[6],
            "payload": json.loads(row[7] or "{}"),
            "created_at": row[8],
        }
