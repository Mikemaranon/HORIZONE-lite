import {
    connectProjectWorkspace,
    createProjectModel,
    createProjectDocumentFolder,
    createConversation,
    createProject,
    deleteProjectModel,
    deleteProjectWorkspace,
    deleteProjectDocumentFolder,
    deleteProject,
    deleteProjectDocument,
    indexProjectWorkspace,
    loadWorkspaceFiles,
    moveProjectDocument,
    updateProject,
    updateProjectModel,
    updateConversation,
    uploadProjectDocuments,
} from "../api.js";
import { renderApp } from "../app-runtime.js";
import { setLoading } from "../composer-ui.js";
import { requestProjectDetails, requestWorkspaceDetails, confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import {
    closeProjectCustomizeModal,
    openDocumentsModal,
    closeProjectAgentSwitchModal,
    openProjectAgentSwitchModal,
    openProjectModelsModal,
} from "../modal-ui.js";
import {
    clearProjectModelCombobox,
    closeProjectModelComboboxOptions,
    filterProjectAgentSwitchOptions,
    filterProjectModelComboboxOptions,
    openProjectModelComboboxOptions,
    renderChatPanel,
    renderConversationHeader,
    renderDocumentsFileList,
    renderProjectModelsManager,
    renderProjectSpace,
    setProjectModelComboboxSelection,
    syncProjectModelSearchClearButtons,
} from "../render.js";
import {
    getActiveProject,
    getDefaultProjectAgent,
    getProjectAgentById,
    getSelectedProjectAgent,
} from "../selectors.js";
import {
    applyConversationsPayload,
    applyProjectDocumentsPayload,
    applyProjectModelsPayload,
    applyProjectWorkspacePayload,
    applyWorkspaceFilesPayload,
    applyProjectsPayload,
    clearActiveConversation,
    enterHomeWorkspace,
    enterProjectWorkspace,
    patchActiveConversation,
    setActiveProjectDocumentFolderId,
    setPendingProjectModelId,
    setProjectAgentSwitchMode,
    setProjectDocumentFolders,
    setProjectDocuments,
    setProjectModelFormState,
    setProjectWorkspace,
    setProjectWorkspaceFiles,
    setStagedDocuments,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import {
    loadConversations,
    loadProjectDocuments,
    loadProjectModels,
    loadProjectWorkspace,
    loadProjects,
} from "../store.js";


export async function handleProjectSelect(projectId, { closeSidebarOnMobile }) {
    enterProjectWorkspace(projectId);

    try {
        await refreshProjectWorkspaceState(projectId);
    } catch (error) {
        clearProjectWorkspaceState();
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
        applyProjectModelsPayload(await loadProjectModels(payload.project.id));
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
    const selectedAgent = getSelectedProjectAgent() || getDefaultProjectAgent();
    if (!selectedAgent || !selectedAgent.model) {
        showStatus("Select an available model before creating the project chat.", true);
        return;
    }

    try {
        const payload = await createConversation({
            title: `${activeProject.name} · chat`,
            project_id: activeProject.id,
            project_model_id: selectedAgent.id,
        });

        const conversations = await loadConversations();
        applyConversationsPayload(conversations);
        renderApp();
        await handleConversationSelect(payload.conversation.id, { closeSidebarOnMobile });
        closeSidebarOnMobile();
        elements.composerInput?.focus({ preventScroll: true });
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


export async function handleProjectConnectWorkspace() {
    closeProjectActionsMenu();
    await openWorkspaceConnectionFlow();
}


export async function handleBackToProject() {
    const projectId = state.activeProjectId;
    if (!projectId) {
        return;
    }

    enterProjectWorkspace(projectId);

    try {
        await refreshProjectWorkspaceState(projectId);
    } catch (error) {
        clearProjectWorkspaceState();
        showStatus(error.message || "The project workspace could not be loaded.", true);
    }

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


export async function handleProjectModelsOpen({ editSelectedAgent = false } = {}) {
    closeProjectActionsMenu();

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    try {
        applyProjectModelsPayload(await loadProjectModels(activeProject.id));
        const selectedAgent = editSelectedAgent ? getSelectedProjectAgent() : null;
        setProjectModelFormState(selectedAgent
            ? { mode: "edit", projectModelId: selectedAgent.id }
            : undefined
        );
        renderProjectModelsManager();
        openProjectModelsModal();
        elements.projectModelNicknameInput?.focus({ preventScroll: true });
    } catch (error) {
        showStatus(error.message || "The project agents could not be loaded.", true);
    }
}


export async function handleProjectAgentChangeOpen({ mode = "change" } = {}) {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    if (mode === "quick-add" && (!state.activeConversationId || !state.activeConversation?.project_id)) {
        showStatus("Open a project chat before adding quick agents.", true);
        return;
    }

    try {
        setProjectAgentSwitchMode(mode);
        applyProjectModelsPayload(await loadProjectModels(activeProject.id));
        syncProjectAgentSwitchCopy(mode);
        renderChatPanel();
        openProjectAgentSwitchModal();
        if (elements.projectAgentSwitchSearchInput) {
            elements.projectAgentSwitchSearchInput.value = "";
            filterProjectAgentSwitchOptions("");
            elements.projectAgentSwitchSearchInput.focus({ preventScroll: true });
            elements.projectAgentSwitchSearchInput.select();
        }
    } catch (error) {
        showStatus(error.message || "The project agents could not be loaded.", true);
    }
}


export async function handleProjectAgentOptionSelect(projectModelId) {
    const activeProject = getActiveProject();
    if (!activeProject || !projectModelId) {
        return;
    }

    try {
        if (state.projectAgentSwitchMode === "quick-add") {
            await addQuickProjectAgent(projectModelId);
            return;
        }

        if (state.activeConversationId && state.activeConversation?.project_id) {
            const agent = getProjectAgentById(projectModelId);
            if (!agent) {
                showStatus("The selected project agent was not found.", true);
                return;
            }

            const payload = await updateConversation({
                id: state.activeConversationId,
                project_model_id: projectModelId,
            });
            patchActiveConversation(payload.conversation || {
                project_model_id: projectModelId,
                profile_id: agent.profile_id,
                model_config_id: agent.model_id,
                provider: agent.model?.provider,
                model: agent.model?.name,
            });
            applyConversationsPayload(await loadConversations());
            closeProjectAgentSwitchModal();
            renderChatPanel();
            renderConversationHeader();
            showStatus("Chat agent updated.");
            return;
        }

        setPendingProjectModelId(projectModelId);
        closeProjectAgentSwitchModal();
        renderProjectSpace();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Agent selected for the next project chat.");
    } catch (error) {
        showStatus(error.message || "The default project agent could not be changed.", true);
    }
}


export async function handleConversationAgentChipsClick(event) {
    if (event.target.closest("[data-add-quick-project-agent]")) {
        await handleProjectAgentChangeOpen({ mode: "quick-add" });
        return;
    }

    const removeButton = event.target.closest("[data-remove-quick-project-agent-id]");
    if (removeButton) {
        await removeQuickProjectAgent(Number(removeButton.dataset.removeQuickProjectAgentId));
    }
}


export function handleProjectAgentSearchInput(event) {
    if (event.target.id !== "project-agent-switch-search") {
        return;
    }

    filterProjectAgentSwitchOptions(event.target.value);
}


export function handleProjectAgentSearchClear() {
    if (!elements.projectAgentSwitchSearchInput) {
        return;
    }

    elements.projectAgentSwitchSearchInput.value = "";
    filterProjectAgentSwitchOptions("");
    elements.projectAgentSwitchSearchInput.focus({ preventScroll: true });
}


async function addQuickProjectAgent(projectModelId) {
    const agent = getProjectAgentById(projectModelId);
    if (!agent) {
        showStatus("The selected project agent was not found.", true);
        return;
    }

    if (state.activeConversation?.project_model_id === projectModelId) {
        closeProjectAgentSwitchModal();
        renderConversationHeader();
        showStatus("The active chat agent is already available for @ mentions.");
        return;
    }

    const currentIds = getActiveQuickProjectAgentIds();
    if (currentIds.includes(projectModelId)) {
        closeProjectAgentSwitchModal();
        renderConversationHeader();
        showStatus("Agent is already ready for @ mentions.");
        return;
    }

    const nextIds = [...currentIds, projectModelId];
    const payload = await updateConversation({
        id: state.activeConversationId,
        quick_project_model_ids: nextIds,
    });
    patchActiveConversation(payload.conversation || { quick_project_model_ids: nextIds });
    applyConversationsPayload(await loadConversations());
    closeProjectAgentSwitchModal();
    renderConversationHeader();
    showStatus(`${agent.nickname || "Agent"} added for @ mentions.`);
}


async function removeQuickProjectAgent(projectModelId) {
    if (!state.activeConversationId || !state.activeConversation?.project_id || !projectModelId) {
        return;
    }

    const nextIds = getActiveQuickProjectAgentIds().filter((agentId) => agentId !== projectModelId);
    const payload = await updateConversation({
        id: state.activeConversationId,
        quick_project_model_ids: nextIds,
    });
    patchActiveConversation(payload.conversation || { quick_project_model_ids: nextIds });
    applyConversationsPayload(await loadConversations());
    renderConversationHeader();
}


function getActiveQuickProjectAgentIds() {
    return Array.isArray(state.activeConversation?.quick_project_model_ids)
        ? state.activeConversation.quick_project_model_ids.map(Number).filter(Boolean)
        : [];
}


function syncProjectAgentSwitchCopy(mode) {
    const isQuickAdd = mode === "quick-add";
    if (elements.projectAgentSwitchTitle) {
        elements.projectAgentSwitchTitle.textContent = isQuickAdd ? "Add quick agent" : "Change agent";
    }
    if (elements.projectAgentSwitchCopy) {
        elements.projectAgentSwitchCopy.textContent = isQuickAdd
            ? "Choose an agent to keep ready for @ mentions in this chat."
            : "Choose the agent for this chat, or for the next project chat if none is open.";
    }
}


export async function handleProjectModelsSubmit(event) {
    event.preventDefault();

    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    const projectModelId = Number(elements.projectModelIdInput?.value || "0") || null;
    const nickname = elements.projectModelNicknameInput?.value.trim() || "";
    const modelId = Number(elements.projectModelSystemModelIdInput?.value || "0") || null;
    const profileId = Number(elements.projectModelProfileIdInput?.value || "0") || null;
    const systemPrompt = elements.projectModelSystemPromptInput?.value.trim() || "";
    const isDefault = Boolean(elements.projectModelDefaultInput?.checked);
    const color = elements.projectModelColorInput?.value || "#1c8b59";

    if (!nickname) {
        showStatus("Add a nickname for this project agent.", true);
        return;
    }
    if (!modelId) {
        showStatus("Select a base model.", true);
        return;
    }
    if (!profileId) {
        showStatus("Select a behavior profile.", true);
        return;
    }

    try {
        if (projectModelId) {
            await updateProjectModel({
                id: projectModelId,
                nickname,
                model_id: modelId,
                profile_id: profileId,
                system_prompt: systemPrompt,
                is_default: isDefault,
                color,
            });
        } else {
            await createProjectModel({
                project_id: activeProject.id,
                nickname,
                model_id: modelId,
                profile_id: profileId,
                system_prompt: systemPrompt,
                is_default: isDefault,
                color,
            });
        }
        applyProjectModelsPayload(await loadProjectModels(activeProject.id));
        setProjectModelFormState();
        renderProjectModelsManager();
        renderProjectSpace();
        renderChatPanel();
        renderConversationHeader();
        showStatus(projectModelId ? "Project agent updated." : "Project agent added.");
    } catch (error) {
        showStatus(error.message || "The project agent could not be saved.", true);
    }
}


export async function handleProjectModelListClick(event) {
    const deleteButton = event.target.closest("[data-delete-project-model-id]");
    if (deleteButton) {
        const activeProject = getActiveProject();
        if (!activeProject) {
            showStatus("Select a project first.", true);
            return;
        }

        const projectModelId = Number(deleteButton.dataset.deleteProjectModelId);
        const projectAgent = getProjectAgentById(projectModelId);
        const agentName = projectAgent?.nickname || projectAgent?.model?.display_name || projectAgent?.model?.name || "this agent";
        const confirmed = await confirmAction({
            eyebrow: "Project agent",
            title: `Delete "${agentName}"`,
            message: "This project agent will be removed from the project. Existing chats will keep their conversation history.",
            confirmLabel: "Delete agent",
            confirmVariant: "danger",
        });

        if (!confirmed) {
            return;
        }

        try {
            await deleteProjectModel(projectModelId);
            const payload = await loadProjectModels(activeProject.id);
            applyProjectModelsPayload(payload);
            setProjectModelFormState();
            renderProjectModelsManager();
            renderProjectSpace();
            renderChatPanel();
            renderConversationHeader();
            showStatus("Project agent deleted.");
        } catch (error) {
            showStatus(error.message || "The project agent could not be deleted.", true);
        }
        return;
    }

    const editButton = event.target.closest("[data-edit-project-model-id]");
    if (editButton) {
        setProjectModelFormState({
            mode: "edit",
            projectModelId: Number(editButton.dataset.editProjectModelId),
        });
        renderProjectModelsManager();
        elements.projectModelNicknameInput?.focus({ preventScroll: true });
        return;
    }
}


export function handleProjectModelCreate() {
    setProjectModelFormState();
    renderProjectModelsManager();
    elements.projectModelNicknameInput?.focus({ preventScroll: true });
}


export function handleProjectModelComboboxInput(event) {
    const kind = getProjectModelComboboxKindFromInput(event.target);
    if (!kind) {
        return;
    }

    const idInput = kind === "model"
        ? elements.projectModelSystemModelIdInput
        : elements.projectModelProfileIdInput;
    if (idInput) {
        idInput.value = "";
    }
    filterProjectModelComboboxOptions(kind, event.target.value);
    openProjectModelComboboxOptions(kind);
    syncProjectModelSearchClearButtons();
}


export function handleProjectModelComboboxFocus(event) {
    const kind = getProjectModelComboboxKindFromInput(event.target);
    if (!kind) {
        return;
    }

    filterProjectModelComboboxOptions(kind, event.target.value);
    openProjectModelComboboxOptions(kind);
}


export function handleProjectModelComboboxClick(event) {
    const option = event.target.closest("[data-project-model-option-kind]");
    if (option) {
        setProjectModelComboboxSelection(
            option.dataset.projectModelOptionKind,
            option.dataset.projectModelOptionId,
        );
        return;
    }

    if (event.target.closest("#project-model-system-model-clear")) {
        clearProjectModelCombobox("model");
        return;
    }

    if (event.target.closest("#project-model-profile-clear")) {
        clearProjectModelCombobox("profile");
    }
}


export function handleProjectModelDocumentClick(event) {
    if (event.target.closest("[data-project-model-combobox]")) {
        return;
    }

    closeProjectModelComboboxOptions();
}


function getProjectModelComboboxKindFromInput(input) {
    if (input?.id === "project-model-system-model-input") {
        return "model";
    }
    if (input?.id === "project-model-profile-input") {
        return "profile";
    }
    return null;
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


async function refreshProjectWorkspaceState(projectId) {
    const [documentsData, workspaceData, projectModelsData] = await Promise.all([
        loadProjectDocuments(projectId),
        loadProjectWorkspace(projectId),
        loadProjectModels(projectId),
    ]);
    applyProjectDocumentsPayload(documentsData);
    applyProjectWorkspacePayload(workspaceData);
    applyProjectModelsPayload(projectModelsData);
    await refreshWorkspaceFilesIfConnected();
}


function clearProjectWorkspaceState() {
    setProjectDocuments([]);
    setProjectDocumentFolders([]);
    applyProjectModelsPayload({});
    setProjectWorkspace(null);
    setProjectWorkspaceFiles([]);
    setActiveProjectDocumentFolderId(null);
}


async function openWorkspaceConnectionFlow() {
    const activeProject = getActiveProject();
    if (!activeProject) {
        showStatus("Select a project first.", true);
        return;
    }

    const workspaceDetails = await requestWorkspaceDetails(state.projectWorkspace, {
        fileCount: state.projectWorkspaceFileCount,
        files: state.projectWorkspaceFiles,
    });
    if (!workspaceDetails) {
        return;
    }

    if (workspaceDetails.action === "reindex") {
        await handleProjectWorkspaceReindex();
        return;
    }

    if (workspaceDetails.action === "disconnect") {
        await handleProjectWorkspaceDisconnect();
        return;
    }

    try {
        setLoading(true);
        const payload = await connectProjectWorkspace({
            project_id: activeProject.id,
            root_path: workspaceDetails.root_path,
            display_name: workspaceDetails.display_name,
        });
        applyProjectWorkspacePayload(payload);
        await refreshWorkspaceFilesIfConnected();
        renderApp();
        showStatus("Workspace connected and indexed.");
    } catch (error) {
        showStatus(error.message || "The workspace could not be connected.", true);
    } finally {
        setLoading(false);
    }
}


async function handleProjectWorkspaceReindex() {
    if (!state.projectWorkspace) {
        showStatus("Connect a workspace first.", true);
        return;
    }

    try {
        setLoading(true);
        const payload = await indexProjectWorkspace(state.projectWorkspace.id);
        applyProjectWorkspacePayload(payload);
        await refreshWorkspaceFilesIfConnected();
        renderApp();
        showStatus("Workspace index refreshed.");
    } catch (error) {
        showStatus(error.message || "The workspace could not be indexed.", true);
    } finally {
        setLoading(false);
    }
}


async function handleProjectWorkspaceDisconnect() {
    if (!state.projectWorkspace) {
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Workspace",
        title: `Disconnect "${state.projectWorkspace.display_name}"`,
        message: "This removes the link from the project. Local files stay untouched.",
        confirmLabel: "Disconnect",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        setLoading(true);
        await deleteProjectWorkspace(state.projectWorkspace.id);
        setProjectWorkspace(null);
        setProjectWorkspaceFiles([]);
        renderApp();
        showStatus("Workspace disconnected.");
    } catch (error) {
        showStatus(error.message || "The workspace could not be disconnected.", true);
    } finally {
        setLoading(false);
    }
}


async function refreshWorkspaceFilesIfConnected() {
    if (!state.projectWorkspace) {
        setProjectWorkspaceFiles([]);
        return;
    }

    const payload = await loadWorkspaceFiles(state.projectWorkspace.id);
    applyWorkspaceFilesPayload(payload);
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
