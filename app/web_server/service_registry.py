from api_m.services import (
    ChatContextBuilder,
    ChatExecutor,
    ChatExportService,
    ChatPersistenceService,
    ChatRequestPreparer,
    ChatService,
    ChatStreamService,
    ConversationService,
    DocumentIngestionService,
    ModelConfigService,
    ProjectContextRetrievalService,
    ProjectDocumentService,
    ProjectService,
    ProfileService,
    ProviderConfigService,
    NativeDirectoryPickerService,
    SourceAttributionService,
    WorkspaceService,
)
from tool_m import ToolExecutor, ToolLoader, ToolManager, ToolRegistry
from tool_m import WorkspaceToolProvider
from runtime_m import RuntimeModelCatalogService, RuntimeModelDownloadService


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
            tool_manager=self.tool_manager,
        )
        self.conversation_service = ConversationService(
            db_manager,
            config_manager,
            export_service=self.chat_export_service,
        )
        self.model_config_service = ModelConfigService(
            db_manager,
            runtime_config=config_manager.runtime,
        )
        self.runtime_model_catalog_service = RuntimeModelCatalogService(
            db_manager=db_manager,
        )
        self.runtime_model_download_service = RuntimeModelDownloadService(
            db_manager=db_manager,
            catalog_service=self.runtime_model_catalog_service,
            runtime_config=config_manager.runtime,
        )
        self.provider_config_service = ProviderConfigService(
            db_manager,
            model_manager,
        )
        self.profile_service = ProfileService(db_manager)
        self.chat_persistence_service = ChatPersistenceService(
            db_manager,
            model_manager,
        )
        self.chat_executor = ChatExecutor(
            model_manager,
            tool_manager=self.tool_manager,
        )
        self.chat_stream_service = ChatStreamService(
            db_manager,
            model_manager,
            self.chat_persistence_service,
            tool_manager=self.tool_manager,
            executor=self.chat_executor,
        )
        self.chat_request_preparer = ChatRequestPreparer(
            db_manager,
            self.chat_context_builder,
            request_id_resolver=self.chat_stream_service.resolve_request_id,
        )
        self.source_attribution_service = SourceAttributionService(db_manager)
        self.chat_service = ChatService(
            db_manager,
            model_manager,
            self.chat_context_builder,
            self.chat_persistence_service,
            self.chat_stream_service,
            tool_manager=self.tool_manager,
            source_attribution_service=self.source_attribution_service,
            request_preparer=self.chat_request_preparer,
            executor=self.chat_executor,
        )

        self.project_service = ProjectService(db_manager)
        self.native_directory_picker = NativeDirectoryPickerService()
        self.project_document_service = ProjectDocumentService(
            db_manager,
            ingestion_service=self.document_ingestion_service,
        )
