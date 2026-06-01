from .chat_tables import CHAT_SCHEMA_STATEMENTS
from .core_tables import CORE_SCHEMA_STATEMENTS
from .migrations import SCHEMA_MIGRATIONS
from .project_tables import PROJECT_SCHEMA_STATEMENTS
from .settings_tables import SETTINGS_SCHEMA_STATEMENTS
from .tool_tables import TOOL_SCHEMA_STATEMENTS
from .workspace_tables import WORKSPACE_SCHEMA_STATEMENTS


class DatabaseSchemaInitializer:
    def __init__(self):
        self.schema_statements = (
            CORE_SCHEMA_STATEMENTS
            + PROJECT_SCHEMA_STATEMENTS
            + CHAT_SCHEMA_STATEMENTS
            + WORKSPACE_SCHEMA_STATEMENTS
            + SETTINGS_SCHEMA_STATEMENTS
            + TOOL_SCHEMA_STATEMENTS
        )
        self.migrations = SCHEMA_MIGRATIONS

    def initialize(self, database):
        for statement in self.schema_statements:
            database.execute(statement)

        for migration in self.migrations:
            self.ensure_column(
                database,
                migration.table_name,
                migration.column_name,
                migration.column_definition,
            )

        self.ensure_project_models_shape(database)
        self.ensure_project_model_defaults(database)

    def ensure_column(self, database, table_name, column_name, column_definition):
        _, rows = database.execute(
            f"PRAGMA table_info({table_name})",
            fetchall=True,
        )
        existing_columns = {row[1] for row in rows}

        if column_name in existing_columns:
            return

        database.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    def ensure_project_models_shape(self, database):
        _, rows = database.execute(
            "PRAGMA table_info(project_models)",
            fetchall=True,
        )
        columns = {row[1] for row in rows}
        if {"nickname", "profile_id"}.issubset(columns):
            return

        database.execute("ALTER TABLE project_models RENAME TO project_models_legacy")
        database.execute(
            """
            CREATE TABLE project_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                model_id INTEGER NOT NULL,
                profile_id INTEGER NOT NULL,
                nickname TEXT NOT NULL,
                color TEXT DEFAULT '#1c8b59',
                system_prompt TEXT DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                UNIQUE(project_id, nickname)
            )
            """
        )
        database.execute(
            """
            INSERT OR IGNORE INTO project_models (
                project_id, model_id, profile_id, nickname, color, system_prompt, is_default, created_at, updated_at
            )
            SELECT
                legacy.project_id,
                legacy.model_id,
                COALESCE(
                    (SELECT id FROM profiles WHERE is_default = 1 ORDER BY id ASC LIMIT 1),
                    (SELECT id FROM profiles ORDER BY id ASC LIMIT 1)
                ) AS profile_id,
                COALESCE(NULLIF(models.display_name, ''), models.name, 'model') AS nickname,
                '#1c8b59',
                '',
                0,
                legacy.created_at,
                legacy.updated_at
            FROM project_models_legacy AS legacy
            INNER JOIN models
                ON models.id = legacy.model_id
            WHERE EXISTS (SELECT 1 FROM profiles)
            """
        )
        database.execute("DROP TABLE project_models_legacy")
        database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_models_project
            ON project_models(project_id)
            """
        )

    def ensure_project_model_defaults(self, database):
        database.execute(
            """
            UPDATE project_models
            SET is_default = 0
            WHERE is_default = 1
                AND id NOT IN (
                    SELECT MIN(id)
                    FROM project_models
                    WHERE is_default = 1
                    GROUP BY project_id
                )
            """
        )
        database.execute(
            """
            UPDATE project_models
            SET is_default = 1
            WHERE id IN (
                SELECT MIN(id)
                FROM project_models
                GROUP BY project_id
                HAVING SUM(CASE WHEN is_default = 1 THEN 1 ELSE 0 END) = 0
            )
            """
        )
        database.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_models_one_default
            ON project_models(project_id)
            WHERE is_default = 1
            """
        )
