import { elements } from "../dom.js";
import { createEmptyListItem, createModelAvatarMarkup, escapeHtml } from "../html.js";
import { getActiveProject, getProjectConversations } from "../selectors.js";
import { state } from "../state.js";

const DEFAULT_AGENT_COLOR = "#1c8b59";


export function renderProjectSpace(onConversationSelect, onConversationDelete) {
    const activeProject = getActiveProject();
    const hasProjectWorkspace = state.workspaceMode === "project" && !!activeProject;

    elements.projectSpace.hidden = !hasProjectWorkspace;

    if (!activeProject) {
        elements.projectConversationsList.innerHTML = "";
        elements.projectChatCount.textContent = "0 chats";
        return;
    }

    elements.projectSpaceTitle.textContent = activeProject.name;
    elements.projectSpaceDescription.textContent = activeProject.description
        || "This project has its own space, separate from standalone chats.";
    elements.projectNameInput.value = activeProject.name || "";
    elements.projectDescriptionInput.value = activeProject.description || "";
    elements.projectSystemPromptInput.value = activeProject.system_prompt || "";

    const projectConversations = getProjectConversations(activeProject.id);
    const totalChats = projectConversations.length;
    const totalDocuments = state.projectDocuments.length;
    const workspaceLabel = state.projectWorkspace ? "connected" : "disconnected";
    elements.projectChatCount.textContent = `${totalChats} chat${totalChats === 1 ? "" : "s"} · ${totalDocuments} document${totalDocuments === 1 ? "" : "s"} · ${workspaceLabel}`;

    const conversationsMarkup = !projectConversations.length
        ? createEmptyListItem("This project does not have chats yet. Use the + button to create the first one.")
        : projectConversations
        .map((conversation) => {
            const activeClass = conversation.id === state.activeConversationId ? " is-active" : "";
            return `
                <div class="project-chat-card${activeClass}" data-conversation-row="${conversation.id}">
                    <button class="project-chat-card__main" type="button" data-conversation-id="${conversation.id}">
                        <span class="project-chat-card__title">${escapeHtml(conversation.title || "New chat")}</span>
                    </button>
                    <button
                        class="icon-button conversation-row__delete"
                        type="button"
                        data-delete-conversation-id="${conversation.id}"
                        aria-label="Delete chat"
                        title="Delete chat"
                    >
                        ×
                    </button>
                </div>
            `;
        })
        .join("");

    elements.projectConversationsList.innerHTML = conversationsMarkup;

    if (onConversationSelect) {
        elements.projectConversationsList.querySelectorAll("[data-conversation-id]").forEach((element) => {
            element.addEventListener("click", () => onConversationSelect(Number(element.dataset.conversationId)));
        });
    }

    if (onConversationDelete) {
        elements.projectConversationsList.querySelectorAll("[data-delete-conversation-id]").forEach((element) => {
            element.addEventListener("click", () => {
                onConversationDelete(Number(element.dataset.deleteConversationId));
            });
        });
    }
}


export function renderProjectModelsManager() {
    if (!elements.projectModelsList) {
        return;
    }

    const projectModels = state.projectModels || [];
    const summary = `${projectModels.length} project agent${projectModels.length === 1 ? "" : "s"}.`;

    if (elements.projectModelsSummary) {
        elements.projectModelsSummary.textContent = summary;
    }

    elements.projectModelsList.innerHTML = projectModels.length
        ? projectModels.map((projectModel) => createProjectModelRowMarkup(projectModel)).join("")
        : `<div class="profile-switch__empty">No project agents yet. Add one from the form.</div>`;

    renderProjectModelFormOptions();
    syncProjectModelForm();
}


