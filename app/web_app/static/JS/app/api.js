import { delete_token, getToken, send_API_request } from "../SERVER_CONN/token-handler.js";


export async function apiRequestJson(method, endpoint, body = null) {
    const response = await send_API_request(method, endpoint, body);
    const payload = await response.json().catch(() => ({}));

    ensureSuccessfulResponse(response, payload);

    if (
        payload.error
        && !payload.response
        && !payload.providers
        && !payload.projects
        && !payload.profiles
        && !payload.conversations
        && !payload.tool
        && !payload.tools
        && !payload.setting
        && !payload.settings
    ) {
        throw new Error(payload.error.message || payload.error);
    }

    return payload;
}


export async function loadProjectsData() {
    return apiRequestJson("GET", "/api/projects");
}


export async function loadProvidersData() {
    return apiRequestJson("GET", "/api/providers");
}


export async function loadProfilesData() {
    return apiRequestJson("GET", "/api/profiles");
}


export async function loadProjectDocumentsData(projectId) {
    return apiRequestJson(
        "GET",
        `/api/projects/documents?project_id=${encodeURIComponent(projectId)}`
    );
}


export async function loadConversationsData(projectId) {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiRequestJson("GET", `/api/conversations${query}`);
}


export async function loadConversationDetailData(conversationId) {
    return apiRequestJson(
        "GET",
        `/api/conversations?id=${encodeURIComponent(conversationId)}&include_messages=1`
    );
}


export async function loadConversationExportData(conversationId) {
    return apiRequestJson(
        "GET",
        `/api/conversations/export?id=${encodeURIComponent(conversationId)}`
    );
}


export async function loadModelsData() {
    return apiRequestJson("GET", "/api/models");
}


export async function loadToolsData() {
    return apiRequestJson("GET", "/api/tools");
}


export async function createModel(data) {
    return apiRequestJson("POST", "/api/models", data);
}


export async function updateModel(data) {
    return apiRequestJson("PATCH", "/api/models", data);
}


export async function deleteModel(modelId) {
    return apiRequestJson("DELETE", `/api/models?id=${encodeURIComponent(modelId)}`);
}


export async function loadSettingsData() {
    return apiRequestJson("GET", "/api/settings");
}


export async function loadCurrentUserData() {
    return apiRequestJson("GET", "/api/users/me");
}


export async function createProject(data) {
    return apiRequestJson("POST", "/api/projects", data);
}


export async function updateProject(data) {
    return apiRequestJson("PATCH", "/api/projects", data);
}


export async function deleteProject(projectId) {
    return apiRequestJson("DELETE", `/api/projects?id=${encodeURIComponent(projectId)}`);
}


export async function uploadProjectDocuments(projectId, files, folderId = null) {
    const formData = new FormData();
    formData.append("project_id", String(projectId));
    if (folderId !== null && folderId !== undefined && folderId !== "") {
        formData.append("folder_id", String(folderId));
    }

    for (const file of files || []) {
        formData.append("files", file, file.name);
    }

    return apiRequestFormData("POST", "/api/projects/documents", formData);
}


export async function deleteProjectDocument(documentId) {
    return apiRequestJson("DELETE", `/api/projects/documents?id=${encodeURIComponent(documentId)}`);
}


export async function moveProjectDocument(documentId, folderId = null) {
    return apiRequestJson("PATCH", "/api/projects/documents", {
        id: documentId,
        folder_id: folderId,
    });
}


export async function createProjectDocumentFolder(data) {
    return apiRequestJson("POST", "/api/projects/document-folders", data);
}


export async function deleteProjectDocumentFolder(folderId) {
    return apiRequestJson("DELETE", `/api/projects/document-folders?id=${encodeURIComponent(folderId)}`);
}


export async function createProfile(data) {
    return apiRequestJson("POST", "/api/profiles", data);
}


export async function createProvider(data) {
    return apiRequestJson("POST", "/api/providers", data);
}


export async function updateProvider(data) {
    return apiRequestJson("PATCH", "/api/providers", data);
}


export async function deleteProvider(providerId) {
    return apiRequestJson("DELETE", `/api/providers?id=${encodeURIComponent(providerId)}`);
}


export async function restoreProvider(providerId) {
    return apiRequestJson("POST", "/api/providers/restore", { id: providerId });
}

export async function updateProfile(data) {
    return apiRequestJson("PATCH", "/api/profiles", data);
}

export async function deleteProfile(profileId) {
    return apiRequestJson("DELETE", `/api/profiles?id=${encodeURIComponent(profileId)}`);
}


export async function createConversation(data) {
    return apiRequestJson("POST", "/api/conversations", data);
}


