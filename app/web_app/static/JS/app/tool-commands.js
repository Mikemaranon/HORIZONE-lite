import {
    filterCommandTools,
    getActiveToolCommandQuery,
    getToolCommandName,
    replaceActiveToolCommand,
} from "./tool-command-utils.js";
import { elements } from "./dom.js";
import { escapeHtml } from "./html.js";
import { getAvailableCommandTools } from "./selectors.js";
import { state } from "./state.js";

let activeCommandTools = [];
let activeCommandIndex = 0;


export function handleComposerCommandInput() {
    syncComposerCommandMenu();
}


export function handleComposerCommandKeyDown(event) {
    if (!isCommandMenuOpen()) {
        return false;
    }

    if (event.key === "ArrowDown") {
        event.preventDefault();
        activeCommandIndex = Math.min(activeCommandIndex + 1, activeCommandTools.length - 1);
        renderComposerCommandMenu();
        return true;
    }

    if (event.key === "ArrowUp") {
        event.preventDefault();
        activeCommandIndex = Math.max(activeCommandIndex - 1, 0);
        renderComposerCommandMenu();
        return true;
    }

    if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        applyCommandTool(activeCommandTools[activeCommandIndex]);
        return true;
    }

    if (event.key === "Escape") {
        event.preventDefault();
        closeComposerCommandMenu();
        return true;
    }

    return false;
}


export function handleComposerCommandMenuClick(event) {
    const option = event.target.closest("[data-composer-command-tool-name]");
    if (!option) {
        return;
    }

    const tool = activeCommandTools.find(
        (item) => getToolCommandName(item) === option.dataset.composerCommandToolName,
    );
    applyCommandTool(tool);
}


export function handleComposerCommandDocumentClick(event) {
    if (
        event.target.closest("#composer-command-menu")
        || event.target.closest("#composer-input")
    ) {
        return;
    }
    closeComposerCommandMenu();
}


export function closeComposerCommandMenu() {
    activeCommandTools = [];
    activeCommandIndex = 0;
    if (elements.composerCommandMenu) {
        elements.composerCommandMenu.hidden = true;
        elements.composerCommandMenu.innerHTML = "";
    }
}


function syncComposerCommandMenu() {
    if (state.loading || !elements.composerInput || !elements.composerCommandMenu) {
        closeComposerCommandMenu();
        return;
    }

    const command = getActiveToolCommandQuery(
        elements.composerInput.value,
        elements.composerInput.selectionStart,
    );
    if (!command) {
        closeComposerCommandMenu();
        return;
    }

    activeCommandTools = filterCommandTools(command.query, getAvailableCommandTools());
    activeCommandIndex = 0;
    if (!activeCommandTools.length) {
        closeComposerCommandMenu();
        return;
    }
    renderComposerCommandMenu();
}


function renderComposerCommandMenu() {
    if (!elements.composerCommandMenu) {
        return;
    }

    elements.composerCommandMenu.innerHTML = activeCommandTools.map((tool, index) => {
        const name = getToolCommandName(tool);
        const meta = tool.display_name || tool.description || "Tool";
        return `
            <button
                class="composer-mention-menu__option${index === activeCommandIndex ? " is-active" : ""}"
                type="button"
                role="option"
                aria-selected="${index === activeCommandIndex ? "true" : "false"}"
                data-composer-command-tool-name="${escapeHtml(name)}"
            >
                <span class="composer-mention-menu__name tool-command-token">/${escapeHtml(name)}</span>
                <span class="composer-mention-menu__meta">${escapeHtml(meta)}</span>
            </button>
        `;
    }).join("");
    elements.composerCommandMenu.hidden = false;
    elements.composerCommandMenu
        .querySelector(".is-active")
        ?.scrollIntoView({ block: "nearest" });
}


function applyCommandTool(tool) {
    if (!tool || !elements.composerInput) {
        closeComposerCommandMenu();
        return;
    }

    const replacement = replaceActiveToolCommand(
        elements.composerInput.value,
        elements.composerInput.selectionStart,
        tool,
    );
    elements.composerInput.value = replacement.value;
    elements.composerInput.focus({ preventScroll: true });
    elements.composerInput.setSelectionRange(
        replacement.cursorPosition,
        replacement.cursorPosition,
    );
    closeComposerCommandMenu();
    elements.composerInput.dispatchEvent(new Event("input", { bubbles: true }));
}


function isCommandMenuOpen() {
    return Boolean(elements.composerCommandMenu && !elements.composerCommandMenu.hidden);
}