function createProjectModelRowMarkup(projectModel) {
    const model = projectModel.model || {};
    const profile = projectModel.profile || {};
    const modelLabel = model.display_name || model.name || "Model";
    const providerLabel = model.provider_name || model.provider || "Provider";
    const isEditing = projectModel.id === state.projectModelFormId;
    const rowClasses = [
        "project-model-row",
        projectModel.is_default ? "is-default" : "",
        isEditing ? "is-editing" : "",
    ].filter(Boolean).join(" ");

    return `
        <article class="${rowClasses}"${isEditing ? ' aria-current="true"' : ""}>
            <button
                class="project-model-row__edit"
                type="button"
                data-edit-project-model-id="${projectModel.id}"
                aria-label="Edit agent ${escapeHtml(projectModel.nickname || modelLabel)}"
                title="Edit agent"
            >
                ${createModelAvatarMarkup(modelLabel, model.icon_image, "model-badge-avatar model-badge-avatar--switch")}
                <span class="project-model-row__copy">
                    <strong>
                        ${escapeHtml(projectModel.nickname || modelLabel)}
                        ${isEditing ? `<span class="project-model-row__badge project-model-row__badge--editing">Editing</span>` : ""}
                        ${projectModel.is_default ? `<span class="project-model-row__badge">Default</span>` : ""}
                    </strong>
                    <span>${escapeHtml(modelLabel)} · ${escapeHtml(profile.name || "Profile")}</span>
                    <span>${escapeHtml(providerLabel)}</span>
                </span>
            </button>
            <div class="project-model-row__actions">
                <button
                    class="icon-button project-model-row__action project-model-row__action--danger"
                    type="button"
                    data-delete-project-model-id="${projectModel.id}"
                    aria-label="Delete agent ${escapeHtml(projectModel.nickname || modelLabel)}"
                    title="Delete"
                >
                    <img src="/static/assets/icons/trash.png" alt="">
                </button>
            </div>
        </article>
    `;
}


export function renderProjectModelFormOptions() {
    const selectedModelId = Number(elements.projectModelSystemModelIdInput?.value || "0") || null;
    const selectedProfileId = Number(elements.projectModelProfileIdInput?.value || "0") || null;

    if (elements.projectModelSystemModelOptions) {
        elements.projectModelSystemModelOptions.innerHTML = (state.models || [])
            .map((model) => createProjectModelOptionMarkup({
                id: model.id,
                kind: "model",
                label: model.display_name || model.name,
                meta: `${model.name} · ${model.provider_name || model.provider || "Provider"}`,
                isSelected: model.id === selectedModelId,
            }))
            .join("");
    }

    if (elements.projectModelProfileOptions) {
        elements.projectModelProfileOptions.innerHTML = (state.profiles || [])
            .map((profile) => createProjectModelOptionMarkup({
                id: profile.id,
                kind: "profile",
                label: profile.name,
                meta: profile.personality || profile.system_prompt || "No prompt",
                isSelected: profile.id === selectedProfileId,
            }))
            .join("");
    }
}


function syncProjectModelForm() {
    const editingProjectModel = state.projectModels.find(
        (projectModel) => projectModel.id === state.projectModelFormId
    ) || null;
    const isEditing = Boolean(editingProjectModel);
    const selectedModel = editingProjectModel?.model
        || state.models.find((model) => model.is_default)
        || state.models[0]
        || null;
    const selectedProfile = editingProjectModel?.profile
        || state.profiles.find((profile) => profile.is_default)
        || state.profiles[0]
        || null;

    if (elements.projectModelFormTitle) {
        elements.projectModelFormTitle.textContent = isEditing ? "Edit agent" : "Add agent";
    }
    if (elements.projectModelSubmitButton) {
        elements.projectModelSubmitButton.textContent = isEditing ? "Save agent" : "Add agent";
    }
    if (elements.projectModelIdInput) {
        elements.projectModelIdInput.value = isEditing ? String(editingProjectModel.id) : "";
    }
    if (elements.projectModelNicknameInput) {
        elements.projectModelNicknameInput.value = editingProjectModel?.nickname || "";
    }
    if (elements.projectModelColorInput) {
        elements.projectModelColorInput.value = normalizeAgentColor(editingProjectModel?.color);
    }
    if (elements.projectModelSystemModelInput) {
        elements.projectModelSystemModelInput.value = selectedModel ? createModelOptionValue(selectedModel) : "";
        elements.projectModelSystemModelInput.setAttribute("aria-expanded", "false");
    }
    if (elements.projectModelSystemModelIdInput) {
        elements.projectModelSystemModelIdInput.value = selectedModel ? String(selectedModel.id) : "";
    }
    if (elements.projectModelProfileInput) {
        elements.projectModelProfileInput.value = selectedProfile ? createProfileOptionValue(selectedProfile) : "";
        elements.projectModelProfileInput.setAttribute("aria-expanded", "false");
    }
    if (elements.projectModelProfileIdInput) {
        elements.projectModelProfileIdInput.value = selectedProfile ? String(selectedProfile.id) : "";
    }
    if (elements.projectModelSystemPromptInput) {
        elements.projectModelSystemPromptInput.value = editingProjectModel?.system_prompt || "";
    }
    if (elements.projectModelDefaultInput) {
        elements.projectModelDefaultInput.checked = editingProjectModel
            ? Boolean(editingProjectModel.is_default)
            : !state.projectModels.length;
    }

    syncProjectModelSearchClearButtons();
    closeProjectModelComboboxOptions();
}


