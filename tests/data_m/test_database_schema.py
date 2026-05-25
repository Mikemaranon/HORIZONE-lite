import sqlite3

from tests.test_support import IsolatedDatabaseTestCase

from data_m.utils.database import Database


class DatabaseSchemaTests(IsolatedDatabaseTestCase):
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
        _, profile_columns = database.execute("PRAGMA table_info(profiles)", fetchall=True)
        _, model_columns = database.execute("PRAGMA table_info(models)", fetchall=True)
        _, message_columns = database.execute("PRAGMA table_info(messages)", fetchall=True)
        _, tool_columns = database.execute("PRAGMA table_info(tools)", fetchall=True)

        project_column_names = {column[1] for column in project_columns}
        project_document_column_names = {column[1] for column in project_document_columns}
        project_document_chunk_column_names = {column[1] for column in project_document_chunk_columns}
        project_folder_column_names = {column[1] for column in project_folder_columns}
        profile_column_names = {column[1] for column in profile_columns}
        model_column_names = {column[1] for column in model_columns}
        message_column_names = {column[1] for column in message_columns}
        tool_column_names = {column[1] for column in tool_columns}

        self.assertIn("system_prompt", project_column_names)
        self.assertIn("folder_id", project_document_column_names)
        self.assertIn("document_id", project_document_chunk_column_names)
        self.assertIn("chunk_index", project_document_chunk_column_names)
        self.assertIn("text_content", project_document_chunk_column_names)
        self.assertIn("parent_folder_id", project_folder_column_names)
        self.assertIn("personality", profile_column_names)
        self.assertIn("tags", profile_column_names)
        self.assertIn("display_name", model_column_names)
        self.assertIn("icon_image", model_column_names)
        self.assertIn("model_config_id", message_column_names)
        self.assertIn("model_name", message_column_names)
        self.assertIn("profile_id", message_column_names)
        self.assertIn("profile_name", message_column_names)
        self.assertIn("tool_events", message_column_names)
        self.assertIn("display_name", tool_column_names)
