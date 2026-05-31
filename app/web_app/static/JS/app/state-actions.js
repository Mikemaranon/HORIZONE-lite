import { state } from "./state.js";


export function setWorkspaceMode(mode) {
    state.workspaceMode = mode;
}


export function setActiveProjectId(projectId) {
    state.activeProjectId = projectId || null;
}


export function setActiveConversationId(conversationId) {
    state.activeConversationId = conversationId || null;
}


export function setActiveConversation(conversation) {
    state.activeConversation = conversation || null;
}


export function patchActiveConversation(fields = {}) {
    if (!state.activeConversation) {
        state.activeConversation = { ...fields };
        return;
    }

    state.activeConversation = {
        ...state.activeConversation,
        ...fields,
    };
}


export function setActiveMessages(messages = []) {
    state.activeMessages = messages;
}


export function setConversationTitleEditMode(isEditing, draft = "") {
    state.isEditingConversationTitle = Boolean(isEditing);
    state.conversationTitleDraft = draft;
}


export function setConversationTitleDraft(draft = "") {
    state.conversationTitleDraft = draft;
}


export function clearActiveConversation() {
    setActiveConversationId(null);
    setActiveConversation(null);
    setActiveMessages([]);
    setConversationTitleEditMode(false);
}


export function setPendingProfileId(profileId) {
    state.pendingProfileId = profileId || null;
}


export function setPendingModelConfigId(modelConfigId) {
    state.pendingModelConfigId = modelConfigId || null;
}


export function setPendingProjectModelId(projectModelId) {
    state.pendingProjectModelId = projectModelId || null;
}


export function setSelectedSettingsProviderId(providerId) {
    state.selectedSettingsProviderId = providerId || null;
}


export function setSelectedSettingsProfileId(profileId) {
    state.selectedSettingsProfileId = profileId || null;
}


export function setSelectedSettingsModelId(modelConfigId) {
    state.selectedSettingsModelId = modelConfigId || null;
}


export function setProviderModalState({ mode, providerId = null }) {
    state.providerModalMode = mode;
    state.providerModalProviderId = providerId;
}


export function setProfileModalState({ mode, profileId = null, context = "settings" }) {
    state.profileModalMode = mode;
    state.profileModalProfileId = profileId;
    state.profileModalContext = context;
}


export function setModelModalState({ mode, modelId = null, context = "settings" }) {
    state.modelModalMode = mode;
    state.modelModalModelId = modelId;
    state.modelModalContext = context;
}


export function setToolsShowActiveOnly(isActiveOnly) {
    state.toolsShowActiveOnly = Boolean(isActiveOnly);
}


export function setProjectDocuments(documents = []) {
    state.projectDocuments = documents;
}


export function setProjectDocumentFolders(folders = []) {
    state.projectDocumentFolders = folders;
}


export function setProjectModels(models = [], usesDefault = true) {
    state.projectModels = models || [];
    state.projectModelsUseDefault = Boolean(usesDefault);
}


export function setProjectModelFormState({ mode = "create", projectModelId = null } = {}) {
    state.projectModelFormMode = mode;
    state.projectModelFormId = projectModelId;
}


export function setProjectWorkspace(workspace = null, fileCount = 0, recentEvents = []) {
    state.projectWorkspace = workspace;
    state.projectWorkspaceFileCount = fileCount || 0;
    state.projectWorkspaceEvents = recentEvents || [];
}


export function setProjectWorkspaceFiles(files = []) {
    state.projectWorkspaceFiles = files;
}


export function setActiveProjectDocumentFolderId(folderId = null) {
    state.activeProjectDocumentFolderId = folderId ?? null;
}


export function setStagedDocuments(documents = []) {
    state.stagedDocuments = documents;
}

export function setActiveGenerationRequestId(requestId = null) {
    state.activeGenerationRequestId = requestId || null;
}


export function setGenerationStopRequested(isRequested) {
    state.generationStopRequested = Boolean(isRequested);
}


export function setChatPanelOpen(isOpen) {
    state.isChatPanelOpen = Boolean(isOpen);
}


export function applyProjectsPayload(data) {
    state.projects = data.projects || [];

    if (state.activeProjectId && !state.projects.some((project) => project.id === state.activeProjectId)) {
        state.activeProjectId = null;
        state.projectDocuments = [];
        state.projectDocumentFolders = [];
        setProjectModels();
        setProjectWorkspace(null);
        setProjectWorkspaceFiles([]);
        state.activeProjectDocumentFolderId = null;
    }
}


