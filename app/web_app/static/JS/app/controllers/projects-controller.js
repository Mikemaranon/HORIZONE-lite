import {
    createProjectDocumentFolder,
    createConversation,
    createProject,
    deleteProjectDocumentFolder,
    deleteProject,
    deleteProjectDocument,
    moveProjectDocument,
    updateProject,
    uploadProjectDocuments,
} from "../api.js";
import { renderApp } from "../app-runtime.js";
import { setLoading } from "../composer-ui.js";
import { requestProjectDetails, confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import { openDocumentsModal, closeProjectCustomizeModal } from "../modal-ui.js";
import { renderDocumentsFileList } from "../render.js";
import { getActiveProject, getSelectedProfileId } from "../selectors.js";
import {
    applyConversationsPayload,
    applyProjectDocumentsPayload,
    applyProjectsPayload,
    clearActiveConversation,
    enterHomeWorkspace,
    enterProjectWorkspace,
    setActiveProjectDocumentFolderId,
    setProjectDocumentFolders,
    setProjectDocuments,
    setStagedDocuments,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import { loadConversations, loadProjectDocuments, loadProjects } from "../store.js";
import { getActualProvider, getSelectedModel } from "../provider-helpers.js";


export async function handleProjectSelect(projectId, { closeSidebarOnMobile }) {
    enterProjectWorkspace(projectId);

    try {
        const data = await loadProjectDocuments(projectId);
        applyProjectDocumentsPayload(data);
    } catch (error) {
        setProjectDocuments([]);
        setProjectDocumentFolders([]);
        setActiveProjectDocumentFolderId(null);
        showStatus(error.message || "The project documents could not be loaded.", true);
    }

    renderApp();
    closeSidebarOnMobile();
}


export async function handleNewProject({ closeSidebarOnMobile }) {
    const projectDetails = await requestProjectDetails();
    if (!projectDetails) {
        return;
    }

    try {
        const payload = await createProject(projectDetails);
        const projects = await loadProjects();
        applyProjectsPayload(projects);
        enterProjectWorkspace(payload.project.id);
        clearActiveConversation();
        renderApp();
        closeSidebarOnMobile();
    } catch (error) {
        showStatus(error.message || "The project could not be created.", true);
    }
}


export async function handleNewProjectChat({ handleConversationSelect, closeSidebarOnMobile }) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }
    if (!getSelectedModel()) {
        showStatus("Select an available model before creating the project chat.", true);
        return;
    }

    try {
        const payload = await createConversation({
            title: `${activeProject.name} · chat`,
            project_id: activeProject.id,
            profile_id: getSelectedProfileId(),
            provider: getActualProvider(),
            model: getSelectedModel(),
        });

        const conversations = await loadConversations();
        applyConversationsPayload(conversations);
        renderApp();
        await handleConversationSelect(payload.conversation.id, { closeSidebarOnMobile });
        closeSidebarOnMobile();
    } catch (error) {
        showStatus(error.message || "The project chat could not be created.", true);
    }
}


export function handleWorkspaceSettingsOpen({ closeSidebarOnMobile }) {
    closeSidebarOnMobile();
    window.location.href = "/settings";
}


export function toggleProjectActionsMenu() {
    if (isProjectActionsMenuOpen()) {
        closeProjectActionsMenu();
        return;
    }

    openProjectActionsMenu();
}


export function openProjectActionsMenu() {
    if (!elements.projectActionsMenu || !elements.projectActionsMenuButton) {
        return;
    }

    elements.projectActionsMenu.hidden = false;
    elements.projectActionsMenuButton.setAttribute("aria-expanded", "true");
}


export function closeProjectActionsMenu() {
    if (!elements.projectActionsMenu || !elements.projectActionsMenuButton) {
        return false;
    }

    if (elements.projectActionsMenu.hidden) {
        return false;
    }

    elements.projectActionsMenu.hidden = true;
    elements.projectActionsMenuButton.setAttribute("aria-expanded", "false");
    return true;
}


export function handleProjectActionsDocumentClick(event) {
    if (!isProjectActionsMenuOpen()) {
        return;
    }

    if (event.target.closest(".project-actions-menu")) {
        return;
    }

    closeProjectActionsMenu();
}


export function handleProjectConnectWorkspace() {
    closeProjectActionsMenu();
    showStatus("Connect to workspace is ready for the next design step.");
}


