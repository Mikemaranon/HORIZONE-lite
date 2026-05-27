class ProjectModelsTable:
    def __init__(self, db):
        self.db = db

    def create(self, project_id, model_id, profile_id, nickname, system_prompt="", is_default=False):
        with self.db.transaction():
            should_be_default = bool(is_default) or not self.has_default(project_id)
            if should_be_default:
                self.clear_project_default(project_id)

            _, project_model_id = self.db.execute(
                """
                INSERT INTO project_models (
                    project_id, model_id, profile_id, nickname, system_prompt, is_default
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, model_id, profile_id, nickname, system_prompt, int(should_be_default)),
                lastrowid=True,
            )
        return project_model_id

    def get(self, project_model_id):
        _, row = self.db.execute(
            self._select_query("WHERE pm.id = ?"),
            (project_model_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def list_models(self, project_id):
        self.ensure_project_default(project_id)
        _, rows = self.db.execute(
            self._select_query(
                "WHERE pm.project_id = ? ORDER BY pm.is_default DESC, pm.updated_at DESC, pm.id DESC"
            ),
            (project_id,),
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def update(self, project_model_id, model_id, profile_id, nickname, system_prompt="", is_default=False):
        existing = self.get(project_model_id)
        if not existing:
            return

        with self.db.transaction():
            if is_default:
                self.clear_project_default(existing["project_id"])

            self.db.execute(
                """
                UPDATE project_models
                SET model_id = ?,
                    profile_id = ?,
                    nickname = ?,
                    system_prompt = ?,
                    is_default = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (model_id, profile_id, nickname, system_prompt, int(bool(is_default)), project_model_id),
            )
            self.ensure_project_default(existing["project_id"])

    def delete(self, project_model_id):
        existing = self.get(project_model_id)
        self.db.execute(
            "DELETE FROM project_models WHERE id = ?",
            (project_model_id,),
        )
        if existing:
            self.ensure_project_default(existing["project_id"])

    def ensure_default(self, project_id, model_id, profile_id, nickname, system_prompt=""):
        if not project_id or not model_id or not profile_id:
            return None

        existing = self.list_models(project_id)
        if existing:
            return existing[0]["id"]

        return self.create(project_id, model_id, profile_id, nickname, system_prompt, is_default=True)

    def set_default(self, project_model_id):
        existing = self.get(project_model_id)
        if not existing:
            return None

        with self.db.transaction():
            self.clear_project_default(existing["project_id"])
            self.db.execute(
                """
                UPDATE project_models
                SET is_default = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (project_model_id,),
            )
        return self.get(project_model_id)

    def clear_project_default(self, project_id):
        self.db.execute(
            "UPDATE project_models SET is_default = 0 WHERE project_id = ?",
            (project_id,),
        )

    def has_default(self, project_id):
        _, row = self.db.execute(
            """
            SELECT id
            FROM project_models
            WHERE project_id = ? AND is_default = 1
            LIMIT 1
            """,
            (project_id,),
            fetchone=True,
        )
        return bool(row)

    def ensure_project_default(self, project_id):
        if not project_id or self.has_default(project_id):
            return

        _, row = self.db.execute(
            """
            SELECT id
            FROM project_models
            WHERE project_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
            fetchone=True,
        )
        if row:
            self.set_default(row[0])

    def nickname_exists(self, project_id, nickname, excluded_project_model_id=None):
        params = [project_id, nickname]
        excluded_clause = ""
        if excluded_project_model_id:
            excluded_clause = " AND id != ?"
            params.append(excluded_project_model_id)

        _, row = self.db.execute(
            f"""
            SELECT id
            FROM project_models
            WHERE project_id = ? AND LOWER(nickname) = LOWER(?){excluded_clause}
            LIMIT 1
            """,
            tuple(params),
            fetchone=True,
        )
        return bool(row)

    def _select_query(self, clause):
        return f"""
            SELECT
                pm.id,
                pm.project_id,
                pm.model_id,
                pm.profile_id,
                pm.nickname,
                pm.system_prompt,
                pm.is_default,
                pm.created_at,
                pm.updated_at,
                m.name,
                m.display_name,
                m.provider_config_id,
                m.provider,
                m.icon_image,
                m.is_default,
                m.is_builtin,
                p.name,
                p.provider_type,
                p.is_builtin,
                pr.name,
                pr.personality,
                pr.is_default
            FROM project_models AS pm
            INNER JOIN models AS m
                ON m.id = pm.model_id
            LEFT JOIN providers AS p
                ON p.id = m.provider_config_id
            INNER JOIN profiles AS pr
                ON pr.id = pm.profile_id
            {clause}
        """

    def _serialize(self, row):
        if not row:
            return None

        model_label = row[10] or row[9]
        provider_name = row[16] or row[12]
        provider_type = row[17] or row[12]

        return {
            "id": row[0],
            "project_id": row[1],
            "model_id": row[2],
            "profile_id": row[3],
            "nickname": row[4],
            "system_prompt": row[5] or "",
            "is_default": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
            "model": {
                "id": row[2],
                "name": row[9],
                "display_name": model_label,
                "provider_id": row[11],
                "provider_config_id": row[11],
                "provider": row[12],
                "icon_image": row[13] or "",
                "is_default": bool(row[14]),
                "is_builtin": bool(row[15]),
                "provider_name": provider_name,
                "provider_type": provider_type,
                "provider_is_builtin": bool(row[18]) if row[18] is not None else False,
            },
            "profile": {
                "id": row[3],
                "name": row[19],
                "personality": row[20] or "",
                "is_default": bool(row[21]),
            },
        }
