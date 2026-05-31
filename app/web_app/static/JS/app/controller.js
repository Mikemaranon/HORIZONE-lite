import { configureAppCallbacks, renderApp } from "./app-runtime.js";
import { autoResizeComposer } from "./composer-ui.js";
import { handleToolTraceMessageClick } from "./message-ui.js";
import {
    disableMessagesAutoScroll,
    ensureActiveConversation,
    handleComposerKeyDown,
    handleComposerSubmit,
    handleConversationDelete,
    handleConversationSelect,
    handleConversationTitleClick,
    handleConversationTitleInput,
    handleConversationTitleKeyDown,
    handleSendButtonClick,
    openNewConversationWorkspace,
    registerChatCallbacks,
    syncMessagesAutoScrollState,
} from "./controllers/chat-controller.js";
import {
    handleChatExportDownload,
    openChatExportDialog,
} from "./controllers/export-controller.js";
import {
    bindSidebarViewportChangeListener,
    closeChatPanel,
    closeSidebar,
    closeSidebarOnMobile,
    dismissStatusBanner,
    handleChatSidebarClick,
    handleDocumentKeyDown,
    handleMessagesWheel,
    syncChatSidebarSections,
    syncChatPanelVisibility,
    syncSidebarVisibility,
    toggleChatPanel,
    toggleSidebar,
} from "./controllers/layout-controller.js";
import {
    handleActiveChatModelEdit,
    handleModelIconClear,
    handleModelIconInputChange,
    handleModelSearchClear,
    handleModelSearchInput,
    handleModelSubmit,
    openCreateModelModal,
    openModelSwitcher,
    syncChatModelActions,
} from "./controllers/models-controller.js";
import {
    handleActiveChatProfileEdit,
    handleDocumentClick,
    handleDocumentInput,
    handleProfileSearchClear,
    handleProfileSubmit,
    openCreateProfileModal,
    openProfileSwitcher,
    syncChatProfileActions,
} from "./controllers/profiles-controller.js";
import {
    handleProviderSubmit,
    openCreateProviderModal,
} from "./controllers/providers-controller.js";
import {
    handleDocumentToolClick,
    handleToolsFilterToggle,
    handleToolUploadButtonClick,
    handleToolUploadDragLeave,
    handleToolUploadDragOver,
    handleToolUploadDrop,
    handleToolUploadInputChange,
    handleToolUploadNameInput,
    handleToolUploadSubmit,
} from "./controllers/tools-controller.js";
import {
    handleBackToProject,
    handleDocumentsDirectoryDragLeave,
    handleDocumentsDirectoryDragOver,
    handleDocumentsDirectoryDrop,
    handleDocumentsDragLeave,
    handleDocumentsDragOver,
    handleDocumentsDrop,
    handleDocumentsOpen,
    handleProjectActionsDocumentClick,
    handleProjectConnectWorkspace,
    handleProjectDocumentDragEnd,
    handleProjectDocumentDragStart,
    handleProjectDocumentFolderCreate,
    handleProjectDocumentFolderDelete,
    handleProjectDocumentFolderSelect,
    handleDocumentsSelected,
    handleNewProject,
    handleNewProjectChat,
    handleProjectModelComboboxClick,
    handleProjectModelComboboxFocus,
    handleProjectModelComboboxInput,
    handleProjectModelDocumentClick,
    handleProjectCustomizeSubmit,
    handleProjectDelete,
    handleProjectDocumentDelete,
    handleProjectAgentChangeOpen,
    handleProjectAgentOptionSelect,
    handleProjectAgentSearchClear,
    handleProjectAgentSearchInput,
    handleProjectModelCreate,
    handleProjectModelListClick,
    handleProjectModelsOpen,
    handleProjectModelsSubmit,
    handleProjectSelect,
    handleWorkspaceSettingsOpen,
    closeProjectActionsMenu,
    toggleProjectActionsMenu,
} from "./controllers/projects-controller.js";
import {
    ensureAuthenticated,
    handleLogout,
    handleSessionProfileSubmit,
    openSessionProfileEditor,
} from "./controllers/session-controller.js";
import { elements } from "./dom.js";
import {
    closeChatExportModal,
    closeDocumentsModal,
    closeModelModal,
    closeModelSwitchModal,
    closeProjectAgentSwitchModal,
    closeProjectModelsModal,
    closeProfileModal,
    closeProfileSwitchModal,
    closeProjectCustomizeModal,
    closeProviderModal,
    closeSessionProfileModal,
    closeToolTraceModal,
    closeToolUploadModal,
    openProjectCustomizeModal,
} from "./modal-ui.js";
import {
    applyConversationsPayload,
    applyCurrentUserPayload,
    applyModelsPayload,
    applyProfilesPayload,
    applyProjectsPayload,
    applyProvidersPayload,
    applySettingsPayload,
    applyToolsPayload,
    enterHomeWorkspace,
} from "./state-actions.js";
import {
    loadConversations,
    loadCurrentUser,
    loadModels,
    loadProfiles,
    loadProjects,
    loadProviders,
    loadSettings,
    loadTools,
} from "./store.js";

const onProjectSelect = (projectId) => handleProjectSelect(projectId, { closeSidebarOnMobile });
const onConversationSelect = (conversationId) => handleConversationSelect(conversationId, { closeSidebarOnMobile });
const onConversationDelete = (conversationId) => handleConversationDelete(conversationId);
const ensureConversation = () => ensureActiveConversation({
    handleConversationSelect: onConversationSelect,
    closeSidebarOnMobile,
});

configureAppCallbacks({
    onConversationDelete,
    onConversationSelect,
    onProjectSelect,
});

registerChatCallbacks({
    handleConversationDelete: onConversationDelete,
    handleConversationSelect: onConversationSelect,
});


export async function bootApp() {
    const [settingsData, providersData, profilesData, projectsData, modelsData, toolsData, conversationsData, currentUserData] = await Promise.all([
        loadSettings(),
        loadProviders(),
        loadProfiles(),
        loadProjects(),
        loadModels(),
        loadTools(),
        loadConversations(),
        loadCurrentUser(),
    ]);

    applySettingsPayload(settingsData);
    applyProvidersPayload(providersData);
    applyProfilesPayload(profilesData);
    applyProjectsPayload(projectsData);
    applyModelsPayload(modelsData);
    applyToolsPayload(toolsData);
    applyConversationsPayload(conversationsData);
    applyCurrentUserPayload(currentUserData);
    enterHomeWorkspace();
    syncSidebarVisibility();
    syncChatPanelVisibility();
    syncChatSidebarSections();
    renderApp();
}


export function bindUI() {
    elements.sidebarToggleButton?.addEventListener("click", toggleSidebar);
    elements.sidebarBackdrop?.addEventListener("click", closeSidebar);
    elements.composerForm.addEventListener("submit", (event) => handleComposerSubmit(event, {
        ensureActiveConversation: ensureConversation,
    }));
    elements.sendButton?.addEventListener("click", handleSendButtonClick);
    elements.composerInput.addEventListener("keydown", handleComposerKeyDown);
    elements.composerInput.addEventListener("input", autoResizeComposer);
    elements.conversationTitle?.addEventListener("click", handleConversationTitleClick);
    elements.conversationTitle?.addEventListener("input", handleConversationTitleInput);
    elements.conversationTitle?.addEventListener("keydown", handleConversationTitleKeyDown);
    elements.newChatButton.addEventListener("click", () => openNewConversationWorkspace({
        closeSidebarOnMobile,
    }));
    elements.newProjectButton.addEventListener("click", () => handleNewProject({ closeSidebarOnMobile }));
    elements.newProjectChatButton?.addEventListener("click", () => handleNewProjectChat({
        handleConversationSelect: onConversationSelect,
        closeSidebarOnMobile,
    }));
    elements.projectActionsMenuButton?.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleProjectActionsMenu();
    });
    elements.addDocumentsButton?.addEventListener("click", handleDocumentsOpen);
    elements.projectModelsButton?.addEventListener("click", handleProjectModelsOpen);
    elements.customizeProjectButton?.addEventListener("click", () => {
        closeProjectActionsMenu();
        openProjectCustomizeModal();
    });
    elements.connectWorkspaceButton?.addEventListener("click", handleProjectConnectWorkspace);
    elements.workspaceSettingsButton?.addEventListener("click", () => handleWorkspaceSettingsOpen({ closeSidebarOnMobile }));
    elements.chatSettingsButton?.addEventListener("click", toggleChatPanel);
    elements.chatPanelBackdrop?.addEventListener("click", closeChatPanel);
    elements.chatAgentsChangeButton?.addEventListener("click", handleProjectAgentChangeOpen);
    elements.chatAgentsEditButton?.addEventListener("click", () => handleProjectModelsOpen({ editSelectedAgent: true }));
    elements.chatExportButton?.addEventListener("click", openChatExportDialog);
    elements.chatExportJsonButton?.addEventListener("click", () => handleChatExportDownload("json"));
    elements.chatExportHtmlButton?.addEventListener("click", () => handleChatExportDownload("html"));
    elements.chatExportMarkdownButton?.addEventListener("click", () => handleChatExportDownload("md"));
    elements.chatSidePanel?.addEventListener("click", handleChatSidebarClick);
    elements.backToProjectButton?.addEventListener("click", handleBackToProject);
    elements.changeModelButton?.addEventListener("click", () => openModelSwitcher("chat-settings"));
    elements.editModelButton?.addEventListener("click", handleActiveChatModelEdit);
    elements.changeProfileButton?.addEventListener("click", openProfileSwitcher);
    elements.editProfileButton?.addEventListener("click", handleActiveChatProfileEdit);
    elements.settingsNewProviderButton?.addEventListener("click", openCreateProviderModal);
    elements.settingsNewModelButton?.addEventListener("click", () => openCreateModelModal("settings"));
    elements.settingsNewToolButton?.addEventListener("click", handleToolUploadButtonClick);
    elements.settingsFilterToolsButton?.addEventListener("click", handleToolsFilterToggle);
    elements.toolsUploadInput?.addEventListener("change", handleToolUploadInputChange);
    elements.toolUploadNameInput?.addEventListener("input", handleToolUploadNameInput);
    elements.toolUploadForm?.addEventListener("submit", handleToolUploadSubmit);
    elements.closeToolUploadButton?.addEventListener("click", closeToolUploadModal);
    elements.closeToolTraceButton?.addEventListener("click", closeToolTraceModal);
    elements.toolUploadCancelButton?.addEventListener("click", closeToolUploadModal);
    elements.toolUploadDropzone?.addEventListener("dragover", handleToolUploadDragOver);
    elements.toolUploadDropzone?.addEventListener("dragleave", handleToolUploadDragLeave);
    elements.toolUploadDropzone?.addEventListener("drop", handleToolUploadDrop);
    elements.closeModelSwitchButton?.addEventListener("click", closeModelSwitchModal);
    elements.closeProjectAgentSwitchButton?.addEventListener("click", closeProjectAgentSwitchModal);
    elements.closeProjectModelsButton?.addEventListener("click", closeProjectModelsModal);
    elements.closeChatExportButton?.addEventListener("click", closeChatExportModal);
    elements.closeModelButton?.addEventListener("click", closeModelModal);
    elements.closeProviderButton?.addEventListener("click", closeProviderModal);
    elements.closeProfileSwitchButton?.addEventListener("click", closeProfileSwitchModal);
    elements.closeProfileButton?.addEventListener("click", closeProfileModal);
    elements.closeProjectCustomizeButton?.addEventListener("click", closeProjectCustomizeModal);
    elements.closeDocumentsButton?.addEventListener("click", closeDocumentsModal);
    elements.modelForm?.addEventListener("submit", handleModelSubmit);
    elements.modelIconInput?.addEventListener("change", handleModelIconInputChange);
    elements.modelIconClearButton?.addEventListener("click", handleModelIconClear);
    elements.providerForm?.addEventListener("submit", handleProviderSubmit);
    elements.profileForm.addEventListener("submit", handleProfileSubmit);
    elements.projectCustomizeForm?.addEventListener("submit", handleProjectCustomizeSubmit);
    elements.projectModelsForm?.addEventListener("submit", handleProjectModelsSubmit);
    elements.projectModelsForm?.addEventListener("input", handleProjectModelComboboxInput);
    elements.projectModelSystemModelInput?.addEventListener("focus", handleProjectModelComboboxFocus);
    elements.projectModelProfileInput?.addEventListener("focus", handleProjectModelComboboxFocus);
    elements.projectModelsList?.addEventListener("click", handleProjectModelListClick);
    elements.projectModelsModal?.addEventListener("click", handleProjectModelComboboxClick);
    elements.projectModelCreateButton?.addEventListener("click", handleProjectModelCreate);
    elements.deleteProjectButton?.addEventListener("click", handleProjectDelete);
    elements.settingsNewProfileButton?.addEventListener("click", () => openCreateProfileModal("settings"));
    elements.editSessionProfileButton?.addEventListener("click", openSessionProfileEditor);
    elements.modelCancelButton?.addEventListener("click", closeModelModal);
    elements.providerCancelButton?.addEventListener("click", closeProviderModal);
    elements.profileCancelButton?.addEventListener("click", closeProfileModal);
    elements.closeSessionProfileButton?.addEventListener("click", closeSessionProfileModal);
    elements.sessionProfileCancelButton?.addEventListener("click", closeSessionProfileModal);
    elements.sessionProfileForm?.addEventListener("submit", handleSessionProfileSubmit);
    elements.documentsInput?.addEventListener("change", handleDocumentsSelected);
    elements.documentsDropzone?.addEventListener("dragover", handleDocumentsDragOver);
    elements.documentsDropzone?.addEventListener("dragleave", handleDocumentsDragLeave);
    elements.documentsDropzone?.addEventListener("drop", handleDocumentsDrop);
    elements.documentsFolderForm?.addEventListener("submit", handleProjectDocumentFolderCreate);
    elements.documentsDeleteFolderButton?.addEventListener("click", handleProjectDocumentFolderDelete);
    elements.documentsDirectoryTree?.addEventListener("click", handleProjectDocumentFolderSelect);
    elements.documentsDirectoryTree?.addEventListener("dragover", handleDocumentsDirectoryDragOver);
    elements.documentsDirectoryTree?.addEventListener("dragleave", handleDocumentsDirectoryDragLeave);
    elements.documentsDirectoryTree?.addEventListener("drop", handleDocumentsDirectoryDrop);
    elements.documentsFileList?.addEventListener("dragstart", handleProjectDocumentDragStart);
    elements.documentsFileList?.addEventListener("dragend", handleProjectDocumentDragEnd);
    elements.statusBannerCloseButton?.addEventListener("click", dismissStatusBanner);
    elements.messagesContainer?.addEventListener("scroll", syncMessagesAutoScrollState, { passive: true });
    elements.messagesContainer?.addEventListener("click", handleToolTraceMessageClick);
    elements.messagesContainer?.addEventListener("wheel", (event) => handleMessagesWheel(event, {
        disableMessagesAutoScroll,
    }), { passive: true });
    elements.logoutButton.addEventListener("click", handleLogout);
    elements.modelSwitchModal?.addEventListener("click", handleModelSwitchModalClick);
    elements.projectAgentSwitchModal?.addEventListener("click", handleProjectAgentSwitchModalClick);
    elements.projectModelsModal?.addEventListener("click", handleProjectModelsModalClick);
    elements.modelModal?.addEventListener("click", handleModelModalClick);
    elements.providerModal?.addEventListener("click", handleProviderModalClick);
    elements.profileSwitchModal?.addEventListener("click", handleProfileSwitchModalClick);
    elements.chatExportModal?.addEventListener("click", handleChatExportModalClick);
    elements.profileModal?.addEventListener("click", handleProfileModalClick);
    elements.sessionProfileModal?.addEventListener("click", handleSessionProfileModalClick);
    elements.projectCustomizeModal?.addEventListener("click", handleProjectModalClick);
    elements.documentsModal?.addEventListener("click", handleDocumentsModalClick);
    elements.toolUploadModal?.addEventListener("click", handleToolUploadModalClick);
    elements.toolTraceModal?.addEventListener("click", handleToolTraceModalClick);
    elements.modelSwitchSearchInput?.addEventListener("input", handleModelSearchInput);
    elements.modelSwitchSearchClearButton?.addEventListener("click", handleModelSearchClear);
    elements.projectAgentSwitchSearchInput?.addEventListener("input", handleProjectAgentSearchInput);
    elements.projectAgentSwitchSearchClearButton?.addEventListener("click", handleProjectAgentSearchClear);
    elements.profileSwitchSearchClearButton?.addEventListener("click", handleProfileSearchClear);
    document.addEventListener("keydown", handleDocumentKeyDown);
    document.querySelectorAll("[data-prompt]").forEach((element) => {
        element.addEventListener("click", () => {
            elements.composerInput.value = element.dataset.prompt || "";
            autoResizeComposer();
            elements.composerInput.focus();
        });
    });
    document.addEventListener("click", (event) => handleDocumentClick(event, { handleProjectDocumentDelete }));
    document.addEventListener("click", handleProjectActionsDocumentClick);
    document.addEventListener("click", handleProjectModelDocumentClick);
    document.addEventListener("click", handleDocumentToolClick);
    document.addEventListener("input", handleDocumentInput);
    bindSidebarViewportChangeListener();
    syncChatSidebarSections();
    syncChatModelActions();
    syncChatProfileActions();
}


