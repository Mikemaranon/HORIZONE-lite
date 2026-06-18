import {
    cancelChatStream,
    createConversation,
    deleteConversation,
    sendChatStream,
    updateConversation,
    updateToolConfirmation,
} from "../api.js";
import { renderApp } from "../app-runtime.js";
import { closeComposerMentionMenu } from "../agent-mentions.js";
import { extractAgentMentionTurns } from "../agent-mention-utils.js";
import { setLoading, syncComposerAvailability, syncComposerHighlight } from "../composer-ui.js";
import { confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import {
    appendStreamingAssistantMessage,
    createPendingAssistantMessage,
    appendTypingMessage,
    disableMessagesAutoScroll,
    enableMessagesAutoScroll,
    finalizeStreamingAssistantMessage,
    findMessageByKey,
    removeStreamingAssistantMessage,
    removeTypingMessage,
    showReasoningStatusMessage,
    showToolStatusMessage,
    syncMessagesAutoScrollState,
    updateAssistantMessageTimer,
    updateStreamingAssistantMessage,
} from "../message-ui.js";
import { renderConversationHeader, renderConversations, renderMessages } from "../render.js";
import { getActualProvider, getSelectedModel } from "../provider-helpers.js";
import {
    buildConversationTitle,
    getSelectedModelConfigId,
    getMentionableProjectAgents,
    getSelectedProfileId,
    getSelectedProjectAgent,
} from "../selectors.js";
import {
    applyConversationDetailPayload,
    applyConversationsPayload,
    enterConversationWorkspace,
    enterHomeWorkspace,
    enterProjectWorkspace,
    patchActiveConversation,
    setActiveConversation,
    setActiveConversationId,
    setActiveGenerationRequestId,
    setActiveMessages,
    setConversationTitleDraft,
    setConversationTitleEditMode,
    setGenerationStopRequested,
    setProjectDocuments,
    setProjectWorkspace,
    setProjectWorkspaceFiles,
    applyProjectWorkspacePayload,
    applyProjectModelsPayload,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import {
    loadConversationDetail,
    loadConversations,
    loadProjectDocuments,
    loadProjectModels,
    loadProjectWorkspace,
} from "../store.js";


export async function handleConversationSelect(conversationId, { closeSidebarOnMobile }) {
    const data = await loadConversationDetail(conversationId);
    applyConversationDetailPayload(data);

    if (state.activeProjectId) {
        const [documents, workspace, projectModels] = await Promise.all([
            loadProjectDocuments(state.activeProjectId),
            loadProjectWorkspace(state.activeProjectId),
            loadProjectModels(state.activeProjectId),
        ]);
        setProjectDocuments(documents.documents || []);
        applyProjectWorkspacePayload(workspace);
        applyProjectModelsPayload(projectModels);
    } else {
        setProjectDocuments([]);
        applyProjectModelsPayload({});
        setProjectWorkspace(null);
        setProjectWorkspaceFiles([]);
    }

    renderApp();
    closeSidebarOnMobile();
}


export async function handleComposerSubmit(event, { ensureActiveConversation }) {
    event.preventDefault();

    if (state.loading) {
        return;
    }

    const content = elements.composerInput.value.trim();
    if (!content) {
        return;
    }
    if (!getSelectedModel()) {
        showStatus("Select a model before sending the message.", true);
        return;
    }

    let activeTurnMessageCount = null;

    try {
        setLoading(true);
        setGenerationStopRequested(false);

        const conversationId = await ensureActiveConversation();
        const requestId = createRequestId();
        setActiveGenerationRequestId(requestId);
        const previousMessages = [...state.activeMessages];
        const visibleUserMessage = { role: "user", content };
        const requestMessages = [...previousMessages, visibleUserMessage];
        const mentionTurns = extractAgentMentionTurns(content, getMentionableProjectAgents());
        const responderTurns = mentionTurns.length
            ? mentionTurns.map((turn) => ({
                responderAgent: turn.agent,
                contextMessages: [
                    ...previousMessages,
                    { role: "user", content: turn.content },
                ],
            }))
            : [{ responderAgent: null, contextMessages: null }];

        setActiveMessages(requestMessages);
        enableMessagesAutoScroll();
        renderMessages();
        elements.composerInput.value = "";
        closeComposerMentionMenu();
        autoResizeComposerHeight();
        syncComposerHighlight();

        let payload = null;
        for (const responderTurn of responderTurns) {
            activeTurnMessageCount = state.activeMessages.length;
            payload = await sendChatTurn({
                conversationId,
                requestId: responderTurns.length === 1 ? requestId : createRequestId(),
                responderAgent: responderTurn.responderAgent,
                contextMessages: responderTurn.contextMessages,
            });
            activeTurnMessageCount = null;

            if (payload.finish_reason === "cancelled") {
                showStatus("Response stopped.", false);
                return;
            }
        }

        const nextConversationFields = {
            ...(state.activeConversation || {}),
            id: conversationId,
            project_model_id: state.activeConversation?.project_model_id || getSelectedProjectAgent()?.id || null,
            model_config_id: getSelectedModelConfigId(),
            provider: getActualProvider(),
            model: getSelectedModel(),
            profile_id: getSelectedProfileId(),
        };
        setActiveConversation(nextConversationFields);
        await updateConversation({
            id: conversationId,
            project_model_id: state.activeConversation?.project_model_id || getSelectedProjectAgent()?.id || null,
            model_config_id: getSelectedModelConfigId(),
            profile_id: getSelectedProfileId(),
        });

        const conversations = await loadConversations();
        applyConversationsPayload(conversations);
        renderConversations(getChatCallbacks().handleConversationSelect, getChatCallbacks().handleConversationDelete);
        renderConversationHeader();

        if (payload && ["length", "max_tokens"].includes(payload.finish_reason)) {
            showStatus("The response stopped due to the provider or model token limit.", true);
        }
        if (payload?.finish_reason === "stream_error") {
            showStatus("The runtime stream dropped after a partial response.", true);
        }
    } catch (error) {
        removeTypingMessage();
        if (error.name === "AbortError") {
            const lastMessage = state.activeMessages[state.activeMessages.length - 1];
            if (
                lastMessage?.role === "assistant"
                && lastMessage.content
                && shouldCleanActiveTurnAssistantMessage(activeTurnMessageCount)
            ) {
                finalizeStreamingAssistantMessage(lastMessage.content);
                showStatus("Response stopped.", false);
            } else {
                if (
                    lastMessage?.role === "assistant"
                    && shouldCleanActiveTurnAssistantMessage(activeTurnMessageCount)
                ) {
                    state.activeMessages.pop();
                }
                removeStreamingAssistantMessage();
                renderMessages({ preserveViewport: true });
            }
            return;
        }
        if (
            state.activeMessages[state.activeMessages.length - 1]?.role === "assistant"
            && shouldCleanActiveTurnAssistantMessage(activeTurnMessageCount)
        ) {
            state.activeMessages.pop();
        }
        removeStreamingAssistantMessage();
        renderMessages({ preserveViewport: true });
        showStatus(error.message || "The message could not be sent.", true);
    } finally {
        setActiveGenerationRequestId(null);
        setGenerationStopRequested(false);
        setLoading(false);
    }
}


async function sendChatTurn({
    conversationId,
    requestId,
    responderAgent = null,
    contextMessages = null,
    toolConfirmation = null,
}) {
    setActiveGenerationRequestId(requestId);
    let assistantMessageMeta = createPendingAssistantMessage(responderAgent);
    const turnStartedAt = Date.now();
    let turnTimer = null;
    let timerMessage = assistantMessageMeta;
    assistantMessageMeta.elapsed_seconds = 0;
    appendTypingMessage(assistantMessageMeta);

    let streamingAssistantMessage = null;
    const syncElapsedSeconds = () => {
        timerMessage.elapsed_seconds = Math.max(0, Math.floor((Date.now() - turnStartedAt) / 1000));
        updateAssistantMessageTimer(timerMessage);
    };
    turnTimer = window.setInterval(syncElapsedSeconds, 1000);

    let payload = null;
    try {
        payload = await sendChatStream(buildChatPayload({
            conversationId,
            requestId,
            responderAgent,
            contextMessages,
            toolConfirmation,
        }), {
            onStart(payloadData) {
                if (payloadData?.request_id) {
                    setActiveGenerationRequestId(payloadData.request_id);
                }
                if (payloadData?.message_meta) {
                    Object.assign(assistantMessageMeta, payloadData.message_meta, {
                        elapsed_seconds: timerMessage.elapsed_seconds,
                    });
                    timerMessage = streamingAssistantMessage || assistantMessageMeta;
                }
            },
            onDelta(delta) {
                if (!streamingAssistantMessage) {
                    removeTypingMessage();
                    streamingAssistantMessage = {
                        ...assistantMessageMeta,
                        role: "assistant",
                        content: "",
                    };
                    timerMessage = streamingAssistantMessage;
                    syncElapsedSeconds();
                    state.activeMessages.push(streamingAssistantMessage);
                    appendStreamingAssistantMessage(streamingAssistantMessage);
                }

                streamingAssistantMessage.content += delta;
                updateStreamingAssistantMessage(streamingAssistantMessage.content);
            },
            onToolStart(toolPayload) {
                showToolStatusMessage(
                    toolPayload?.display_name || toolPayload?.tool_name || "tool",
                    assistantMessageMeta,
                );
            },
            onReasoningStart() {
                showReasoningStatusMessage(assistantMessageMeta);
            },
        });
    } finally {
        window.clearInterval(turnTimer);
        syncElapsedSeconds();
    }
    payload.message.tool_events = payload.raw?.tool_events || [];
    payload.message.elapsed_seconds = timerMessage.elapsed_seconds;

    removeTypingMessage();
    if (streamingAssistantMessage) {
        Object.assign(streamingAssistantMessage, payload.message);
        streamingAssistantMessage.content = payload.message.content;
        if (payload.message.content) {
            finalizeStreamingAssistantMessage(payload.message.content);
            renderMessages({ preserveViewport: true });
        } else {
            state.activeMessages.pop();
            removeStreamingAssistantMessage();
            renderMessages({ preserveViewport: true });
        }
    } else if (payload.message.content) {
        state.activeMessages.push(payload.message);
        renderMessages();
    }

    return payload;
}


function buildChatPayload({
    conversationId,
    requestId,
    responderAgent = null,
    contextMessages = null,
    toolConfirmation = null,
}) {
    if (!responderAgent) {
        return {
            conversation_id: conversationId,
            messages: [...state.activeMessages],
            ...(contextMessages ? { context_messages: contextMessages } : {}),
            provider: getActualProvider(),
            model: getSelectedModel(),
            project_model_id: state.activeConversation?.project_model_id || getSelectedProjectAgent()?.id || null,
            model_config_id: getSelectedModelConfigId(),
            profile_id: getSelectedProfileId(),
            request_id: requestId,
            ...(toolConfirmation ? { tool_confirmation: toolConfirmation } : {}),
        };
    }

    const model = responderAgent.model || {};
    return {
        conversation_id: conversationId,
        messages: [...state.activeMessages],
        ...(contextMessages ? { context_messages: contextMessages } : {}),
        provider: model.provider || getActualProvider(),
        model: model.name || getSelectedModel(),
        project_model_id: responderAgent.id,
        model_config_id: responderAgent.model_id || model.id || getSelectedModelConfigId(),
        profile_id: responderAgent.profile_id || getSelectedProfileId(),
        request_id: requestId,
        ...(toolConfirmation ? { tool_confirmation: toolConfirmation } : {}),
    };
}


function shouldCleanActiveTurnAssistantMessage(activeTurnMessageCount) {
    if (activeTurnMessageCount === null || activeTurnMessageCount === undefined) {
        return false;
    }

    return state.activeMessages.length > activeTurnMessageCount;
}


export async function handleToolConfirmationClick(event) {
    const actionButton = event.target.closest("[data-tool-confirm-action]");
    if (!actionButton) {
        return;
    }

    event.preventDefault();
    const message = findMessageByKey(actionButton.dataset.messageKey || "");
    const toolEventIndex = Number(actionButton.dataset.toolEventIndex);
    const toolEvent = Array.isArray(message?.tool_events)
        ? message.tool_events[toolEventIndex]
        : null;
    if (!toolEvent) {
        return;
    }

    const action = actionButton.dataset.toolConfirmAction;
    if (action === "cancel") {
        try {
            markToolConfirmationCancelled(toolEvent);
            await persistToolConfirmationStatus(message, toolEventIndex, "cancelled");
            renderMessages({ preserveViewport: true });
            showStatus("Workspace write cancelled.", false);
        } catch (error) {
            markToolConfirmationPending(toolEvent);
            renderMessages({ preserveViewport: true });
            showStatus(error.message || "The workspace write cancellation could not be saved.", true);
        }
        return;
    }

    if (state.loading) {
        return;
    }

    try {
        setLoading(true);
        setGenerationStopRequested(false);
        markToolConfirmationApproved(toolEvent);
        await persistToolConfirmationStatus(message, toolEventIndex, "confirming");
        renderMessages({ preserveViewport: true });

        await sendChatTurn({
            conversationId: state.activeConversationId,
            requestId: createRequestId(),
            toolConfirmation: {
                name: toolEvent.tool_name,
                arguments: toolEvent.arguments || {},
                reason: toolEvent.reason || "",
            },
        });
        markToolConfirmationConfirmed(toolEvent);
        await persistToolConfirmationStatus(message, toolEventIndex, "confirmed");
        renderMessages({ preserveViewport: true });
    } catch (error) {
        markToolConfirmationPending(toolEvent);
        await persistToolConfirmationStatus(message, toolEventIndex, "confirmation_required").catch(() => {});
        removeTypingMessage();
        removeStreamingAssistantMessage();
        renderMessages({ preserveViewport: true });
        showStatus(error.message || "The workspace write could not be confirmed.", true);
    } finally {
        setActiveGenerationRequestId(null);
        setGenerationStopRequested(false);
        setLoading(false);
    }
}


export function handleComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (!state.loading) {
            elements.composerForm.requestSubmit();
        }
    }
}


