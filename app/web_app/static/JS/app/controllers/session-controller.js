import {
    delete_token,
    getToken,
    loadPage,
    send_API_request,
    store_token,
} from "../../SERVER_CONN/token-handler.js";
import { updateCurrentUser } from "../api.js";
import { elements } from "../dom.js";
import { closeSessionProfileModal, openSessionProfileModal } from "../modal-ui.js";
import { renderSettingsSession } from "../render.js";
import { applyCurrentUserPayload } from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";


export function ensureAuthenticated() {
    return true;
}


export async function handleLogout() {
    try {
        await send_API_request("POST", "/logout");
    } catch (error) {
        console.warn("Logout server call failed:", error);
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

        if (payload.token) {
            store_token(payload.token);
        }

        applyCurrentUserPayload(payload);
        renderSettingsSession();
        closeSessionProfileModal();
        elements.sessionProfileForm?.reset();
        showStatus(payload.message || "Session profile updated.");
    } catch (error) {
        showStatus(error.message || "The session profile could not be updated.", true);
    }
}
