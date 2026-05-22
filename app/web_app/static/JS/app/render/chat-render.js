import { syncComposerAvailability } from "../composer-ui.js";
import { elements } from "../dom.js";
import { createMetaChipsMarkup } from "../html.js";
import { createMessageMarkup, enableMessagesAutoScroll, scrollMessagesToBottom } from "../message-ui.js";
import { getActualProvider, getProviderDisplayName, getSelectedModel, getSelectedModelConfig } from "../provider-helpers.js";
import { getActiveProject, getProfileNameById, getSelectedProfileId } from "../selectors.js";
import { state } from "../state.js";


export function renderMessages({ preserveViewport = false } = {}) {
    const showConversation = state.workspaceMode === "conversation" && !!state.activeConversation;
    const showEmptyState = state.workspaceMode === "home";

    elements.emptyState.hidden = !showEmptyState;

    if (!showConversation) {
        elements.messagesContainer.hidden = true;
        elements.messagesContainer.innerHTML = "";
        enableMessagesAutoScroll();
        return;
    }

    elements.messagesContainer.hidden = false;
    elements.messagesContainer.innerHTML = state.activeMessages
        .map((message) => createMessageMarkup(message))
        .join("");

    if (preserveViewport) {
        return;
    }

    enableMessagesAutoScroll();
    scrollMessagesToBottom();
}


export function renderConversationHeader() {
    const activeProject = getActiveProject();

    if (state.workspaceMode === "conversation" && state.activeConversation) {
        const selectedModelConfig = getSelectedModelConfig();
        const provider = selectedModelConfig?.provider_name
            || getProviderDisplayName(state.activeConversation?.provider || getActualProvider());
        const model = state.activeConversation?.model || getSelectedModel() || "modelo pendiente";
        const profileName = getProfileNameById(state.activeConversation?.profile_id || getSelectedProfileId());

        elements.workspaceEyebrow.textContent = activeProject ? "Chat del proyecto" : "Chat";
        elements.conversationTitle.textContent = state.activeConversation.title || "Nueva conversación";
        elements.conversationMeta.innerHTML = createMetaChipsMarkup([
            { group: "provider", label: "Proveedor", value: provider },
            { group: "model", label: "Modelo", value: model },
            { group: "profile", label: "Perfil", value: profileName },
        ]);
        elements.conversationMeta.hidden = false;
        elements.conversationSubtitle.hidden = true;
        elements.backToProjectButton.hidden = !activeProject;
        elements.chatSettingsButton.hidden = false;
        return;
    }

    if (state.workspaceMode === "project" && activeProject) {
        elements.workspaceEyebrow.textContent = "Proyecto";
        elements.conversationTitle.textContent = activeProject.name;
        elements.conversationSubtitle.textContent = "Gestiona aquí el prompt del proyecto y sus chats, sin mezclarlo con los chats puntuales.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = false;
        return;
    }

    if (state.workspaceMode === "settings") {
        elements.workspaceEyebrow.textContent = "Configuración";
        elements.conversationTitle.textContent = "Ajustes generales";
        elements.conversationSubtitle.textContent = "Gestiona aquí proveedores, modelos, perfiles y la sesión de HORIZONE lite.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = true;
        return;
    }

    if (state.workspaceMode === "home") {
        elements.workspaceEyebrow.textContent = "Chat";
        elements.conversationTitle.textContent = "Nueva conversación";
        elements.conversationSubtitle.textContent = "Configura el modelo por defecto en ajustes generales y cambia modelo o perfil por chat desde el panel lateral.";
        elements.conversationMeta.innerHTML = "";
        elements.conversationMeta.hidden = true;
        elements.conversationSubtitle.hidden = false;
        elements.backToProjectButton.hidden = true;
        elements.chatSettingsButton.hidden = false;
    }
}


export function renderChatSurface() {
    renderMessages();
    renderConversationHeader();
    syncComposerAvailability();
}