export async function handleSendButtonClick() {
    if (state.loading) {
        await handleStopGeneration();
        return;
    }

    elements.composerForm.requestSubmit();
}


export async function handleStopGeneration() {
    if (!state.loading || !state.activeGenerationRequestId || state.generationStopRequested) {
        return;
    }

    setGenerationStopRequested(true);
    syncComposerAvailability();

    try {
        await cancelChatStream(state.activeGenerationRequestId);
    } catch (error) {
        setGenerationStopRequested(false);
        syncComposerAvailability();
        showStatus(error.message || "The current response could not be stopped.", true);
    }
}


export function openNewConversationWorkspace({ closeSidebarOnMobile }) {
    enterHomeWorkspace();
    renderApp();
    closeSidebarOnMobile();
    elements.composerInput.focus();
}


export async function ensureActiveConversation({ handleConversationSelect, closeSidebarOnMobile }) {
    if (state.activeConversationId) {
        return state.activeConversationId;
    }

    if (!getSelectedModel()) {
        throw new Error("Select a model before starting to chat.");
    }

    enterConversationWorkspace();
    const conversationId = await createConversationRecord({
        title: buildConversationTitle(),
        project_id: state.activeProjectId,
        project_model_id: getSelectedProjectAgent()?.id || null,
        profile_id: getSelectedProfileId(),
        model_config_id: getSelectedModelConfigId(),
    });
    await handleConversationSelect(conversationId, { closeSidebarOnMobile });
    return conversationId;
}


