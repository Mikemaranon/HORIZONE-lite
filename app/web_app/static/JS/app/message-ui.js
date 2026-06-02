import { elements } from "./dom.js";
import { createModelAvatarMarkup, escapeHtml } from "./html.js";
import { renderMarkdown } from "./markdown.js";
import { closeToolTraceModal, openToolTraceModal } from "./modal-ui.js";
import { applySyntaxHighlighting } from "./syntax-highlight.js";
import {
    getModelConfigById,
    getModelDisplayNameById,
    getProjectAgentNameForMessage,
    getSelectedProjectAgent,
    getProfileNameById,
    getSelectedModelConfigId,
    getSelectedProfileId,
} from "./selectors.js";
import { state } from "./state.js";

const MESSAGES_AUTO_SCROLL_THRESHOLD = 24;
let messageClientKeyCounter = 0;


export function createMessageMarkup(message) {
    const isUser = message.role === "user";
    const roleLabel = isUser ? "You" : null;
    const contentClass = isUser ? "message__content--plain" : "message__content--markdown";
    const renderedContent = isUser
        ? escapeHtml(message.content || "")
        : renderMarkdown(message.content || "");
    const persistentToolStatusMarkup = isUser ? "" : createPersistentToolStatusListMarkup(message);
    const toolConfirmationMarkup = isUser ? "" : createPendingToolConfirmationListMarkup(message);

    return createMessageFrameMarkup(
        message,
        `
            <div class="message__content ${contentClass}" data-message-content="true">${renderedContent}</div>
            ${persistentToolStatusMarkup}
            ${toolConfirmationMarkup}
        `,
        createMessageMetaMarkup(message, roleLabel),
    );
}


export function isMessagesContainerNearBottom() {
    const container = elements.messagesContainer;

    if (!container || container.hidden) {
        return true;
    }

    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    return distanceToBottom <= MESSAGES_AUTO_SCROLL_THRESHOLD;
}


export function scrollMessagesToBottom() {
    if (!elements.messagesContainer) {
        return;
    }

    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}


export function highlightMessageCodeBlocks(rootElement = elements.messagesContainer) {
    applySyntaxHighlighting(rootElement);
}


export function enableMessagesAutoScroll() {
    state.messagesAutoScrollEnabled = true;
}


export function disableMessagesAutoScroll() {
    state.messagesAutoScrollEnabled = false;
}


export function syncMessagesAutoScrollState() {
    state.messagesAutoScrollEnabled = isMessagesContainerNearBottom();
}


export function keepMessagesPinnedToBottomIfNeeded() {
    if (!state.messagesAutoScrollEnabled) {
        return;
    }

    scrollMessagesToBottom();
}


export function appendTypingMessage(message = createPendingAssistantMessage()) {
    elements.emptyState.hidden = true;
    elements.messagesContainer.hidden = false;
    elements.messagesContainer.insertAdjacentHTML(
        "beforeend",
        createMessageFrameMarkup(
            message,
            `
                <div class="message__content message__content--status" data-pending-message-body="true">
                    ${createTypingIndicatorMarkup()}
                </div>
            `,
            createMessageMetaMarkup(message),
            ` data-typing-message="true"`,
        )
    );
    keepMessagesPinnedToBottomIfNeeded();
}


export function showToolStatusMessage(toolDisplayName, message = createPendingAssistantMessage()) {
    const normalizedToolName = String(toolDisplayName || "").trim() || "tool";
    if (!document.querySelector("[data-typing-message='true']")) {
        appendTypingMessage(message);
    }

    const pendingBody = document.querySelector(
        "[data-typing-message='true'] [data-pending-message-body='true']"
    );
    if (!pendingBody) {
        return;
    }

    pendingBody.innerHTML = createToolStatusMarkup(normalizedToolName);
    keepMessagesPinnedToBottomIfNeeded();
}


export function removeTypingMessage() {
    document.querySelector("[data-typing-message='true']")?.remove();
}


export function appendStreamingAssistantMessage(message = createPendingAssistantMessage()) {
    elements.emptyState.hidden = true;
    elements.messagesContainer.hidden = false;
    elements.messagesContainer.insertAdjacentHTML(
        "beforeend",
        createMessageFrameMarkup(
            message,
            `<div class="message__content message__content--markdown" data-message-content="true"></div>`,
            createMessageMetaMarkup(message),
            ` data-streaming-message="true"`,
        )
    );
    keepMessagesPinnedToBottomIfNeeded();
}


