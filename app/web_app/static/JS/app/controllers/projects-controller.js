import {
    createConversation,
    createProject,
    deleteProject,
    deleteProjectDocument,
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


export async function handleDocumentsSelected(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    await uploadDocuments(files);
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
    await uploadDocuments(Array.from(event.dataTransfer.files || []));
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
        const data = await loadProjectDocuments(activeProject.id);
        applyProjectDocumentsPayload(data);
        renderApp();
        showStatus("Document removed from the project.");
    } catch (error) {
        showStatus(error.message || "The document could not be deleted.", true);
    } finally {
        setLoading(false);
    }
}


async function uploadDocuments(files) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    if (!files.length) {
        return;
    }

    stageDocuments(files);

    try {
        setLoading(true);
        await uploadProjectDocuments(activeProject.id, files);
        const data = await loadProjectDocuments(activeProject.id);
        applyProjectDocumentsPayload(data);
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


function stageDocuments(fileList) {
    const files = Array.from(fileList || []);
    setStagedDocuments(files.map((file) => ({
        name: file.name,
        sizeLabel: formatFileSize(file.size),
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
