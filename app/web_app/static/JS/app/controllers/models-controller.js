import {
    cancelRuntimeModelDownload,
    createModel,
    deleteModel,
    startRuntimeModelDownload,
    updateConversation,
    updateModel,
} from "../api.js";
import { confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import {
    closeModelModal,
    closeModelSwitchModal,
    closeRuntimeModelCatalogModal,
    openModelModal,
    openModelSwitchModal,
    openRuntimeModelCatalogModal,
} from "../modal-ui.js";
import {
    renderChatPanel,
    renderConversationHeader,
    renderRuntimeModelCatalogSearchResults,
    renderSettingsModelsManager,
    updateRuntimeModelCatalogCard,
} from "../render.js";
import { getProviderTypeDisplayName } from "../provider-helpers.js";
import {
    getDefaultModelConfigId,
    getModelConfigById,
    getSelectedModelConfigId,
} from "../selectors.js";
import {
    applyConversationsPayload,
    applyModelsPayload,
    applyRuntimeModelCatalogPayload,
    patchActiveConversation,
    setModelModalState,
    setPendingModelConfigId,
    setRuntimeModelCatalogSearchState,
    setSelectedSettingsModelId,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import { loadConversations, loadModels, loadRuntimeModelCatalog, searchRuntimeModelCatalog } from "../store.js";
import { requiresProviderSelection } from "../model-form-validation.js";

const ALLOWED_MODEL_ICON_TYPES = new Set([
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
]);
const MAX_MODEL_ICON_SIZE_BYTES = 512 * 1024;
let runtimeDownloadPollTimer = null;
let runtimeCatalogSearchTimer = null;
let runtimeCatalogSearchRequestId = 0;


export async function handleModelSubmit(event) {
    event.preventDefault();

    try {
        const modelPayload = await readModelFormValues();
        if (!modelPayload.name) {
            showStatus("The model needs a technical name.", true);
            return;
        }
        if (requiresProviderSelection(modelPayload, state.models) && !modelPayload.provider_id) {
            showStatus("Select a provider for this model.", true);
            return;
        }

        const isEditing = Boolean(modelPayload.id);
        const payload = isEditing
            ? await updateModel(modelPayload)
            : await createModel(modelPayload);

        applyModelsPayload(await loadModels());
        applyConversationsPayload(await loadConversations());
        setSelectedSettingsModelId(payload.model.id);

        if (state.modelModalContext === "chat-settings") {
            await assignModelToCurrentChat(payload.model.id);
        } else if (!state.activeConversationId) {
            setPendingModelConfigId(getDefaultModelConfigId());
        }

        setModelModalState({
            mode: "edit",
            modelId: payload.model.id,
            context: state.modelModalContext,
        });
        populateModelModal(payload.model);
        closeModelModal();

        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus(isEditing ? "Model updated." : "Model created.");
    } catch (error) {
        showStatus(error.message || "The model could not be saved.", true);
    }
}


export async function handleModelOptionSelect(modelConfigId) {
    if (!modelConfigId) {
        return;
    }

    try {
        await assignModelToCurrentChat(modelConfigId);
        closeModelSwitchModal();
        renderChatPanel();
        renderConversationHeader();
    } catch (error) {
        showStatus(error.message || "The model could not be changed.", true);
    }
}


export function openCreateModelModal(context = "settings") {
    if (!(state.providers || []).length) {
        showStatus("Create at least one provider before creating models.", true);
        return;
    }

    closeModelSwitchModal();
    setModelModalState({
        mode: "create",
        modelId: null,
        context,
    });
    populateModelModal();
    openModelModal();
    elements.modelDisplayNameInput?.focus({ preventScroll: true });
}


export function handleModelEdit(modelConfigId, context = "settings") {
    if (!modelConfigId) {
        return;
    }

    const model = getModelConfigById(modelConfigId);
    if (!model) {
        showStatus("The selected model was not found.", true);
        return;
    }

    setSelectedSettingsModelId(model.id);
    setModelModalState({
        mode: "edit",
        modelId: model.id,
        context,
    });
    populateModelModal(model);
    renderSettingsModelsManager();
    openModelModal();
    elements.modelDisplayNameInput?.focus({ preventScroll: true });
}


export async function handleModelDelete(modelConfigId) {
    if (!modelConfigId) {
        return;
    }

    const model = getModelConfigById(modelConfigId);
    if (!model) {
        showStatus("The selected model was not found.", true);
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Model",
        title: "Delete model",
        message: `\"${model.display_name || model.name}\" will be deleted. Chats using it will move to whatever fallback model the application determines.`,
        confirmLabel: "Delete model",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        await deleteModel(modelConfigId);
        applyModelsPayload(await loadModels());
        applyConversationsPayload(await loadConversations());
        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Model deleted.");
    } catch (error) {
        showStatus(error.message || "The model could not be deleted.", true);
    }
}


export async function handleRuntimeModelDownload(catalogKey) {
    if (!catalogKey) {
        return;
    }

    try {
        await startRuntimeModelDownload(catalogKey);
        await refreshRuntimeModelState();
        syncRuntimeSearchResultsFromCatalog();
        updateRuntimeModelCards([catalogKey]);
        renderSettingsModelsManager();
        showStatus("Runtime model download started.");
        scheduleRuntimeDownloadPolling();
    } catch (error) {
        showStatus(error.message || "The runtime model download could not start.", true);
    }
}


export async function handleRuntimeModelDownloadCancel(downloadId) {
    if (!downloadId) {
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Runtime model",
        title: "Cancel download",
        message: "The partial model file will be removed and you can start the download again later.",
        confirmLabel: "Cancel download",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        const payload = await cancelRuntimeModelDownload(downloadId);
        const catalogKey = payload.download?.catalog_key;
        await refreshRuntimeModelState();
        syncRuntimeSearchResultsFromCatalog();
        updateRuntimeModelCards(catalogKey ? [catalogKey] : getActiveRuntimeDownloadKeys());
        renderSettingsModelsManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Runtime model download cancelled.");
    } catch (error) {
        showStatus(error.message || "The runtime model download could not be cancelled.", true);
    }
}


export function openRuntimeModelCatalog() {
    closeModelSwitchModal();
    setRuntimeModelCatalogSearchState({
        query: "",
        results: [],
        isSearching: false,
    });
    if (elements.runtimeModelCatalogSearchInput) {
        elements.runtimeModelCatalogSearchInput.value = "";
    }
    renderRuntimeModelCatalogSearchResults();
    openRuntimeModelCatalogModal();
    elements.runtimeModelCatalogSearchInput?.focus({ preventScroll: true });
}


export function closeRuntimeModelCatalog() {
    closeRuntimeModelCatalogModal();
}


export function handleRuntimeModelCatalogSearchInput(event) {
    if (event.target.id !== "runtime-model-catalog-search") {
        return;
    }

    const query = event.target.value || "";
    queueRuntimeModelCatalogSearch(query);
}


export function handleActiveChatModelEdit() {
    const activeModelId = getSelectedModelConfigId();
    if (!activeModelId) {
        showStatus("There is no selected model to edit.", true);
        return;
    }

    handleModelEdit(Number(activeModelId), "chat-settings");
}


export function syncChatModelActions() {
    if (!elements.editModelButton) {
        return;
    }

    const activeModelId = getSelectedModelConfigId();
    elements.editModelButton.disabled = !activeModelId;
}


export function openModelSwitcher(context = "chat-settings") {
    renderChatPanel();
    if (elements.modelSwitchModal) {
        elements.modelSwitchModal.dataset.context = context;
    }
    openModelSwitchModal();

    if (elements.modelSwitchSearchInput) {
        elements.modelSwitchSearchInput.value = "";
        elements.modelSwitchSearchInput.focus({ preventScroll: true });
        elements.modelSwitchSearchInput.select();
        filterModelSwitchOptions("");
    }
}


export function handleModelSearchInput(event) {
    if (event.target.id !== "model-switch-search") {
        return;
    }

    filterModelSwitchOptions(event.target.value);
}


export function handleModelSearchClear() {
    if (!elements.modelSwitchSearchInput) {
        return;
    }

    elements.modelSwitchSearchInput.value = "";
    filterModelSwitchOptions("");
    elements.modelSwitchSearchInput.focus({ preventScroll: true });
}


export async function handleModelIconInputChange() {
    try {
        const iconImage = await readModelIconFromInput();
        setModelIconValue(iconImage);
    } catch (error) {
        resetModelIconInputs();
        showStatus(error.message || "The model icon could not be loaded.", true);
    }
}


export function handleModelIconClear() {
    resetModelIconInputs();
}


export function getModelProviderOptionsMarkup(selectedProviderId = null) {
    return (state.providers || []).filter((provider) => !provider.is_system_managed).map((provider) => {
        const selected = Number(selectedProviderId) === provider.id ? " selected" : "";
        return `<option value="${provider.id}"${selected}>${provider.name} · ${getProviderTypeDisplayName(provider.provider_type)}</option>`;
    }).join("");
}


export function scheduleRuntimeDownloadPolling() {
    if (runtimeDownloadPollTimer) {
        window.clearTimeout(runtimeDownloadPollTimer);
    }

    runtimeDownloadPollTimer = window.setTimeout(async () => {
        runtimeDownloadPollTimer = null;
        try {
            const updateKeys = new Set(getActiveRuntimeDownloadKeys());
            await refreshRuntimeModelState();
            getActiveRuntimeDownloadKeys().forEach((catalogKey) => updateKeys.add(catalogKey));
            syncRuntimeSearchResultsFromCatalog();
            updateRuntimeModelCards(updateKeys);
            renderSettingsModelsManager();
            renderChatPanel();
            renderConversationHeader();

            if (hasActiveRuntimeDownloads()) {
                scheduleRuntimeDownloadPolling();
            }
        } catch (error) {
            showStatus(error.message || "Runtime model download status could not be refreshed.", true);
        }
    }, 1000);
}


function filterModelSwitchOptions(query) {
    const normalized = String(query || "").trim().toLowerCase();
    let visibleCount = 0;
    let totalOptions = 0;

    elements.modelSwitchResults?.querySelectorAll("[data-model-switch-option]").forEach((node) => {
        totalOptions += 1;
        const matches = normalized ? node.textContent.toLowerCase().includes(normalized) : true;
        node.hidden = !matches;
        if (matches) {
            visibleCount += 1;
        }
    });

    if (elements.modelSwitchResults) {
        elements.modelSwitchResults.hidden = totalOptions > 0 && visibleCount === 0;
    }
    if (elements.modelSwitchNoResults) {
        elements.modelSwitchNoResults.hidden = visibleCount !== 0 || totalOptions === 0;
    }
    if (elements.modelSwitchSearchClearButton) {
        elements.modelSwitchSearchClearButton.hidden = !normalized;
    }
}


async function assignModelToCurrentChat(modelConfigId) {
    const model = getModelConfigById(modelConfigId);
    if (!model) {
        throw new Error("The selected model was not found.");
    }

    if (state.activeConversationId && state.activeConversation) {
        await updateConversation({
            id: state.activeConversationId,
            model_config_id: model.id,
        });
        patchActiveConversation({
            model_config_id: model.id,
            provider: model.provider,
            model: model.name,
        });
        applyConversationsPayload(await loadConversations());
    } else {
        setPendingModelConfigId(model.id);
    }
}


async function refreshRuntimeModelState() {
    applyRuntimeModelCatalogPayload(await loadRuntimeModelCatalog());
    applyModelsPayload(await loadModels());
}


function syncRuntimeSearchResultsFromCatalog() {
    const results = state.runtimeModelCatalogSearchResults || [];
    if (!results.length) {
        return;
    }

    const catalogByKey = new Map(
        (state.runtimeModelCatalog || []).map((entry) => [entry.catalog_key, entry])
    );

    setRuntimeModelCatalogSearchState({
        results: results.map((entry) => {
            const current = catalogByKey.get(entry.catalog_key);
            if (!current) {
                return entry;
            }

            return {
                ...entry,
                is_installed: current.is_installed,
                model_config_id: current.model_config_id,
                download: current.download,
            };
        }),
    });
}


function updateRuntimeModelCards(catalogKeys) {
    if (!elements.runtimeModelCatalogModal || elements.runtimeModelCatalogModal.hidden) {
        return;
    }

    for (const catalogKey of catalogKeys || []) {
        updateRuntimeModelCatalogCard(catalogKey);
    }
}


function queueRuntimeModelCatalogSearch(query) {
    const normalizedQuery = String(query || "").trim();
    window.clearTimeout(runtimeCatalogSearchTimer);

    setRuntimeModelCatalogSearchState({
        query: normalizedQuery,
        results: normalizedQuery ? state.runtimeModelCatalogSearchResults : [],
        isSearching: Boolean(normalizedQuery),
    });
    renderRuntimeModelCatalogSearchResults();

    if (!normalizedQuery) {
        return;
    }

    runtimeCatalogSearchTimer = window.setTimeout(() => {
        performRuntimeModelCatalogSearch(normalizedQuery);
    }, 350);
}


async function performRuntimeModelCatalogSearch(query) {
    const requestId = runtimeCatalogSearchRequestId + 1;
    runtimeCatalogSearchRequestId = requestId;
    const normalizedQuery = String(query || "").trim();
    if (!normalizedQuery) {
        setRuntimeModelCatalogSearchState({
            query: "",
            results: [],
            isSearching: false,
        });
        renderRuntimeModelCatalogSearchResults();
        return;
    }

    setRuntimeModelCatalogSearchState({
        query: normalizedQuery,
        isSearching: true,
    });
    renderRuntimeModelCatalogSearchResults();

    try {
        const payload = await searchRuntimeModelCatalog(normalizedQuery);
        if (requestId !== runtimeCatalogSearchRequestId) {
            return;
        }
        setRuntimeModelCatalogSearchState({
            query: normalizedQuery,
            results: payload.catalog || [],
            isSearching: false,
        });
    } catch (error) {
        if (requestId !== runtimeCatalogSearchRequestId) {
            return;
        }
        setRuntimeModelCatalogSearchState({
            query: normalizedQuery,
            results: [],
            isSearching: false,
        });
        showStatus(error.message || "The model catalog search failed.", true);
    }

    renderRuntimeModelCatalogSearchResults();
}


function hasActiveRuntimeDownloads() {
    return (state.runtimeModelCatalog || []).some((entry) => (
        isActiveRuntimeDownload(entry)
    ));
}


function getActiveRuntimeDownloadKeys() {
    return (state.runtimeModelCatalog || [])
        .filter(isActiveRuntimeDownload)
        .map((entry) => entry.catalog_key);
}


function isActiveRuntimeDownload(entry) {
    return ["queued", "downloading", "verifying"].includes(entry?.download?.status);
}


async function readModelFormValues() {
    const iconImage = await readModelIconFromInput();
    if (iconImage || !elements.modelIconDataInput?.value) {
        setModelIconValue(iconImage);
    }

    return {
        id: Number(elements.modelIdInput?.value || "0") || undefined,
        display_name: elements.modelDisplayNameInput?.value.trim() || "",
        name: elements.modelNameInput?.value.trim() || "",
        provider_id: Number(elements.modelProviderSelect?.value || "0") || undefined,
        icon_image: elements.modelIconDataInput?.value || "",
        is_default: Boolean(elements.modelDefaultInput?.checked),
        is_builtin: elements.modelBuiltinInput?.value === "true",
    };
}


function populateModelModal(model = null) {
    const isEditing = Boolean(model);
    const isRuntimeModel = model?.provider === "llama_cpp";
    const modelLabel = model?.display_name || model?.name || "";

    elements.modelModalEyebrow.textContent = isRuntimeModel ? "HORIZONE runtime" : (isEditing ? "Edit model" : "Model");
    elements.modelModalTitle.textContent = isEditing ? modelLabel : "Create model";
    elements.modelSubmitButton.textContent = isEditing ? "Save changes" : "Create model";
    elements.modelIdInput.value = isEditing ? String(model.id) : "";
    elements.modelBuiltinInput.value = isEditing && model.is_builtin ? "true" : "false";
    elements.modelDisplayNameInput.value = model?.display_name || model?.name || "";
    elements.modelNameInput.value = model?.name || "";
    elements.modelProviderSelect.innerHTML = getModelProviderOptionsMarkup(model?.provider_id || state.providers[0]?.id || null);
    elements.modelProviderSelect.value = String(model?.provider_id || state.providers[0]?.id || "");
    elements.modelDefaultInput.checked = Boolean(model?.is_default);
    syncRuntimeModelModalFields(isRuntimeModel);
    if (elements.modelIconInput) {
        elements.modelIconInput.value = "";
    }
    setModelIconValue(model?.icon_image || "");
}


function syncRuntimeModelModalFields(isRuntimeModel) {
    const technicalNameField = elements.modelNameInput?.closest(".field");
    const providerField = elements.modelProviderSelect?.closest(".field");

    if (technicalNameField) {
        technicalNameField.hidden = Boolean(isRuntimeModel);
    }
    if (providerField) {
        providerField.hidden = Boolean(isRuntimeModel);
    }

    if (elements.modelNameInput) {
        elements.modelNameInput.disabled = Boolean(isRuntimeModel);
    }
    if (elements.modelProviderSelect) {
        elements.modelProviderSelect.disabled = Boolean(isRuntimeModel);
    }
}


async function readModelIconFromInput() {
    const file = elements.modelIconInput?.files?.[0];
    if (!file) {
        return "";
    }

    if (!ALLOWED_MODEL_ICON_TYPES.has(file.type)) {
        throw new Error("The icon must be PNG, JPEG, WEBP, or GIF.");
    }

    if (file.size > MAX_MODEL_ICON_SIZE_BYTES) {
        throw new Error("The icon exceeds the 512 KB limit.");
    }

    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("The selected icon could not be read."));
        reader.readAsDataURL(file);
    });
}


function resetModelIconInputs() {
    if (elements.modelIconInput) {
        elements.modelIconInput.value = "";
    }
    setModelIconValue("");
}


function setModelIconValue(iconImage) {
    if (elements.modelIconDataInput) {
        elements.modelIconDataInput.value = iconImage || "";
    }
    syncModelIconPreview(iconImage || "");
}


function syncModelIconPreview(iconImage) {
    if (!elements.modelIconPreview) {
        return;
    }

    const hasIcon = Boolean(iconImage);
    elements.modelIconPreview.innerHTML = hasIcon
        ? `<img src="${iconImage}" alt="Model icon preview">`
        : `<span>AI</span>`;

    elements.modelIconPreview.classList.toggle("is-empty", !hasIcon);

    if (elements.modelIconClearButton) {
        elements.modelIconClearButton.hidden = !hasIcon;
    }
}
