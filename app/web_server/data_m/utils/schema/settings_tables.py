SETTINGS_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        provider_type TEXT NOT NULL,
        endpoint TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        resolved_adapter TEXT DEFAULT '',
        resolved_metadata TEXT DEFAULT '',
        is_builtin INTEGER DEFAULT 0,
        builtin_key TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS models_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        model_id TEXT NOT NULL,
        display_name TEXT,
        source TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        provider_config_id INTEGER,
        provider TEXT NOT NULL,
        icon_image TEXT DEFAULT '',
        endpoint TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        is_default INTEGER DEFAULT 0,
        is_builtin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider_config_id, name),
        FOREIGN KEY (provider_config_id) REFERENCES providers(id) ON DELETE SET NULL
    )
    """,
]
