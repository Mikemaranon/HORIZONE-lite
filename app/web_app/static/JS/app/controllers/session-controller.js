import {
    delete_token,
    loadPage,
    send_API_request,
} from "../../SERVER_CONN/token-handler.js";
import { updateCurrentUser, updateCurrentUserAvatar } from "../api.js";
import { elements } from "../dom.js";
import {
    closeSessionAvatarModal,
    closeSessionProfileModal,
    openSessionAvatarModal,
    openSessionProfileModal,
} from "../modal-ui.js";
import { renderSettingsSession } from "../render.js";
import { applyCurrentUserPayload } from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";


export function ensureAuthenticated() {
    return true;
}


export function dismissDefaultPasswordWarning() {
    state.defaultPasswordWarningDismissed = true;
    renderSettingsSession();
}


export async function handleLogout() {
    try {
        await send_API_request("POST", "/logout");
    } catch (error) {
        // Continue local sign-out even if the session cookie is already gone.
    }

    delete_token();
    loadPage("/login");
}


export function openSessionProfileEditor() {
    if (!elements.sessionUsernameInput) {
        return;
    }

    elements.sessionProfileForm?.reset();
    elements.sessionUsernameInput.value = state.currentUser?.username || "";
    openSessionProfileModal();
    elements.sessionUsernameInput.focus({ preventScroll: true });
    elements.sessionUsernameInput.select();
}


export function openSessionAvatarEditor() {
    renderSettingsSession();
    openSessionAvatarModal();
    elements.sessionAvatarChangeButton?.focus({ preventScroll: true });
}


export function handleSessionAvatarChangeClick() {
    elements.sessionAvatarInput?.click();
}


export async function handleSessionAvatarInputChange(event) {
    const file = event.target.files?.[0] || null;
    event.target.value = "";
    if (!file) {
        return;
    }
    if (!file.type.startsWith("image/")) {
        showStatus("Choose an image file for the profile photo.", true);
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        showStatus("Choose an image smaller than 10 MB.", true);
        return;
    }

    try {
        const avatarImage = await readFileAsDataUrl(file);
        await saveSessionAvatar(avatarImage);
    } catch (error) {
        showStatus(error.message || "The profile photo could not be updated.", true);
    }
}


export async function handleSessionAvatarDelete() {
    if (!state.currentUser?.avatar_image) {
        return;
    }
    await saveSessionAvatar("");
}


export async function handleSessionProfileSubmit(event) {
    event.preventDefault();

    const username = elements.sessionUsernameInput?.value.trim() || "";
    const currentPassword = elements.sessionCurrentPasswordInput?.value || "";
    const newPassword = elements.sessionNewPasswordInput?.value || "";
    const confirmPassword = elements.sessionConfirmPasswordInput?.value || "";

    if (!username) {
        showStatus("The username cannot be empty.", true);
        elements.sessionUsernameInput?.focus();
        return;
    }

    if (!currentPassword) {
        showStatus("You need the current password to save changes.", true);
        elements.sessionCurrentPasswordInput?.focus();
        return;
    }

    if (newPassword && newPassword !== confirmPassword) {
        showStatus("The new password confirmation does not match.", true);
        elements.sessionConfirmPasswordInput?.focus();
        return;
    }

    try {
        const payload = await updateCurrentUser({
            username,
            current_password: currentPassword,
            password: newPassword,
        });

        applyCurrentUserPayload(payload);
        renderSettingsSession();
        closeSessionProfileModal();
        elements.sessionProfileForm?.reset();
        showStatus(payload.message || "Session profile updated.");
    } catch (error) {
        showStatus(error.message || "The session profile could not be updated.", true);
    }
}


async function saveSessionAvatar(avatarImage) {
    try {
        const payload = await updateCurrentUserAvatar(avatarImage);
        applyCurrentUserPayload(payload);
        renderSettingsSession();
        closeSessionAvatarModal();
        showStatus(payload.message || "Profile photo updated.");
    } catch (error) {
        showStatus(error.message || "The profile photo could not be updated.", true);
    }
}


function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.addEventListener("load", () => resolve(String(reader.result || "")));
        reader.addEventListener("error", () => reject(new Error("The image could not be read.")));
        reader.readAsDataURL(file);
    });
}
