import { syncComposerAvailability } from "../composer-ui.js";
import { syncChatExportState } from "../controllers/export-controller.js";
import { elements } from "../dom.js";
import { createMetaChipsMarkup, escapeHtml } from "../html.js";
import {
    createMessageMarkup,
    enableMessagesAutoScroll,
    highlightMessageCodeBlocks,
    scrollMessagesToBottom,
} from "../message-ui.js";
import { getActualProvider, getProviderDisplayName, getSelectedModel, getSelectedModelConfig } from "../provider-helpers.js";
import {
    getActiveProject,
    getProfileNameById,
    getProjectModels,
    getSelectedProfileId,
} from "../selectors.js";
import { state } from "../state.js";

const DEFAULT_AGENT_COLOR = "#1c8b59";


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
        .map((message, index, messages) => createMessageMarkup(message, {
            previousMessage: messages[index - 1] || null,
            nextMessage: messages[index + 1] || null,
            messages,
            messageIndex: index,
        }))
        .join("");
    highlightMessageCodeBlocks(elements.messagesContainer);

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
    elements.conversationTitle.classList.toggle(
        "workspace__title--project",
        state.workspaceMode === "project" && !!activeProject,
    );

    if (state.workspaceMode === "conversation" && state.activeConversation) {
        const selectedModelConfig = getSelectedModelConfig();
        const provider = selectedModelConfig?.provider_name
            || getProviderDisplayName(state.activeConversation?.provider || getActualProvider());
        const model = state.activeConversation?.model || getSelectedModel() || "pending model";
        const profileName = getProfileNameById(state.activeConversation?.profile_id || getSelectedProfileId());
        const isProjectConversation = Boolean(activeProject);

        elements.workspaceEyebrow.textContent = activeProject ? "Project chat" : "Chat";
        elements.conversationTitle.innerHTML = createConversationTitleMarkup(
            state.activeConversation.title || "New conversation",
        );
        elements.conversationMeta.innerHTML = isProjectConversation
            ? createProjectAgentChipsMarkup(getProjectModels())
            : createMetaChipsMarkup([
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
        const workspaceName = state.projectWorkspace?.display_name || activeProject.name || "Project";
        elements.workspaceEyebrow.textContent = "Project";
        elements.conversationTitle.textContent = `Active workspace: ${workspaceName}`;
        elements.conversationMeta.innerHTML = createProjectAgentChipsMarkup(getProjectModels());
        elements.conversationMeta.hidden = false;
        elements.conversationSubtitle.hidden = true;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = false;
        return;
    }

    if (state.workspaceMode === "settings") {
        elements.workspaceEyebrow.textContent = "Configuration";
        elements.conversationTitle.textContent = "General settings";
        elements.conversationSubtitle.textContent = "Manage HORIZONE providers, models, profiles, and session here.";
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


function createProjectAgentChipsMarkup(agents) {
    const sortedAgents = getDefaultFirstProjectAgents(agents);
    if (!sortedAgents.length) {
        return `<span class="project-model-chip project-model-chip--empty">No agents</span>`;
    }

    return `
        <span class="project-model-chips" aria-label="Project agents">
            ${sortedAgents.map((agent, index) => createProjectAgentChipMarkup(agent, index)).join("")}
        </span>
    `;
}


function createProjectAgentChipMarkup(agent, index) {
    const baseModel = agent.model || agent;
    const nickname = agent.nickname || baseModel.display_name || baseModel.name || "agent";
    const modelLabel = baseModel.display_name || baseModel.name || "Model";
    const title = `${nickname} | ${modelLabel}`;
    const color = normalizeAgentColor(agent.color);
    const leadingSeparator = index === 1 ? `<span class="project-agent-chip-separator" aria-hidden="true">|</span>` : "";

    return `
        ${leadingSeparator}
        <span
            class="selection-chip selection-chip--static selection-chip--agent"
            data-group="project-agent"
            style="--project-agent-color: ${escapeHtml(color)}"
            title="${escapeHtml(baseModel.name || title)}"
        >
            <span class="selection-chip__value project-agent-chip__name">${escapeHtml(nickname)}</span>
            <span class="selection-chip__model">${escapeHtml(modelLabel)}</span>
        </span>
    `;
}


function getDefaultFirstProjectAgents(agents) {
    return [...(agents || [])].sort((left, right) => {
        if (Boolean(left.is_default) !== Boolean(right.is_default)) {
            return left.is_default ? -1 : 1;
        }
        return 0;
    });
}


function normalizeAgentColor(color) {
    const normalized = String(color || DEFAULT_AGENT_COLOR).trim();
    return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized.toLowerCase() : DEFAULT_AGENT_COLOR;
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
