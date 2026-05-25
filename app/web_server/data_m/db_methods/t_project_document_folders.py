class ProjectDocumentFoldersTable:
    def __init__(self, db):
        self.db = db

    def create(self, project_id, name, parent_folder_id=None):
        _, folder_id = self.db.execute(
            """
            INSERT INTO project_document_folders (
                project_id,
                parent_folder_id,
                name
            )
            VALUES (?, ?, ?)
            """,
            (project_id, parent_folder_id, name),
            lastrowid=True,
        )
        return folder_id

    def get(self, folder_id):
        _, row = self.db.execute(
            """
            SELECT id, project_id, parent_folder_id, name, created_at, updated_at
            FROM project_document_folders
            WHERE id = ?
            """,
            (folder_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def for_project(self, project_id):
        _, rows = self.db.execute(
            """
            SELECT id, project_id, parent_folder_id, name, created_at, updated_at
            FROM project_document_folders
            WHERE project_id = ?
            ORDER BY LOWER(name) ASC, id ASC
            """,
            (project_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def find_by_name(self, project_id, name, parent_folder_id=None):
        _, row = self.db.execute(
            """
            SELECT id, project_id, parent_folder_id, name, created_at, updated_at
            FROM project_document_folders
            WHERE project_id = ?
              AND name = ?
              AND (
                    (parent_folder_id IS NULL AND ? IS NULL)
                    OR parent_folder_id = ?
              )
            LIMIT 1
            """,
            (project_id, name, parent_folder_id, parent_folder_id),
            fetchone=True,
        )
        return self._serialize(row)

    def delete(self, folder_id):
        self.db.execute(
            "DELETE FROM project_document_folders WHERE id = ?",
            (folder_id,),
        )

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "parent_folder_id": row[2],
            "name": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