export function updateStreamingAssistantMessage(content) {
    const contentNode = document.querySelector(
        "[data-streaming-message='true'] [data-message-content='true']"
    );

    if (!contentNode) {
        return;
    }

    contentNode.innerHTML = renderMarkdown(content || "");
    highlightMessageCodeBlocks(contentNode);
    keepMessagesPinnedToBottomIfNeeded();
}


export function finalizeStreamingAssistantMessage(content) {
    const streamingNode = document.querySelector("[data-streaming-message='true']");
    if (!streamingNode) {
        return;
    }

    updateStreamingAssistantMessage(content);
    streamingNode.removeAttribute("data-streaming-message");
}


export function removeStreamingAssistantMessage() {
    document.querySelector("[data-streaming-message='true']")?.remove();
}


export function handleToolTraceMessageClick(event) {
    const traceButton = event.target.closest("[data-tool-trace-button]");
    if (!traceButton) {
        return;
    }

    const messageKey = traceButton.dataset.messageKey || "";
    const toolEventIndex = Number(traceButton.dataset.toolEventIndex);
    const message = findMessageByKey(messageKey);
    const toolEvents = Array.isArray(message?.tool_events) ? message.tool_events : [];
    const toolEvent = toolEvents[toolEventIndex];

    if (!toolEvent) {
        return;
    }

    renderToolTraceModal(toolEvent);
    openToolTraceModal();
}


export function handleToolTraceModalClick(event) {
    if (event.target.dataset.closeToolTraceModal === "true") {
        closeToolTraceModal();
    }
}


export function createPendingAssistantMessage(projectAgent = null) {
    const selectedModel = projectAgent?.model || getModelConfigById(getSelectedModelConfigId()) || null;
    const selectedProfileId = projectAgent?.profile_id || getSelectedProfileId();
    const selectedProjectAgent = projectAgent || getSelectedProjectAgent();

    return {
        role: "assistant",
        content: "",
        project_model_id: selectedProjectAgent?.id || state.activeConversation?.project_model_id || null,
        project_model_name: selectedProjectAgent?.nickname || "",
        model_config_id: selectedModel?.id || state.activeConversation?.model_config_id || null,
        model_name: selectedModel?.display_name || selectedModel?.name || state.activeConversation?.model || "Assistant",
        profile_id: selectedProfileId,
        profile_name: getProfileNameById(selectedProfileId),
    };
}


function createMessageFrameMarkup(message, bodyMarkup, metaMarkup, articleAttributes = "") {
    const isUser = message.role === "user";
    const messageKey = getOrCreateMessageClientKey(message);
    const avatarMarkup = isUser
        ? `<div class="message__avatar">YOU</div>`
        : createModelAvatarMarkup(
            resolveAssistantModelName(message),
            resolveAssistantIconImage(message),
            "message__avatar",
        );

    return `
        <article class="message message--${isUser ? "user" : "assistant"}" data-message-key="${escapeHtml(messageKey)}"${articleAttributes}>
            ${avatarMarkup}
            <div class="message__card">
                <div class="message__meta">${metaMarkup}</div>
                ${bodyMarkup}
            </div>
        </article>
    `;
}


function createMessageMetaMarkup(message, userLabel = "You") {
    if (message.role === "user") {
        return escapeHtml(userLabel);
    }

    const projectAgentName = getProjectAgentNameForMessage(message);
    if (projectAgentName) {
        return `
            <span class="message__meta-model">${escapeHtml(projectAgentName)}</span>
        `;
    }

    return `
        <span class="message__meta-model">${escapeHtml(resolveAssistantModelName(message))}</span>
        <span class="message__meta-separator" aria-hidden="true">|</span>
        <span class="message__meta-profile">${escapeHtml(resolveAssistantProfileName(message))}</span>
    `;
}


function resolveAssistantModelName(message) {
    if (message.model_name) {
        return message.model_name;
    }

    return getModelDisplayNameById(message.model_config_id)
        || state.activeConversation?.model
        || "Assistant";
}


function resolveAssistantProfileName(message) {
    if (message.profile_name) {
        return message.profile_name;
    }

    return getProfileNameById(message.profile_id || state.activeConversation?.profile_id);
}


function resolveAssistantIconImage(message) {
    return getModelConfigById(message.model_config_id)?.icon_image || "";
}


function createTypingIndicatorMarkup() {
    return `<div class="typing-indicator"><span></span><span></span><span></span></div>`;
}