export async function updateConversation(data) {
    return apiRequestJson("PATCH", "/api/conversations", data);
}


export async function deleteConversation(conversationId) {
    return apiRequestJson("DELETE", `/api/conversations?id=${encodeURIComponent(conversationId)}`);
}


export async function sendChat(data) {
    return apiRequestJson("POST", "/api/chat", data);
}


export async function cancelChatStream(requestId) {
    return apiRequestJson("POST", "/api/chat/cancel", { request_id: requestId });
}


export async function sendChatStream(data, handlers = {}, options = {}) {
    const response = await send_API_request("POST", "/api/chat", {
        ...data,
        stream: true,
    }, {
        signal: options.signal,
    });

    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        ensureSuccessfulResponse(response, payload);
    }

    if (!response.body) {
        throw new Error("The browser does not support streaming responses in this environment.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalResponse = null;

    while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        buffer = buffer.replaceAll("\r\n", "\n");

        let boundaryIndex = buffer.indexOf("\n\n");
        while (boundaryIndex !== -1) {
            const rawEvent = buffer.slice(0, boundaryIndex);
            buffer = buffer.slice(boundaryIndex + 2);

            const event = parseSseEvent(rawEvent);
            if (event) {
                finalResponse = handleStreamEvent(event, handlers) || finalResponse;
            }

            boundaryIndex = buffer.indexOf("\n\n");
        }

        if (done) {
            break;
        }
    }

    const trailingEvent = parseSseEvent(buffer);
    if (trailingEvent) {
        finalResponse = handleStreamEvent(trailingEvent, handlers) || finalResponse;
    }

    if (!finalResponse) {
        throw new Error("The streaming response ended without a final event.");
    }

    return finalResponse;
}


export async function persistSetting(key, value) {
    return apiRequestJson("POST", "/api/settings", { key, value });
}


export async function updateCurrentUser(data) {
    return apiRequestJson("PATCH", "/api/users/me", data);
}


export async function updateTool(data) {
    return apiRequestJson("PATCH", "/api/tools", data);
}


export async function reloadToolsData() {
    return apiRequestJson("POST", "/api/tools/reload", {});
}


export async function uploadToolFile(file, filename = file?.name) {
    const formData = new FormData();
    formData.append("file", file, filename);
    return apiRequestFormData("POST", "/api/tools", formData);
}


function ensureSuccessfulResponse(response, payload) {
    if (!response.ok) {
        const errorMessage = payload.error?.message
            || payload.error
            || payload.message
            || `Request failed: ${response.status}`;

        if (response.status === 401) {
            delete_token();
            window.location.href = "/login";
            throw new Error("Your session has expired.");
        }

        throw new Error(errorMessage);
    }
}


async function apiRequestFormData(method, endpoint, body) {
    const token = getToken();
    if (!token) {
        delete_token();
        window.location.href = "/login";
        throw new Error("Your session has expired.");
    }

    const response = await fetch(endpoint, {
        method: method.toUpperCase(),
        headers: {
            Authorization: `Bearer ${token}`,
        },
        body,
    });

    const payload = await response.json().catch(() => ({}));
    ensureSuccessfulResponse(response, payload);
    return payload;
}


function parseSseEvent(rawEvent) {
    const normalized = (rawEvent || "").trim();
    if (!normalized) {
        return null;
    }

    let eventName = "message";
    const dataLines = [];

    normalized.split("\n").forEach((line) => {
        if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
            return;
        }

        if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
        }
    });

    let payload = {};
    if (dataLines.length) {
        try {
            payload = JSON.parse(dataLines.join("\n"));
        } catch {
            throw new Error("The server response arrived with an invalid streaming format.");
        }
    }

    return {
        event: eventName,
        payload,
    };
}


function handleStreamEvent(event, handlers) {
    if (event.event === "start") {
        handlers.onStart?.(event.payload);
        return null;
    }

    if (event.event === "delta") {
        handlers.onDelta?.(event.payload.delta || "", event.payload);
        return null;
    }

    if (event.event === "tool_start") {
        handlers.onToolStart?.(event.payload, event.payload);
        return null;
    }

    if (event.event === "tool_result") {
        handlers.onToolResult?.(event.payload, event.payload);
        return null;
    }

    if (event.event === "end") {
        handlers.onEnd?.(event.payload.response, event.payload);
        return event.payload.response;
    }

    if (event.event === "error") {
        handlers.onError?.(event.payload.error, event.payload);
        throw new Error(
            event.payload.error?.message
            || "Streaming generation failed."
        );
    }

    return null;
}
