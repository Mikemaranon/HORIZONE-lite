import { selectWorkspaceDirectory } from "./native-directory-picker.js";

let confirmState = null;
let projectDialogState = null;
let workspaceDialogState = null;


export function confirmAction({
    title = "Confirm action",
    message = "",
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    eyebrow = "Confirmation",
    confirmVariant = "danger",
} = {}) {
    const state = ensureConfirmDialog();

    return new Promise((resolve) => {
        state.queue.push({
            title,
            message,
            confirmLabel,
            cancelLabel,
            eyebrow,
            confirmVariant,
            resolve,
        });
        pumpConfirmQueue(state);
    });
}


export function requestProjectDetails() {
    const state = ensureProjectDialog();

    return new Promise((resolve) => {
        state.resolve = resolve;
        state.nameInput.value = "";
        state.descriptionInput.value = "";
        state.errorNode.hidden = true;
        openDialog(state);
        state.nameInput.focus({ preventScroll: true });
    });
}


export function requestWorkspaceDetails(existingWorkspace = null, workspaceMeta = {}) {
    const state = ensureWorkspaceDialog();

    return new Promise((resolve) => {
        state.resolve = resolve;
        configureWorkspaceDialog(state, existingWorkspace, workspaceMeta);
        openDialog(state);
        state.browseButton.focus({ preventScroll: true });
    });
}