function createToolStatusMarkup(toolDisplayName, options = {}) {
    const {
        interactive = false,
        messageKey = "",
        toolEventIndex = 0,
        labelOverride = "",
    } = options;
    const label = interactive
        ? (labelOverride || `Tool used: ${escapeHtml(toolDisplayName)}`)
        : `Using tool: ${escapeHtml(toolDisplayName)}`;
    if (!interactive) {
        return `
            <p class="tool-status" aria-live="polite">
                <span class="tool-status__dot" aria-hidden="true"></span>
                <span>${label}</span>
            </p>
        `;
    }

    return `
        <button
            class="tool-status tool-status--interactive"
            type="button"
            data-tool-trace-button="true"
            data-message-key="${escapeHtml(messageKey)}"
            data-tool-event-index="${toolEventIndex}"
        >
            <span class="tool-status__dot" aria-hidden="true"></span>
            <span>${label}</span>
        </button>
    `;
}


function createPersistentToolStatusListMarkup(message) {
    const toolEvents = Array.isArray(message?.tool_events) ? message.tool_events : [];
    if (!toolEvents.length) {
        return "";
    }

    const messageKey = getOrCreateMessageClientKey(message);
    const itemsMarkup = toolEvents.map((toolEvent, index) => {
        const toolDisplayName = resolveToolDisplayName(toolEvent);
        return createToolStatusMarkup(toolDisplayName, {
            interactive: true,
            messageKey,
            toolEventIndex: index,
            labelOverride: createToolStatusLabel(toolEvent),
        });
    }).join("");

    return `<div class="message__tool-traces">${itemsMarkup}</div>`;
}


function getOrCreateMessageClientKey(message) {
    if (message?.id) {
        return `message-${message.id}`;
    }

    if (!message.__clientKey) {
        messageClientKeyCounter += 1;
        message.__clientKey = `local-message-${messageClientKeyCounter}`;
    }

    return message.__clientKey;
}


export function findMessageByKey(messageKey) {
    return (state.activeMessages || []).find((message) => getOrCreateMessageClientKey(message) === messageKey) || null;
}


function resolveToolDisplayName(toolEvent) {
    return String(toolEvent?.tool_display_name || toolEvent?.tool_name || "tool")
        .replace(/_/g, " ")
        .trim();
}


function createToolStatusLabel(toolEvent) {
    const toolName = String(toolEvent?.tool_name || "").trim();
    const result = toolEvent?.result || {};
    const argumentsPayload = toolEvent?.arguments || {};

    if (!toolEvent?.ok) {
        if (isToolConfirmationRequired(toolEvent)) {
            return `Needs approval: ${escapeHtml(resolveToolDisplayName(toolEvent))}`;
        }
        return `Tool failed: ${escapeHtml(resolveToolDisplayName(toolEvent))}`;
    }

    if (toolName === "workspace_write_file") {
        const filePayload = result?.file || {};
        const path = String(filePayload?.path || argumentsPayload?.path || "").trim();
        const action = filePayload?.created ? "File created" : "File updated";
        return path ? `${action}: ${escapeHtml(path)}` : `${action} in workspace`;
    }

    if (toolName === "workspace_read_file") {
        const filePayload = result?.file || {};
        const path = String(filePayload?.path || argumentsPayload?.path || "").trim();
        return path ? `File read: ${escapeHtml(path)}` : "Workspace file read";
    }

    if (toolName === "workspace_search") {
        const query = String(argumentsPayload?.query || "").trim();
        return query ? `Workspace searched: ${escapeHtml(query)}` : "Workspace searched";
    }

    return "";
}


function createPendingToolConfirmationListMarkup(message) {
    const toolEvents = Array.isArray(message?.tool_events) ? message.tool_events : [];
    const pendingEvents = toolEvents
        .map((toolEvent, index) => ({ toolEvent, index }))
        .filter(({ toolEvent }) => isWorkspaceWriteConfirmationRequired(toolEvent));

    if (!pendingEvents.length) {
        return "";
    }

    const messageKey = getOrCreateMessageClientKey(message);
    return `
        <div class="tool-confirmations">
            ${pendingEvents.map(({ toolEvent, index }) => createToolConfirmationMarkup(
                toolEvent,
                messageKey,
                index,
            )).join("")}
        </div>
    `;
}


