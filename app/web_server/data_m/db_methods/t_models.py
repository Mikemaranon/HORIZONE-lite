import platform


class ModelsTable:
    BUILTIN_MODEL_NAME_UPGRADES = {
        ("mlx", "gemma-3-4b-it-4bit"): "mlx-community/gemma-3-4b-it-4bit",
    }

    def __init__(self, db):
        self.db = db

    def create(
        self,
        name,
        provider_config_id,
        display_name="",
        icon_image="",
        is_default=False,
        is_builtin=False,
    ):
        normalized_display_name = self._normalize_display_name(display_name, name)
        provider = self._require_provider(provider_config_id)
        _, model_id = self.db.execute(
            """
            INSERT INTO models (
                name, display_name, provider_config_id, provider, icon_image, endpoint, api_key, is_default, is_builtin
            )
            VALUES (?, ?, ?, ?, ?, '', '', ?, ?)
            """,
            (
                name,
                normalized_display_name,
                provider_config_id,
                provider["provider_type"],
                icon_image,
                int(is_default),
                int(is_builtin),
            ),
            lastrowid=True,
        )

        if is_default:
            self.set_default(model_id)

        return model_id

    def get(self, model_id):
        _, row = self.db.execute(
            """
            SELECT m.id, m.name, m.display_name, m.provider_config_id, m.provider, m.icon_image, m.is_default, m.is_builtin,
                   m.created_at, m.updated_at,
                   p.name, p.provider_type, p.is_builtin
            FROM models AS m
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            WHERE m.id = ?
            """,
            (model_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def get_default(self):
        _, row = self.db.execute(
            """
            SELECT m.id, m.name, m.display_name, m.provider_config_id, m.provider, m.icon_image, m.is_default, m.is_builtin,
                   m.created_at, m.updated_at,
                   p.name, p.provider_type, p.is_builtin
            FROM models AS m
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            WHERE m.is_default = 1
            ORDER BY m.id ASC
            LIMIT 1
            """,
            fetchone=True,
        )
        return self._serialize(row)

    def get_by_provider_and_name(self, provider, name):
        _, row = self.db.execute(
            """
            SELECT m.id, m.name, m.display_name, m.provider_config_id, m.provider, m.icon_image, m.is_default, m.is_builtin,
                   m.created_at, m.updated_at,
                   p.name, p.provider_type, p.is_builtin
            FROM models AS m
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            WHERE m.provider = ? AND m.name = ?
            ORDER BY m.id ASC
            LIMIT 1
            """,
            (provider, name),
            fetchone=True,
        )
        return self._serialize(row)

    def get_by_id_and_provider_type(self, model_id, provider_type):
        _, row = self.db.execute(
            """
            SELECT m.id, m.name, m.display_name, m.provider_config_id, m.provider, m.icon_image, m.is_default, m.is_builtin,
                   m.created_at, m.updated_at,
                   p.name, p.provider_type, p.is_builtin
            FROM models AS m
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            WHERE m.id = ? AND m.provider = ?
            LIMIT 1
            """,
            (model_id, provider_type),
            fetchone=True,
        )
        return self._serialize(row)

    def all(self):
        _, rows = self.db.execute(
            """
            SELECT m.id, m.name, m.display_name, m.provider_config_id, m.provider, m.icon_image, m.is_default, m.is_builtin,
                   m.created_at, m.updated_at,
                   p.name, p.provider_type, p.is_builtin
            FROM models AS m
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            ORDER BY m.is_default DESC, m.is_builtin DESC, m.updated_at DESC, m.id DESC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def update(
        self,
        model_id,
        name,
        provider_config_id,
        display_name="",
        icon_image="",
        is_default=False,
        is_builtin=False,
    ):
        normalized_display_name = self._normalize_display_name(display_name, name)
        provider = self._require_provider(provider_config_id)
        self.db.execute(
            """
            UPDATE models
            SET name = ?,
                display_name = ?,
                provider_config_id = ?,
                provider = ?,
                icon_image = ?,
                is_default = ?,
                is_builtin = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name,
                normalized_display_name,
                provider_config_id,
                provider["provider_type"],
                icon_image,
                int(is_default),
                int(is_builtin),
                model_id,
            ),
        )

        if is_default:
            self.set_default(model_id)

    def set_default(self, model_id):
        self.db.execute("UPDATE models SET is_default = 0")
        self.db.execute(
            """
            UPDATE models
            SET is_default = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (model_id,),
        )

    def count(self):
        _, row = self.db.execute(
            "SELECT COUNT(*) FROM models",
            fetchone=True,
        )
        return row[0] if row else 0

    def count_for_provider(self, provider_config_id):
        _, row = self.db.execute(
            "SELECT COUNT(*) FROM models WHERE provider_config_id = ?",
            (provider_config_id,),
            fetchone=True,
        )
        return row[0] if row else 0

    def delete(self, model_id):
        with self.db.transaction():
            _, row = self.db.execute(
                """
                SELECT m.id, m.name, m.provider
                FROM models AS m
                WHERE m.id != ?
                ORDER BY m.is_default DESC, m.is_builtin DESC, m.updated_at DESC, m.id DESC
                LIMIT 1
                """,
                (model_id,),
                fetchone=True,
            )
            fallback = row if row else None

            if fallback:
                self.db.execute(
                    """
                    UPDATE conversations
                    SET model_config_id = ?,
                        provider = ?,
                        model = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE model_config_id = ?
                    """,
                    (fallback[0], fallback[2], fallback[1], model_id),
                )

            self.db.execute(
                "DELETE FROM models WHERE id = ?",
                (model_id,),
            )

            if fallback and not self.get_default():
                self.set_default(fallback[0])

    def sync_provider_snapshot(self, provider_config_id):
        provider = self._require_provider(provider_config_id)
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE models
                SET provider = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider_config_id = ?
                """,
                (provider["provider_type"], provider_config_id),
            )
            self.db.execute(
                """
                UPDATE conversations
                SET provider = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE model_config_id IN (
                    SELECT id
                    FROM models
                    WHERE provider_config_id = ?
                )
                """,
                (provider["provider_type"], provider_config_id),
            )

    def ensure_seed_models(self):
        self._upgrade_builtin_model_names()
        self._backfill_display_names()
        self._sync_message_model_labels()
        existing_models = self.all()
        if existing_models:
            if not self.get_default():
                self.set_default(existing_models[0]["id"])
            return

        is_apple = platform.system().lower() == "darwin"
        created_ids = []
        mlx_provider = self._get_provider_by_builtin_key("mlx")
        ollama_provider = self._get_provider_by_builtin_key("ollama")

        if is_apple and mlx_provider:
            created_ids.append(
                self.create(
                    name="mlx-community/gemma-3-4b-it-4bit",
                    display_name="gemma-3",
                    provider_config_id=mlx_provider["id"],
                    is_default=True,
                    is_builtin=True,
                )
            )

        if ollama_provider:
            created_ids.append(
                self.create(
                    name="llama3.2",
                    display_name="llama3.2",
                    provider_config_id=ollama_provider["id"],
                    is_default=not is_apple,
                    is_builtin=True,
                )
            )

        if not self.get_default() and created_ids:
            self.set_default(created_ids[0])

    def _upgrade_builtin_model_names(self):
        for (provider, old_name), new_name in self.BUILTIN_MODEL_NAME_UPGRADES.items():
            old_model = self.get_by_provider_and_name(provider, old_name)
            if not old_model:
                continue

            canonical_model = self.get_by_provider_and_name(provider, new_name)
            if canonical_model and canonical_model["id"] != old_model["id"]:
                self.db.execute(
                    """
                    UPDATE conversations
                    SET model_config_id = ?,
                        model = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE model_config_id = ?
                    """,
                    (canonical_model["id"], new_name, old_model["id"]),
                )
                self.db.execute(
                    """
                    UPDATE messages
                    SET model_config_id = ?,
                        model_name = ?
                    WHERE model_config_id = ?
                    """,
                    (canonical_model["id"], new_name, old_model["id"]),
                )
                self.delete(old_model["id"])
            else:
                self.db.execute(
                    """
                    UPDATE models
                    SET name = ?,
                        display_name = CASE
                            WHEN COALESCE(TRIM(display_name), '') = '' OR display_name = ?
                                THEN ?
                            ELSE display_name
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_name, old_name, self._default_display_name_for_model(provider, new_name), old_model["id"]),
                )

            self.db.execute(
                """
                UPDATE conversations
                SET model = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = ? AND model = ?
                """,
                (new_name, provider, old_name),
            )
            self.db.execute(
                """
                UPDATE messages
                SET model_name = ?
                WHERE model_name = ?
                """,
                (new_name, old_name),
            )

    def _backfill_display_names(self):
        self.db.execute(
            """
            UPDATE models
            SET display_name = name,
                updated_at = CURRENT_TIMESTAMP
            WHERE COALESCE(TRIM(display_name), '') = ''
            """
        )

        for (provider, technical_name), preferred_display_name in self._builtin_display_name_upgrades().items():
            self.db.execute(
                """
                UPDATE models
                SET display_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = ?
                  AND name = ?
                  AND (
                    COALESCE(TRIM(display_name), '') = ''
                    OR display_name = name
                  )
                """,
                (preferred_display_name, provider, technical_name),
            )

    def _builtin_display_name_upgrades(self):
        return {
            ("mlx", "mlx-community/gemma-3-4b-it-4bit"): "gemma-3",
        }

    def _default_display_name_for_model(self, provider, technical_name):
        return self._builtin_display_name_upgrades().get(
            (provider, technical_name),
            technical_name,
        )

    def _sync_message_model_labels(self):
        self.db.execute(
            """
            UPDATE messages
            SET model_name = (
                SELECT COALESCE(NULLIF(TRIM(models.display_name), ''), models.name)
                FROM models
                WHERE models.id = messages.model_config_id
            )
            WHERE model_config_id IS NOT NULL
              AND (
                COALESCE(TRIM(model_name), '') = ''
                OR model_name = (
                    SELECT models.name
                    FROM models
                    WHERE models.id = messages.model_config_id
                )
              )
            """
        )

    def _normalize_display_name(self, display_name, technical_name):
        normalized = str(display_name or "").strip()
        if normalized:
            return normalized
        return str(technical_name or "").strip()

    def _require_provider(self, provider_config_id):
        _, row = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, is_builtin, builtin_key,
                   resolved_adapter, resolved_metadata, created_at, updated_at
            FROM providers
            WHERE id = ?
            """,
            (provider_config_id,),
            fetchone=True,
        )
        provider = self._serialize_provider(row)
        if not provider:
            raise ValueError("Provider not found")
        return provider

    def _get_provider_by_builtin_key(self, builtin_key):
        _, row = self.db.execute(
            """
            SELECT id, name, provider_type, endpoint, api_key, is_builtin, builtin_key,
                   resolved_adapter, resolved_metadata, created_at, updated_at
            FROM providers
            WHERE builtin_key = ?
            LIMIT 1
            """,
            (builtin_key,),
            fetchone=True,
        )
        return self._serialize_provider(row)

    def _serialize(self, row):
        if not row:
            return None

        provider_name = row[10] or row[4]
        provider_type = row[11] or row[4]
        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2] or row[1],
            "provider_id": row[3],
            "provider": provider_type,
            "icon_image": row[5] or "",
            "provider_name": provider_name,
            "provider_type": provider_type,
            "is_default": bool(row[6]),
            "is_builtin": bool(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }

    def _serialize_provider(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "provider_type": row[2],
            "endpoint": row[3] or "",
            "api_key": row[4] or "",
            "is_builtin": bool(row[5]),
            "builtin_key": row[6] or "",
            "resolved_adapter": row[7] or "",
            "resolved_metadata": row[8] or "",
            "created_at": row[9],
            "updated_at": row[10],
        }
