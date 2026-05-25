class ProjectDocumentChunksTable:
    def __init__(self, db):
        self.db = db

    def replace_for_document(self, document_id, project_id, chunks):
        self.delete_for_document(document_id)

        for index, chunk in enumerate(chunks):
            text_content = self._extract_chunk_text(chunk)
            if not text_content:
                continue

            self.db.execute(
                """
                INSERT INTO project_document_chunks (
                    project_id,
                    document_id,
                    chunk_index,
                    text_content
                )
                VALUES (?, ?, ?, ?)
                """,
                (project_id, document_id, index, text_content),
            )

    def for_project(self, project_id):
        _, rows = self.db.execute(
            """
            SELECT
                c.id,
                c.project_id,
                c.document_id,
                c.chunk_index,
                c.text_content,
                c.created_at,
                c.updated_at,
                d.filename,
                d.folder_id
            FROM project_document_chunks c
            JOIN project_documents d ON d.id = c.document_id
            WHERE c.project_id = ?
            ORDER BY d.id ASC, c.chunk_index ASC
            """,
            (project_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def for_document(self, document_id):
        _, rows = self.db.execute(
            """
            SELECT
                c.id,
                c.project_id,
                c.document_id,
                c.chunk_index,
                c.text_content,
                c.created_at,
                c.updated_at,
                d.filename,
                d.folder_id
            FROM project_document_chunks c
            JOIN project_documents d ON d.id = c.document_id
            WHERE c.document_id = ?
            ORDER BY c.chunk_index ASC
            """,
            (document_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def count_for_document(self, document_id):
        _, row = self.db.execute(
            """
            SELECT COUNT(*)
            FROM project_document_chunks
            WHERE document_id = ?
            """,
            (document_id,),
            fetchone=True,
        )
        return row[0] if row else 0

    def delete_for_document(self, document_id):
        self.db.execute(
            "DELETE FROM project_document_chunks WHERE document_id = ?",
            (document_id,),
        )

    def _extract_chunk_text(self, chunk):
        if isinstance(chunk, dict):
            return str(chunk.get("text_content") or chunk.get("text") or "").strip()

        return str(chunk or "").strip()

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "document_id": row[2],
            "chunk_index": row[3],
            "text_content": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "filename": row[7],
            "folder_id": row[8],
        }
