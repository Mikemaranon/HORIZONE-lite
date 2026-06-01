import {
    filterMentionAgents,
    getActiveMentionQuery,
    getAgentMentionLabel,
    replaceActiveMention,
} from "./agent-mention-utils.js";
import { elements } from "./dom.js";
import { escapeHtml } from "./html.js";
import { getMentionableProjectAgents } from "./selectors.js";
import { state } from "./state.js";

let activeMentionAgents = [];
let activeMentionIndex = 0;


export function handleComposerMentionInput() {
    syncComposerMentionMenu();
}


export function handleComposerMentionKeyDown(event) {
    if (!isMentionMenuOpen()) {
        return false;
    }

    if (event.key === "ArrowDown") {
        event.preventDefault();
        activeMentionIndex = Math.min(activeMentionIndex + 1, activeMentionAgents.length - 1);
        renderComposerMentionMenu();
        return true;
    }

    if (event.key === "ArrowUp") {
        event.preventDefault();
        activeMentionIndex = Math.max(activeMentionIndex - 1, 0);
        renderComposerMentionMenu();
        return true;
    }

    if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        applyMentionAgent(activeMentionAgents[activeMentionIndex]);
        return true;
    }

    if (event.key === "Escape") {
        event.preventDefault();
        closeComposerMentionMenu();
        return true;
    }

    return false;
}


export function handleComposerMentionMenuClick(event) {
    const option = event.target.closest("[data-composer-mention-agent-id]");
    if (!option) {
        return;
    }

    const agent = activeMentionAgents.find(
        (item) => item.id === Number(option.dataset.composerMentionAgentId)
    );
    applyMentionAgent(agent);
}


export function handleComposerMentionDocumentClick(event) {
    if (
        event.target.closest("#composer-mention-menu")
        || event.target.closest("#composer-input")
    ) {
        return;
    }

    closeComposerMentionMenu();
}


export function closeComposerMentionMenu() {
    activeMentionAgents = [];
    activeMentionIndex = 0;
    if (elements.composerMentionMenu) {
        elements.composerMentionMenu.hidden = true;
        elements.composerMentionMenu.innerHTML = "";
    }
}


function syncComposerMentionMenu() {
    if (state.loading || !elements.composerInput || !elements.composerMentionMenu) {
        closeComposerMentionMenu();
        return;
    }

    const mention = getActiveMentionQuery(
        elements.composerInput.value,
        elements.composerInput.selectionStart,
    );
    if (!mention) {
        closeComposerMentionMenu();
        return;
    }

    activeMentionAgents = filterMentionAgents(mention.query, getMentionableProjectAgents());
    activeMentionIndex = 0;
    if (!activeMentionAgents.length) {
        closeComposerMentionMenu();
        return;
    }

    renderComposerMentionMenu();
}


function renderComposerMentionMenu() {
    if (!elements.composerMentionMenu) {
        return;
    }

    elements.composerMentionMenu.innerHTML = activeMentionAgents.map((agent, index) => {
        const label = getAgentMentionLabel(agent);
        const model = agent.model || {};
        const modelLabel = model.display_name || model.name || "Model";
        return `
            <button
                class="composer-mention-menu__option${index === activeMentionIndex ? " is-active" : ""}"
                type="button"
                role="option"
                aria-selected="${index === activeMentionIndex ? "true" : "false"}"
                data-composer-mention-agent-id="${agent.id}"
            >
                <span class="composer-mention-menu__name">@${escapeHtml(label)}</span>
                <span class="composer-mention-menu__meta">${escapeHtml(modelLabel)}</span>
            </button>
        `;
    }).join("");
    elements.composerMentionMenu.hidden = false;
}


function applyMentionAgent(agent) {
    if (!agent || !elements.composerInput) {
        closeComposerMentionMenu();
        return;
    }

    const replacement = replaceActiveMention(
        elements.composerInput.value,
        elements.composerInput.selectionStart,
        agent,
    );

    elements.composerInput.value = replacement.value;
    elements.composerInput.focus({ preventScroll: true });
    elements.composerInput.setSelectionRange(
        replacement.cursorPosition,
        replacement.cursorPosition,
    );
    closeComposerMentionMenu();
    elements.composerInput.dispatchEvent(new Event("input", { bubbles: true }));
}


function isMentionMenuOpen() {
    return Boolean(elements.composerMentionMenu && !elements.composerMentionMenu.hidden);
}
