import sqlite3

from tests.test_support import IsolatedDatabaseTestCase

from data_m.utils.database import Database


class DatabaseSchemaTests(IsolatedDatabaseTestCase):
    def test_schema_migrations_are_versioned_and_hot_indexes_exist(self):
        database = Database()

        _, migration_rows = database.execute(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version ASC
            """,
            fetchall=True,
        )
        _, message_indexes = database.execute("PRAGMA index_list(messages)", fetchall=True)
        _, conversation_indexes = database.execute("PRAGMA index_list(conversations)", fetchall=True)
        _, model_indexes = database.execute("PRAGMA index_list(models)", fetchall=True)
        _, provider_indexes = database.execute("PRAGMA index_list(providers)", fetchall=True)
        _, runtime_catalog_columns = database.execute("PRAGMA table_info(runtime_model_catalog)", fetchall=True)
        _, runtime_download_columns = database.execute("PRAGMA table_info(runtime_model_downloads)", fetchall=True)

        migration_names = [row[1] for row in migration_rows]
        message_index_names = {index[1] for index in message_indexes}
        conversation_index_names = {index[1] for index in conversation_indexes}
        model_index_names = {index[1] for index in model_indexes}
        provider_index_names = {index[1] for index in provider_indexes}
        runtime_catalog_column_names = {column[1] for column in runtime_catalog_columns}
        runtime_download_column_names = {column[1] for column in runtime_download_columns}

        self.assertEqual(
            migration_names,
            [
                "legacy_column_backfills",
                "project_models_shape",
                "project_model_defaults",
                "chat_integrity_indexes",
                "hot_path_indexes",
                "llama_cpp_runtime_foundation",
                "message_reasoning_content",
                "user_avatar_image",
            ],
        )
        self.assertIn("idx_messages_conversation_position", message_index_names)
        self.assertIn("idx_conversations_project_updated", conversation_index_names)
        self.assertIn("idx_conversations_model_config", conversation_index_names)
        self.assertIn("idx_models_provider_config", model_index_names)
        self.assertIn("idx_models_provider_name", model_index_names)
        self.assertIn("idx_providers_provider_type", provider_index_names)
        self.assertIn("catalog_key", runtime_catalog_column_names)
        self.assertIn("checksum_sha256", runtime_catalog_column_names)
        self.assertIn("bytes_downloaded", runtime_download_column_names)
        self.assertIn("finished_at", runtime_download_column_names)

    def test_legacy_tables_receive_expected_columns_on_boot(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    system_prompt TEXT DEFAULT '',
                    temperature REAL DEFAULT 0.7,
                    top_p REAL DEFAULT 1.0,
                    max_tokens INTEGER DEFAULT 2048,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        database = Database()

        _, project_columns = database.execute("PRAGMA table_info(projects)", fetchall=True)
        _, project_document_columns = database.execute("PRAGMA table_info(project_documents)", fetchall=True)
        _, project_document_chunk_columns = database.execute("PRAGMA table_info(project_document_chunks)", fetchall=True)
        _, project_folder_columns = database.execute("PRAGMA table_info(project_document_folders)", fetchall=True)
        _, project_model_columns = database.execute("PRAGMA table_info(project_models)", fetchall=True)
        _, profile_columns = database.execute("PRAGMA table_info(profiles)", fetchall=True)
        _, model_columns = database.execute("PRAGMA table_info(models)", fetchall=True)
        _, conversation_columns = database.execute("PRAGMA table_info(conversations)", fetchall=True)
        _, message_columns = database.execute("PRAGMA table_info(messages)", fetchall=True)
        _, message_indexes = database.execute("PRAGMA index_list(messages)", fetchall=True)
        _, tool_columns = database.execute("PRAGMA table_info(tools)", fetchall=True)
        _, provider_columns = database.execute("PRAGMA table_info(providers)", fetchall=True)

        project_column_names = {column[1] for column in project_columns}
        project_document_column_names = {column[1] for column in project_document_columns}
        project_document_chunk_column_names = {column[1] for column in project_document_chunk_columns}
        project_folder_column_names = {column[1] for column in project_folder_columns}
        project_model_column_names = {column[1] for column in project_model_columns}
        profile_column_names = {column[1] for column in profile_columns}
        model_column_names = {column[1] for column in model_columns}
        conversation_column_names = {column[1] for column in conversation_columns}
        message_column_names = {column[1] for column in message_columns}
        message_index_names = {index[1] for index in message_indexes}
        tool_column_names = {column[1] for column in tool_columns}
        provider_column_names = {column[1] for column in provider_columns}

        self.assertIn("system_prompt", project_column_names)
        self.assertIn("folder_id", project_document_column_names)
        self.assertIn("document_id", project_document_chunk_column_names)
        self.assertIn("chunk_index", project_document_chunk_column_names)
        self.assertIn("text_content", project_document_chunk_column_names)
        self.assertIn("parent_folder_id", project_folder_column_names)
        self.assertIn("system_prompt", project_model_column_names)
        self.assertIn("is_default", project_model_column_names)
        self.assertIn("color", project_model_column_names)
        self.assertIn("personality", profile_column_names)
        self.assertIn("tags", profile_column_names)
        self.assertIn("display_name", model_column_names)
        self.assertIn("icon_image", model_column_names)
        self.assertIn("project_model_id", conversation_column_names)
        self.assertIn("quick_project_model_ids", conversation_column_names)
        self.assertIn("project_model_id", message_column_names)
        self.assertIn("project_model_name", message_column_names)
        self.assertIn("model_config_id", message_column_names)
        self.assertIn("model_name", message_column_names)
        self.assertIn("profile_id", message_column_names)
        self.assertIn("profile_name", message_column_names)
        self.assertIn("reasoning_content", message_column_names)
        self.assertIn("tool_events", message_column_names)
        self.assertIn("idx_messages_conversation_position", message_index_names)
        self.assertIn("display_name", tool_column_names)
        self.assertIn("is_system_managed", provider_column_names)

    def test_existing_migrated_database_receives_reasoning_content_column(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for version, name in [
                (1, "legacy_column_backfills"),
                (2, "project_models_shape"),
                (3, "project_model_defaults"),
                (4, "chat_integrity_indexes"),
                (5, "hot_path_indexes"),
                (6, "llama_cpp_runtime_foundation"),
            ]:
                connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
            connection.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    project_model_id INTEGER,
                    project_model_name TEXT DEFAULT '',
                    model_config_id INTEGER,
                    model_name TEXT DEFAULT '',
                    profile_id INTEGER,
                    profile_name TEXT DEFAULT '',
                    tool_events TEXT DEFAULT '',
                    provider_message_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        database = Database()

        _, message_columns = database.execute("PRAGMA table_info(messages)", fetchall=True)
        _, migration_rows = database.execute(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version ASC
            """,
            fetchall=True,
        )
        message_column_names = {column[1] for column in message_columns}
        migration_names = [row[1] for row in migration_rows]

        self.assertIn("reasoning_content", message_column_names)
        self.assertIn("message_reasoning_content", migration_names)

    def test_existing_migrated_database_receives_user_avatar_column(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for version, name in [
                (1, "legacy_column_backfills"),
                (2, "project_models_shape"),
                (3, "project_model_defaults"),
                (4, "chat_integrity_indexes"),
                (5, "hot_path_indexes"),
                (6, "llama_cpp_runtime_foundation"),
                (7, "message_reasoning_content"),
            ]:
                connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
            connection.execute(
                """
                CREATE TABLE users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    role TEXT DEFAULT 'user'
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        database = Database()

        _, user_columns = database.execute("PRAGMA table_info(users)", fetchall=True)
        _, migration_rows = database.execute(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version ASC
            """,
            fetchall=True,
        )
        user_column_names = {column[1] for column in user_columns}
        migration_names = [row[1] for row in migration_rows]

        self.assertIn("avatar_image", user_column_names)
        self.assertIn("user_avatar_image", migration_names)
