let confirmState = null;
let projectDialogState = null;


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
