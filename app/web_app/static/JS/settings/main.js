import {
    handleModelIconClear,
    handleModelIconInputChange,
    handleModelSubmit,
    openCreateModelModal,
} from "../app/controllers/models-controller.js";
import { dismissStatusBanner } from "../app/controllers/layout-controller.js";
import {
    handleDocumentClick,
    handleProfileSubmit,
    openCreateProfileModal,
} from "../app/controllers/profiles-controller.js";
import {
    handleProviderSubmit,
    openCreateProviderModal,
} from "../app/controllers/providers-controller.js";
import {
    ensureAuthenticated,
    handleLogout,
    handleSessionProfileSubmit,
    openSessionProfileEditor,
} from "../app/controllers/session-controller.js";
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
} from "../app/controllers/tools-controller.js";
import { elements } from "../app/dom.js";
import {
    closeModelModal,
    closeProfileModal,
    closeProviderModal,
    closeSessionProfileModal,
    closeToolUploadModal,
} from "../app/modal-ui.js";
import {
    applyConversationsPayload,
    applyCurrentUserPayload,
    applyModelsPayload,
    applyProfilesPayload,
    applyProvidersPayload,
    applySettingsPayload,
    applyToolsPayload,
    enterSettingsWorkspace,
} from "../app/state-actions.js";
import { showStatus } from "../app/status-ui.js";
import {
    loadConversations,
    loadCurrentUser,
    loadModels,
    loadProfiles,
    loadProviders,
    loadSettings,
    loadTools,
} from "../app/store.js";
import {
    getActiveSettingsCategory,
    renderSettingsPage,
    selectSettingsCategory,
} from "./render.js";

const overlaySidebarMediaQuery = window.matchMedia("(max-width: 1100px)");
let isSettingsSidebarOpen = false;


document.addEventListener("DOMContentLoaded", () => {
    if (!ensureAuthenticated()) {
        return;
    }

    bindSettingsUI();
    bootSettingsPage().catch((error) => {
        console.error(error);
        showStatus(error.message || "The settings page could not be loaded.", true);
    });
});