function normalizeAgentColor(color) {
    const normalized = String(color || DEFAULT_AGENT_COLOR).trim();
    return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized.toLowerCase() : DEFAULT_AGENT_COLOR;
}


function createModelOptionValue(model) {
    return model.display_name || model.name || "";
}


function createProfileOptionValue(profile) {
    return profile.name || "";
}


function createProjectModelOptionMarkup({ id, kind, label, meta, isSelected }) {
    return `
        <button
            class="app-combobox__option${isSelected ? " is-selected" : ""}"
            type="button"
            role="option"
            aria-selected="${isSelected ? "true" : "false"}"
            data-project-model-option-kind="${escapeHtml(kind)}"
            data-project-model-option-id="${id}"
            data-project-model-option-label="${escapeHtml(label || "")}"
        >
            <span class="app-combobox__option-label">${escapeHtml(label || "")}</span>
            <span class="app-combobox__option-meta">${escapeHtml(meta || "")}</span>
        </button>
    `;
}


export function setProjectModelComboboxSelection(kind, id) {
    const selectedId = Number(id || "0") || null;
    const collection = kind === "model" ? state.models : state.profiles;
    const selectedItem = collection.find((item) => item.id === selectedId) || null;
    const input = getProjectModelComboboxInput(kind);
    const idInput = getProjectModelComboboxIdInput(kind);

    if (input) {
        input.value = selectedItem
            ? (kind === "model" ? createModelOptionValue(selectedItem) : createProfileOptionValue(selectedItem))
            : "";
    }
    if (idInput) {
        idInput.value = selectedItem ? String(selectedItem.id) : "";
    }

    renderProjectModelFormOptions();
    filterProjectModelComboboxOptions(kind, "");
    closeProjectModelComboboxOptions(kind);
    syncProjectModelSearchClearButtons();
}


export function clearProjectModelCombobox(kind) {
    const input = getProjectModelComboboxInput(kind);
    const idInput = getProjectModelComboboxIdInput(kind);

    if (input) {
        input.value = "";
        input.focus({ preventScroll: true });
    }
    if (idInput) {
        idInput.value = "";
    }

    renderProjectModelFormOptions();
    filterProjectModelComboboxOptions(kind, "");
    openProjectModelComboboxOptions(kind);
    syncProjectModelSearchClearButtons();
}


export function openProjectModelComboboxOptions(kind) {
    const options = getProjectModelComboboxOptions(kind);
    const input = getProjectModelComboboxInput(kind);

    if (options) {
        options.hidden = false;
    }
    if (input) {
        input.setAttribute("aria-expanded", "true");
    }
}


export function closeProjectModelComboboxOptions(kind = null) {
    const kinds = kind ? [kind] : ["model", "profile"];

    for (const item of kinds) {
        const options = getProjectModelComboboxOptions(item);
        const input = getProjectModelComboboxInput(item);
        if (options) {
            options.hidden = true;
        }
        if (input) {
            input.setAttribute("aria-expanded", "false");
        }
    }
}


