import json


class ToolsTable:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        *,
        name,
        display_name="",
        description="",
        parameters=None,
        filename="",
        module_path="",
        is_active=False,
        is_builtin=False,
    ):
        _, tool_id = self.db.execute(
            """
            INSERT INTO tools (
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                name,
                display_name,
                description,
                self._serialize_parameters(parameters),
                filename,
                module_path,
                int(bool(is_active)),
                int(bool(is_builtin)),
            ),
            lastrowid=True,
        )
        return tool_id

    def get(self, tool_id):
        _, row = self.db.execute(
            """
            SELECT
                id,
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                created_at,
                updated_at
            FROM tools
            WHERE id = ?
            """,
            (tool_id,),
            fetchone=True,
        )
        return self._serialize(row)

    def get_by_name(self, name):
        _, row = self.db.execute(
            """
            SELECT
                id,
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                created_at,
                updated_at
            FROM tools
            WHERE name = ?
            """,
            (name,),
            fetchone=True,
        )
        return self._serialize(row)

    def get_by_filename(self, filename):
        _, row = self.db.execute(
            """
            SELECT
                id,
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                created_at,
                updated_at
            FROM tools
            WHERE filename = ?
            """,
            (filename,),
            fetchone=True,
        )
        return self._serialize(row)

    def all(self):
        _, rows = self.db.execute(
            """
            SELECT
                id,
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                created_at,
                updated_at
            FROM tools
            ORDER BY is_builtin DESC, LOWER(COALESCE(NULLIF(display_name, ''), name)) ASC, name ASC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def active(self):
        _, rows = self.db.execute(
            """
            SELECT
                id,
                name,
                display_name,
                description,
                parameters,
                filename,
                module_path,
                is_active,
                is_builtin,
                created_at,
                updated_at
            FROM tools
            WHERE is_active = 1
            ORDER BY is_builtin DESC, LOWER(COALESCE(NULLIF(display_name, ''), name)) ASC, name ASC
            """,
            fetchall=True,
        )
        return [self._serialize(row) for row in rows]

    def upsert_discovered(
        self,
        *,
        name,
        display_name,
        description,
        parameters,
        filename,
        module_path,
        is_builtin,
        default_is_active=False,
    ):
        current = self.get_by_name(name) or self.get_by_filename(filename)
        if current:
            self.db.execute(
                """
                UPDATE tools
                SET name = ?,
                    display_name = ?,
                    description = ?,
                    parameters = ?,
                    filename = ?,
                    module_path = ?,
                    is_builtin = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    display_name,
                    description,
                    self._serialize_parameters(parameters),
                    filename,
                    module_path,
                    int(bool(is_builtin)),
                    current["id"],
                ),
            )
            return current["id"]

        return self.create(
            name=name,
            display_name=display_name,
            description=description,
            parameters=parameters,
            filename=filename,
            module_path=module_path,
            is_active=default_is_active,
            is_builtin=is_builtin,
        )

    def set_active(self, tool_id, is_active):
        self.db.execute(
            """
            UPDATE tools
            SET is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(bool(is_active)), tool_id),
        )

    def delete(self, tool_id):
        self.db.execute(
            "DELETE FROM tools WHERE id = ?",
            (tool_id,),
        )

    def _serialize(self, row):
        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2] or row[1],
            "description": row[3],
            "parameters": self._parse_parameters(row[4]),
            "filename": row[5],
            "module_path": row[6],
            "is_active": bool(row[7]),
            "is_builtin": bool(row[8]),
            "created_at": row[9],
            "updated_at": row[10],
        }

    def _parse_parameters(self, raw_value):
        if not raw_value:
            return {}

        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}

        return value if isinstance(value, dict) else {}

    def _serialize_parameters(self, parameters):
        normalized = parameters if isinstance(parameters, dict) else {}
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
