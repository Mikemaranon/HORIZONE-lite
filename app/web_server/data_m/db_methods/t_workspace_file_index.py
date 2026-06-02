class WorkspaceFileIndexTable:
    def __init__(self, db):
        self.db = db

    def replace_for_workspace(self, workspace_id, files):
        self.db.execute(
            "DELETE FROM workspace_file_index WHERE workspace_id = ?",
            (workspace_id,),
        )

        for file_record in files:
            self.upsert_file(workspace_id, file_record)

    def upsert_file(self, workspace_id, file_record):
        self.db.execute(
            """
            INSERT INTO workspace_file_index (
                workspace_id, path, kind, size_bytes, mtime, language, is_ignored, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(workspace_id, path)
            DO UPDATE SET
                kind = excluded.kind,
                size_bytes = excluded.size_bytes,
                mtime = excluded.mtime,
                language = excluded.language,
                is_ignored = excluded.is_ignored,
                indexed_at = CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                file_record["path"],
                file_record.get("kind", "file"),
                file_record.get("size_bytes", 0),
                file_record.get("mtime", 0),
                file_record.get("language", ""),
                1 if file_record.get("is_ignored") else 0,
            ),
        )

    def delete_file(self, workspace_id, relative_path):
        self.db.execute(
            """
            DELETE FROM workspace_file_index
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, relative_path),
        )

    def list_for_workspace(self, workspace_id, query=None, limit=200):
        params = [workspace_id]
        where_clause = "WHERE workspace_id = ?"
        if query:
            where_clause += " AND path LIKE ?"
            params.append(f"%{query}%")
        params.append(limit)

        _, rows = self.db.execute(
            f"""
            SELECT id, workspace_id, path, kind, size_bytes, mtime, language, is_ignored, indexed_at
            FROM workspace_file_index
            {where_clause}
            ORDER BY path ASC
            LIMIT ?
            """,
            tuple(params),
            fetchall=True,
        )
        return [self._row_to_dict(row) for row in rows]

    def count_for_workspace(self, workspace_id):
        _, row = self.db.execute(
            "SELECT COUNT(*) FROM workspace_file_index WHERE workspace_id = ?",
            (workspace_id,),
            fetchone=True,
        )
        return row[0] if row else 0

    def _row_to_dict(self, row):
        return {
            "id": row[0],
            "workspace_id": row[1],
            "path": row[2],
            "kind": row[3],
            "size_bytes": row[4],
            "mtime": row[5],
            "language": row[6] or "",
            "is_ignored": bool(row[7]),
            "indexed_at": row[8],
        }