export function applyProvidersPayload(data) {
    state.providers = data.providers || [];
}


export function applyProfilesPayload(data) {
    state.profiles = data.profiles || [];
}


export function applyProjectDocumentsPayload(data) {
    state.projectDocuments = data.documents || [];
    state.projectDocumentFolders = data.folders || [];

    if (
        state.activeProjectDocumentFolderId
        && !state.projectDocumentFolders.some((folder) => folder.id === state.activeProjectDocumentFolderId)
    ) {
        state.activeProjectDocumentFolderId = null;
    }
}


export function applyProjectModelsPayload(data) {
    setProjectModels(data.models || [], data.uses_default !== false);
    if (
        state.pendingProjectModelId
        && !state.projectModels.some((agent) => agent.id === Number(state.pendingProjectModelId))
    ) {
        state.pendingProjectModelId = null;
    }
}


export function applyProjectWorkspacePayload(data) {
    setProjectWorkspace(data.workspace || null, data.file_count || 0, data.recent_events || []);
    if (!data.workspace) {
        setProjectWorkspaceFiles([]);
    }
}


export function applyWorkspaceFilesPayload(data) {
    setProjectWorkspaceFiles(data.files || []);
    if (data.workspace) {
        state.projectWorkspace = data.workspace;
    }
    if (Number.isFinite(data.file_count)) {
        state.projectWorkspaceFileCount = data.file_count;
    }
}


export function applyConversationsPayload(data) {
    state.conversations = (data.conversations || []).map(enrichConversationModelConfig);

    if (!state.activeConversationId) {
        return;
    }

    const matchingConversation = state.conversations.find(
        (conversation) => conversation.id === state.activeConversationId
    );

    if (!matchingConversation) {
        clearActiveConversation();
        return;
    }

    state.activeConversation = {
        ...(state.activeConversation || {}),
        ...matchingConversation,
    };
}


export function applyConversationDetailPayload(data) {
    const conversation = enrichConversationModelConfig(data.conversation);
    state.activeConversation = conversation;
    state.activeConversationId = conversation.id;
    state.activeMessages = data.messages || [];
    state.activeProjectId = conversation.project_id || null;
    state.pendingProjectModelId = null;
    state.pendingModelConfigId = null;
    state.isEditingConversationTitle = false;
    state.conversationTitleDraft = "";
    state.workspaceMode = "conversation";
}


export function applyModelsPayload(data) {
    state.models = data.models || [];
}


export function applyToolsPayload(data) {
    state.tools = data.tools || [];
}


export function applySettingsPayload(data) {
    const settings = {};

    for (const item of data.settings || []) {
        settings[item.key] = item.value;
    }

    state.settings = settings;
}


export function applyCurrentUserPayload(data) {
    state.currentUser = data.user || null;
}


export function enterHomeWorkspace() {
    state.workspaceMode = "home";
    state.activeProjectId = null;
    clearActiveConversation();
    state.pendingProjectModelId = null;
    state.projectDocuments = [];
    state.projectDocumentFolders = [];
    setProjectModels();
    setProjectWorkspace(null);
    setProjectWorkspaceFiles([]);
    state.activeProjectDocumentFolderId = null;
    state.stagedDocuments = [];
}


export function enterProjectWorkspace(projectId) {
    state.workspaceMode = "project";
    state.activeProjectId = projectId || null;
    state.pendingProjectModelId = null;
    state.activeProjectDocumentFolderId = null;
    setProjectModels();
    setProjectWorkspace(null);
    setProjectWorkspaceFiles([]);
    state.stagedDocuments = [];
    clearActiveConversation();
}


export function enterConversationWorkspace() {
    state.workspaceMode = "conversation";
}


export function enterSettingsWorkspace() {
    state.workspaceMode = "settings";
}


function enrichConversationModelConfig(conversation) {
    if (!conversation) {
        return conversation;
    }

    if (conversation.model_config_id) {
        return conversation;
    }

    const matchedModel = state.models.find((model) => (
        model.provider === conversation.provider
        && model.name === conversation.model
    ));

    return {
        ...conversation,
        model_config_id: matchedModel?.id || null,
    };
}
