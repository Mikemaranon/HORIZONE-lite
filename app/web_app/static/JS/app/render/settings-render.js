import { elements } from "../dom.js";
import { createModelAvatarMarkup, escapeHtml } from "../html.js";
import { PROFILE_SETTINGS_PREVIEW_TAGS } from "../profile-helpers.js";
import { getProviderTypeDisplayName } from "../provider-helpers.js";
import {
    getDefaultProfileId,
    getSelectedModelConfigId,
    getSelectedProfileId,
} from "../selectors.js";
import {
    setSelectedSettingsProviderId,
    setSelectedSettingsProfileId,
} from "../state-actions.js";
import { state } from "../state.js";


export function renderSettingsSpace() {
    elements.settingsSpace.hidden = state.workspaceMode !== "settings";
}


export function renderSettingsSession() {
    if (!elements.sessionUsernameValue || !elements.sessionRoleValue) {
        return;
    }

    const username = state.currentUser?.username || "Sin sesión";
    const role = state.currentUser?.role || "unknown";

    elements.sessionUsernameValue.textContent = username;
    elements.sessionRoleValue.textContent = `Rol: ${role}`;
}


export function renderSettingsProvidersManager() {
    if (!elements.settingsProvidersList) {
        return;
    }

    const providers = state.providers || [];
    const fallbackProviderId = providers.some(
        (provider) => provider.id === Number(state.selectedSettingsProviderId)
    )
        ? Number(state.selectedSettingsProviderId)
        : (providers[0]?.id || null);
    setSelectedSettingsProviderId(fallbackProviderId || null);

    elements.settingsProvidersList.innerHTML = providers.length
        ? providers.map((provider) => {
            const typeBadge = `<span class="profile-summary-card__tag">${escapeHtml(getProviderTypeDisplayName(provider.provider_type))}</span>`;
            const builtinBadge = provider.is_builtin
                ? `<span class="profile-summary-card__badge">Integrado</span>`
                : "";
            const endpoint = provider.endpoint || "Sin endpoint configurado";
            const actions = provider.is_builtin
                ? `
                    <button
                        class="ghost-button ghost-button--compact"
                        type="button"
                        data-edit-provider-id="${provider.id}"
                    >
                        Editar
                    </button>
                    <button
                        class="ghost-button ghost-button--compact"
                        type="button"
                        data-restore-provider-id="${provider.id}"
                    >
                        Restore
                    </button>
                `
                : `
                    <button
                        class="ghost-button ghost-button--compact"
                        type="button"
                        data-edit-provider-id="${provider.id}"
                    >
                        Editar
                    </button>
                    <button
                        class="action-button action-button--danger action-button--compact"
                        type="button"
                        data-delete-provider-id="${provider.id}"
                    >
                        Borrar
                    </button>
                `;

            return `
                <article class="profile-summary-card">
                    <div class="profile-summary-card__top">
                        <div class="profile-summary-card__heading">
                            <strong class="profile-summary-card__name">${escapeHtml(provider.name)}</strong>
                            <p class="profile-summary-card__personality">${escapeHtml(endpoint)}</p>
                        </div>
                        <div class="profile-summary-card__status">
                            ${builtinBadge}
                        </div>
                    </div>
                    <div class="profile-summary-card__footer">
                        <div class="profile-summary-card__tags">${typeBadge}</div>
                        <div class="profile-summary-card__actions">
                            ${actions}
                        </div>
                    </div>
                </article>
            `;
        }).join("")
        : `<div class="profiles-manager__empty">Todavía no hay proveedores guardados.</div>`;
}


export function renderSettingsModelsManager() {
    if (!elements.settingsModelsList) {
        return;
    }

    const models = state.models || [];
    elements.settingsModelsList.innerHTML = models.length
        ? models.map((model) => {
            const defaultBadge = model.is_default
                ? `<span class="profile-summary-card__badge">Default</span>`
                : "";
            const modelLabel = model.display_name || model.name;
            const avatar = createModelAvatarMarkup(modelLabel, model.icon_image, "model-badge-avatar");
            return `
                <article class="profile-summary-card">
                    <div class="profile-summary-card__top">
                        <div class="profile-summary-card__heading">
                            <div class="profile-summary-card__identity">
                                ${avatar}
                                <strong class="profile-summary-card__name">${escapeHtml(modelLabel)}</strong>
                            </div>
                            <p class="profile-summary-card__personality">${escapeHtml(model.name)}</p>
                        </div>
                        <div class="profile-summary-card__status">
                            ${defaultBadge}
                        </div>
                    </div>
                    <div class="profile-summary-card__footer">
                        <div class="profile-summary-card__tags">
                            <span class="profile-summary-card__tag">${escapeHtml(getProviderTypeDisplayName(model.provider_type || model.provider))}</span>
                        </div>
                        <div class="profile-summary-card__actions">
                            <button
                                class="ghost-button ghost-button--compact"
                                type="button"
                                data-edit-model-id="${model.id}"
                            >
                                Editar
                            </button>
                            <button
                                class="action-button action-button--danger action-button--compact"
                                type="button"
                                data-delete-model-id="${model.id}"
                            >
                                Borrar
                            </button>
                        </div>
                    </div>
                </article>
            `;
        }).join("")
        : `<div class="profiles-manager__empty">Todavía no hay modelos guardados.</div>`;
}


