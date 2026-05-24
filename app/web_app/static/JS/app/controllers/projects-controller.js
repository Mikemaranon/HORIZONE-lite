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
        showStatus(error.message || "No se pudieron cargar los documentos del proyecto.", true);
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
        showStatus(error.message || "No se pudo crear el proyecto.", true);
    }
}


export async function handleNewProjectChat({ handleConversationSelect, closeSidebarOnMobile }) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Selecciona primero un proyecto.", true);
        return;
    }
    if (!getSelectedModel()) {
        showStatus("Selecciona un modelo disponible antes de crear el chat del proyecto.", true);
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
        showStatus(error.message || "No se pudo crear el chat del proyecto.", true);
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
        showStatus("No hay un proyecto activo para personalizar.", true);
        return;
    }

    const name = elements.projectNameInput.value.trim();
    if (!name) {
        showStatus("El proyecto necesita un nombre.", true);
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
        showStatus(error.message || "No se pudo guardar la personalización.", true);
    }
}


export async function handleProjectDelete() {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("No hay un proyecto activo para borrar.", true);
        return;
    }

    const confirmed = await confirmAction({
        title: `Borrar "${activeProject.name}"`,
        message: "El proyecto se elimina de la lista. Sus chats se conservarán como chats puntuales.",
        confirmLabel: "Borrar proyecto",
        eyebrow: "Proyecto",
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
        showStatus(error.message || "No se pudo borrar el proyecto.", true);
    }
}


export async function handleDocumentsOpen() {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Selecciona primero un proyecto.", true);
        return;
    }

    try {
        const data = await loadProjectDocuments(activeProject.id);
        applyProjectDocumentsPayload(data);
        setStagedDocuments([]);
        renderDocumentsFileList();
        openDocumentsModal();
    } catch (error) {
        showStatus(error.message || "No se pudieron cargar los documentos del proyecto.", true);
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
        showStatus("Selecciona primero un proyecto.", true);
        return;
    }

    try {
        setLoading(true);
        await deleteProjectDocument(documentId);
        const data = await loadProjectDocuments(activeProject.id);
        applyProjectDocumentsPayload(data);
        renderApp();
        showStatus("Documento eliminado del proyecto.");
    } catch (error) {
        showStatus(error.message || "No se pudo borrar el documento.", true);
    } finally {
        setLoading(false);
    }
}


async function uploadDocuments(files) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Selecciona primero un proyecto.", true);
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
                ? "Documento agregado al proyecto."
                : `${files.length} documentos agregados al proyecto.`
        );
    } catch (error) {
        showStatus(error.message || "No se pudieron subir los documentos.", true);
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