export async function handleConversationDelete(conversationId) {
    const conversation = state.conversations.find((item) => item.id === conversationId);
    const label = conversation?.title || "this chat";
    const confirmed = await confirmAction({
        title: `Delete "${label}"`,
        message: "This action deletes the chat and its messages. It cannot be undone.",
        confirmLabel: "Delete chat",
        eyebrow: "Chat",
    });

    if (!confirmed) {
        return;
    }

    try {
        await deleteConversation(conversationId);

        if (state.activeConversationId === conversationId) {
            setActiveConversationId(null);
            setActiveConversation(null);
            setActiveMessages([]);
            if (state.activeProjectId) {
                enterProjectWorkspace(state.activeProjectId);
            } else {
                enterHomeWorkspace();
            }
        }

        const data = await loadConversations();
        applyConversationsPayload(data);
        renderApp();
    } catch (error) {
        showStatus(error.message || "The chat could not be deleted.", true);
    }
}


export function handleConversationTitleClick(event) {
    if (event.target.closest("[data-conversation-title-edit]")) {
        openConversationTitleEditor();
        return;
    }

    if (event.target.closest("[data-conversation-title-save]")) {
        commitConversationTitleEdit();
        return;
    }

    if (event.target.closest("[data-conversation-title-cancel]")) {
        cancelConversationTitleEdit();
    }
}