function createToolConfirmationMarkup(toolEvent, messageKey, toolEventIndex) {
    const toolName = String(toolEvent?.tool_name || "").trim();
    const path = String(toolEvent?.arguments?.path || "").trim();
    const action = toolName === "workspace_append_file" ? "Append to workspace file" : "Write workspace file";
    const detail = path ? path : resolveToolDisplayName(toolEvent);

    return `
        <section class="tool-confirmation" aria-label="Workspace write approval">
            <div class="tool-confirmation__body">
                <span class="tool-confirmation__label">${escapeHtml(action)}</span>
                <strong class="tool-confirmation__path">${escapeHtml(detail)}</strong>
            </div>
            <div class="tool-confirmation__actions">
                <button
                    class="tool-confirmation__button tool-confirmation__button--approve"
                    type="button"
                    data-tool-confirm-action="approve"
                    data-message-key="${escapeHtml(messageKey)}"
                    data-tool-event-index="${toolEventIndex}"
                >Allow</button>
                <button
                    class="tool-confirmation__button"
                    type="button"
                    data-tool-confirm-action="cancel"
                    data-message-key="${escapeHtml(messageKey)}"
                    data-tool-event-index="${toolEventIndex}"
                >Cancel</button>
            </div>
        </section>
    `;
}


function isWorkspaceWriteConfirmationRequired(toolEvent) {
    const toolName = String(toolEvent?.tool_name || "").trim();
    return ["workspace_write_file", "workspace_append_file"].includes(toolName)
        && isToolConfirmationRequired(toolEvent);
}


function isToolConfirmationRequired(toolEvent) {
    return String(toolEvent?.policy?.status || "").trim() === "confirmation_required";
}


function renderToolTraceModal(toolEvent) {
    const toolDisplayName = resolveToolDisplayName(toolEvent);
    const toolName = String(toolEvent?.tool_name || "tool").trim();
    const toolSummary = String(toolEvent?.tool_summary || "").trim();

    if (elements.toolTraceModalEyebrow) {
        elements.toolTraceModalEyebrow.textContent = "Tool";
    }
    if (elements.toolTraceModalTitle) {
        elements.toolTraceModalTitle.textContent = toolDisplayName;
    }
    if (elements.toolTraceModalSummary) {
        elements.toolTraceModalSummary.textContent = toolSummary || `${toolDisplayName} details`;
    }
    if (elements.toolTraceModalContent) {
        elements.toolTraceModalContent.innerHTML = createToolTraceContentMarkup(toolName, toolEvent);
    }
}


function createToolTraceContentMarkup(toolName, toolEvent) {
    if (!toolEvent?.ok) {
        return `
            <div class="tool-trace__group">
                <h4>Status</h4>
                <p>${escapeHtml(String(toolEvent?.error || "The tool could not complete."))}</p>
            </div>
        `;
    }

    if (toolName === "web_search") {
        return createWebSearchTraceMarkup(toolEvent);
    }

    if (toolName === "current_date") {
        return createCurrentDateTraceMarkup(toolEvent);
    }

    if (toolName.startsWith("workspace_")) {
        return createWorkspaceTraceMarkup(toolName, toolEvent);
    }

    return createGenericToolTraceMarkup(toolEvent);
}


function createWebSearchTraceMarkup(toolEvent) {
    const result = toolEvent?.result || {};
    const query = String(toolEvent?.arguments?.query || result?.query || "").trim();
    const results = Array.isArray(result?.results) ? result.results : [];
    const resultCount = Number(result?.result_count || results.length || 0);

    const headerMarkup = `
        <div class="tool-trace__group">
            <h4>Search query</h4>
            <p>${escapeHtml(query || "No query recorded.")}</p>
            <p class="tool-trace__meta">${escapeHtml(`${resultCount} result${resultCount === 1 ? "" : "s"}`)}</p>
        </div>
    `;

    const resultsMarkup = results.length
        ? results.map((item, index) => `
            <article class="tool-trace-result">
                <div class="tool-trace-result__index">${index + 1}</div>
                <div class="tool-trace-result__body">
                    <a class="tool-trace-result__title" href="${escapeHtml(String(item?.url || "#"))}" target="_blank" rel="noreferrer">
                        ${escapeHtml(String(item?.title || item?.url || "Search result"))}
                    </a>
                </div>
            </article>
        `).join("")
        : `<p class="tool-trace__empty">No search results were recorded for this tool run.</p>`;

    return `
        ${headerMarkup}
        <div class="tool-trace__group">
            <h4>Visited results</h4>
            <div class="tool-trace-results">${resultsMarkup}</div>
        </div>
    `;
}


