import { createProvider, deleteProvider, restoreProvider, updateProvider } from "../api.js";
import { confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import { closeProviderModal, openProviderModal } from "../modal-ui.js";
import { renderChatPanel, renderConversationHeader, renderSettingsModelsManager, renderSettingsProvidersManager } from "../render.js";
import { getProviderConfigById, getProviderTypeDisplayName, normalizeProviderValue } from "../provider-helpers.js";
import {
    applyConversationsPayload,
    applyModelsPayload,
    applyProvidersPayload,
    setProviderModalState,
    setSelectedSettingsProviderId,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import { loadConversations, loadModels, loadProviders } from "../store.js";

const PROVIDER_TYPE_OPTIONS = ["mlx", "ollama", "cloud"];


export async function handleProviderSubmit(event) {
    event.preventDefault();

    const providerPayload = readProviderFormValues();
    if (!providerPayload.name) {
        showStatus("The provider needs a name.", true);
        return;
    }
    if (!providerPayload.provider_type) {
        showStatus("The provider type is required.", true);
        return;
    }

    try {
        const isEditing = Boolean(providerPayload.id);
        const payload = isEditing
            ? await updateProvider(providerPayload)
            : await createProvider(providerPayload);

        await refreshProviderDependentState();
        setSelectedSettingsProviderId(payload.provider.id);
        setProviderModalState({
            mode: "edit",
            providerId: payload.provider.id,
        });
        populateProviderModal(payload.provider);
        closeProviderModal();
        renderSettingsProvidersManager();
        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus(isEditing ? "Provider updated." : "Provider created.");
    } catch (error) {
        showStatus(error.message || "The provider could not be saved.", true);
    }
}


export function openCreateProviderModal() {
    setProviderModalState({
        mode: "create",
        providerId: null,
    });
    populateProviderModal();
    openProviderModal();
    elements.providerNameInput?.focus({ preventScroll: true });
}


export function handleProviderEdit(providerId) {
    if (!providerId) {
        return;
    }

    const provider = getProviderConfigById(providerId);
    if (!provider) {
        showStatus("The selected provider was not found.", true);
        return;
    }

    setSelectedSettingsProviderId(provider.id);
    setProviderModalState({
        mode: "edit",
        providerId: provider.id,
    });
    populateProviderModal(provider);
    openProviderModal();
    elements.providerNameInput?.focus({ preventScroll: true });
}


export async function handleProviderDelete(providerId) {
    if (!providerId) {
        return;
    }

    const provider = getProviderConfigById(providerId);
    if (!provider) {
        showStatus("The selected provider was not found.", true);
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Provider",
        title: "Delete provider",
        message: `\"${provider.name}\" will be deleted. Remove or move its models to another provider first.`,
        confirmLabel: "Delete provider",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        await deleteProvider(providerId);
        await refreshProviderDependentState();
        renderSettingsProvidersManager();
        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Provider deleted.");
    } catch (error) {
        showStatus(error.message || "The provider could not be deleted.", true);
    }
}


export async function handleProviderRestore(providerId) {
    if (!providerId) {
        return;
    }

    try {
        await restoreProvider(providerId);
        await refreshProviderDependentState();
        renderSettingsProvidersManager();
        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Provider restored.");
    } catch (error) {
        showStatus(error.message || "The provider could not be restored.", true);
    }
}


export function getProviderTypeOptionsMarkup(selectedType = "") {
    return PROVIDER_TYPE_OPTIONS.map((providerType) => {
        const selected = providerType === normalizeProviderValue(selectedType) ? " selected" : "";
        return `<option value="${providerType}"${selected}>${getProviderTypeDisplayName(providerType)}</option>`;
    }).join("");
}


async function refreshProviderDependentState() {
    applyProvidersPayload(await loadProviders());
    applyModelsPayload(await loadModels());
    applyConversationsPayload(await loadConversations());
}


function readProviderFormValues() {
    return {
        id: Number(elements.providerIdInput?.value || "0") || undefined,
        name: elements.providerNameInput?.value.trim() || "",
        provider_type: normalizeProviderValue(elements.providerTypeSelect?.value),
        endpoint: elements.providerEndpointInput?.value.trim() || "",
        api_key: elements.providerApiKeyInput?.value.trim() || "",
        is_builtin: elements.providerBuiltinInput?.value === "true",
        builtin_key: elements.providerBuiltinKeyInput?.value.trim() || "",
    };
}


function populateProviderModal(provider = null) {
    const isEditing = Boolean(provider);

    elements.providerModalEyebrow.textContent = isEditing ? "Edit provider" : "Provider";
    elements.providerModalTitle.textContent = isEditing ? provider.name : "Create provider";
    elements.providerSubmitButton.textContent = isEditing ? "Save changes" : "Create provider";
    elements.providerIdInput.value = isEditing ? String(provider.id) : "";
    elements.providerBuiltinInput.value = isEditing && provider.is_builtin ? "true" : "false";
    elements.providerBuiltinKeyInput.value = isEditing ? (provider.builtin_key || "") : "";
    elements.providerNameInput.value = provider?.name || "";
    elements.providerTypeSelect.innerHTML = getProviderTypeOptionsMarkup(provider?.provider_type || "cloud");
    elements.providerTypeSelect.value = provider?.provider_type || "cloud";
    elements.providerEndpointInput.value = provider?.endpoint || "";
    elements.providerApiKeyInput.value = "";
    elements.providerApiKeyInput.placeholder = provider?.has_api_key
        ? "Saved key hidden; enter a new key to replace it"
        : "";
}