export function handleBackToProject() {
    if (!state.activeProjectId) {
        return;
    }

    enterProjectWorkspace(state.activeProjectId);
    renderApp();
}


export async function handleProjectCustomizeSubmit(event) {
    event.preventDefault();

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("There is no active project to customize.", true);
        return;
    }

    const name = elements.projectNameInput.value.trim();
    if (!name) {
        showStatus("The project needs a name.", true);
        return;
    }

    try {
        await updateProject({
            id: activeProject.id,
            name,
            description: elements.projectDescriptionInput.value.trim(),
            system_prompt: elements.projectSystemPromptInput.value.trim(),
        });

        const projects = await loadProjects();
        applyProjectsPayload(projects);
        renderApp();
        closeProjectCustomizeModal();
    } catch (error) {
        showStatus(error.message || "The customization could not be saved.", true);
    }
}


export async function handleProjectDelete() {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("There is no active project to delete.", true);
        return;
    }

    const confirmed = await confirmAction({
        title: `Delete "${activeProject.name}"`,
        message: "The project will be removed from the list. Its chats will remain as standalone chats.",
        confirmLabel: "Delete project",
        eyebrow: "Project",
    });

    if (!confirmed) {
        return;
    }

    try {
        await deleteProject(activeProject.id);
        enterHomeWorkspace();

        const [projects, conversations] = await Promise.all([loadProjects(), loadConversations()]);
        applyProjectsPayload(projects);
        applyConversationsPayload(conversations);
        renderApp();
        closeProjectCustomizeModal();
    } catch (error) {
        showStatus(error.message || "The project could not be deleted.", true);
    }
}


export async function handleDocumentsOpen() {
    closeProjectActionsMenu();

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    try {
        const data = await loadProjectDocuments(activeProject.id);
        applyProjectDocumentsPayload(data);
        setStagedDocuments([]);
        renderDocumentsFileList();
        openDocumentsModal();
    } catch (error) {
        showStatus(error.message || "The project documents could not be loaded.", true);
    }
}


function isProjectActionsMenuOpen() {
    return Boolean(elements.projectActionsMenu && !elements.projectActionsMenu.hidden);
}


export async function handleDocumentsSelected(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    await uploadDocuments(files, getSelectedFolderId());
}


export function handleDocumentsDragOver(event) {
    event.preventDefault();
    elements.documentsDropzone.classList.add("is-dragging");
}


export function handleDocumentsDragLeave() {
    elements.documentsDropzone.classList.remove("is-dragging");
}


export async function handleDocumentsDrop(event) {
    event.preventDefault();
    elements.documentsDropzone.classList.remove("is-dragging");
    await uploadDocuments(Array.from(event.dataTransfer.files || []), getSelectedFolderId());
}


export function handleProjectDocumentFolderSelect(event) {
    const folderTarget = event.target.closest("[data-document-folder-select]");
    if (!folderTarget) {
        return;
    }

    setActiveProjectDocumentFolderId(parseFolderId(folderTarget.dataset.folderId));
    renderDocumentsFileList();
}


export async function handleProjectDocumentFolderCreate(event) {
    event.preventDefault();

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    const name = elements.documentsFolderInput?.value.trim();
    if (!name) {
        showStatus("The folder needs a name.", true);
        return;
    }

    try {
        setLoading(true);
        const payload = await createProjectDocumentFolder({
            project_id: activeProject.id,
            parent_folder_id: getSelectedFolderId(),
            name,
        });
        elements.documentsFolderInput.value = "";
        setActiveProjectDocumentFolderId(payload.folder.id);
        await refreshProjectDocuments(activeProject.id);
        renderDocumentsFileList();
        showStatus(`Folder "${payload.folder.name}" created.`);
    } catch (error) {
        showStatus(error.message || "The folder could not be created.", true);
    } finally {
        setLoading(false);
    }
}


export async function handleProjectDocumentFolderDelete() {
    const activeProject = getActiveProject();
    const selectedFolderId = getSelectedFolderId();
    const selectedFolder = (state.projectDocumentFolders || []).find((folder) => folder.id === selectedFolderId);

    if (!activeProject || !selectedFolder) {
        showStatus("Select a folder first.", true);
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Documents",
        title: `Delete folder "${selectedFolder.name}"`,
        message: "The folder and its subfolders will be removed. Documents inside them will be kept and moved back to Project root.",
        confirmLabel: "Delete folder",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        setLoading(true);
        await deleteProjectDocumentFolder(selectedFolder.id);
        setActiveProjectDocumentFolderId(selectedFolder.parent_folder_id ?? null);
        await refreshProjectDocuments(activeProject.id);
        renderApp();
        showStatus(`Folder "${selectedFolder.name}" deleted.`);
    } catch (error) {
        showStatus(error.message || "The folder could not be deleted.", true);
    } finally {
        setLoading(false);
    }
}


