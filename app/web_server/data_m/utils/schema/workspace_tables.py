WORKSPACE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS project_workspaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL UNIQUE,
        root_path TEXT NOT NULL,
        display_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'connected',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_indexed_at TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_file_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'file',
        size_bytes INTEGER NOT NULL DEFAULT 0,
        mtime REAL NOT NULL DEFAULT 0,
        language TEXT DEFAULT '',
        is_ignored INTEGER NOT NULL DEFAULT 0,
        indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES project_workspaces(id) ON DELETE CASCADE,
        UNIQUE(workspace_id, path)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workspace_file_index_workspace
    ON workspace_file_index(workspace_id, path)
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        project_id INTEGER NOT NULL,
        conversation_id INTEGER,
        message_id INTEGER,
        event_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        payload_json TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES project_workspaces(id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workspace_events_workspace
    ON workspace_events(workspace_id, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_command_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id INTEGER NOT NULL,
        conversation_id INTEGER,
        command TEXT NOT NULL,
        cwd TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        exit_code INTEGER,
        stdout TEXT DEFAULT '',
        stderr TEXT DEFAULT '',
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        FOREIGN KEY (workspace_id) REFERENCES project_workspaces(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
    )
    """,
]
