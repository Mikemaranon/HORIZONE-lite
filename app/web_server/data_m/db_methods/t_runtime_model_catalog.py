class RuntimeModelCatalogTable:
    def __init__(self, db):
        self.db = db

    def upsert(
        self,
        *,
        catalog_key,
        display_name,
        source_url,
        filename,
        description="",
        provider_type="llama_cpp",
        size_bytes=0,
        checksum_sha256="",
        architecture="",
        quantization="",
        context_length=0,
        recommended_ram_gb=0,
        license="",
        is_featured=False,
        sort_order=0,
    ):
        self.db.execute(
            """
            INSERT INTO runtime_model_catalog (
                catalog_key, display_name, description, provider_type, source_url, filename,
                size_bytes, checksum_sha256, architecture, quantization, context_length,
                recommended_ram_gb, license, is_featured, sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                provider_type = excluded.provider_type,
                source_url = excluded.source_url,
                filename = excluded.filename,
                size_bytes = excluded.size_bytes,
                checksum_sha256 = excluded.checksum_sha256,
                architecture = excluded.architecture,
                quantization = excluded.quantization,
                context_length = excluded.context_length,
                recommended_ram_gb = excluded.recommended_ram_gb,
                license = excluded.license,
                is_featured = excluded.is_featured,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                catalog_key,
                display_name,
                description or "",
                provider_type or "llama_cpp",
                source_url,
                filename,
                int(size_bytes or 0),
                checksum_sha256 or "",
                architecture or "",
                quantization or "",
                int(context_length or 0),
                int(recommended_ram_gb or 0),
                license or "",
                int(is_featured),
                int(sort_order or 0),
            ),
        )
        return self.get_by_catalog_key(catalog_key)

    def get_by_catalog_key(self, catalog_key):
        _, row = self.db.execute(
            """
            SELECT id, catalog_key, display_name, description, provider_type, source_url, filename,
                   size_bytes, checksum_sha256, architecture, quantization, context_length,
                   recommended_ram_gb, license, is_featured, sort_order, created_at, updated_at
            FROM runtime_model_catalog
            WHERE catalog_key = ?
            """,
            (catalog_key,),
            fetchone=True,
        )
        return self._serialize(row)

    def all(self):
        _, rows = self.db.execute(
            """
            SELECT id, catalog_key, display_name, description, provider_type, source_url, filename,
                   size_bytes, checksum_sha256, architecture, quantization, context_length,
                   recommended_ram_gb, license, is_featured, sort_order, created_at, updated_at
            FROM runtime_model_catalog
            ORDER BY sort_order ASC, display_name ASC, id ASC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "catalog_key": row[1],
            "display_name": row[2],
            "description": row[3] or "",
            "provider_type": row[4] or "llama_cpp",
            "source_url": row[5],
            "filename": row[6],
            "size_bytes": row[7] or 0,
            "checksum_sha256": row[8] or "",
            "architecture": row[9] or "",
            "quantization": row[10] or "",
            "context_length": row[11] or 0,
            "recommended_ram_gb": row[12] or 0,
            "license": row[13] or "",
            "is_featured": bool(row[14]),
            "sort_order": row[15] or 0,
            "created_at": row[16],
            "updated_at": row[17],
        }
