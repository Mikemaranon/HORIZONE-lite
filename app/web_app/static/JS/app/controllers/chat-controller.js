import { cancelChatStream, createConversation, deleteConversation, sendChatStream, updateConversation } from "../api.js";
import { renderApp } from "../app-runtime.js";
import { setLoading, syncComposerAvailability } from "../composer-ui.js";
import { confirmAction } from "../dialogs.js";
import { elements } from "../dom.js";
import {
    appendStreamingAssistantMessage,
    createPendingAssistantMessage,
    appendTypingMessage,
    disableMessagesAutoScroll,
    enableMessagesAutoScroll,
    finalizeStreamingAssistantMessage,
    removeStreamingAssistantMessage,
    removeTypingMessage,
    showToolStatusMessage,
    syncMessagesAutoScrollState,
    updateStreamingAssistantMessage,
} from "../message-ui.js";
import { renderConversationHeader, renderConversations, renderMessages } from "../render.js";
import { getActualProvider, getSelectedModel } from "../provider-helpers.js";
import { buildConversationTitle, getSelectedModelConfigId, getSelectedProfileId } from "../selectors.js";
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
    setGenerationStopRequested,
    setProjectDocuments,
} from "../state-actions.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";
import {
    loadConversationDetail,
    loadConversations,
    loadProjectDocuments,
} from "../store.js";


export async function handleConversationSelect(conversationId, { closeSidebarOnMobile }) {
    const data = await loadConversationDetail(conversationId);
    applyConversationDetailPayload(data);

    if (state.activeProjectId) {
        const documents = await loadProjectDocuments(state.activeProjectId);
        setProjectDocuments(documents.documents || []);
    } else {
        setProjectDocuments([]);
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
        showStatus("Selecciona un modelo antes de enviar el mensaje.", true);
        return;
    }

    try {
        setLoading(true);
        setGenerationStopRequested(false);

        const conversationId = await ensureActiveConversation();
        const requestId = createRequestId();
        setActiveGenerationRequestId(requestId);
        const requestMessages = [...state.activeMessages, { role: "user", content }];

        setActiveMessages(requestMessages);
        enableMessagesAutoScroll();
        renderMessages();
        elements.composerInput.value = "";
        autoResizeComposerHeight();
        let assistantMessageMeta = createPendingAssistantMessage();
        appendTypingMessage(assistantMessageMeta);

        let streamingAssistantMessage = null;
        const payload = await sendChatStream({
            conversation_id: conversationId,
            messages: requestMessages,
            provider: getActualProvider(),
            model: getSelectedModel(),
            model_config_id: getSelectedModelConfigId(),
            profile_id: getSelectedProfileId(),
            request_id: requestId,
        }, {
            onStart(payloadData) {
                if (payloadData?.request_id) {
                    setActiveGenerationRequestId(payloadData.request_id);
                }
                if (payloadData?.message_meta) {
                    assistantMessageMeta = {
                        ...assistantMessageMeta,
                        ...payloadData.message_meta,
                    };
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
                    state.activeMessages.push(streamingAssistantMessage);
                    appendStreamingAssistantMessage(streamingAssistantMessage);
                }

                streamingAssistantMessage.content += delta;
                updateStreamingAssistantMessage(streamingAssistantMessage.content);
            },
            onToolStart(toolPayload) {
                showToolStatusMessage(
                    toolPayload?.display_name || toolPayload?.tool_name || "herramienta",
                    assistantMessageMeta,
                );
            },
        });

        removeTypingMessage();
        if (streamingAssistantMessage) {
            Object.assign(streamingAssistantMessage, payload.message);
            streamingAssistantMessage.content = payload.message.content;
            if (payload.message.content) {
                finalizeStreamingAssistantMessage(payload.message.content);
            } else {
                state.activeMessages.pop();
                removeStreamingAssistantMessage();
            }
        } else if (payload.message.content) {
            state.activeMessages.push(payload.message);
            renderMessages();
        }

        const nextConversationFields = {
            ...(state.activeConversation || {}),
            id: conversationId,
            model_config_id: getSelectedModelConfigId(),
            provider: getActualProvider(),
            model: getSelectedModel(),
            profile_id: getSelectedProfileId(),
        };
        setActiveConversation(nextConversationFields);
        await updateConversation({
            id: conversationId,
            model_config_id: getSelectedModelConfigId(),
            profile_id: getSelectedProfileId(),
        });

        const conversations = await loadConversations();
        applyConversationsPayload(conversations);
        renderConversations(getChatCallbacks().handleConversationSelect, getChatCallbacks().handleConversationDelete);
        renderConversationHeader();

        if (payload.finish_reason === "cancelled") {
            showStatus("Respuesta detenida.", false);
            return;
        }
        if (["length", "max_tokens"].includes(payload.finish_reason)) {
            showStatus("La respuesta se detuvo por límite de tokens del proveedor o del modelo.", true);
        }
    } catch (error) {
        removeTypingMessage();
        if (error.name === "AbortError") {
            const lastMessage = state.activeMessages[state.activeMessages.length - 1];
            if (lastMessage?.role === "assistant" && lastMessage.content) {
                finalizeStreamingAssistantMessage(lastMessage.content);
                showStatus("Respuesta detenida.", false);
            } else {
                if (lastMessage?.role === "assistant") {
                    state.activeMessages.pop();
                }
                removeStreamingAssistantMessage();
                renderMessages({ preserveViewport: true });
            }
            return;
        }
        if (state.activeMessages[state.activeMessages.length - 1]?.role === "assistant") {
            state.activeMessages.pop();
        }
        removeStreamingAssistantMessage();
        renderMessages({ preserveViewport: true });
        showStatus(error.message || "No se pudo enviar el mensaje.", true);
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
        showStatus(error.message || "No se pudo detener la respuesta en curso.", true);
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
        throw new Error("Selecciona un modelo antes de empezar a chatear.");
    }

    enterConversationWorkspace();
    const conversationId = await createConversationRecord({
        title: buildConversationTitle(),
        project_id: state.activeProjectId,
        profile_id: getSelectedProfileId(),
        model_config_id: getSelectedModelConfigId(),
    });
    await handleConversationSelect(conversationId, { closeSidebarOnMobile });
    return conversationId;
}


export async function handleConversationDelete(conversationId) {
    const conversation = state.conversations.find((item) => item.id === conversationId);
    const label = conversation?.title || "este chat";
    const confirmed = await confirmAction({
        title: `Borrar "${label}"`,
        message: "Esta acción elimina el chat y sus mensajes. No se puede deshacer.",
        confirmLabel: "Borrar chat",
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
        showStatus(error.message || "No se pudo borrar el chat.", true);
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


const chatCallbacks = {
    handleConversationDelete: null,
    handleConversationSelect: null,
};
