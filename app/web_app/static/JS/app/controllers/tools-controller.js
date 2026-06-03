import { updateTool, uploadToolFile } from "../api.js";
import { elements } from "../dom.js";
import { escapeHtml } from "../html.js";
import { closeToolUploadModal, openToolUploadModal } from "../modal-ui.js";
import { renderChatPanel, renderSettingsToolsManager } from "../render.js";
import { applyToolsPayload, setToolsShowActiveOnly } from "../state-actions.js";
import { showStatus } from "../status-ui.js";
import { loadTools } from "../store.js";

let stagedToolFile = null;


export async function handleToolToggle(toolId, isActive) {
    if (!toolId) {
        return;
    }

    try {
        await updateTool({
            id: toolId,
            is_active: isActive,
        });
        await refreshToolsState();
        renderSettingsToolsManager();
        renderChatPanel();
        showStatus(isActive ? "Tool enabled." : "Tool disabled.");
    } catch (error) {
        showStatus(error.message || "The tool could not be updated.", true);
    }
}


export function handleToolUploadButtonClick() {
    stagedToolFile = null;
    clearToolUploadError();
    if (elements.toolUploadNameInput) {
        elements.toolUploadNameInput.value = "";
    }
    if (elements.toolsUploadInput) {
        elements.toolsUploadInput.value = "";
    }
    renderToolUploadDraft();
    openToolUploadModal();
    elements.toolUploadNameInput?.focus({ preventScroll: true });
}


export function handleToolUploadInputChange(event) {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    if (!file) {
        return;
    }

    stageToolFile(file);
}


export function handleToolUploadNameInput() {
    clearToolUploadError();
    renderToolUploadDraft();
}


export function handleToolUploadDragOver(event) {
    event.preventDefault();
    elements.toolUploadDropzone?.classList.add("is-dragging");
}


export function handleToolUploadDragLeave() {
    elements.toolUploadDropzone?.classList.remove("is-dragging");
}


export function handleToolUploadDrop(event) {
    event.preventDefault();
    elements.toolUploadDropzone?.classList.remove("is-dragging");
    const [file] = Array.from(event.dataTransfer?.files || []);
    if (!file) {
        return;
    }

    stageToolFile(file);
}


export async function handleToolUploadSubmit(event) {
    event.preventDefault();

    if (!stagedToolFile) {
        setToolUploadError("Select a .py file before uploading the tool.");
        return;
    }

    const rawName = elements.toolUploadNameInput?.value.trim() || "";
    const filename = buildToolFilename(rawName);
    if (!filename) {
        setToolUploadError("Provide a valid name to save the tool.");
        return;
    }

    try {
        clearToolUploadError();
        await uploadToolFile(stagedToolFile, filename);
        await refreshToolsState();
        renderSettingsToolsManager();
        renderChatPanel();
        stagedToolFile = null;
        if (elements.toolUploadNameInput) {
            elements.toolUploadNameInput.value = "";
        }
        if (elements.toolsUploadInput) {
            elements.toolsUploadInput.value = "";
        }
        renderToolUploadDraft();
        closeToolUploadModal();
        showStatus(`Tool uploaded: ${filename}`);
    } catch (error) {
        const message = error.message || "The tool could not be uploaded.";
        setToolUploadError(message);
        showStatus(message, true);
    }
}


export function handleToolsFilterToggle() {
    setToolsShowActiveOnly(!elements.settingsFilterToolsButton || elements.settingsFilterToolsButton.getAttribute("aria-pressed") !== "true");
    renderSettingsToolsManager();
}


export function handleDocumentToolClick(event) {
    const workspaceToggleButton = event.target.closest("[data-chat-workspace-tool-toggle]");
    if (workspaceToggleButton) {
        handleToolToggle(
            workspaceToggleButton.dataset.chatWorkspaceToolToggle,
            workspaceToggleButton.getAttribute("aria-pressed") !== "true",
        );
        return;
    }

    const chatToggleButton = event.target.closest("[data-chat-tool-toggle]");
    if (chatToggleButton) {
        handleToolToggle(
            Number(chatToggleButton.dataset.chatToolToggle),
            chatToggleButton.getAttribute("aria-pressed") !== "true",
        );
        return;
    }

    const settingsToggleButton = event.target.closest("[data-settings-tool-toggle]");
    if (settingsToggleButton) {
        handleToolToggle(
            Number(settingsToggleButton.dataset.settingsToolToggle),
            settingsToggleButton.getAttribute("aria-pressed") !== "true",
        );
    }
}


async function refreshToolsState() {
    applyToolsPayload(await loadTools());
}


function stageToolFile(file) {
    if (!isPythonFile(file)) {
        stagedToolFile = null;
        setToolUploadError("Only Python files with the .py extension are supported.");
        renderToolUploadDraft();
        return;
    }

    stagedToolFile = file;
    clearToolUploadError();
    if (elements.toolUploadNameInput && !elements.toolUploadNameInput.value.trim()) {
        elements.toolUploadNameInput.value = deriveToolName(file.name);
    }
    renderToolUploadDraft();
}


function renderToolUploadDraft() {
    if (elements.toolUploadFileList) {
        if (!stagedToolFile) {
            elements.toolUploadFileList.innerHTML = `
                <p class="documents-file-list__empty">You have not selected any file yet.</p>
            `;
        } else {
            const name = elements.toolUploadNameInput?.value.trim() || "";
            const filename = buildToolFilename(name);
            const metaParts = [formatFileSize(stagedToolFile.size)];
            if (filename) {
                metaParts.unshift(`Will be saved as ${filename}`);
            }
            elements.toolUploadFileList.innerHTML = `
                <div class="documents-file documents-file--pending">
                    <div class="documents-file__copy">
                        <strong class="documents-file__name">${escapeHtml(stagedToolFile.name)}</strong>
                        <span class="documents-file__meta">${escapeHtml(metaParts.join(" · "))}</span>
                    </div>
                </div>
            `;
        }
    }

    if (elements.toolUploadSubmitButton) {
        elements.toolUploadSubmitButton.disabled = !stagedToolFile || !buildToolFilename(elements.toolUploadNameInput?.value.trim() || "");
    }
}


function setToolUploadError(message) {
    if (!elements.toolUploadError) {
        return;
    }

    elements.toolUploadError.hidden = false;
    elements.toolUploadError.textContent = message;
}


function clearToolUploadError() {
    if (!elements.toolUploadError) {
        return;
    }

    elements.toolUploadError.hidden = true;
    elements.toolUploadError.textContent = "";
}


function deriveToolName(filename) {
    return String(filename || "")
        .replace(/\.py$/i, "")
        .trim();
}


function buildToolFilename(name) {
    const normalized = String(name || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");

    if (!normalized) {
        return "";
    }

    return `${normalized}.py`;
}


function isPythonFile(file) {
    return /\.py$/i.test(file?.name || "");
}


function formatFileSize(size) {
    if (size < 1024) {
        return `${size} B`;
    }
    if (size < 1024 * 1024) {
        return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
