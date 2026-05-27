import { elements } from "../dom.js";
import { setChatPanelOpen } from "../state-actions.js";
import { state } from "../state.js";
import {
    closeChatExportModal,
    closeDocumentsModal,
    closeModelModal,
    closeModelSwitchModal,
    closeProviderModal,
    closeProfileModal,
    closeProfileSwitchModal,
    closeProjectCustomizeModal,
    closeToolUploadModal,
} from "../modal-ui.js";
import { closeProjectActionsMenu } from "./projects-controller.js";
import { hideStatus } from "../status-ui.js";

const mobileSidebarMediaQuery = window.matchMedia("(max-width: 1120px)");
const overlayChatPanelMediaQuery = window.matchMedia("(max-width: 1180px)");


export function handleMessagesWheel(event, { disableMessagesAutoScroll }) {
    if (event.deltaY < 0) {
        disableMessagesAutoScroll();
    }
}


export function syncSidebarVisibility() {
    const isMobile = isMobileSidebarViewport();
    const isSidebarOpen = isMobile ? Boolean(state.isSidebarOpen) : !Boolean(state.isDesktopSidebarCollapsed);

    if (!isMobile) {
        state.isSidebarOpen = false;
    }

    elements.appShell?.classList.toggle("is-sidebar-open", isSidebarOpen);
    document.body.classList.toggle("is-sidebar-open", Boolean(isMobile && state.isSidebarOpen));

    if (elements.appSidebar) {
        elements.appSidebar.setAttribute("aria-hidden", String(!isSidebarOpen));
    }

    syncSidebarToggleAria();
}


export function bindSidebarViewportChangeListener() {
    const listener = () => syncSidebarVisibility();
    const chatPanelListener = () => syncChatPanelVisibility();

    if (typeof mobileSidebarMediaQuery.addEventListener === "function") {
        mobileSidebarMediaQuery.addEventListener("change", listener);
    } else if (typeof mobileSidebarMediaQuery.addListener === "function") {
        mobileSidebarMediaQuery.addListener(listener);
    }

    if (typeof overlayChatPanelMediaQuery.addEventListener === "function") {
        overlayChatPanelMediaQuery.addEventListener("change", chatPanelListener);
        return;
    }

    if (typeof overlayChatPanelMediaQuery.addListener === "function") {
        overlayChatPanelMediaQuery.addListener(chatPanelListener);
    }
}


export function openSidebar() {
    if (isMobileSidebarViewport()) {
        state.isSidebarOpen = true;
        syncSidebarVisibility();
        return true;
    }

    if (!state.isDesktopSidebarCollapsed) {
        return false;
    }

    state.isDesktopSidebarCollapsed = false;
    syncSidebarVisibility();
    return true;
}


export function closeSidebar() {
    if (isMobileSidebarViewport()) {
        if (!state.isSidebarOpen) {
            return false;
        }

        state.isSidebarOpen = false;
        syncSidebarVisibility();
        return true;
    }

    if (state.isDesktopSidebarCollapsed) {
        return false;
    }

    state.isDesktopSidebarCollapsed = true;
    syncSidebarVisibility();
    return true;
}


export function toggleSidebar() {
    const isOpen = isMobileSidebarViewport() ? Boolean(state.isSidebarOpen) : !Boolean(state.isDesktopSidebarCollapsed);

    if (isOpen) {
        closeSidebar();
        return;
    }

    openSidebar();
}


export function closeSidebarOnMobile() {
    if (!isMobileSidebarViewport()) {
        return;
    }

    closeSidebar();
}


export function syncChatPanelVisibility() {
    const isOpen = Boolean(state.isChatPanelOpen);
    const isOverlay = isOverlayChatPanelViewport();

    elements.workspaceStage?.classList.toggle("is-chat-panel-open", isOpen);
    elements.workspaceStage?.classList.toggle("is-chat-panel-overlay", isOverlay);
    document.body.classList.toggle("is-chat-panel-open", Boolean(isOpen && isOverlay));

    if (elements.chatSettingsButton) {
        elements.chatSettingsButton.setAttribute("aria-expanded", String(isOpen));
        elements.chatSettingsButton.setAttribute(
            "aria-label",
            isOpen ? "Close chat panel" : "Open chat panel"
        );
    }

    if (elements.chatSidePanel) {
        elements.chatSidePanel.setAttribute("aria-hidden", String(!isOpen));
    }

    syncChatSidebarSectionHeights();
}


export function openChatPanel() {
    setActiveChatSidebarSection(null);
    setChatPanelOpen(true);
    syncChatPanelVisibility();
}


export function closeChatPanel() {
    if (!state.isChatPanelOpen) {
        return false;
    }

    setChatPanelOpen(false);
    syncChatPanelVisibility();
    return true;
}


export function toggleChatPanel() {
    if (state.isChatPanelOpen) {
        closeChatPanel();
        return;
    }

    openChatPanel();
}


export function dismissStatusBanner() {
    hideStatus();
}