async function bootSettingsPage() {
    const [
        settingsData,
        providersData,
        profilesData,
        modelsData,
        toolsData,
        conversationsData,
        currentUserData,
    ] = await Promise.all([
        loadSettings(),
        loadProviders(),
        loadProfiles(),
        loadModels(),
        loadTools(),
        loadConversations(),
        loadCurrentUser(),
    ]);

    applySettingsPayload(settingsData);
    applyProvidersPayload(providersData);
    applyProfilesPayload(profilesData);
    applyModelsPayload(modelsData);
    applyToolsPayload(toolsData);
    applyConversationsPayload(conversationsData);
    applyCurrentUserPayload(currentUserData);
    enterSettingsWorkspace();

    if (getActiveSettingsCategory() !== window.location.hash.replace(/^#/, "")) {
        selectSettingsCategory(getActiveSettingsCategory());
        return;
    }

    renderSettingsPage();
}


function bindSettingsUI() {
    document.querySelectorAll("[data-settings-category]").forEach((button) => {
        button.addEventListener("click", () => {
            selectSettingsCategory(button.dataset.settingsCategory);
            closeSettingsSidebar();
        });
    });

    window.addEventListener("hashchange", () => {
        renderSettingsPage();
    });
    bindSettingsSidebarViewportChangeListener();
    syncSettingsSidebarVisibility();

    elements.settingsNewProviderButton?.addEventListener("click", openCreateProviderModal);
    elements.settingsNewModelButton?.addEventListener("click", () => openCreateModelModal("settings"));
    elements.settingsNewProfileButton?.addEventListener("click", () => openCreateProfileModal("settings"));
    elements.settingsNewToolButton?.addEventListener("click", handleToolUploadButtonClick);
    elements.settingsFilterToolsButton?.addEventListener("click", handleToolsFilterToggle);

    elements.editSessionProfileButton?.addEventListener("click", openSessionProfileEditor);
    elements.logoutButton?.addEventListener("click", handleLogout);
    elements.statusBannerCloseButton?.addEventListener("click", dismissStatusBanner);

    elements.modelForm?.addEventListener("submit", handleModelSubmit);
    elements.providerForm?.addEventListener("submit", handleProviderSubmit);
    elements.profileForm?.addEventListener("submit", handleProfileSubmit);
    elements.sessionProfileForm?.addEventListener("submit", handleSessionProfileSubmit);
    elements.toolUploadForm?.addEventListener("submit", handleToolUploadSubmit);

    elements.modelIconInput?.addEventListener("change", handleModelIconInputChange);
    elements.modelIconClearButton?.addEventListener("click", handleModelIconClear);
    elements.toolsUploadInput?.addEventListener("change", handleToolUploadInputChange);
    elements.toolUploadNameInput?.addEventListener("input", handleToolUploadNameInput);
    elements.toolUploadDropzone?.addEventListener("dragover", handleToolUploadDragOver);
    elements.toolUploadDropzone?.addEventListener("dragleave", handleToolUploadDragLeave);
    elements.toolUploadDropzone?.addEventListener("drop", handleToolUploadDrop);

    elements.modelCancelButton?.addEventListener("click", closeModelModal);
    elements.providerCancelButton?.addEventListener("click", closeProviderModal);
    elements.profileCancelButton?.addEventListener("click", closeProfileModal);
    elements.closeSessionProfileButton?.addEventListener("click", closeSessionProfileModal);
    elements.sessionProfileCancelButton?.addEventListener("click", closeSessionProfileModal);
    elements.closeToolUploadButton?.addEventListener("click", closeToolUploadModal);
    elements.toolUploadCancelButton?.addEventListener("click", closeToolUploadModal);

    elements.closeModelButton?.addEventListener("click", closeModelModal);
    elements.closeProviderButton?.addEventListener("click", closeProviderModal);
    elements.closeProfileButton?.addEventListener("click", closeProfileModal);

    elements.modelModal?.addEventListener("click", handleModalBackdropClick("closeModelModal", closeModelModal));
    elements.providerModal?.addEventListener("click", handleModalBackdropClick("closeProviderModal", closeProviderModal));
    elements.profileModal?.addEventListener("click", handleModalBackdropClick("closeProfileModal", closeProfileModal));
    elements.sessionProfileModal?.addEventListener("click", handleModalBackdropClick("closeSessionProfileModal", closeSessionProfileModal));
    elements.toolUploadModal?.addEventListener("click", handleModalBackdropClick("closeToolUploadModal", closeToolUploadModal));
    document.getElementById("settings-sidebar-toggle")?.addEventListener("click", toggleSettingsSidebar);
    document.getElementById("settings-sidebar-backdrop")?.addEventListener("click", closeSettingsSidebar);

    document.addEventListener("click", handleSettingsDocumentClick);
    document.addEventListener("keydown", handleSettingsEscape);
}


function handleSettingsDocumentClick(event) {
    handleDocumentClick(event, {
        handleProjectDocumentDelete: () => {},
    });
    handleDocumentToolClick(event);
}


function handleSettingsEscape(event) {
    if (event.key !== "Escape") {
        return;
    }

    if (closeSettingsSidebar()) {
        event.stopPropagation();
        return;
    }

    if (elements.profileModal && !elements.profileModal.hidden) {
        closeProfileModal();
        event.stopPropagation();
        return;
    }

    if (elements.modelModal && !elements.modelModal.hidden) {
        closeModelModal();
        event.stopPropagation();
        return;
    }

    if (elements.providerModal && !elements.providerModal.hidden) {
        closeProviderModal();
        event.stopPropagation();
        return;
    }

    if (elements.sessionProfileModal && !elements.sessionProfileModal.hidden) {
        closeSessionProfileModal();
        event.stopPropagation();
        return;
    }

    if (elements.toolUploadModal && !elements.toolUploadModal.hidden) {
        closeToolUploadModal();
        event.stopPropagation();
        return;
    }
}


function handleModalBackdropClick(dataAttribute, closeHandler) {
    return (event) => {
        if (event.target.dataset[dataAttribute] === "true") {
            closeHandler();
        }
    };
}


function bindSettingsSidebarViewportChangeListener() {
    const listener = () => syncSettingsSidebarVisibility();

    if (typeof overlaySidebarMediaQuery.addEventListener === "function") {
        overlaySidebarMediaQuery.addEventListener("change", listener);
        return;
    }

    if (typeof overlaySidebarMediaQuery.addListener === "function") {
        overlaySidebarMediaQuery.addListener(listener);
    }
}


function syncSettingsSidebarVisibility() {
    const toggleButton = document.getElementById("settings-sidebar-toggle");
    const backdrop = document.getElementById("settings-sidebar-backdrop");
    const sidebar = document.getElementById("settings-sidebar");
    const isOverlay = overlaySidebarMediaQuery.matches;

    if (!isOverlay) {
        isSettingsSidebarOpen = false;
    }

    document.body.classList.toggle(
        "is-settings-sidebar-open",
        Boolean(isOverlay && isSettingsSidebarOpen),
    );

    if (toggleButton) {
        toggleButton.hidden = !isOverlay;
        toggleButton.setAttribute("aria-expanded", String(Boolean(isOverlay && isSettingsSidebarOpen)));
        toggleButton.setAttribute(
            "aria-label",
            isSettingsSidebarOpen ? "Close settings navigation" : "Open settings navigation",
        );
    }

    if (backdrop) {
        backdrop.hidden = !(isOverlay && isSettingsSidebarOpen);
    }

    if (sidebar) {
        sidebar.setAttribute("aria-hidden", String(isOverlay ? !isSettingsSidebarOpen : false));
    }
}


function openSettingsSidebar() {
    if (!overlaySidebarMediaQuery.matches) {
        return false;
    }

    if (isSettingsSidebarOpen) {
        return false;
    }

    isSettingsSidebarOpen = true;
    syncSettingsSidebarVisibility();
    return true;
}


function closeSettingsSidebar() {
    if (!overlaySidebarMediaQuery.matches || !isSettingsSidebarOpen) {
        return false;
    }

    isSettingsSidebarOpen = false;
    syncSettingsSidebarVisibility();
    return true;
}


function toggleSettingsSidebar() {
    if (isSettingsSidebarOpen) {
        closeSettingsSidebar();
        return;
    }

    openSettingsSidebar();
}
