import json


class ProvidersTable:
    BUILTIN_DEFAULTS = {
        "mlx": {
            "name": "MLX",
            "provider_type": "mlx",
            "endpoint": "",
            "api_key": "",
        },
        "ollama": {
            "name": "Ollama",
            "provider_type": "ollama",
            "endpoint": "http://localhost:11434/api",
            "api_key": "",
        },
        "horizone_runtime": {
            "name": "HORIZONE runtime",
            "provider_type": "llama_cpp",
            "endpoint": "",
            "api_key": "",
            "is_system_managed": True,
        },
    }

    def __init__(self, db):
        self.db = db

    def create(
        self,
        name,
        provider_type,
        endpoint="",
        api_key="",
        resolved_adapter="",
        resolved_metadata=None,
        is_builtin=False,
        is_system_managed=False,
        builtin_key=None,
    ):
        _, provider_id = self.db.execute(
            """
            INSERT INTO providers (
                name, provider_type, endpoint, api_key, resolved_adapter, resolved_metadata,
                is_builtin, is_system_managed, builtin_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                provider_type,
                endpoint or "",
                api_key or "",
                resolved_adapter or "",
                self._dump_metadata(resolved_metadata),
                int(is_builtin),
                int(is_system_managed),
                builtin_key or "",
            ),
            lastrowid=True,
        )
        return provider_id

    def get(self, provider_id):
        _, row = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, resolved_adapter, resolved_metadata,
                   is_builtin, is_system_managed, builtin_key,
                   created_at, updated_at
            FROM providers
            WHERE id = ?
            """,
            (provider_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def get_by_builtin_key(self, builtin_key):
        _, row = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, resolved_adapter, resolved_metadata,
                   is_builtin, is_system_managed, builtin_key,
                   created_at, updated_at
            FROM providers
            WHERE builtin_key = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (builtin_key,),
            fetchone=True,
        )
        return self._serialize(row)

    def get_first_by_type(self, provider_type):
        _, row = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, resolved_adapter, resolved_metadata,
                   is_builtin, is_system_managed, builtin_key,
                   created_at, updated_at
            FROM providers
            WHERE provider_type = ?
            ORDER BY is_builtin DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (provider_type,),
            fetchone=True,
        )
        return self._serialize(row)

    def all(self):
        _, rows = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, resolved_adapter, resolved_metadata,
                   is_builtin, is_system_managed, builtin_key,
                   created_at, updated_at
            FROM providers
            ORDER BY
                CASE WHEN builtin_key = 'horizone_runtime' THEN 0 ELSE 1 END,
                updated_at DESC,
                id DESC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def update(
        self,
        provider_id,
        name,
        provider_type,
        endpoint="",
        api_key="",
        resolved_adapter="",
        resolved_metadata=None,
        is_builtin=False,
        is_system_managed=False,
        builtin_key=None,
    ):
        self.db.execute(
            """
            UPDATE providers
            SET name = ?,
                provider_type = ?,
                endpoint = ?,
                api_key = ?,
                resolved_adapter = ?,
                resolved_metadata = ?,
                is_builtin = ?,
                is_system_managed = ?,
                builtin_key = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name,
                provider_type,
                endpoint or "",
                api_key or "",
                resolved_adapter or "",
                self._dump_metadata(resolved_metadata),
                int(is_builtin),
                int(is_system_managed),
                builtin_key or "",
                provider_id,
            ),
        )

    def delete(self, provider_id):
        self.db.execute(
            "DELETE FROM providers WHERE id = ?",
            (provider_id,),
        )

    def models_count(self, provider_id):
        _, row = self.db.execute(
            "SELECT COUNT(*) FROM models WHERE provider_config_id = ?",
            (provider_id,),
            fetchone=True,
        )
        return row[0] if row else 0

    def restore(self, provider_id):
        provider = self.get(provider_id)
        if not provider or not provider.get("is_builtin"):
            return None

        defaults = self.BUILTIN_DEFAULTS.get(provider["builtin_key"])
        if not defaults:
            return None

        self.update(
            provider_id=provider_id,
            name=defaults["name"],
            provider_type=defaults["provider_type"],
            endpoint=defaults["endpoint"],
            api_key=defaults["api_key"],
            is_builtin=True,
            is_system_managed=defaults.get("is_system_managed", False),
            builtin_key=provider["builtin_key"],
        )
        return self.get(provider_id)

    def ensure_seed_providers(self):
        self._migrate_legacy_cloud_providers()
        for builtin_key, defaults in self.BUILTIN_DEFAULTS.items():
            existing_provider = self.get_by_builtin_key(builtin_key)
            if existing_provider:
                self._repair_system_managed_provider(existing_provider, defaults)
                continue

            self.create(
                name=defaults["name"],
                provider_type=defaults["provider_type"],
                endpoint=defaults["endpoint"],
                api_key=defaults["api_key"],
                resolved_adapter="",
                resolved_metadata={},
                is_builtin=True,
                is_system_managed=defaults.get("is_system_managed", False),
                builtin_key=builtin_key,
            )

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "provider_type": row[2],
            "endpoint": row[3] or "",
            "api_key": row[4] or "",
            "resolved_adapter": row[5] or "",
            "resolved_metadata": self._load_metadata(row[6]),
            "is_builtin": bool(row[7]),
            "is_system_managed": bool(row[8]),
            "builtin_key": row[9] or "",
            "created_at": row[10],
            "updated_at": row[11],
        }

    def _repair_system_managed_provider(self, provider, defaults):
        if not defaults.get("is_system_managed"):
            return

        expected = {
            "name": defaults["name"],
            "provider_type": defaults["provider_type"],
            "endpoint": defaults["endpoint"],
            "api_key": defaults["api_key"],
            "is_builtin": True,
            "is_system_managed": True,
        }
        needs_repair = any(provider.get(key) != value for key, value in expected.items())
        if not needs_repair:
            return

        self.update(
            provider_id=provider["id"],
            name=defaults["name"],
            provider_type=defaults["provider_type"],
            endpoint=defaults["endpoint"],
            api_key=defaults["api_key"],
            resolved_adapter=provider.get("resolved_adapter", ""),
            resolved_metadata=provider.get("resolved_metadata", {}),
            is_builtin=True,
            is_system_managed=True,
            builtin_key=provider["builtin_key"],
        )

    def _migrate_legacy_cloud_providers(self):
        legacy_adapters = {
            "openai": "openai_compatible",
            "anthropic": "anthropic",
            "google": "google",
        }

        _, rows = self.db.execute(
            """
            SELECT id, provider_type, endpoint
            FROM providers
            WHERE provider_type IN ('openai', 'anthropic', 'google')
            """,
            fetchall=True,
        )

        for provider_id, provider_type, endpoint in rows:
            resolved_adapter = legacy_adapters.get(provider_type)
            resolved_metadata = self._dump_metadata(
                {
                    "migrated_from": provider_type,
                    "base_url": (endpoint or "").rstrip("/"),
                }
            )
            self.db.execute(
                """
                UPDATE providers
                SET provider_type = 'cloud',
                    resolved_adapter = ?,
                    resolved_metadata = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (resolved_adapter, resolved_metadata, provider_id),
            )
            self.db.execute(
                """
                UPDATE models
                SET provider = 'cloud',
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider_config_id = ?
                   OR (provider_config_id IS NULL AND provider = ?)
                """,
                (provider_id, provider_type),
            )
            self.db.execute(
                """
                UPDATE conversations
                SET provider = 'cloud',
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = ?
                   OR model_config_id IN (
                        SELECT id
                        FROM models
                        WHERE provider_config_id = ?
                    )
                """,
                (provider_type, provider_id),
            )

    def _dump_metadata(self, metadata):
        if not metadata:
            return ""
        return json.dumps(metadata, ensure_ascii=True, sort_keys=True)

    def _load_metadata(self, raw_value):
        normalized = str(raw_value or "").strip()
        if not normalized:
            return {}

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return {}

        return parsed if isinstance(parsed, dict) else {}
