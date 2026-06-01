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


export function getProjectModels() {
    return state.projectModels || [];
}


export function getDefaultProjectAgent() {
    const projectAgents = getProjectModels();
    return projectAgents.find((agent) => agent.is_default) || projectAgents[0] || null;
}


export function getProjectAgentById(projectModelId) {
    if (!projectModelId) {
        return null;
    }

    return getProjectModels().find((agent) => agent.id === Number(projectModelId)) || null;
}


export function getQuickProjectAgentsForConversation(conversation = state.activeConversation) {
    if (!conversation?.project_id) {
        return [];
    }

    const quickAgentIds = Array.isArray(conversation.quick_project_model_ids)
        ? conversation.quick_project_model_ids
        : [];

    return quickAgentIds
        .map((projectModelId) => getProjectAgentById(projectModelId))
        .filter(Boolean);
}


export function getMentionableProjectAgents(conversation = state.activeConversation) {
    if (!conversation?.project_id) {
        return [];
    }

    return getProjectModels();
}


export function getProjectAgentDisplayName(agent) {
    if (!agent) {
        return "custom";
    }

    const model = agent.model || {};
    return agent.nickname || model.display_name || model.name || "default";
}


export function getProjectAgentForConversation(conversation = state.activeConversation) {
    if (!conversation?.project_id) {
        return null;
    }

    const explicitAgent = getProjectAgentById(conversation.project_model_id);
    if (explicitAgent) {
        return explicitAgent;
    }

    return getProjectAgentForModelProfile(
        conversation.model_config_id,
        conversation.profile_id,
    ) || null;
}


export function getSelectedProjectAgent() {
    if (state.activeConversation?.project_id) {
        return getProjectAgentForConversation(state.activeConversation);
    }

    if (!state.activeProjectId) {
        return null;
    }

    const pendingAgent = getProjectAgentById(state.pendingProjectModelId);
    if (pendingAgent) {
        return pendingAgent;
    }

    return getDefaultProjectAgent();
}


export function getProjectAgentNameForConversation(conversation = state.activeConversation) {
    return getProjectAgentDisplayName(
        getProjectAgentForConversation(conversation)
        || getSelectedProjectAgent()
    );
}


export function getProjectAgentNameForMessage(message) {
    if (!state.activeConversation?.project_id) {
        return "";
    }

    if (message?.project_model_name) {
        return message.project_model_name;
    }

    const messageAgent = getProjectAgentById(message?.project_model_id);
    if (messageAgent) {
        return getProjectAgentDisplayName(messageAgent);
    }

    return getProjectAgentDisplayName(
        getProjectAgentForModelProfile(
            message?.model_config_id || state.activeConversation.model_config_id,
            message?.profile_id || state.activeConversation.profile_id,
        ) || getProjectAgentForConversation(state.activeConversation)
    );
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

    const selectedProjectAgent = getSelectedProjectAgent();
    if (state.activeProjectId && selectedProjectAgent?.profile_id) {
        return Number(selectedProjectAgent.profile_id);
    }

    if (state.pendingProfileId) {
        return Number(state.pendingProfileId);
    }

    if (selectedProjectAgent?.profile_id) {
        return Number(selectedProjectAgent.profile_id);
    }

    return getDefaultProfileId();
}


export function getSelectedModelConfigId() {
    if (state.activeConversation?.model_config_id) {
        return Number(state.activeConversation.model_config_id);
    }

    const selectedProjectAgent = getSelectedProjectAgent();
    if (state.activeProjectId && selectedProjectAgent?.model_id) {
        return Number(selectedProjectAgent.model_id);
    }

    if (state.pendingModelConfigId) {
        return Number(state.pendingModelConfigId);
    }

    if (selectedProjectAgent?.model_id) {
        return Number(selectedProjectAgent.model_id);
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


function getProjectAgentForModelProfile(modelConfigId, profileId) {
    const normalizedModelId = Number(modelConfigId || "0") || null;
    const normalizedProfileId = Number(profileId || "0") || null;
    if (!normalizedModelId) {
        return null;
    }

    const projectAgents = getProjectModels();
    if (normalizedProfileId) {
        const exactMatch = projectAgents.find((agent) => (
            Number(agent.model_id) === normalizedModelId
            && Number(agent.profile_id) === normalizedProfileId
        ));
        if (exactMatch) {
            return exactMatch;
        }
    }

    return projectAgents.find((agent) => Number(agent.model_id) === normalizedModelId) || null;
}