export function renderSettingsProfilesManager() {
    if (!elements.settingsProfilesList) {
        return;
    }

    const profiles = state.profiles || [];
    const fallbackProfileId = profiles.some(
        (profile) => profile.id === Number(state.selectedSettingsProfileId)
    )
        ? Number(state.selectedSettingsProfileId)
        : getDefaultProfileId();
    setSelectedSettingsProfileId(fallbackProfileId || null);

    elements.settingsProfilesList.innerHTML = profiles.length
        ? profiles.map((profile) => {
            const isSelected = profile.id === Number(state.selectedSettingsProfileId);
            const defaultBadge = profile.is_default
                ? `<span class="profile-summary-card__badge">Default</span>`
                : "";
            const personality = profile.personality || "Sin personalidad definida";
            const tags = Array.isArray(profile.tags) ? profile.tags.slice(0, PROFILE_SETTINGS_PREVIEW_TAGS) : [];
            const tagsMarkup = tags.length
                ? tags.map((tag) => `
                    <span class="profile-summary-card__tag">${escapeHtml(tag)}</span>
                `).join("")
                : `<span class="profile-summary-card__tag profile-summary-card__tag--muted">Sin etiquetas</span>`;

            return `
                <article class="profile-summary-card${isSelected ? " is-selected" : ""}" data-settings-profile-card="${profile.id}">
                    <div class="profile-summary-card__top">
                        <div class="profile-summary-card__heading">
                            <strong class="profile-summary-card__name">${escapeHtml(profile.name)}</strong>
                            <p class="profile-summary-card__personality">${escapeHtml(personality)}</p>
                        </div>
                        <div class="profile-summary-card__status">
                            ${defaultBadge}
                        </div>
                    </div>
                    <div class="profile-summary-card__footer">
                        <div class="profile-summary-card__tags">${tagsMarkup}</div>
                        <div class="profile-summary-card__actions">
                            <button
                                class="ghost-button ghost-button--compact"
                                type="button"
                                data-edit-profile-id="${profile.id}"
                            >
                                Editar
                            </button>
                            <button
                                class="action-button action-button--danger action-button--compact"
                                type="button"
                                data-delete-profile-id="${profile.id}"
                            >
                                Borrar
                            </button>
                        </div>
                    </div>
                </article>
            `;
        }).join("")
        : `<div class="profiles-manager__empty">Todavía no hay perfiles guardados.</div>`;
}


export function renderSettingsToolsManager() {
    if (!elements.settingsToolsList) {
        return;
    }

    const tools = getSortedTools().filter((tool) => (
        state.toolsShowActiveOnly ? tool.is_active : true
    ));
    if (elements.settingsFilterToolsButton) {
        elements.settingsFilterToolsButton.setAttribute(
            "aria-pressed",
            state.toolsShowActiveOnly ? "true" : "false",
        );
    }
    elements.settingsToolsList.innerHTML = tools.length
        ? tools.map((tool) => createToolCardMarkup(tool, "data-settings-tool-toggle")).join("")
        : `<div class="profiles-manager__empty">${
            state.toolsShowActiveOnly
                ? "No hay tools activas ahora mismo."
                : "Todavia no hay tools disponibles. Sube un archivo .py para empezar."
        }</div>`;
}


export function renderChatPanel() {
    renderChatToolsList();
    renderChatModelCard();
    renderModelSwitchModal();
    renderChatProfileCard();
    renderProfileSwitchModal();
}