export function handleConversationTitleInput(event) {
    if (event.target?.id !== "conversation-title-input") {
        return;
    }

    setConversationTitleDraft(event.target.value);
}


export function handleConversationTitleKeyDown(event) {
    if (event.target?.id !== "conversation-title-input") {
        return;
    }

    if (event.key === "Enter") {
        event.preventDefault();
        commitConversationTitleEdit();
        return;
    }

    if (event.key === "Escape") {
        event.preventDefault();
        cancelConversationTitleEdit();
    }
}


export function getChatCallbacks() {
    return {
        handleConversationDelete: chatCallbacks.handleConversationDelete,
        handleConversationSelect: chatCallbacks.handleConversationSelect,
    };
}


export function registerChatCallbacks(callbacks) {
    Object.assign(chatCallbacks, callbacks);
}


export {
    disableMessagesAutoScroll,
    syncMessagesAutoScrollState,
};


function autoResizeComposerHeight() {
    elements.composerInput.style.height = "auto";
    elements.composerInput.style.height = `${Math.min(elements.composerInput.scrollHeight, 220)}px`;
}


function openConversationTitleEditor() {
    if (state.workspaceMode !== "conversation" || !state.activeConversation) {
        return;
    }

    const titleRect = elements.conversationTitle?.getBoundingClientRect();
    const titleWidth = titleRect?.width || 0;
    const titleHeight = titleRect?.height || 0;
    if (titleWidth > 0 && titleHeight > 0) {
        elements.conversationTitle.style.setProperty(
            "--conversation-title-editor-width",
            `${Math.ceil(titleWidth)}px`,
        );
        elements.conversationTitle.style.setProperty(
            "--conversation-title-editor-height",
            `${Math.ceil(titleHeight)}px`,
        );
        elements.conversationTitle.style.width = `${Math.ceil(titleWidth)}px`;
        elements.conversationTitle.style.height = `${Math.ceil(titleHeight)}px`;
    }

    setConversationTitleEditMode(true, state.activeConversation.title || "");
    renderConversationHeader();

    window.requestAnimationFrame(() => {
        const input = document.getElementById("conversation-title-input");
        input?.focus();
        input?.select();
    });
}


