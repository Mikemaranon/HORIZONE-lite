from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnMigration:
    table_name: str
    column_name: str
    column_definition: str


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str


SCHEMA_MIGRATIONS = [
    ColumnMigration("projects", "system_prompt", "TEXT DEFAULT ''"),
    ColumnMigration("profiles", "personality", "TEXT DEFAULT ''"),
    ColumnMigration("profiles", "tags", "TEXT DEFAULT ''"),
    ColumnMigration("conversations", "project_model_id", "INTEGER"),
    ColumnMigration("conversations", "quick_project_model_ids", "TEXT DEFAULT ''"),
    ColumnMigration("conversations", "model_config_id", "INTEGER"),
    ColumnMigration("models", "provider_config_id", "INTEGER"),
    ColumnMigration("models", "display_name", "TEXT DEFAULT ''"),
    ColumnMigration("models", "icon_image", "TEXT DEFAULT ''"),
    ColumnMigration("messages", "model_config_id", "INTEGER"),
    ColumnMigration("messages", "model_name", "TEXT DEFAULT ''"),
    ColumnMigration("messages", "project_model_id", "INTEGER"),
    ColumnMigration("messages", "project_model_name", "TEXT DEFAULT ''"),
    ColumnMigration("messages", "profile_id", "INTEGER"),
    ColumnMigration("messages", "profile_name", "TEXT DEFAULT ''"),
    ColumnMigration("messages", "tool_events", "TEXT DEFAULT ''"),
    ColumnMigration("providers", "resolved_adapter", "TEXT DEFAULT ''"),
    ColumnMigration("providers", "resolved_metadata", "TEXT DEFAULT ''"),
    ColumnMigration("providers", "is_system_managed", "INTEGER DEFAULT 0"),
    ColumnMigration("tools", "display_name", "TEXT DEFAULT ''"),
    ColumnMigration("project_documents", "folder_id", "INTEGER"),
    ColumnMigration("project_models", "color", "TEXT DEFAULT '#1c8b59'"),
    ColumnMigration("project_models", "system_prompt", "TEXT DEFAULT ''"),
    ColumnMigration("project_models", "is_default", "INTEGER NOT NULL DEFAULT 0"),
]


VERSIONED_SCHEMA_MIGRATIONS = [
    SchemaMigration(1, "legacy_column_backfills"),
    SchemaMigration(2, "project_models_shape"),
    SchemaMigration(3, "project_model_defaults"),
    SchemaMigration(4, "chat_integrity_indexes"),
    SchemaMigration(5, "hot_path_indexes"),
    SchemaMigration(6, "llama_cpp_runtime_foundation"),
]
