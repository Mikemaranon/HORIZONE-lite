class ProjectDocumentsTable:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        project_id,
        filename,
        content_type,
        size_bytes,
        text_content,
        folder_id=None,
    ):
        _, document_id = self.db.execute(
            """
            INSERT INTO project_documents (
                project_id,
                folder_id,
                filename,
                content_type,
                size_bytes,
                text_content
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, folder_id, filename, content_type, size_bytes, text_content),
            lastrowid=True,
        )
        return document_id

    def get(self, document_id):
        _, row = self.db.execute(
            """
            SELECT id, project_id, folder_id, filename, content_type, size_bytes, text_content,
                   created_at, updated_at
            FROM project_documents
            WHERE id = ?
            """,
            (document_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def for_project(self, project_id):
        _, rows = self.db.execute(
            """
            SELECT id, project_id, folder_id, filename, content_type, size_bytes, text_content,
                   created_at, updated_at
            FROM project_documents
            WHERE project_id = ?
            ORDER BY
                CASE WHEN folder_id IS NULL THEN 0 ELSE 1 END ASC,
                folder_id ASC,
                LOWER(filename) ASC,
                id ASC
            """,
            (project_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def move_to_folder(self, document_id, folder_id):
        self.db.execute(
            """
            UPDATE project_documents
            SET folder_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (folder_id, document_id),
        )

    def delete(self, document_id):
        self.db.execute(
            "DELETE FROM project_documents WHERE id = ?",
            (document_id,),
        )

    def delete_for_project(self, project_id):
        self.db.execute(
            "DELETE FROM project_documents WHERE project_id = ?",
            (project_id,),
        )

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "folder_id": row[2],
            "filename": row[3],
            "content_type": row[4],
            "size_bytes": row[5],
            "text_content": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }
