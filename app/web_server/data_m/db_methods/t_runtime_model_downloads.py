class RuntimeModelDownloadsTable:
    VALID_STATUSES = {
        "queued",
        "downloading",
        "verifying",
        "ready",
        "error",
        "cancelled",
    }

    def __init__(self, db):
        self.db = db

    def create(
        self,
        *,
        catalog_key,
        status,
        source_url,
        filename,
        model_config_id=None,
        local_path="",
        bytes_downloaded=0,
        total_bytes=0,
        error_message="",
    ):
        self._require_valid_status(status)
        _, download_id = self.db.execute(
            """
            INSERT INTO runtime_model_downloads (
                catalog_key, model_config_id, status, source_url, filename, local_path,
                bytes_downloaded, total_bytes, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                catalog_key,
                model_config_id,
                status,
                source_url,
                filename,
                local_path or "",
                int(bytes_downloaded or 0),
                int(total_bytes or 0),
                error_message or "",
            ),
            lastrowid=True,
        )
        return download_id

    def get(self, download_id):
        _, row = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            WHERE id = ?
            """,
            (download_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def latest_for_catalog_key(self, catalog_key):
        _, row = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            WHERE catalog_key = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (catalog_key,),
            fetchone=True,
        )
        return self._serialize(row)

    def ready(self):
        _, rows = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            WHERE status = 'ready'
                AND model_config_id IS NOT NULL
                AND local_path != ''
            ORDER BY updated_at DESC, id DESC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def for_model(self, model_config_id):
        _, rows = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            WHERE model_config_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (model_config_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def active(self):
        _, rows = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            WHERE status IN ('queued', 'downloading', 'verifying')
            ORDER BY updated_at DESC, id DESC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def update_progress(self, download_id, *, status=None, bytes_downloaded=None, total_bytes=None):
        current = self.get(download_id)
        if not current:
            return None

        next_status = status or current["status"]
        self._require_valid_status(next_status)
        self.db.execute(
            """
            UPDATE runtime_model_downloads
            SET status = ?,
                bytes_downloaded = ?,
                total_bytes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                next_status,
                int(bytes_downloaded if bytes_downloaded is not None else current["bytes_downloaded"]),
                int(total_bytes if total_bytes is not None else current["total_bytes"]),
                download_id,
            ),
        )
        return self.get(download_id)

    def finish(self, download_id, *, status, model_config_id=None, local_path="", error_message=""):
        self._require_valid_status(status)
        self.db.execute(
            """
            UPDATE runtime_model_downloads
            SET status = ?,
                model_config_id = COALESCE(?, model_config_id),
                local_path = ?,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                model_config_id,
                local_path or "",
                error_message or "",
                download_id,
            ),
        )
        return self.get(download_id)

    def all(self):
        _, rows = self.db.execute(
            """
            SELECT id, catalog_key, model_config_id, status, source_url, filename, local_path,
                   bytes_downloaded, total_bytes, error_message, created_at, updated_at, finished_at
            FROM runtime_model_downloads
            ORDER BY updated_at DESC, id DESC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def delete_for_model(self, model_config_id):
        self.db.execute(
            "DELETE FROM runtime_model_downloads WHERE model_config_id = ?",
            (model_config_id,),
        )

    def _require_valid_status(self, status):
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported runtime download status: {status}")

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "catalog_key": row[1],
            "model_config_id": row[2],
            "status": row[3],
            "source_url": row[4],
            "filename": row[5],
            "local_path": row[6] or "",
            "bytes_downloaded": row[7] or 0,
            "total_bytes": row[8] or 0,
            "error_message": row[9] or "",
            "created_at": row[10],
            "updated_at": row[11],
            "finished_at": row[12],
        }