export function filterProjectModelComboboxOptions(kind, query) {
    const options = getProjectModelComboboxOptions(kind);
    if (!options) {
        return;
    }

    const normalized = String(query || "").trim().toLowerCase();
    let visibleCount = 0;

    options.querySelectorAll("[data-project-model-option-kind]").forEach((option) => {
        const matches = normalized ? option.textContent.toLowerCase().includes(normalized) : true;
        option.hidden = !matches;
        if (matches) {
            visibleCount += 1;
        }
    });

    options.classList.toggle("is-empty", visibleCount === 0);
}


export function syncProjectModelSearchClearButtons() {
    if (elements.projectModelSystemModelClearButton) {
        elements.projectModelSystemModelClearButton.hidden = !elements.projectModelSystemModelInput?.value;
    }
    if (elements.projectModelProfileClearButton) {
        elements.projectModelProfileClearButton.hidden = !elements.projectModelProfileInput?.value;
    }
}


function getProjectModelComboboxInput(kind) {
    return kind === "model"
        ? elements.projectModelSystemModelInput
        : elements.projectModelProfileInput;
}


function getProjectModelComboboxIdInput(kind) {
    return kind === "model"
        ? elements.projectModelSystemModelIdInput
        : elements.projectModelProfileIdInput;
}


function getProjectModelComboboxOptions(kind) {
    return kind === "model"
        ? elements.projectModelSystemModelOptions
        : elements.projectModelProfileOptions;
}


export function renderDocumentsFileList() {
    if (
        !elements.documentsFileList
        || !elements.documentsDirectoryTree
        || !elements.documentsCurrentFolderLabel
        || !elements.documentsCurrentFolderMeta
        || !elements.documentsDeleteFolderButton
    ) {
        return;
    }

    const uploadedDocuments = state.projectDocuments || [];
    const folders = state.projectDocumentFolders || [];
    const selectedFolderId = state.activeProjectDocumentFolderId ?? null;
    const selectedFolder = folders.find((folder) => folder.id === selectedFolderId) || null;
    const selectedFolderPath = selectedFolder?.path || "Project root";
    const currentFolderDocuments = uploadedDocuments.filter(
        (document) => normalizeFolderId(document.folder_id) === selectedFolderId
    );
    const stagedDocuments = (state.stagedDocuments || []).filter(
        (document) => normalizeFolderId(document.folderId) === selectedFolderId
    );

    elements.documentsCurrentFolderLabel.textContent = selectedFolderPath;
    elements.documentsCurrentFolderMeta.textContent = buildCurrentFolderMeta(
        currentFolderDocuments.length,
        uploadedDocuments.length,
        selectedFolderPath,
    );
    elements.documentsDeleteFolderButton.hidden = !selectedFolder;
    elements.documentsDeleteFolderButton.dataset.folderId = selectedFolder ? String(selectedFolder.id) : "";
    elements.documentsDirectoryTree.innerHTML = renderDirectoryTree(
        folders,
        uploadedDocuments,
        selectedFolderId,
    );

    if (!currentFolderDocuments.length && !stagedDocuments.length) {
        elements.documentsFileList.innerHTML = `
            <p class="documents-file-list__empty">
                No files in ${escapeHtml(selectedFolderPath)} yet.
            </p>
        `;
        return;
    }

    const uploadedMarkup = currentFolderDocuments.map((file) => `
        <div class="documents-file">
            <div class="documents-file__copy">
                <span class="documents-file__name">${escapeHtml(file.filename)}</span>
                <span class="documents-file__meta">${escapeHtml(formatDocumentMeta(file))}</span>
            </div>
            <div class="documents-file__actions">
                <span
                    class="documents-file__drag"
                    draggable="true"
                    data-project-document-drag-id="${file.id}"
                    title="Drag to another folder"
                >
                    Move
                </span>
                <button
                    class="ghost-button ghost-button--compact"
                    type="button"
                    data-delete-project-document-id="${file.id}"
                >
                    Delete
                </button>
            </div>
        </div>
    `).join("");

    const stagedMarkup = stagedDocuments.map((file) => `
        <div class="documents-file documents-file--pending">
            <div class="documents-file__copy">
                <span class="documents-file__name">${escapeHtml(file.name)}</span>
                <span class="documents-file__meta">${escapeHtml(`${file.sizeLabel} · uploading…`)}</span>
            </div>
        </div>
    `).join("");

    elements.documentsFileList.innerHTML = `${uploadedMarkup}${stagedMarkup}`;
}