function createCurrentDateTraceMarkup(toolEvent) {
    const result = toolEvent?.result || {};
    const fields = [
        ["Date", result?.date],
        ["Time", result?.time],
        ["Timezone", result?.timezone],
        ["ISO datetime", result?.iso_datetime],
    ].filter(([, value]) => String(value || "").trim());

    const rowsMarkup = fields.map(([label, value]) => `
        <div class="tool-trace-kv">
            <span class="tool-trace-kv__label">${escapeHtml(label)}</span>
            <span class="tool-trace-kv__value">${escapeHtml(String(value))}</span>
        </div>
    `).join("");

    return `
        <div class="tool-trace__group">
            <h4>Returned values</h4>
            <div class="tool-trace-kv-list">${rowsMarkup}</div>
        </div>
    `;
}


function createWorkspaceTraceMarkup(toolName, toolEvent) {
    if (toolName === "workspace_search") {
        return createWorkspaceSearchTraceMarkup(toolEvent);
    }

    const result = toolEvent?.result || {};
    const filePayload = result?.file || {};
    const path = String(filePayload?.path || toolEvent?.arguments?.path || "").trim();
    const sizeBytes = Number(filePayload?.size_bytes || 0);
    const action = toolName === "workspace_write_file"
        ? (filePayload?.created ? "Created" : "Updated")
        : "Read";
    const rows = [
        ["Action", action],
        ["Path", path],
        ["Size", sizeBytes ? `${sizeBytes} B` : ""],
    ].filter(([, value]) => String(value || "").trim());
    const rowsMarkup = rows.map(([label, value]) => `
        <div class="tool-trace-kv">
            <span class="tool-trace-kv__label">${escapeHtml(label)}</span>
            <span class="tool-trace-kv__value">${escapeHtml(String(value))}</span>
        </div>
    `).join("");
    const content = String(filePayload?.content || "").trim();
    const contentMarkup = content
        ? `
            <div class="tool-trace__group">
                <h4>Content preview</h4>
                <pre class="tool-trace__pre"><code>${escapeHtml(content.slice(0, 4000))}</code></pre>
            </div>
        `
        : "";

    return `
        <div class="tool-trace__group">
            <h4>Workspace action</h4>
            <div class="tool-trace-kv-list">${rowsMarkup}</div>
        </div>
        ${contentMarkup}
    `;
}


function createWorkspaceSearchTraceMarkup(toolEvent) {
    const result = toolEvent?.result || {};
    const query = String(toolEvent?.arguments?.query || "").trim();
    const matches = Array.isArray(result?.matches) ? result.matches : [];
    const matchesMarkup = matches.length
        ? matches.map((match, index) => `
            <article class="tool-trace-result">
                <div class="tool-trace-result__index">${index + 1}</div>
                <div class="tool-trace-result__body">
                    <strong class="tool-trace-result__title">${escapeHtml(String(match?.path || "workspace file"))}:${escapeHtml(String(match?.line || ""))}</strong>
                    <p class="tool-trace__meta">${escapeHtml(String(match?.preview || ""))}</p>
                </div>
            </article>
        `).join("")
        : `<p class="tool-trace__empty">No workspace matches were recorded for this tool run.</p>`;

    return `
        <div class="tool-trace__group">
            <h4>Search query</h4>
            <p>${escapeHtml(query || "No query recorded.")}</p>
            <p class="tool-trace__meta">${escapeHtml(`${matches.length} match${matches.length === 1 ? "" : "es"}`)}</p>
        </div>
        <div class="tool-trace__group">
            <h4>Matches</h4>
            <div class="tool-trace-results">${matchesMarkup}</div>
        </div>
    `;
}


function createGenericToolTraceMarkup(toolEvent) {
    const argumentsMarkup = escapeHtml(JSON.stringify(toolEvent?.arguments || {}, null, 2));
    const resultMarkup = escapeHtml(JSON.stringify(toolEvent?.result || {}, null, 2));

    return `
        <div class="tool-trace__group">
            <h4>Arguments</h4>
            <pre class="tool-trace__pre"><code>${argumentsMarkup}</code></pre>
        </div>
        <div class="tool-trace__group">
            <h4>Result</h4>
            <pre class="tool-trace__pre"><code>${resultMarkup}</code></pre>
        </div>
    `;
}
