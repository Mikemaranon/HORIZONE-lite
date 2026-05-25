import { elements } from "../dom.js";
import { createEmptyListItem, escapeHtml } from "../html.js";
import { getActiveProject, getProjectConversations } from "../selectors.js";
import { state } from "../state.js";


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
    elements.projectChatCount.textContent = `${totalChats} chat${totalChats === 1 ? "" : "s"} · ${totalDocuments} document${totalDocuments === 1 ? "" : "s"}`;

    if (!projectConversations.length) {
        elements.projectConversationsList.innerHTML = createEmptyListItem(
            "This project does not have chats yet. Use the + button to create the first one."
        );
        return;
    }

    elements.projectConversationsList.innerHTML = projectConversations
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
