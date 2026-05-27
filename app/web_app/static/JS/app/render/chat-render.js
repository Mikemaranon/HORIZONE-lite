import { syncComposerAvailability } from "../composer-ui.js";
import { syncChatExportState } from "../controllers/export-controller.js";
import { elements } from "../dom.js";
import { createMetaChipsMarkup, escapeHtml } from "../html.js";
import { createMessageMarkup, enableMessagesAutoScroll, scrollMessagesToBottom } from "../message-ui.js";
import { getActualProvider, getProviderDisplayName, getSelectedModel, getSelectedModelConfig } from "../provider-helpers.js";
import { getActiveProject, getProfileNameById, getProjectModels, getSelectedProfileId } from "../selectors.js";
import { state } from "../state.js";


export function renderMessages({ preserveViewport = false } = {}) {
    const showConversation = state.workspaceMode === "conversation" && !!state.activeConversation;
    const showEmptyState = state.workspaceMode === "home";

    syncChatExportState();

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
    elements.workspaceEyebrow.classList.toggle(
        "workspace__eyebrow--project-models",
        state.workspaceMode === "project" && !!activeProject,
    );

    if (state.workspaceMode === "conversation" && state.activeConversation) {
        const selectedModelConfig = getSelectedModelConfig();
        const provider = selectedModelConfig?.provider_name
            || getProviderDisplayName(state.activeConversation?.provider || getActualProvider());
        const model = state.activeConversation?.model || getSelectedModel() || "pending model";
        const profileName = getProfileNameById(state.activeConversation?.profile_id || getSelectedProfileId());

        elements.workspaceEyebrow.textContent = activeProject ? "Project chat" : "Chat";
        elements.conversationTitle.innerHTML = createConversationTitleMarkup(
            state.activeConversation.title || "New conversation",
        );
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
        elements.conversationTitle.innerHTML = createProjectModelChipsMarkup(getProjectModels());
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = true;
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


function createProjectModelChipsMarkup(models) {
    if (!models.length) {
        return `<span class="project-model-chip project-model-chip--empty">No agents</span>`;
    }

    return `
        <span class="project-model-chips" aria-label="Project agents">
            ${models.map((model) => {
                const nickname = model.nickname || "agent";
                const baseModel = model.model || model;
                const modelLabel = baseModel.display_name || baseModel.name || "Model";
                const label = `${nickname} | ${modelLabel}`;
                return `
                    <span class="project-model-chip" title="${escapeHtml(baseModel.name || label)}">
                        ${escapeHtml(label)}
                    </span>
                `;
            }).join("")}
        </span>
    `;
}


function createConversationTitleMarkup(title) {
    const safeTitle = escapeHtml(title || "New conversation");
    const draft = state.conversationTitleDraft || title || "";

    if (state.isEditingConversationTitle) {
        return `
            <span class="conversation-title-editor">
                <input
                    id="conversation-title-input"
                    class="conversation-title-editor__input"
                    type="text"
                    value="${escapeHtml(draft)}"
                    maxlength="120"
                    aria-label="Chat title"
                >
                <span class="conversation-title-editor__actions">
                    <button
                        class="conversation-title-editor__button"
                        type="button"
                        data-conversation-title-save="true"
                        aria-label="Save title"
                        title="Save title"
                    >&check;</button>
                    <button
                        class="conversation-title-editor__button"
                        type="button"
                        data-conversation-title-cancel="true"
                        aria-label="Cancel title edit"
                        title="Cancel"
                    >&times;</button>
                </span>
            </span>
        `;
    }

    return `
        <span class="workspace__title-text">${safeTitle}</span>
        <button
            class="workspace__title-edit-button"
            type="button"
            data-conversation-title-edit="true"
            aria-label="Edit chat title"
            title="Edit title"
        >
            <img src="/static/assets/icons/pencil.png" alt="">
        </button>
    `;
}
