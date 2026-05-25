import { state } from "./state.js";


export function getDefaultProfileId() {
    return state.profiles.find((profile) => profile.is_default)?.id || state.profiles[0]?.id || null;
}


export function getProfileNameById(profileId) {
    if (!profileId) {
        return "no profile";
    }

    return state.profiles.find((profile) => profile.id === Number(profileId))?.name || "no profile";
}


export function getProviderNameById(providerId) {
    if (!providerId) {
        return "no provider";
    }

    return state.providers.find((provider) => provider.id === Number(providerId))?.name || "no provider";
}


export function getDefaultModelConfigId() {
    return state.models.find((model) => model.is_default)?.id || state.models[0]?.id || null;
}


export function getModelConfigById(modelConfigId) {
    if (!modelConfigId) {
        return null;
    }

    return state.models.find((model) => model.id === Number(modelConfigId)) || null;
}


export function getModelDisplayNameById(modelConfigId) {
    const model = getModelConfigById(modelConfigId);
    if (!model) {
        return "";
    }

    return model.display_name || model.name || "";
}


export function getActiveProject() {
    return state.projects.find((project) => project.id === state.activeProjectId) || null;
}


export function getProjectConversations(projectId = state.activeProjectId) {
    if (!projectId) {
        return [];
    }

    return state.conversations.filter((conversation) => conversation.project_id === projectId);
}


export function getStandaloneConversations() {
    return state.conversations.filter((conversation) => !conversation.project_id);
}


export function getSelectedProfileId() {
    if (state.activeConversation?.profile_id) {
        return Number(state.activeConversation.profile_id);
    }

    if (state.pendingProfileId) {
        return Number(state.pendingProfileId);
    }

    return getDefaultProfileId();
}


export function getSelectedModelConfigId() {
    if (state.activeConversation?.model_config_id) {
        return Number(state.activeConversation.model_config_id);
    }

    if (state.pendingModelConfigId) {
        return Number(state.pendingModelConfigId);
    }

    return getDefaultModelConfigId();
}


export function buildConversationTitle() {
    const project = state.projects.find((item) => item.id === state.activeProjectId);
    if (project) {
        return `${project.name} · chat`;
    }

    return "New conversation";
}