export function handleChatSidebarClick(event) {
    const summary = event.target.closest(".chat-sidebar-section__summary");
    if (!summary) {
        return;
    }

    const section = summary.parentElement;
    if (!section?.classList.contains("chat-sidebar-section")) {
        return;
    }

    event.preventDefault();

    if (section.classList.contains("is-open")) {
        setActiveChatSidebarSection(null);
        return;
    }

    setActiveChatSidebarSection(section);
}


export function syncChatSidebarSections() {
    const activeSection = document.querySelector(".chat-sidebar-section.is-open:not([hidden])");
    setActiveChatSidebarSection(activeSection || null);
}


export function handleDocumentKeyDown(event) {
    if (event.key !== "Escape") {
        return;
    }

    if (closeProjectActionsMenu()) {
        event.stopPropagation();
        return;
    }

    if (closeSidebar()) {
        event.stopPropagation();
        return;
    }

    if (elements.profileSwitchModal && !elements.profileSwitchModal.hidden) {
        closeProfileSwitchModal();
        event.stopPropagation();
        return;
    }
    if (elements.modelSwitchModal && !elements.modelSwitchModal.hidden) {
        closeModelSwitchModal();
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
    if (elements.projectCustomizeModal && !elements.projectCustomizeModal.hidden) {
        closeProjectCustomizeModal();
        event.stopPropagation();
        return;
    }
    if (elements.documentsModal && !elements.documentsModal.hidden) {
        closeDocumentsModal();
        event.stopPropagation();
        return;
    }
    if (elements.toolUploadModal && !elements.toolUploadModal.hidden) {
        closeToolUploadModal();
        event.stopPropagation();
        return;
    }
    if (elements.chatExportModal && !elements.chatExportModal.hidden) {
        closeChatExportModal();
        event.stopPropagation();
        return;
    }

    if (closeChatPanel()) {
        event.stopPropagation();
        return;
    }
}


function isMobileSidebarViewport() {
    return mobileSidebarMediaQuery.matches;
}


function isOverlayChatPanelViewport() {
    return overlayChatPanelMediaQuery.matches;
}


function setActiveChatSidebarSection(activeSection) {
    const body = elements.chatSidePanel?.querySelector(".chat-side-panel__body");
    const sections = Array.from(document.querySelectorAll(".chat-sidebar-section"));

    sections.forEach((section) => {
        const isActive = section === activeSection;
        section.classList.toggle("is-open", isActive);
        section.open = isActive;
        section.classList.remove("is-hidden-top", "is-hidden-bottom");
        section.toggleAttribute("data-is-active", isActive);

        if (!isActive) {
            section.style.removeProperty("--chat-sidebar-open-max-height");
            section.style.removeProperty("--chat-sidebar-content-max-height");
            section.style.removeProperty("--chat-sidebar-content-rendered-height");
        }
    });

    syncChatSidebarSectionHeights();

    if (activeSection) {
        requestAnimationFrame(() => {
            activeSection.scrollIntoView({
                block: "nearest",
                inline: "nearest",
            });
        });
    }

    body?.classList.toggle("has-active-section", Boolean(activeSection));
    if (body) {
        if (activeSection?.dataset.chatSidebarSection) {
            body.dataset.activeSection = activeSection.dataset.chatSidebarSection;
        } else {
            delete body.dataset.activeSection;
        }
    }
}


function syncChatSidebarSectionHeights() {
    const body = elements.chatSidePanel?.querySelector(".chat-side-panel__body");
    const activeSection = body?.querySelector(".chat-sidebar-section.is-open");

    if (!body || !activeSection) {
        return;
    }

    requestAnimationFrame(() => {
        const bodyHeight = body.clientHeight;
        const summary = activeSection.querySelector(".chat-sidebar-section__summary");
        const contentInner = activeSection.querySelector(".chat-sidebar-section__content-inner");

        if (!bodyHeight || !summary || !contentInner) {
            return;
        }

        const sectionMaxHeight = Math.floor(bodyHeight * 0.7);
        const summaryHeight = summary.offsetHeight;
        const contentMaxHeight = Math.max(sectionMaxHeight - summaryHeight, 0);
        const contentRenderedHeight = Math.min(contentMaxHeight, contentInner.scrollHeight);

        activeSection.style.setProperty("--chat-sidebar-open-max-height", `${sectionMaxHeight}px`);
        activeSection.style.setProperty("--chat-sidebar-content-max-height", `${contentMaxHeight}px`);
        activeSection.style.setProperty("--chat-sidebar-content-rendered-height", `${contentRenderedHeight}px`);
    });
}


function syncSidebarToggleAria() {
    const isOpen = isMobileSidebarViewport() ? Boolean(state.isSidebarOpen) : !Boolean(state.isDesktopSidebarCollapsed);

    if (elements.sidebarToggleButton) {
        elements.sidebarToggleButton.setAttribute("aria-expanded", String(isOpen));
        elements.sidebarToggleButton.setAttribute(
            "aria-label",
            isOpen ? "Close side navigation" : "Open side navigation"
        );
        elements.sidebarToggleButton.title = isOpen
            ? "Hide sidebar"
            : "Show sidebar";
    }
}
