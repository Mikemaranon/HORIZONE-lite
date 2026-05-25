from api_m.services import (
    ChatContextBuilder,
    ChatExportService,
    ChatPersistenceService,
    ChatService,
    ChatStreamService,
    DocumentIngestionService,
    ProjectContextRetrievalService,
    ProjectDocumentService,
    ProjectService,
    WorkspaceService,
)
from tool_m import ToolExecutor, ToolLoader, ToolManager, ToolRegistry
from tool_m import WorkspaceToolProvider


class ServiceRegistry:
    def __init__(
        self,
        *,
        config_manager,
        db_manager,
        user_manager,
        model_manager,
    ):
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.user_manager = user_manager
        self.model_manager = model_manager

        self.tool_loader = ToolLoader()
        self.tool_registry = ToolRegistry(
            db_manager,
            self.tool_loader,
            default_is_active=False,
        )
        self.tool_executor = ToolExecutor(db_manager)
        self.workspace_service = WorkspaceService(db_manager)
        self.workspace_tool_provider = WorkspaceToolProvider(self.workspace_service)
        self.tool_manager = ToolManager(
            db_manager=db_manager,
            model_manager=model_manager,
            tool_loader=self.tool_loader,
            tool_registry=self.tool_registry,
            tool_executor=self.tool_executor,
            workspace_tool_provider=self.workspace_tool_provider,
        )

        self.document_ingestion_service = DocumentIngestionService()
        self.project_context_retrieval_service = ProjectContextRetrievalService(
            db_manager,
            ingestion_service=self.document_ingestion_service,
        )
        self.chat_context_builder = ChatContextBuilder(
            db_manager,
            project_context_retrieval_service=self.project_context_retrieval_service,
        )
        self.chat_export_service = ChatExportService(
            db_manager,
            self.chat_context_builder,
        )
        self.chat_persistence_service = ChatPersistenceService(
            db_manager,
            model_manager,
        )
        self.chat_stream_service = ChatStreamService(
            db_manager,
            model_manager,
            self.chat_persistence_service,
            tool_manager=self.tool_manager,
        )
        self.chat_service = ChatService(
            db_manager,
            model_manager,
            self.chat_context_builder,
            self.chat_persistence_service,
            self.chat_stream_service,
            tool_manager=self.tool_manager,
        )

        self.project_service = ProjectService(db_manager)
        self.project_document_service = ProjectDocumentService(
            db_manager,
            ingestion_service=self.document_ingestion_service,
        )
