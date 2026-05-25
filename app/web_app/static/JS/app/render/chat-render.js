import { syncComposerAvailability } from "../composer-ui.js";
import { elements } from "../dom.js";
import { createMetaChipsMarkup } from "../html.js";
import { createMessageMarkup, enableMessagesAutoScroll, scrollMessagesToBottom } from "../message-ui.js";
import { getActualProvider, getProviderDisplayName, getSelectedModel, getSelectedModelConfig } from "../provider-helpers.js";
import { getActiveProject, getProfileNameById, getSelectedProfileId } from "../selectors.js";
import { state } from "../state.js";


export function renderMessages({ preserveViewport = false } = {}) {
    const showConversation = state.workspaceMode === "conversation" && !!state.activeConversation;
    const showEmptyState = state.workspaceMode === "home";

    elements.emptyState.hidden = !showEmptyState;

    if (!showConversation) {
        elements.messagesContainer.hidden = true;
        elements.messagesContainer.innerHTML = "";
        enableMessagesAutoScroll();
        return;
    }

    elements.messagesContainer.hidden = false;
    elements.messagesContainer.innerHTML = state.activeMessages
        .map((message) => createMessageMarkup(message))
        .join("");

    if (preserveViewport) {
        return;
    }

    enableMessagesAutoScroll();
    scrollMessagesToBottom();
}


export function renderConversationHeader() {
    const activeProject = getActiveProject();

    if (state.workspaceMode === "conversation" && state.activeConversation) {
        const selectedModelConfig = getSelectedModelConfig();
        const provider = selectedModelConfig?.provider_name
            || getProviderDisplayName(state.activeConversation?.provider || getActualProvider());
        const model = state.activeConversation?.model || getSelectedModel() || "pending model";
        const profileName = getProfileNameById(state.activeConversation?.profile_id || getSelectedProfileId());

        elements.workspaceEyebrow.textContent = activeProject ? "Project chat" : "Chat";
        elements.conversationTitle.textContent = state.activeConversation.title || "New conversation";
        elements.conversationMeta.innerHTML = createMetaChipsMarkup([
            { group: "provider", label: "Provider", value: provider },
            { group: "model", label: "Model", value: model },
            { group: "profile", label: "Profile", value: profileName },
        ]);
        elements.conversationMeta.hidden = false;
        elements.conversationSubtitle.hidden = true;
        elements.backToProjectButton.hidden = !activeProject;
        elements.chatSettingsButton.hidden = false;
        return;
    }

    if (state.workspaceMode === "project" && activeProject) {
        elements.workspaceEyebrow.textContent = "Project";
        elements.conversationTitle.textContent = activeProject.name;
        elements.conversationSubtitle.textContent = "Manage the project prompt and its chats here, without mixing them with standalone chats.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = false;
        return;
    }

    if (state.workspaceMode === "settings") {
        elements.workspaceEyebrow.textContent = "Configuration";
        elements.conversationTitle.textContent = "General settings";
        elements.conversationSubtitle.textContent = "Manage HORIZONE lite providers, models, profiles, and session here.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = true;
        return;
    }

    if (state.workspaceMode === "home") {
        elements.workspaceEyebrow.textContent = "Chat";
        elements.conversationTitle.textContent = "New conversation";
        elements.conversationSubtitle.textContent = "Set the default model in general settings and change the model or profile per chat from the side panel.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = false;
    }
}


export function renderChatSurface() {
    renderMessages();
    renderConversationHeader();
    syncComposerAvailability();
}
