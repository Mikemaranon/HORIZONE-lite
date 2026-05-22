from .chat_tables import CHAT_SCHEMA_STATEMENTS
from .core_tables import CORE_SCHEMA_STATEMENTS
from .migrations import SCHEMA_MIGRATIONS
from .project_tables import PROJECT_SCHEMA_STATEMENTS
from .settings_tables import SETTINGS_SCHEMA_STATEMENTS
from .tool_tables import TOOL_SCHEMA_STATEMENTS


class DatabaseSchemaInitializer:
    def __init__(self):
        self.schema_statements = (
            CORE_SCHEMA_STATEMENTS
            + PROJECT_SCHEMA_STATEMENTS
            + CHAT_SCHEMA_STATEMENTS
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
