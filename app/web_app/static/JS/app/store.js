import {
    loadConversationDetailData,
    loadConversationsData,
    loadCurrentUserData,
    loadModelsData,
    loadProfilesData,
    loadProvidersData,
    loadProjectDocumentsData,
    loadProjectModelsData,
    loadProjectWorkspaceData,
    loadProjectsData,
    loadSettingsData,
    loadToolsData,
} from "./api.js";


export async function loadProjects() {
    return loadProjectsData();
}


export async function loadProfiles() {
    return loadProfilesData();
}


export async function loadProviders() {
    return loadProvidersData();
}


export async function loadProjectDocuments(projectId) {
    if (!projectId) {
        return { documents: [], folders: [] };
    }

    return loadProjectDocumentsData(projectId);
}


export async function loadProjectWorkspace(projectId) {
    if (!projectId) {
        return { workspace: null, file_count: 0, recent_events: [] };
    }

    return loadProjectWorkspaceData(projectId);
}


export async function loadProjectModels(projectId) {
    if (!projectId) {
        return { models: [], uses_default: true };
    }

    return loadProjectModelsData(projectId);
}


export async function loadConversations(projectId) {
    return loadConversationsData(projectId);
}


export async function loadConversationDetail(conversationId) {
    return loadConversationDetailData(conversationId);
}


export async function loadModels() {
    return loadModelsData();
}


export async function loadTools() {
    return loadToolsData();
}


export async function loadSettings() {
    return loadSettingsData();
}


export async function loadCurrentUser() {
    return loadCurrentUserData();
}