export { ensureAuthenticated };


function handleModelSwitchModalClick(event) {
    if (event.target.dataset.closeModelSwitchModal === "true") {
        closeModelSwitchModal();
    }
}


function handleProjectAgentSwitchModalClick(event) {
    if (event.target.dataset.closeProjectAgentSwitchModal === "true") {
        closeProjectAgentSwitchModal();
        return;
    }

    const option = event.target.closest("[data-project-agent-switch-option]");
    if (option) {
        handleProjectAgentOptionSelect(Number(option.dataset.projectAgentSwitchOption));
    }
}


function handleProjectModelsModalClick(event) {
    if (event.target.dataset.closeProjectModelsModal === "true") {
        closeProjectModelsModal();
    }
}


function handleModelModalClick(event) {
    if (event.target.dataset.closeModelModal === "true") {
        closeModelModal();
    }
}


function handleProviderModalClick(event) {
    if (event.target.dataset.closeProviderModal === "true") {
        closeProviderModal();
    }
}


function handleProfileSwitchModalClick(event) {
    if (event.target.dataset.closeProfileSwitchModal === "true") {
        closeProfileSwitchModal();
    }
}


function handleChatExportModalClick(event) {
    if (event.target.dataset.closeChatExportModal === "true") {
        closeChatExportModal();
    }
}


function handleProfileModalClick(event) {
    if (event.target.dataset.closeProfileModal === "true") {
        closeProfileModal();
    }
}


function handleProjectModalClick(event) {
    if (event.target.dataset.closeProjectModal === "true") {
        closeProjectCustomizeModal();
    }
}


function handleSessionProfileModalClick(event) {
    if (event.target.dataset.closeSessionProfileModal === "true") {
        closeSessionProfileModal();
    }
}


function handleDocumentsModalClick(event) {
    if (event.target.dataset.closeDocumentsModal === "true") {
        closeDocumentsModal();
    }
}


function handleToolUploadModalClick(event) {
    if (event.target.dataset.closeToolUploadModal === "true") {
        closeToolUploadModal();
    }
}


function handleToolTraceModalClick(event) {
    if (event.target.dataset.closeToolTraceModal === "true") {
        closeToolTraceModal();
    }
}
