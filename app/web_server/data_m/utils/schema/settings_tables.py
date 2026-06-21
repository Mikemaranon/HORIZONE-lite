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
        is_system_managed INTEGER DEFAULT 0,
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
        reasoning_mode TEXT NOT NULL DEFAULT 'auto',
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
    """,
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
    """,
]
