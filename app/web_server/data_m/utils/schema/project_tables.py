PROJECT_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        system_prompt TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_document_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        parent_folder_id INTEGER,
        name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_folder_id) REFERENCES project_document_folders(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        folder_id INTEGER,
        filename TEXT NOT NULL,
        content_type TEXT,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        text_content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (folder_id) REFERENCES project_document_folders(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_document_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        document_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        text_content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES project_documents(id) ON DELETE CASCADE,
        UNIQUE(document_id, chunk_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_document_chunks_project
    ON project_document_chunks(project_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_document_chunks_document
    ON project_document_chunks(document_id, chunk_index)
    """,
]
