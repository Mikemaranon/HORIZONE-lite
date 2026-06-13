import { createMentionedContentMarkup } from "./agent-mention-markup.js";
import { elements } from "./dom.js";
import { getSelectedModel, getSelectedModelConfig } from "./provider-helpers.js";
import { getMentionableProjectAgents } from "./selectors.js";
import { state } from "./state.js";


export function autoResizeComposer() {
    elements.composerInput.style.height = "auto";
    elements.composerInput.style.height = `${Math.min(elements.composerInput.scrollHeight, 220)}px`;
    syncComposerHighlight();
}


export function syncComposerHighlight() {
    if (!elements.composerHighlight || !elements.composerInput) {
        return;
    }

    elements.composerHighlight.innerHTML = createMentionedContentMarkup(
        elements.composerInput.value,
        getMentionableProjectAgents(),
    ) || "<br>";
    elements.composerInput.closest(".composer__input-wrap")?.classList.add("is-highlight-ready");
    syncComposerHighlightScroll();
}


export function syncComposerHighlightScroll() {
    if (!elements.composerHighlight || !elements.composerInput) {
        return;
    }

    elements.composerHighlight.scrollTop = elements.composerInput.scrollTop;
}


export function syncComposerAvailability() {
    const isProjectWorkspace = state.workspaceMode === "project";
    const isSettingsWorkspace = state.workspaceMode === "settings";
    const selectedModelConfig = getSelectedModelConfig();
    const shouldDisableComposer = isProjectWorkspace || isSettingsWorkspace || !selectedModelConfig;

    elements.composerShell.hidden = isProjectWorkspace || isSettingsWorkspace;
    elements.sendButton.disabled = shouldDisableComposer || (state.loading && state.generationStopRequested);
    elements.composerInput.disabled = shouldDisableComposer || state.loading;

    if (state.loading) {
        elements.sendButton.classList.remove("action-button--primary");
        elements.sendButton.classList.add("action-button--danger", "composer__send--stop");
        elements.sendButton.setAttribute("aria-label", state.generationStopRequested ? "Stopping" : "Stop");
        elements.sendButton.setAttribute("title", state.generationStopRequested ? "Stopping" : "Stop");
        elements.sendButton.innerHTML = `<span class="composer__stop-icon" aria-hidden="true"></span>`;
    } else {
        elements.sendButton.classList.add("action-button--primary");
        elements.sendButton.classList.remove("action-button--danger", "composer__send--stop");
        elements.sendButton.setAttribute("aria-label", "Send");
        elements.sendButton.setAttribute("title", "Send");
        elements.sendButton.innerHTML = `
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M3 20v-6l8-2-8-2V4l19 8-19 8z" fill="currentColor"></path>
            </svg>
        `;
    }

    if (isProjectWorkspace) {
        elements.composerInput.placeholder = "Open or create a chat inside the project to type.";
        elements.composerHint.textContent = "Projects manage context; text is written inside a project chat.";
    } else if (isSettingsWorkspace) {
        elements.composerInput.placeholder = "Return to a chat to type.";
        elements.composerHint.textContent = "General settings are managed from this view.";
    } else if (!getSelectedModel()) {
        elements.composerInput.placeholder = "Select a model before typing.";
        elements.composerHint.textContent = "Each chat uses its own model without affecting the others.";
    } else if (state.loading && state.generationStopRequested) {
        elements.composerInput.placeholder = "Stopping the current response...";
        elements.composerHint.textContent = "Waiting for the provider to close the current generation.";
    } else if (state.loading) {
        elements.composerInput.placeholder = "Press stop if you want to interrupt this response.";
        elements.composerHint.textContent = "The response is being generated right now.";
    } else {
        elements.composerInput.placeholder = "Ask anything...";
        elements.composerHint.textContent = "`Shift + Enter` for a new line";
    }
    syncComposerHighlight();
}


export function setLoading(isLoading) {
    state.loading = isLoading;
    elements.newChatButton.disabled = isLoading;
    elements.newProjectButton.disabled = isLoading;
    if (elements.newProjectChatButton) {
        elements.newProjectChatButton.disabled = isLoading;
    }
    if (elements.projectActionsMenuButton) {
        elements.projectActionsMenuButton.disabled = isLoading;
    }
    if (elements.addDocumentsButton) {
        elements.addDocumentsButton.disabled = isLoading;
    }
    if (elements.customizeProjectButton) {
        elements.customizeProjectButton.disabled = isLoading;
    }
    if (elements.connectWorkspaceButton) {
        elements.connectWorkspaceButton.disabled = isLoading;
    }
    syncComposerAvailability();
}