function formatDocumentMeta(document) {
    const sizeInBytes = Number(document.size_bytes || 0);

    if (sizeInBytes < 1024) {
        return `${sizeInBytes} B`;
    }
    if (sizeInBytes < 1024 * 1024) {
        return `${(sizeInBytes / 1024).toFixed(1)} KB`;
    }
    return `${(sizeInBytes / 1024 / 1024).toFixed(1)} MB`;
}


function buildCurrentFolderMeta(currentFolderCount, totalCount, selectedFolderPath) {
    const currentLabel = `${currentFolderCount} file${currentFolderCount === 1 ? "" : "s"} here`;
    const totalLabel = `${totalCount} total`;

    if (selectedFolderPath === "Project root") {
        return `${currentLabel} · ${totalLabel} in the project library.`;
    }

    return `${currentLabel} · ${totalLabel} in the project library. New uploads go to this folder.`;
}


function renderDirectoryTree(folders, documents, selectedFolderId) {
    const folderCounts = buildFolderDocumentCountMap(documents);
    const childrenByParent = buildFolderChildrenMap(folders);

    return `
        <div class="documents-tree">
            ${renderFolderNode({
                folder: null,
                childrenByParent,
                folderCounts,
                selectedFolderId,
            })}
        </div>
    `;
}


function renderFolderNode({ folder, childrenByParent, folderCounts, selectedFolderId }) {
    const folderId = folder?.id ?? null;
    const children = childrenByParent.get(folderId) || [];
    const folderName = folder?.name || "Project root";
    const folderPath = folder?.path || "Project root";
    const isSelected = folderId === selectedFolderId;
    const directCount = folderCounts.get(folderId) || 0;
    const folderIdValue = folderId ?? "";

    const childrenMarkup = children.length
        ? `
            <div class="documents-tree__children">
                ${children.map((child) => renderFolderNode({
                    folder: child,
                    childrenByParent,
                    folderCounts,
                    selectedFolderId,
                })).join("")}
            </div>
        `
        : "";

    return `
        <div
            class="documents-tree__node"
            data-document-folder-drop-target="true"
            data-folder-id="${escapeHtml(String(folderIdValue))}"
        >
            <button
                class="documents-tree__item${isSelected ? " is-active" : ""}"
                type="button"
                data-document-folder-select="true"
                data-folder-id="${escapeHtml(String(folderIdValue))}"
                title="${escapeHtml(folderPath)}"
            >
                <span class="documents-tree__name">${escapeHtml(folderName)}</span>
                <span class="documents-tree__meta">${directCount}</span>
            </button>
            ${childrenMarkup}
        </div>
    `;
}


function buildFolderChildrenMap(folders) {
    const map = new Map();
    map.set(null, []);

    for (const folder of folders || []) {
        const parentId = normalizeFolderId(folder.parent_folder_id);
        if (!map.has(parentId)) {
            map.set(parentId, []);
        }
        map.get(parentId).push(folder);
        if (!map.has(folder.id)) {
            map.set(folder.id, []);
        }
    }

    return map;
}


function buildFolderDocumentCountMap(documents) {
    const counts = new Map();
    counts.set(null, 0);

    for (const document of documents || []) {
        const folderId = normalizeFolderId(document.folder_id);
        counts.set(folderId, (counts.get(folderId) || 0) + 1);
    }

    return counts;
}


function normalizeFolderId(folderId) {
    return folderId === undefined || folderId === null || folderId === "" ? null : Number(folderId);
}
