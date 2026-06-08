import { createProfile, deleteProfile, updateConversation, updateProfile } from "../api.js";
import { confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import { closeProfileModal, closeProfileSwitchModal, openProfileModal, openProfileSwitchModal } from "../modal-ui.js";
import { MAX_PROFILE_TAGS } from "../profile-helpers.js";
import { renderChatPanel, renderConversationHeader, renderSettingsProfilesManager } from "../render.js";
import { getDefaultProfileId } from "../selectors.js";
import {
    handleModelDelete,
    handleModelEdit,
    handleModelOptionSelect,
    handleRuntimeModelDownload,
    handleRuntimeModelDownloadCancel,
} from "./models-controller.js";
import { handleProviderDelete, handleProviderEdit, handleProviderRestore } from "./providers-controller.js";
import {
    applyConversationsPayload,
    applyProfilesPayload,
    patchActiveConversation,
    setPendingProfileId,
    setProfileModalState,
    setSelectedSettingsProfileId,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import { loadConversations, loadProfiles } from "../store.js";


export async function handleProfileSubmit(event) {
    event.preventDefault();

    const profilePayload = readProfileFormValues({
        idInput: elements.profileIdInput,
        nameInput: elements.profileNameInput,
        personalityInput: elements.profilePersonalityInput,
        tagsInput: elements.profileTagsInput,
        systemPromptInput: elements.profileSystemPromptInput,
        temperatureInput: elements.profileTemperatureInput,
        topPInput: elements.profileTopPInput,
        maxTokensInput: elements.profileMaxTokensInput,
        defaultInput: elements.profileDefaultInput,
    });

    if (!profilePayload.name) {
        showStatus("The profile needs a name.", true);
        return;
    }
    if (profilePayload.tags.length > MAX_PROFILE_TAGS) {
        showStatus(`Tags support a maximum of ${MAX_PROFILE_TAGS} items.`, true);
        return;
    }

    try {
        const isEditing = Boolean(profilePayload.id);
        const payload = isEditing
            ? await updateProfile(profilePayload)
            : await createProfile(profilePayload);

        applyProfilesPayload(await loadProfiles());
        setSelectedSettingsProfileId(payload.profile.id);

        if (!isEditing && state.profileModalContext === "chat-settings") {
            if (state.activeConversationId && state.activeConversation) {
                await updateConversation({
                    id: state.activeConversationId,
                    profile_id: payload.profile.id,
                });
                patchActiveConversation({ profile_id: payload.profile.id });
            } else {
                setPendingProfileId(payload.profile.id);
            }
        }

        setProfileModalState({
            mode: "edit",
            profileId: payload.profile.id,
            context: state.profileModalContext,
        });
        populateProfileModal(payload.profile);
        closeProfileModal();

        renderSettingsProfilesManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus(isEditing ? "Profile updated." : "Profile created.");
    } catch (error) {
        showStatus(error.message || "The profile could not be saved.", true);
    }
}


export async function handleProfileOptionSelect(profileId) {
    if (!profileId) {
        return;
    }

    try {
        if (state.activeConversationId && state.activeConversation) {
            await updateConversation({
                id: state.activeConversationId,
                profile_id: profileId,
            });
            patchActiveConversation({ profile_id: profileId });
            applyConversationsPayload(await loadConversations());
        } else {
            setPendingProfileId(profileId);
        }

        closeProfileSwitchModal();
        renderChatPanel();
        renderConversationHeader();
    } catch (error) {
        showStatus(error.message || "The chat profile could not be changed.", true);
    }
}


export function openCreateProfileModal(context = "settings") {
    closeProfileSwitchModal();
    setProfileModalState({
        mode: "create",
        profileId: null,
        context,
    });
    populateProfileModal();
    openProfileModal();
    elements.profileNameInput?.focus({ preventScroll: true });
}


export function handleSettingsProfileEdit(profileId, context = "settings") {
    if (!profileId) {
        return;
    }

    const profile = state.profiles.find((item) => item.id === profileId);
    if (!profile) {
        showStatus("The selected profile was not found.", true);
        return;
    }

    setSelectedSettingsProfileId(profileId);
    setProfileModalState({
        mode: "edit",
        profileId,
        context,
    });
    populateProfileModal(profile);
    renderSettingsProfilesManager();
    openProfileModal();
    elements.profileNameInput?.focus({ preventScroll: true });
}


export async function handleSettingsProfileDelete(profileId) {
    if (!profileId) {
        return;
    }

    const profile = state.profiles.find((item) => item.id === profileId);
    if (!profile) {
        showStatus("The selected profile was not found.", true);
        return;
    }

    const confirmed = await confirmAction({
        eyebrow: "Profile",
        title: "Delete profile",
        message: `\"${profile.name}\" will be deleted. Chats using it will end up without an explicit profile.`,
        confirmLabel: "Delete profile",
        confirmVariant: "danger",
    });

    if (!confirmed) {
        return;
    }

    try {
        await deleteProfile(profileId);
        applyProfilesPayload(await loadProfiles());
        applyConversationsPayload(await loadConversations());

        const fallbackProfileId = getDefaultProfileId();

        if (Number(state.pendingProfileId) === profileId) {
            setPendingProfileId(fallbackProfileId);
        }

        if (state.activeConversation && Number(state.activeConversation.profile_id) === profileId) {
            patchActiveConversation({ profile_id: fallbackProfileId });
        }

        if (Number(state.selectedSettingsProfileId) === profileId) {
            setSelectedSettingsProfileId(fallbackProfileId);
        }

        renderSettingsProfilesManager();
        renderChatPanel();
        renderConversationHeader();
        showStatus("Profile deleted.");
    } catch (error) {
        showStatus(error.message || "The profile could not be deleted.", true);
    }
}


export function handleDocumentClick(event, { handleProjectDocumentDelete }) {
    const deleteProjectDocumentButton = event.target.closest("[data-delete-project-document-id]");
    if (deleteProjectDocumentButton) {
        handleProjectDocumentDelete(Number(deleteProjectDocumentButton.dataset.deleteProjectDocumentId));
        return;
    }

    const option = event.target.closest("[data-profile-switch-option]");
    if (option) {
        handleProfileOptionSelect(Number(option.dataset.profileSwitchOption));
        return;
    }

    const modelOption = event.target.closest("[data-model-switch-option]");
    if (modelOption) {
        handleModelOptionSelect(Number(modelOption.dataset.modelSwitchOption));
        return;
    }

    const editModelButton = event.target.closest("[data-edit-model-id]");
    if (editModelButton) {
        handleModelEdit(Number(editModelButton.dataset.editModelId), "settings");
        return;
    }

    const deleteModelButton = event.target.closest("[data-delete-model-id]");
    if (deleteModelButton) {
        handleModelDelete(Number(deleteModelButton.dataset.deleteModelId));
        return;
    }

    const runtimeModelDownloadButton = event.target.closest("[data-runtime-model-download]");
    if (runtimeModelDownloadButton) {
        handleRuntimeModelDownload(runtimeModelDownloadButton.dataset.runtimeModelDownload);
        return;
    }

    const runtimeModelDownloadCancelButton = event.target.closest("[data-runtime-model-download-cancel]");
    if (runtimeModelDownloadCancelButton) {
        handleRuntimeModelDownloadCancel(
            Number(runtimeModelDownloadCancelButton.dataset.runtimeModelDownloadCancel)
        );
        return;
    }

    const editProviderButton = event.target.closest("[data-edit-provider-id]");
    if (editProviderButton) {
        handleProviderEdit(Number(editProviderButton.dataset.editProviderId));
        return;
    }

    const deleteProviderButton = event.target.closest("[data-delete-provider-id]");
    if (deleteProviderButton) {
        handleProviderDelete(Number(deleteProviderButton.dataset.deleteProviderId));
        return;
    }

    const restoreProviderButton = event.target.closest("[data-restore-provider-id]");
    if (restoreProviderButton) {
        handleProviderRestore(Number(restoreProviderButton.dataset.restoreProviderId));
        return;
    }

    const editProfileButton = event.target.closest("[data-edit-profile-id]");
    if (editProfileButton) {
        handleSettingsProfileEdit(Number(editProfileButton.dataset.editProfileId));
        return;
    }

    const deleteProfileButton = event.target.closest("[data-delete-profile-id]");
    if (deleteProfileButton) {
        handleSettingsProfileDelete(Number(deleteProfileButton.dataset.deleteProfileId));
        return;
    }

}


export function handleActiveChatProfileEdit() {
    const activeProfileId = state.activeConversation?.profile_id || state.pendingProfileId || getDefaultProfileId();
    if (!activeProfileId) {
        showStatus("There is no selected profile to edit.", true);
        return;
    }

    handleSettingsProfileEdit(Number(activeProfileId), "chat-settings");
}


export function syncChatProfileActions() {
    if (!elements.editProfileButton) {
        return;
    }

    const activeProfileId = state.activeConversation?.profile_id || state.pendingProfileId || getDefaultProfileId();
    elements.editProfileButton.disabled = !activeProfileId;
}


export function openProfileSwitcher() {
    renderChatPanel();
    openProfileSwitchModal();
    if (elements.profileSwitchSearchInput) {
        elements.profileSwitchSearchInput.value = "";
        elements.profileSwitchSearchInput.focus({ preventScroll: true });
        elements.profileSwitchSearchInput.select();
        filterProfileSwitchOptions(elements.profileSwitchSearchInput.value);
    }
}


export function handleDocumentInput(event) {
    if (event.target.id !== "profile-switch-search") {
        return;
    }

    filterProfileSwitchOptions(event.target.value);
}


export function handleProfileSearchClear() {
    if (!elements.profileSwitchSearchInput) {
        return;
    }

    elements.profileSwitchSearchInput.value = "";
    filterProfileSwitchOptions("");
    elements.profileSwitchSearchInput.focus({ preventScroll: true });
}


export function filterProfileSwitchOptions(query) {
    const normalized = String(query || "").trim().toLowerCase();
    let visibleCount = 0;
    let totalOptions = 0;

    elements.profileSwitchResults?.querySelectorAll("[data-profile-switch-option]").forEach((node) => {
        totalOptions += 1;
        const matches = normalized ? node.textContent.toLowerCase().includes(normalized) : true;
        node.hidden = !matches;
        if (matches) {
            visibleCount += 1;
        }
    });

    if (elements.profileSwitchResults) {
        elements.profileSwitchResults.hidden = totalOptions > 0 && visibleCount === 0;
    }
    if (elements.profileSwitchNoResults) {
        elements.profileSwitchNoResults.hidden = visibleCount !== 0 || totalOptions === 0;
    }
    if (elements.profileSwitchSearchClearButton) {
        elements.profileSwitchSearchClearButton.hidden = !normalized;
    }
}


function readProfileFormValues({
    idInput,
    nameInput,
    personalityInput,
    tagsInput,
    systemPromptInput,
    temperatureInput,
    topPInput,
    maxTokensInput,
    defaultInput,
}) {
    return {
        id: Number(idInput?.value || "0") || undefined,
        name: nameInput.value.trim(),
        personality: personalityInput.value.trim(),
        tags: tagsInput.value
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        system_prompt: systemPromptInput.value.trim(),
        temperature: Number(temperatureInput.value || "0.7"),
        top_p: Number(topPInput.value || "1"),
        max_tokens: Number(maxTokensInput.value || "2048"),
        is_default: defaultInput.checked,
    };
}


function populateProfileModal(profile = null) {
    const isEditing = Boolean(profile);
    const tags = Array.isArray(profile?.tags) ? profile.tags.slice(0, MAX_PROFILE_TAGS).join(", ") : "";

    elements.profileModalEyebrow.textContent = isEditing ? "Edit profile" : "Profile";
    elements.profileModalTitle.textContent = isEditing ? profile.name : "Create profile";
    elements.profileSubmitButton.textContent = isEditing ? "Save changes" : "Create profile";
    elements.profileIdInput.value = isEditing ? String(profile.id) : "";
    elements.profileNameInput.value = profile?.name || "";
    elements.profilePersonalityInput.value = profile?.personality || "";
    elements.profileTagsInput.value = tags;
    elements.profileSystemPromptInput.value = profile?.system_prompt || "";
    elements.profileTemperatureInput.value = String(profile?.temperature ?? 0.7);
    elements.profileTopPInput.value = String(profile?.top_p ?? 1);
    elements.profileMaxTokensInput.value = String(profile?.max_tokens ?? 2048);
    elements.profileDefaultInput.checked = Boolean(profile?.is_default);
}
