# db_manager.py

from .utils import Database, LogRepository
from .db_methods import (
    UsersTable,
    SessionsTable,
    AgentLogsTable,
    ProjectsTable,
    ProjectDocumentFoldersTable,
    ProjectDocumentChunksTable,
    ProjectDocumentsTable,
    ProfilesTable,
    ProvidersTable,
    ConversationsTable,
    MessagesTable,
    ModelsTable,
    SettingsTable,
    ModelsCacheTable,
    ToolsTable,
)

class DBManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "initialized") and self.initialized:
            return

        self.db = Database()
        self.logger = LogRepository()

        # Export table interfaces
        self.users = UsersTable(self.db)
        self.sessions = SessionsTable(self.db)
        self.agent_logs = AgentLogsTable(self.db)
        self.projects = ProjectsTable(self.db)
        self.project_document_folders = ProjectDocumentFoldersTable(self.db)
        self.project_document_chunks = ProjectDocumentChunksTable(self.db)
        self.project_documents = ProjectDocumentsTable(self.db)
        self.profiles = ProfilesTable(self.db)
        self.providers = ProvidersTable(self.db)
        self.conversations = ConversationsTable(self.db)
        self.messages = MessagesTable(self.db)
        self.models = ModelsTable(self.db)
        self.settings = SettingsTable(self.db)
        self.models_cache = ModelsCacheTable(self.db)
        self.tools = ToolsTable(self.db)

        self._ensure_defaults()

        self.initialized = True

    # Generic wrapper for execute with logging
    def execute(
        self,
        query,
        params=(),
        *,
        fetchone=False,
        fetchall=False,
        lastrowid=False
    ):
        op, data = self.db.execute(
            query,
            params,
            fetchone=fetchone,
            fetchall=fetchall,
            lastrowid=lastrowid
        )

        # Secure logging: avoid logging data_logs operations to prevent recursion
        if op in ("INSERT", "UPDATE", "DELETE") and "data_logs" not in query.lower():
            self.logger.log(
                level="INFO",
                source="DBManager",
                message=f"{op} executed",
                payload={"query": query, "params": params}
            )

        return data

    def _ensure_defaults(self):
        default_profile = self.profiles.get_default()
        self.providers.ensure_seed_providers()
        if default_profile:
            self.models.ensure_seed_models()
            return

        self.profiles.create(
            name="Default Assistant",
            system_prompt="You are a helpful local-first AI assistant.",
            temperature=0.7,
            top_p=1.0,
            max_tokens=2048,
            is_default=True,
        )
        self.models.ensure_seed_models()