export function handleDocumentsDirectoryDragOver(event) {
    const folderTarget = event.target.closest("[data-document-folder-drop-target]");
    if (!folderTarget) {
        return;
    }

    event.preventDefault();
    folderTarget.classList.add("is-dragging-over");
}


export function handleDocumentsDirectoryDragLeave(event) {
    const folderTarget = event.target.closest("[data-document-folder-drop-target]");
    if (!folderTarget) {
        return;
    }

    const relatedTarget = event.relatedTarget;
    if (relatedTarget && folderTarget.contains(relatedTarget)) {
        return;
    }

    folderTarget.classList.remove("is-dragging-over");
}


export async function handleDocumentsDirectoryDrop(event) {
    const folderTarget = event.target.closest("[data-document-folder-drop-target]");
    if (!folderTarget) {
        return;
    }

    event.preventDefault();
    folderTarget.classList.remove("is-dragging-over");

    const targetFolderId = parseFolderId(folderTarget.dataset.folderId);
    const movedDocumentId = Number(event.dataTransfer.getData("application/x-project-document-id") || 0);
    if (movedDocumentId) {
        await moveDocumentToFolder(movedDocumentId, targetFolderId);
        return;
    }

    const files = Array.from(event.dataTransfer.files || []);
    if (files.length) {
        await uploadDocuments(files, targetFolderId);
    }
}


export function handleProjectDocumentDragStart(event) {
    const dragSource = event.target.closest("[data-project-document-drag-id]");
    if (!dragSource || !event.dataTransfer) {
        return;
    }

    const documentId = Number(dragSource.dataset.projectDocumentDragId);
    if (!documentId) {
        return;
    }

    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-project-document-id", String(documentId));
}


export function handleProjectDocumentDragEnd() {
    clearDirectoryDragState();
}


export async function handleProjectDocumentDelete(documentId) {
    if (!documentId) {
        return;
    }

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    try {
        setLoading(true);
        await deleteProjectDocument(documentId);
        await refreshProjectDocuments(activeProject.id);
        renderApp();
        showStatus("Document removed from the project.");
    } catch (error) {
        showStatus(error.message || "The document could not be deleted.", true);
    } finally {
        setLoading(false);
    }
}

async function uploadDocuments(files, folderId = null) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    if (!files.length) {
        return;
    }

    stageDocuments(files, folderId);

    try {
        setLoading(true);
        await uploadProjectDocuments(activeProject.id, files, folderId);
        await refreshProjectDocuments(activeProject.id);
        setStagedDocuments([]);
        renderApp();
        showStatus(
            files.length === 1
                ? "Document added to the project."
                : `${files.length} documents added to the project.`
        );
    } catch (error) {
        showStatus(error.message || "The documents could not be uploaded.", true);
    } finally {
        setLoading(false);
    }
}


async function moveDocumentToFolder(documentId, folderId) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    try {
        setLoading(true);
        await moveProjectDocument(documentId, folderId);
        await refreshProjectDocuments(activeProject.id);
        renderApp();
        showStatus("Document moved.");
    } catch (error) {
        showStatus(error.message || "The document could not be moved.", true);
    } finally {
        clearDirectoryDragState();
        setLoading(false);
    }
}


async function refreshProjectDocuments(projectId) {
    const data = await loadProjectDocuments(projectId);
    applyProjectDocumentsPayload(data);
}


function stageDocuments(fileList, folderId = null) {
    const files = Array.from(fileList || []);
    setStagedDocuments(files.map((file) => ({
        name: file.name,
        sizeLabel: formatFileSize(file.size),
        folderId,
    })));
    renderDocumentsFileList();
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


function getSelectedFolderId() {
    return state.activeProjectDocumentFolderId ?? null;
}


function parseFolderId(value) {
    return value === undefined || value === null || value === "" ? null : Number(value);
}


function clearDirectoryDragState() {
    elements.documentsDirectoryTree?.querySelectorAll(".is-dragging-over").forEach((element) => {
        element.classList.remove("is-dragging-over");
    });
}
