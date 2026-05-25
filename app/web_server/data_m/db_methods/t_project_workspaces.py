class ProjectWorkspacesTable:
    def __init__(self, db):
        self.db = db

    def upsert(self, project_id, root_path, display_name, status="connected"):
        existing = self.get_by_project(project_id)
        if existing:
            self.db.execute(
                """
                UPDATE project_workspaces
                SET root_path = ?, display_name = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
                """,
                (root_path, display_name, status, project_id),
            )
            return existing["id"]

        _, workspace_id = self.db.execute(
            """
            INSERT INTO project_workspaces (project_id, root_path, display_name, status)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, root_path, display_name, status),
            lastrowid=True,
        )
        return workspace_id

    def get(self, workspace_id):
        _, row = self.db.execute(
            """
            SELECT id, project_id, root_path, display_name, status, created_at, updated_at, last_indexed_at
            FROM project_workspaces
            WHERE id = ?
            """,
            (workspace_id,),
            fetchone=True,
        )
        return self._row_to_dict(row)

    def get_by_project(self, project_id):
        _, row = self.db.execute(
            """
            SELECT id, project_id, root_path, display_name, status, created_at, updated_at, last_indexed_at
            FROM project_workspaces
            WHERE project_id = ?
            """,
            (project_id,),
            fetchone=True,
        )
        return self._row_to_dict(row)

    def update_indexed_at(self, workspace_id):
        self.db.execute(
            """
            UPDATE project_workspaces
            SET last_indexed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, status = 'connected'
            WHERE id = ?
            """,
            (workspace_id,),
        )

    def update_status(self, workspace_id, status):
        self.db.execute(
            """
            UPDATE project_workspaces
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, workspace_id),
        )

    def delete(self, workspace_id):
        self.db.execute("DELETE FROM project_workspaces WHERE id = ?", (workspace_id,))

    def _row_to_dict(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "root_path": row[2],
            "display_name": row[3],
            "status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "last_indexed_at": row[7],
        }
