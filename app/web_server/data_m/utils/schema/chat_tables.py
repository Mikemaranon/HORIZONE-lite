CHAT_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        personality TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        system_prompt TEXT DEFAULT '',
        temperature REAL DEFAULT 0.7,
        top_p REAL DEFAULT 1.0,
        max_tokens INTEGER DEFAULT 2048,
        is_default INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL DEFAULT 'New Chat',
        project_id INTEGER,
        project_model_id INTEGER,
        quick_project_model_ids TEXT DEFAULT '',
        profile_id INTEGER,
        model_config_id INTEGER,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
        FOREIGN KEY (project_model_id) REFERENCES project_models(id) ON DELETE SET NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL,
        FOREIGN KEY (model_config_id) REFERENCES models(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
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
        reasoning_content TEXT DEFAULT '',
        tool_events TEXT DEFAULT '',
        provider_message_id TEXT,
        elapsed_seconds INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
        FOREIGN KEY (project_model_id) REFERENCES project_models(id) ON DELETE SET NULL,
        FOREIGN KEY (model_config_id) REFERENCES models(id) ON DELETE SET NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
    )
    """,
]