function cancelConversationTitleEdit() {
    setConversationTitleEditMode(false);
    elements.conversationTitle?.style.removeProperty("--conversation-title-editor-width");
    elements.conversationTitle?.style.removeProperty("--conversation-title-editor-height");
    elements.conversationTitle?.style.removeProperty("width");
    elements.conversationTitle?.style.removeProperty("height");
    renderConversationHeader();
}


async function commitConversationTitleEdit() {
    if (!state.activeConversationId || !state.activeConversation) {
        cancelConversationTitleEdit();
        return;
    }

    const nextTitle = String(state.conversationTitleDraft || "").trim();
    if (!nextTitle) {
        showStatus("The chat title cannot be empty.", true);
        document.getElementById("conversation-title-input")?.focus();
        return;
    }

    const currentTitle = String(state.activeConversation.title || "").trim();
    if (nextTitle === currentTitle) {
        cancelConversationTitleEdit();
        return;
    }

    try {
        const payload = await updateConversation({
            id: state.activeConversationId,
            title: nextTitle,
        });
        patchActiveConversation(payload.conversation || { title: nextTitle });
        setConversationTitleEditMode(false);
        elements.conversationTitle?.style.removeProperty("--conversation-title-editor-width");
        elements.conversationTitle?.style.removeProperty("--conversation-title-editor-height");
        elements.conversationTitle?.style.removeProperty("width");
        elements.conversationTitle?.style.removeProperty("height");

        const conversations = await loadConversations();
        applyConversationsPayload(conversations);
        renderConversations(getChatCallbacks().handleConversationSelect, getChatCallbacks().handleConversationDelete);
        renderConversationHeader();
    } catch (error) {
        showStatus(error.message || "The chat title could not be updated.", true);
        document.getElementById("conversation-title-input")?.focus();
    }
}


async function createConversationRecord(payload) {
    const data = await createConversation(payload);
    const conversations = await loadConversations();
    applyConversationsPayload(conversations);
    renderApp();
    return data.conversation.id;
}


function createRequestId() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }

    return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}


function markToolConfirmationApproved(toolEvent) {
    toolEvent.policy = {
        ...(toolEvent.policy || {}),
        status: "confirming",
    };
}


function markToolConfirmationConfirmed(toolEvent) {
    toolEvent.policy = {
        ...(toolEvent.policy || {}),
        status: "confirmed",
    };
}


function markToolConfirmationPending(toolEvent) {
    toolEvent.policy = {
        ...(toolEvent.policy || {}),
        status: "confirmation_required",
    };
}


function markToolConfirmationCancelled(toolEvent) {
    toolEvent.policy = {
        ...(toolEvent.policy || {}),
        status: "cancelled",
    };
    toolEvent.error = "Workspace write cancelled by the user.";
}


async function persistToolConfirmationStatus(message, toolEventIndex, status) {
    if (!message?.id) {
        return;
    }

    await updateToolConfirmation({
        message_id: message.id,
        tool_event_index: toolEventIndex,
        status,
    });
}


const chatCallbacks = {
    handleConversationDelete: null,
    handleConversationSelect: null,
};
