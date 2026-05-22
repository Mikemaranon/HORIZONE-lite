import { elements } from "./dom.js";
import { createModelAvatarMarkup, escapeHtml } from "./html.js";
import { renderMarkdown } from "./markdown.js";
import {
    getModelConfigById,
    getModelDisplayNameById,
    getProfileNameById,
    getSelectedModelConfigId,
    getSelectedProfileId,
} from "./selectors.js";
import { state } from "./state.js";

const MESSAGES_AUTO_SCROLL_THRESHOLD = 24;


export function createMessageMarkup(message) {
    const isUser = message.role === "user";
    const roleLabel = isUser ? "Tú" : null;
    const contentClass = isUser ? "message__content--plain" : "message__content--markdown";
    const renderedContent = isUser
        ? escapeHtml(message.content || "")
        : renderMarkdown(message.content || "");

    return createMessageFrameMarkup(
        message,
        `<div class="message__content ${contentClass}" data-message-content="true">${renderedContent}</div>`,
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
    const normalizedToolName = String(toolDisplayName || "").trim() || "herramienta";
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


export function createPendingAssistantMessage() {
    const selectedModel = getModelConfigById(getSelectedModelConfigId()) || null;
    const selectedProfileId = getSelectedProfileId();

    return {
        role: "assistant",
        content: "",
        model_config_id: selectedModel?.id || state.activeConversation?.model_config_id || null,
        model_name: selectedModel?.display_name || selectedModel?.name || state.activeConversation?.model || "Asistente",
        profile_id: selectedProfileId,
        profile_name: getProfileNameById(selectedProfileId),
    };
}


function createMessageFrameMarkup(message, bodyMarkup, metaMarkup, articleAttributes = "") {
    const isUser = message.role === "user";
    const avatarMarkup = isUser
        ? `<div class="message__avatar">YOU</div>`
        : createModelAvatarMarkup(
            resolveAssistantModelName(message),
            resolveAssistantIconImage(message),
            "message__avatar",
        );

    return `
        <article class="message message--${isUser ? "user" : "assistant"}"${articleAttributes}>
            ${avatarMarkup}
            <div class="message__card">
                <div class="message__meta">${metaMarkup}</div>
                ${bodyMarkup}
            </div>
        </article>
    `;
}


function createMessageMetaMarkup(message, userLabel = "Tú") {
    if (message.role === "user") {
        return escapeHtml(userLabel);
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
        || "Asistente";
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


function createToolStatusMarkup(toolDisplayName) {
    return `
        <p class="tool-status" aria-live="polite">
            <span class="tool-status__dot" aria-hidden="true"></span>
            <span>Usando herramienta: ${escapeHtml(toolDisplayName)}</span>
        </p>
    `;
}