export function renderModelSwitchModal() {
    if (!elements.modelSwitchResults) {
        return;
    }

    const models = state.models || [];
    const selectedModelId = getSelectedModelConfigId();
    const query = elements.modelSwitchSearchInput?.value || "";

    elements.modelSwitchResults.innerHTML = models.length
        ? models.map((model) => {
            const isSelected = model.id === Number(selectedModelId);
            const suffix = model.is_default ? " · default" : "";
            const modelLabel = model.display_name || model.name;
            const avatar = createModelAvatarMarkup(modelLabel, model.icon_image, "model-badge-avatar model-badge-avatar--switch");
            return `
                <button
                    class="profile-switch__option${isSelected ? " is-selected" : ""}"
                    type="button"
                    data-model-switch-option="${model.id}"
                >
                    <span class="profile-switch__option-top">
                        ${avatar}
                        <span class="profile-switch__option-name">${escapeHtml(modelLabel)}</span>
                    </span>
                    <span class="profile-switch__option-meta">${escapeHtml(model.name)}</span>
                    <span class="profile-switch__option-meta">${escapeHtml((model.provider_name || getProviderTypeDisplayName(model.provider)) + suffix)}</span>
                </button>
            `;
        }).join("")
        : `<div class="profile-switch__empty">Todavía no hay modelos. Crea el primero desde ajustes generales.</div>`;

    applySwitchQueryState({
        resultsElement: elements.modelSwitchResults,
        emptyElement: elements.modelSwitchNoResults,
        optionSelector: "[data-model-switch-option]",
        query,
    });
}


export function renderProfileSwitchModal() {
    if (!elements.profileSwitchResults) {
        return;
    }

    const profiles = state.profiles || [];
    const selectedProfileId = getSelectedProfileId();
    const query = elements.profileSwitchSearchInput?.value || "";

    elements.profileSwitchResults.innerHTML = profiles.length
        ? profiles.map((profile) => {
            const isSelected = profile.id === Number(selectedProfileId);
            const suffix = profile.is_default ? " · default" : "";
            return `
                <button
                    class="profile-switch__option${isSelected ? " is-selected" : ""}"
                    type="button"
                    data-profile-switch-option="${profile.id}"
                >
                    <span class="profile-switch__option-name">${escapeHtml(profile.name)}</span>
                    <span class="profile-switch__option-meta">${escapeHtml((profile.system_prompt || "Sin system prompt") + suffix)}</span>
                </button>
            `;
        }).join("")
        : `<div class="profile-switch__empty">Todavía no hay perfiles. Crea el primero desde ajustes generales.</div>`;

    applySwitchQueryState({
        resultsElement: elements.profileSwitchResults,
        emptyElement: elements.profileSwitchNoResults,
        optionSelector: "[data-profile-switch-option]",
        query,
    });
}


function renderChatToolsList() {
    if (!elements.chatToolsList) {
        return;
    }

    const tools = getSortedTools();
    elements.chatToolsList.innerHTML = tools.length
        ? tools.map((tool) => createToolCardMarkup(tool, "data-chat-tool-toggle")).join("")
        : `<div class="chat-profile-card__empty">No hay tools listas todavia. Sube una desde ajustes generales o activa una de las integradas.</div>`;
}


