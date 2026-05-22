TOOL_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        display_name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        parameters TEXT DEFAULT '',
        filename TEXT NOT NULL UNIQUE,
        module_path TEXT DEFAULT '',
        is_active INTEGER DEFAULT 0,
        is_builtin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
]
