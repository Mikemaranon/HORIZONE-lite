class WorkspaceFileIndexTable:
    def __init__(self, db):
        self.db = db

    def replace_for_workspace(self, workspace_id, files):
        self.db.execute(
            "DELETE FROM workspace_file_index WHERE workspace_id = ?",
            (workspace_id,),
        )

        for file_record in files:
            self.db.execute(
                """
                INSERT INTO workspace_file_index (
                    workspace_id, path, kind, size_bytes, mtime, language, is_ignored
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
