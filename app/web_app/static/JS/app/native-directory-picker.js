import { requestNativeDirectoryPicker } from "./api.js";


export async function selectWorkspaceDirectory({ currentPath = "", title = "Choose workspace folder" } = {}) {
    const tauriResult = await selectWithTauri({ currentPath, title });
    if (tauriResult !== undefined) {
        return tauriResult;
    }

    const payload = await requestNativeDirectoryPicker({
        initial_path: currentPath,
        title,
    });
    if (payload.canceled) {
        return null;
    }

    return normalizeDirectoryPayload(payload.directory);
}


async function selectWithTauri({ currentPath, title }) {
    const tauri = window.__TAURI__;
    if (!tauri) {
        return undefined;
    }

    if (tauri.dialog?.open) {
        const selectedPath = await tauri.dialog.open({
            directory: true,
            multiple: false,
            defaultPath: currentPath || undefined,
            title,
        });
        return normalizeDirectoryPayload(selectedPath);
    }

    if (tauri.core?.invoke) {
        const selectedPath = await tauri.core.invoke("select_workspace_directory", {
            initialPath: currentPath || null,
            title,
        });
        return normalizeDirectoryPayload(selectedPath);
    }

    if (tauri.invoke) {
        const selectedPath = await tauri.invoke("select_workspace_directory", {
            initialPath: currentPath || null,
            title,
        });
        return normalizeDirectoryPayload(selectedPath);
    }

    return undefined;
}


function normalizeDirectoryPayload(payload) {
    if (!payload) {
        return null;
    }

    if (Array.isArray(payload)) {
        return normalizeDirectoryPayload(payload[0]);
    }

    if (typeof payload === "string") {
        return {
            root_path: payload,
            display_name: deriveDisplayName(payload),
        };
    }

    const rootPath = payload.root_path || payload.path || payload.value || "";
    if (!rootPath) {
        return null;
    }

    return {
        root_path: rootPath,
        display_name: payload.display_name || deriveDisplayName(rootPath),
    };
}


function deriveDisplayName(path) {
    return String(path || "")
        .replace(/[\\\/]+$/, "")
        .split(/[\\\/]/)
        .pop() || "Workspace";
}