function ensureConfirmDialog() {
    if (confirmState) {
        return confirmState;
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
        <div id="confirm-dialog" class="modal confirm-dialog" hidden>
            <div class="modal__backdrop" data-dialog-cancel="true"></div>
            <div class="modal__panel modal__panel--narrow confirm-dialog__panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message">
                <button id="confirm-dialog-close" class="icon-button modal__close-button" type="button" aria-label="Close">×</button>
                <div class="confirm-dialog__body">
                    <div class="confirm-dialog__header">
                        <p id="confirm-dialog-eyebrow" class="modal__eyebrow">Confirmation</p>
                        <h3 id="confirm-dialog-title">Confirm action</h3>
                        <p id="confirm-dialog-message" class="confirm-dialog__message"></p>
                    </div>
                    <div class="confirm-dialog__actions">
                        <button id="confirm-dialog-cancel" class="ghost-button" type="button">Cancel</button>
                        <button id="confirm-dialog-confirm" class="action-button action-button--danger" type="button">Confirm</button>
                    </div>
                </div>
            </div>
        </div>
    `.trim();
    document.body.appendChild(wrapper.firstElementChild);

    confirmState = {
        modal: document.getElementById("confirm-dialog"),
        eyebrowNode: document.getElementById("confirm-dialog-eyebrow"),
        titleNode: document.getElementById("confirm-dialog-title"),
        messageNode: document.getElementById("confirm-dialog-message"),
        closeButton: document.getElementById("confirm-dialog-close"),
        cancelButton: document.getElementById("confirm-dialog-cancel"),
        confirmButton: document.getElementById("confirm-dialog-confirm"),
        queue: [],
        activeRequest: null,
        isClosing: false,
        resolve: null,
        lastFocusedElement: null,
    };

    confirmState.modal.addEventListener("click", (event) => {
        if (event.target.dataset.dialogCancel === "true") {
            resolveConfirm(false);
        }
    });
    confirmState.closeButton.addEventListener("click", () => resolveConfirm(false));
    confirmState.cancelButton.addEventListener("click", () => resolveConfirm(false));
    confirmState.confirmButton.addEventListener("click", () => resolveConfirm(true));

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !confirmState.modal.hidden) {
            resolveConfirm(false);
        }
    });

    return confirmState;
}


function ensureProjectDialog() {
    if (projectDialogState) {
        return projectDialogState;
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
        <div id="project-create-dialog" class="modal project-create-dialog" hidden>
            <div class="modal__backdrop" data-dialog-cancel="true"></div>
            <div class="modal__panel modal__panel--narrow" role="dialog" aria-modal="true" aria-labelledby="project-create-dialog-title">
                <button id="project-create-dialog-close" class="icon-button modal__close-button" type="button" aria-label="Close">×</button>
                <div class="modal__header">
                    <div>
                        <p class="modal__eyebrow">Project</p>
                        <h3 id="project-create-dialog-title">New project</h3>
                    </div>
                </div>
                <form id="project-create-dialog-form" class="modal__body project-create-dialog__form">
                    <label class="field field--stacked">
                        <span>Name</span>
                        <input id="project-create-name-input" type="text" autocomplete="off" placeholder="e.g. Local research">
                    </label>
                    <label class="field field--stacked">
                        <span>Description</span>
                        <textarea id="project-create-description-input" rows="3" placeholder="Short project context..."></textarea>
                    </label>
                    <p id="project-create-error" class="form-error" hidden>The project needs a name.</p>
                    <div class="confirm-dialog__actions">
                        <button id="project-create-cancel" class="ghost-button" type="button">Cancel</button>
                        <button class="action-button action-button--primary" type="submit">Create project</button>
                    </div>
                </form>
            </div>
        </div>
    `.trim();
    document.body.appendChild(wrapper.firstElementChild);

    projectDialogState = {
        modal: document.getElementById("project-create-dialog"),
        form: document.getElementById("project-create-dialog-form"),
        nameInput: document.getElementById("project-create-name-input"),
        descriptionInput: document.getElementById("project-create-description-input"),
        errorNode: document.getElementById("project-create-error"),
        closeButton: document.getElementById("project-create-dialog-close"),
        cancelButton: document.getElementById("project-create-cancel"),
        isClosing: false,
        resolve: null,
        lastFocusedElement: null,
    };

    projectDialogState.modal.addEventListener("click", (event) => {
        if (event.target.dataset.dialogCancel === "true") {
            resolveProjectDialog(null);
        }
    });
    projectDialogState.closeButton.addEventListener("click", () => resolveProjectDialog(null));
    projectDialogState.cancelButton.addEventListener("click", () => resolveProjectDialog(null));
    projectDialogState.form.addEventListener("submit", (event) => {
        event.preventDefault();
        const name = projectDialogState.nameInput.value.trim();
        if (!name) {
            projectDialogState.errorNode.hidden = false;
            projectDialogState.nameInput.focus({ preventScroll: true });
            return;
        }

        resolveProjectDialog({
            name,
            description: projectDialogState.descriptionInput.value.trim(),
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !projectDialogState.modal.hidden) {
            resolveProjectDialog(null);
        }
    });

    return projectDialogState;
}


function ensureWorkspaceDialog() {
    if (workspaceDialogState) {
        return workspaceDialogState;
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
        <div id="workspace-connect-dialog" class="modal workspace-connect-dialog" hidden>
            <div class="modal__backdrop" data-dialog-cancel="true"></div>
            <div class="modal__panel modal__panel--narrow workspace-connect-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="workspace-connect-dialog-title">
                <button id="workspace-connect-dialog-close" class="icon-button modal__close-button" type="button" aria-label="Close">×</button>
                <div class="modal__header">
                    <div>
                        <p class="modal__eyebrow">Workspace</p>
                        <h3 id="workspace-connect-dialog-title">Workspace</h3>
                    </div>
                </div>
                <form id="workspace-connect-dialog-form" class="modal__body project-create-dialog__form">
                    <section id="workspace-connect-summary" class="workspace-dialog-summary">
                        <div>
                            <span class="workspace-dialog-summary__kicker">Status</span>
                            <strong id="workspace-connect-status-title">Not connected</strong>
                            <span id="workspace-connect-status-meta">Choose a local folder to make project files available to chats.</span>
                        </div>
                    </section>
                    <div class="workspace-folder-picker">
                        <label class="field field--stacked workspace-folder-picker__path">
                            <span>Workspace folder</span>
                            <input id="workspace-connect-path-input" type="text" autocomplete="off" readonly placeholder="No folder selected">
                        </label>
                        <button id="workspace-folder-picker-button" class="ghost-button workspace-folder-picker__button" type="button">Choose folder</button>
                    </div>
                    <label class="field field--stacked">
                        <span>Display name</span>
                        <input id="workspace-connect-name-input" type="text" autocomplete="off" placeholder="Optional">
                    </label>
                    <section id="workspace-connect-files-section" class="workspace-dialog-files" hidden>
                        <div class="workspace-dialog-files__header">
                            <span>Workspace tree</span>
                            <span id="workspace-connect-file-count">0 files</span>
                        </div>
                        <pre id="workspace-connect-files" class="workspace-dialog-files__tree" aria-label="Workspace tree"></pre>
                    </section>
                    <p id="workspace-connect-error" class="form-error" hidden>Enter a local folder path.</p>
                    <div class="workspace-dialog-actions">
                        <div class="workspace-dialog-actions__secondary">
                            <button id="workspace-reindex-button" class="ghost-button" type="button" hidden>Reindex</button>
                            <button id="workspace-disconnect-button" class="ghost-button ghost-button--danger" type="button" hidden>Disconnect</button>
                        </div>
                        <div class="workspace-dialog-actions__primary">
                            <button id="workspace-connect-cancel" class="ghost-button" type="button">Cancel</button>
                            <button id="workspace-connect-submit" class="action-button action-button--primary" type="submit">Connect</button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    `.trim();
    document.body.appendChild(wrapper.firstElementChild);

    workspaceDialogState = {
        modal: document.getElementById("workspace-connect-dialog"),
        form: document.getElementById("workspace-connect-dialog-form"),
        pathInput: document.getElementById("workspace-connect-path-input"),
        browseButton: document.getElementById("workspace-folder-picker-button"),
        displayNameInput: document.getElementById("workspace-connect-name-input"),
        statusTitle: document.getElementById("workspace-connect-status-title"),
        statusMeta: document.getElementById("workspace-connect-status-meta"),
        filesSection: document.getElementById("workspace-connect-files-section"),
        fileCount: document.getElementById("workspace-connect-file-count"),
        filesList: document.getElementById("workspace-connect-files"),
        errorNode: document.getElementById("workspace-connect-error"),
        closeButton: document.getElementById("workspace-connect-dialog-close"),
        cancelButton: document.getElementById("workspace-connect-cancel"),
        submitButton: document.getElementById("workspace-connect-submit"),
        reindexButton: document.getElementById("workspace-reindex-button"),
        disconnectButton: document.getElementById("workspace-disconnect-button"),
        isClosing: false,
        resolve: null,
        lastFocusedElement: null,
    };

    workspaceDialogState.modal.addEventListener("click", (event) => {
        if (event.target.dataset.dialogCancel === "true") {
            resolveWorkspaceDialog(null);
        }
    });
    workspaceDialogState.closeButton.addEventListener("click", () => resolveWorkspaceDialog(null));
    workspaceDialogState.cancelButton.addEventListener("click", () => resolveWorkspaceDialog(null));
    workspaceDialogState.browseButton.addEventListener("click", handleWorkspaceFolderBrowse);
    workspaceDialogState.pathInput.addEventListener("click", handleWorkspaceFolderBrowse);
    workspaceDialogState.reindexButton.addEventListener("click", () => {
        resolveWorkspaceDialog({ action: "reindex" });
    });
    workspaceDialogState.disconnectButton.addEventListener("click", () => {
        resolveWorkspaceDialog({ action: "disconnect" });
    });
    workspaceDialogState.form.addEventListener("submit", (event) => {
        event.preventDefault();
        const rootPath = workspaceDialogState.pathInput.value.trim();
        if (!rootPath) {
            workspaceDialogState.errorNode.textContent = "Choose a local folder.";
            workspaceDialogState.errorNode.hidden = false;
            workspaceDialogState.browseButton.focus({ preventScroll: true });
            return;
        }

        resolveWorkspaceDialog({
            action: "connect",
            root_path: rootPath,
            display_name: workspaceDialogState.displayNameInput.value.trim(),
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !workspaceDialogState.modal.hidden) {
            resolveWorkspaceDialog(null);
        }
    });

    return workspaceDialogState;
}


async function handleWorkspaceFolderBrowse() {
    if (!workspaceDialogState || workspaceDialogState.modal.hidden) {
        return;
    }

    const originalLabel = workspaceDialogState.browseButton.textContent;
    workspaceDialogState.errorNode.hidden = true;
    workspaceDialogState.browseButton.disabled = true;
    workspaceDialogState.browseButton.textContent = "Choosing...";

    try {
        const directory = await selectWorkspaceDirectory({
            currentPath: workspaceDialogState.pathInput.value.trim(),
            title: "Choose workspace folder",
        });
        if (!directory) {
            return;
        }

        workspaceDialogState.pathInput.value = directory.root_path;
        if (!workspaceDialogState.displayNameInput.value.trim()) {
            workspaceDialogState.displayNameInput.value = directory.display_name || "";
        }
    } catch (error) {
        workspaceDialogState.errorNode.textContent = error.message || "The folder picker could not be opened.";
        workspaceDialogState.errorNode.hidden = false;
    } finally {
        workspaceDialogState.browseButton.disabled = false;
        workspaceDialogState.browseButton.textContent = originalLabel;
        workspaceDialogState.browseButton.focus({ preventScroll: true });
    }
}


function configureWorkspaceDialog(state, existingWorkspace, workspaceMeta) {
    const isConnected = !!existingWorkspace;
    const fileCount = Number(workspaceMeta.fileCount || 0);
    const files = workspaceMeta.files || [];
    const indexedLabel = existingWorkspace?.last_indexed_at
        ? `Last indexed ${existingWorkspace.last_indexed_at}`
        : "Not indexed yet";

    state.pathInput.value = existingWorkspace?.root_path || "";
    state.displayNameInput.value = existingWorkspace?.display_name || "";
    state.browseButton.textContent = "Choose folder";
    state.browseButton.disabled = false;
    state.errorNode.hidden = true;
    state.errorNode.textContent = "Choose a local folder.";
    state.submitButton.textContent = isConnected ? "Save" : "Connect";
    state.reindexButton.hidden = !isConnected;
    state.disconnectButton.hidden = !isConnected;
    state.filesSection.hidden = !isConnected;
    state.statusTitle.textContent = isConnected
        ? (existingWorkspace.display_name || "Workspace connected")
        : "Not connected";
    state.statusMeta.textContent = isConnected
        ? `${indexedLabel} · ${fileCount} file${fileCount === 1 ? "" : "s"}`
        : "Choose a local folder to make project files available to chats.";
    state.fileCount.textContent = `${fileCount} file${fileCount === 1 ? "" : "s"}`;
    state.filesList.innerHTML = "";

    if (!isConnected) {
        return;
    }

    if (!files.length) {
        state.filesList.textContent = "No indexed files shown yet.";
        return;
    }

    state.filesList.textContent = createWorkspaceTreeText(files);
}


function createWorkspaceTreeText(files) {
    const root = createTreeNode(".");
    for (const file of files || []) {
        addPathToTree(root, String(file.path || "").split("/").filter(Boolean), file.kind || "file");
    }
    return renderTreeNode(root).join("\n");
}


function createTreeNode(name, kind = "directory") {
    return { name, kind, children: new Map() };
}


function addPathToTree(root, parts, kind) {
    if (!parts.length) {
        return;
    }
    let current = root;
    parts.forEach((part, index) => {
        const isLeaf = index === parts.length - 1;
        if (!current.children.has(part)) {
            current.children.set(part, createTreeNode(part, isLeaf ? kind : "directory"));
        }
        current = current.children.get(part);
        if (isLeaf) {
            current.kind = kind;
        }
    });
}


function renderTreeNode(root) {
    const lines = [root.name];
    renderTreeChildren(root, "", lines);
    return lines;
}


function renderTreeChildren(node, prefix, lines) {
    const children = [...node.children.values()].sort((left, right) => {
        if (left.kind !== right.kind) {
            return left.kind === "directory" ? -1 : 1;
        }
        return left.name.localeCompare(right.name);
    });
    children.forEach((child, index) => {
        const isLast = index === children.length - 1;
        lines.push(`${prefix}${isLast ? "└── " : "├── "}${child.name}`);
        renderTreeChildren(child, `${prefix}${isLast ? "    " : "│   "}`, lines);
    });
}


function pumpConfirmQueue(state) {
    if (state.activeRequest || state.isClosing) {
        return;
    }

    const nextRequest = state.queue.shift();
    if (!nextRequest) {
        return;
    }

    state.activeRequest = nextRequest;
    state.eyebrowNode.textContent = nextRequest.eyebrow;
    state.titleNode.textContent = nextRequest.title;
    state.messageNode.textContent = nextRequest.message;
    state.cancelButton.textContent = nextRequest.cancelLabel;
    state.confirmButton.textContent = nextRequest.confirmLabel;
    setConfirmVariant(state.confirmButton, nextRequest.confirmVariant);
    openDialog(state);
    state.confirmButton.focus({ preventScroll: true });
}


function openDialog(state) {
    state.isClosing = false;
    state.lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    state.modal.hidden = false;
    state.modal.dataset.state = "closed";
    document.body.classList.add("modal-open", "is-modal-open");

    window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
            state.modal.dataset.state = "open";
        });
    });
}


function closeDialog(state, onClosed) {
    if (state.modal.hidden || state.isClosing) {
        return;
    }

    state.isClosing = true;
    state.modal.dataset.state = "closing";
    window.setTimeout(() => {
        state.modal.hidden = true;
        state.modal.dataset.state = "closed";
        state.isClosing = false;
        restoreFocus(state);

        if (!hasOpenModal()) {
            document.body.classList.remove("modal-open", "is-modal-open");
        }

        if (typeof onClosed === "function") {
            onClosed();
        }
    }, 240);
}


function resolveConfirm(result) {
    const state = ensureConfirmDialog();
    if (!state.activeRequest) {
        return;
    }

    const { resolve } = state.activeRequest;
    state.activeRequest = null;
    closeDialog(state, () => {
        resolve(result);
        pumpConfirmQueue(state);
    });
}


function resolveProjectDialog(result) {
    const state = ensureProjectDialog();
    if (!state.resolve) {
        return;
    }

    const resolve = state.resolve;
    state.resolve = null;
    closeDialog(state, () => resolve(result));
}


function resolveWorkspaceDialog(result) {
    const state = ensureWorkspaceDialog();
    if (!state.resolve) {
        return;
    }

    const resolve = state.resolve;
    state.resolve = null;
    closeDialog(state, () => resolve(result));
}


function setConfirmVariant(button, variant) {
    button.classList.remove("action-button--danger", "action-button--primary");
    button.classList.add(variant === "primary" ? "action-button--primary" : "action-button--danger");
}


function restoreFocus(state) {
    if (state.lastFocusedElement && document.contains(state.lastFocusedElement)) {
        state.lastFocusedElement.focus({ preventScroll: true });
    }
    state.lastFocusedElement = null;
}


function hasOpenModal() {
    return [...document.querySelectorAll(".modal")].some((modal) => !modal.hidden);
}
