from .chat_tables import CHAT_SCHEMA_STATEMENTS
from .core_tables import CORE_SCHEMA_STATEMENTS
from .migrations import SCHEMA_MIGRATIONS, VERSIONED_SCHEMA_MIGRATIONS
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
        self.column_migrations = SCHEMA_MIGRATIONS
        self.versioned_migrations = VERSIONED_SCHEMA_MIGRATIONS

    def initialize(self, database):
        for statement in self.schema_statements:
            database.execute(statement)

        self.ensure_migrations_table(database)
        self.run_versioned_migrations(database)

    def ensure_migrations_table(self, database):
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def run_versioned_migrations(self, database):
        handlers = {
            "legacy_column_backfills": self.ensure_legacy_column_backfills,
            "project_models_shape": self.ensure_project_models_shape,
            "project_model_defaults": self.ensure_project_model_defaults,
            "chat_integrity_indexes": self.ensure_chat_integrity_indexes,
            "hot_path_indexes": self.ensure_hot_path_indexes,
            "llama_cpp_runtime_foundation": self.ensure_llama_cpp_runtime_foundation,
            "message_reasoning_content": self.ensure_message_reasoning_content,
        }

        for migration in self.versioned_migrations:
            if self.has_migration(database, migration.version):
                continue

            handler = handlers[migration.name]
            with database.transaction():
                handler(database)
                database.execute(
                    """
                    INSERT INTO schema_migrations (version, name)
                    VALUES (?, ?)
                    """,
                    (migration.version, migration.name),
                )

    def has_migration(self, database, version):
        _, row = database.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (version,),
            fetchone=True,
        )
        return row is not None

    def ensure_legacy_column_backfills(self, database):
        for migration in self.column_migrations:
            self.ensure_column(
                database,
                migration.table_name,
                migration.column_name,
                migration.column_definition,
            )

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

    def ensure_chat_integrity_indexes(self, database):
        database.execute(
            """
            UPDATE messages
            SET position = (
                SELECT COUNT(*) - 1
                FROM messages AS ordered
                WHERE ordered.conversation_id = messages.conversation_id
                    AND (
                        ordered.position < messages.position
                        OR (
                            ordered.position = messages.position
                            AND ordered.id <= messages.id
                        )
                    )
            )
            """
        )
        database.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conversation_position
            ON messages(conversation_id, position)
            """
        )
        database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
            ON messages(conversation_id, created_at)
            """
        )
        database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_project_updated
            ON conversations(project_id, updated_at)
            """
        )

    def ensure_hot_path_indexes(self, database):
        statements = [
            """
            CREATE INDEX IF NOT EXISTS idx_models_provider_config
            ON models(provider_config_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_models_provider_name
            ON models(provider, name)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_providers_provider_type
            ON providers(provider_type)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_model_config
            ON conversations(model_config_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workspace_command_runs_workspace
            ON workspace_command_runs(workspace_id, started_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workspace_events_project_created
            ON workspace_events(project_id, created_at)
            """,
        ]
        for statement in statements:
            database.execute(statement)

    def ensure_llama_cpp_runtime_foundation(self, database):
        self.ensure_column(
            database,
            "providers",
            "is_system_managed",
            "INTEGER DEFAULT 0",
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_model_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_key TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                provider_type TEXT NOT NULL DEFAULT 'llama_cpp',
                source_url TEXT NOT NULL,
                filename TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                checksum_sha256 TEXT DEFAULT '',
                architecture TEXT DEFAULT '',
                quantization TEXT DEFAULT '',
                context_length INTEGER DEFAULT 0,
                recommended_ram_gb INTEGER DEFAULT 0,
                license TEXT DEFAULT '',
                is_featured INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def ensure_message_reasoning_content(self, database):
        self.ensure_column(
            database,
            "messages",
            "reasoning_content",
            "TEXT DEFAULT ''",
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_model_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_key TEXT NOT NULL,
                model_config_id INTEGER,
                status TEXT NOT NULL,
                source_url TEXT NOT NULL,
                filename TEXT NOT NULL,
                local_path TEXT DEFAULT '',
                bytes_downloaded INTEGER DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY (model_config_id) REFERENCES models(id) ON DELETE SET NULL
            )
            """
        )