function getSortedTools() {
    return [...(state.tools || [])].sort((left, right) => {
        if (left.is_builtin !== right.is_builtin) {
            return left.is_builtin ? -1 : 1;
        }
        const leftLabel = String(left.display_name || left.name || "");
        const rightLabel = String(right.display_name || right.name || "");
        const displayComparison = leftLabel.localeCompare(rightLabel);
        if (displayComparison !== 0) {
            return displayComparison;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
    });
}


function createToolCardMarkup(tool, toggleAttribute) {
    const isEnabled = Boolean(tool.is_active);
    const toolLabel = tool.display_name || tool.name;
    const toggleActionLabel = `${isEnabled ? "Desactivar" : "Activar"} ${toolLabel}`;
    const badges = [
        tool.is_builtin
            ? `<span class="profile-summary-card__tag">Integrada</span>`
            : `<span class="profile-summary-card__tag">Custom</span>`,
        `<span class="profile-summary-card__tag">${escapeHtml(tool.name)}</span>`,
        `<span class="profile-summary-card__tag">${escapeHtml(tool.filename || "tool.py")}</span>`,
    ].join("");

    return `
        <article class="chat-tool-card${isEnabled ? " is-enabled" : ""}">
            <div class="chat-tool-card__copy">
                <div class="chat-tool-card__heading">
                    <strong>${escapeHtml(toolLabel)}</strong>
                </div>
                <p>${escapeHtml(tool.description || "Sin descripcion.")}</p>
                <div class="chat-tool-card__meta">${badges}</div>
            </div>
            <button
                class="chat-tool-card__toggle"
                type="button"
                ${toggleAttribute}="${tool.id}"
                aria-pressed="${isEnabled ? "true" : "false"}"
                aria-label="${escapeHtml(toggleActionLabel)}"
                title="${escapeHtml(toggleActionLabel)}"
            >
                <span class="chat-tool-card__switch" aria-hidden="true">
                    <span class="chat-tool-card__switch-thumb"></span>
                </span>
            </button>
        </article>
    `;
}


function renderChatModelCard() {
    if (!elements.chatModelCard) {
        return;
    }

    const model = state.models.find((item) => item.id === Number(getSelectedModelConfigId())) || null;

    if (!model) {
        if (elements.editModelButton) {
            elements.editModelButton.disabled = true;
        }
        if (elements.changeModelButton) {
            elements.changeModelButton.disabled = true;
        }
        elements.chatModelCard.innerHTML = `
            <div class="chat-profile-card__empty">
                No hay modelos configurados todavía. Crea uno desde ajustes generales para poder chatear.
            </div>
        `;
        return;
    }

    elements.chatModelCard.innerHTML = createModelCardMarkup(model, { includeDefaultBadge: true });

    if (elements.editModelButton) {
        elements.editModelButton.disabled = false;
    }
    if (elements.changeModelButton) {
        elements.changeModelButton.disabled = state.models.length <= 1;
    }
}


function renderChatProfileCard() {
    if (!elements.chatProfileCard) {
        return;
    }

    const selectedProfileId = getSelectedProfileId();
    const profile = (state.profiles || []).find((item) => item.id === Number(selectedProfileId)) || null;

    if (!profile) {
        if (elements.editProfileButton) {
            elements.editProfileButton.disabled = true;
        }
        elements.chatProfileCard.innerHTML = `
            <div class="chat-profile-card__empty">
                No hay perfiles disponibles todavía. Crea uno para definir el comportamiento del chat.
            </div>
        `;
        return;
    }

    const tags = Array.isArray(profile.tags) ? profile.tags.slice(0, PROFILE_SETTINGS_PREVIEW_TAGS) : [];
    const tagsMarkup = tags.length
        ? tags.map((tag) => `<span class="chat-profile-card__tag">${escapeHtml(tag)}</span>`).join("")
        : `<span class="chat-profile-card__tag chat-profile-card__tag--muted">Sin etiquetas</span>`;
    const defaultBadge = profile.is_default
        ? `<span class="chat-profile-card__badge">Default</span>`
        : "";

    elements.chatProfileCard.innerHTML = `
        <article class="chat-profile-card__surface">
            <div class="chat-profile-card__top">
                <div class="chat-profile-card__heading">
                    <strong>${escapeHtml(profile.name)}</strong>
                    <span>${escapeHtml(profile.personality || "Sin personalidad definida")}</span>
                </div>
                ${defaultBadge}
            </div>
            <div class="chat-profile-card__meta">
                <span class="chat-profile-card__metric">Temp ${escapeHtml(String(profile.temperature ?? 0.7))}</span>
                <span class="chat-profile-card__metric">Top P ${escapeHtml(String(profile.top_p ?? 1))}</span>
                <span class="chat-profile-card__metric">Max ${escapeHtml(String(profile.max_tokens ?? 2048))}</span>
            </div>
            <div class="chat-profile-card__tags">${tagsMarkup}</div>
        </article>
    `;

    if (elements.editProfileButton) {
        elements.editProfileButton.disabled = false;
    }
}


function createModelCardMarkup(model, { includeDefaultBadge = false } = {}) {
    const modelLabel = model.display_name || model.name;
    const defaultBadge = includeDefaultBadge && model.is_default
        ? `<span class="chat-profile-card__badge">Default</span>`
        : "";

    return `
        <article class="chat-profile-card__surface">
            <div class="chat-profile-card__top">
                <div class="chat-profile-card__heading">
                    <div class="chat-profile-card__identity">
                        ${createModelAvatarMarkup(modelLabel, model.icon_image, "model-badge-avatar model-badge-avatar--card")}
                        <strong>${escapeHtml(modelLabel)}</strong>
                    </div>
                </div>
                ${defaultBadge}
            </div>
            <div class="chat-profile-card__tags">
                <span class="chat-profile-card__tag">${escapeHtml(model.name)}</span>
                <span class="chat-profile-card__tag">${escapeHtml(model.provider_name || getProviderTypeDisplayName(model.provider))}</span>
            </div>
        </article>
    `;
}


function applySwitchQueryState({
    resultsElement,
    emptyElement,
    optionSelector,
    query,
}) {
    const normalized = String(query || "").trim().toLowerCase();
    let visibleCount = 0;
    let totalOptions = 0;

    resultsElement?.querySelectorAll(optionSelector).forEach((node) => {
        totalOptions += 1;
        const matches = normalized ? node.textContent.toLowerCase().includes(normalized) : true;
        node.hidden = !matches;
        if (matches) {
            visibleCount += 1;
        }
    });

    if (resultsElement) {
        resultsElement.hidden = totalOptions > 0 && visibleCount === 0;
    }
    if (emptyElement) {
        emptyElement.hidden = visibleCount !== 0 || totalOptions === 0;
    }
}
