import { loadConversationExportData } from "../api.js";
import { elements } from "../dom.js";
import { createModelAvatarMarkup, escapeHtml } from "../html.js";
import { renderMarkdown } from "../markdown.js";
import { closeChatExportModal, openChatExportModal } from "../modal-ui.js";
import { state } from "../state.js";
import { showStatus } from "../status-ui.js";

const EXPORT_STYLESHEET_PATHS = [
    "/static/CSS/index/tokens.css",
    "/static/CSS/index/base.css",
    "/static/CSS/index/chat.css",
];

let exportStylesPromise = null;
let exportInFlight = false;


export function openChatExportDialog() {
    if (!hasExportableConversation()) {
        showStatus("Necesitas una conversación con mensajes para poder exportarla.", true);
        return;
    }

    setExportStatus("");
    syncChatExportState();
    openChatExportModal();
}


export function syncChatExportState() {
    const hasConversation = Boolean(state.activeConversationId);
    const messageCount = state.activeMessages.length;
    const canExport = hasExportableConversation();

    if (elements.chatExportButton) {
        elements.chatExportButton.disabled = !canExport;
        elements.chatExportButton.title = canExport
            ? "Exportar chat"
            : "Necesitas una conversación con mensajes para exportar";
    }

    if (elements.chatExportSummary) {
        if (canExport) {
            const conversationTitle = state.activeConversation?.title || "Conversación";
            const messageLabel = messageCount === 1 ? "mensaje" : "mensajes";
            elements.chatExportSummary.textContent = `${conversationTitle} · ${messageCount} ${messageLabel} listos para descargar.`;
        } else if (hasConversation) {
            elements.chatExportSummary.textContent = "Este chat todavía no tiene mensajes guardados para exportar.";
        } else {
            elements.chatExportSummary.textContent = "Abre una conversación o envía el primer mensaje para habilitar la exportación.";
        }
    }

    setExportButtonsDisabled(!canExport || exportInFlight);
}


export async function handleChatExportDownload(format) {
    if (exportInFlight || !hasExportableConversation()) {
        return;
    }

    exportInFlight = true;
    syncChatExportState();
    setExportStatus("Preparando archivo...");

    try {
        const payload = await loadConversationExportData(state.activeConversationId);
        const exportData = payload.export;
        const filenameBase = buildExportFilenameBase(exportData);

        if (format === "json") {
            triggerDownload(
                `${filenameBase}.json`,
                "application/json;charset=utf-8",
                JSON.stringify(exportData, null, 2),
            );
        } else if (format === "html") {
            const html = await buildConversationHtmlExport(exportData);
            triggerDownload(
                `${filenameBase}.html`,
                "text/html;charset=utf-8",
                html,
            );
        } else if (format === "md") {
            triggerDownload(
                `${filenameBase}.md`,
                "text/markdown;charset=utf-8",
                buildConversationMarkdownExport(exportData),
            );
        } else {
            throw new Error("Formato de exportación no soportado.");
        }

        closeChatExportModal();
        showStatus("Conversación exportada correctamente.", false);
    } catch (error) {
        const message = error.message || "No se pudo exportar la conversación.";
        setExportStatus(message);
        showStatus(message, true);
    } finally {
        exportInFlight = false;
        syncChatExportState();
    }
}


function hasExportableConversation() {
    return Boolean(state.activeConversationId && state.activeMessages.length > 0);
}


function setExportButtonsDisabled(isDisabled) {
    [
        elements.chatExportJsonButton,
        elements.chatExportHtmlButton,
        elements.chatExportMarkdownButton,
    ].forEach((button) => {
        if (!button) {
            return;
        }
        button.disabled = isDisabled;
    });
}


function setExportStatus(message) {
    if (!elements.chatExportStatus) {
        return;
    }

    const normalizedMessage = String(message || "").trim();
    elements.chatExportStatus.hidden = !normalizedMessage;
    elements.chatExportStatus.textContent = normalizedMessage;
}


function buildExportFilenameBase(exportData) {
    const conversationTitle = exportData?.conversation?.title || "chat";
    const createdAt = exportData?.conversation?.created_at || new Date().toISOString();
    const normalizedDate = String(createdAt).replace(/[:\s]/g, "-").replace(/[^\w-]/g, "");
    return `${slugify(conversationTitle) || "chat"}-${normalizedDate || "export"}`;
}


function slugify(value) {
    return String(value || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 64);
}


function triggerDownload(filename, mimeType, content) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
}


async function buildConversationHtmlExport(exportData) {
    const inlineCss = await loadExportStyles();
    const conversation = exportData.conversation || {};
    const project = exportData.project || null;
    const messagesMarkup = (exportData.messages || [])
        .map((message) => createExportMessageMarkup(message))
        .join("\n");

    return [
        "<!DOCTYPE html>",
        '<html lang="es">',
        "<head>",
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        `    <title>${escapeHtml(conversation.title || "Conversación exportada")}</title>`,
        `    <style>${inlineCss}</style>`,
        "</head>",
        "<body>",
        '    <main class="chat-export-page">',
        '        <section class="chat-export-shell">',
        '            <header class="chat-export-header">',
        `                <p class="chat-export-header__eyebrow">${escapeHtml(project ? "Chat del proyecto" : "Chat exportado")}</p>`,
        `                <h1 class="chat-export-header__title">${escapeHtml(conversation.title || "Conversación")}</h1>`,
        "            </header>",
        '            <section class="messages-container chat-export-messages">',
        messagesMarkup,
        "            </section>",
        "        </section>",
        "    </main>",
        "</body>",
        "</html>",
    ].join("\n");
}


function createExportMessageMarkup(message) {
    const isUser = message.role === "user";
    const assistantLabel = resolveAssistantModelLabel(message);
    const profileLabel = resolveAssistantProfileLabel(message);
    const avatarMarkup = isUser
        ? '<div class="message__avatar">YOU</div>'
        : createModelAvatarMarkup(
            assistantLabel,
            message.model?.icon_image || "",
            "message__avatar",
        );
    const contentMarkup = isUser
        ? `<div class="message__content message__content--plain">${escapeHtml(message.content || "")}</div>`
        : `<div class="message__content message__content--markdown">${renderMarkdown(message.content || "")}</div>`;
    const metaMarkup = isUser
        ? "Tú"
        : `
            <span class="message__meta-model">${escapeHtml(assistantLabel)}</span>
            <span class="message__meta-separator" aria-hidden="true">|</span>
            <span class="message__meta-profile">${escapeHtml(profileLabel)}</span>
        `;

    return `
        <article class="message message--${isUser ? "user" : "assistant"}">
            ${avatarMarkup}
            <div class="message__card">
                <div class="message__meta">${metaMarkup}</div>
                ${contentMarkup}
            </div>
        </article>
    `;
}


function resolveAssistantModelLabel(message) {
    return (
        message.model?.display_name
        || message.model_name
        || message.author_label
        || "Asistente"
    );
}


function resolveAssistantProfileLabel(message) {
    return (
        message.profile?.name
        || message.profile_name
        || "Perfil"
    );
}


function buildConversationMarkdownExport(exportData) {
    const conversation = exportData.conversation || {};
    const blocks = [
        `# ${conversation.title || "Conversación"}`,
        "",
    ];

    for (const message of exportData.messages || []) {
        blocks.push(`## ${resolveMarkdownParticipant(message)}`);
        blocks.push("");
        blocks.push(String(message.content || "").trim() || "_Sin contenido_");
        blocks.push("");
    }

    return blocks.join("\n");
}


function resolveMarkdownParticipant(message) {
    if (message.role === "user") {
        return "Tú";
    }

    const assistantLabel = resolveAssistantModelLabel(message);
    return message.profile?.name
        ? `${assistantLabel} (${message.profile.name})`
        : assistantLabel;
}


async function loadExportStyles() {
    if (!exportStylesPromise) {
        exportStylesPromise = Promise.all(
            EXPORT_STYLESHEET_PATHS.map(async (path) => {
                const response = await fetch(path);
                if (!response.ok) {
                    throw new Error("No se pudieron cargar los estilos para exportar el HTML.");
                }
                return response.text();
            }),
        ).then((stylesheets) => `${stylesheets.join("\n")}

html,
body {
    height: auto;
    overflow: auto;
}

body {
    min-height: 100%;
}

.chat-export-page {
    min-height: 100vh;
    padding: 32px 18px 56px;
    background:
        radial-gradient(circle at top left, rgba(28, 139, 89, 0.12), transparent 28%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0)),
        var(--bg);
}

.chat-export-shell {
    width: min(100%, 1080px);
    margin: 0 auto;
    display: grid;
    gap: 40px;
}

.chat-export-header {
    width: min(100%, var(--content-width));
    margin: 0 auto;
    padding: 34px 36px;
    border: 1px solid var(--line);
    border-radius: var(--radius-xl);
    background: rgba(255, 255, 255, 0.58);
    box-shadow: var(--shadow);
    backdrop-filter: blur(12px);
}

.chat-export-header__eyebrow {
    margin: 0 0 6px;
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-soft);
}

.chat-export-header__title {
    margin: 0;
    font-family: var(--font-display);
    font-size: clamp(1.6rem, 3vw, 2.2rem);
    line-height: 1.14;
}

.chat-export-messages {
    height: auto;
    overflow: visible;
    padding: 8px 0 40px;
}

.chat-export-messages .message {
    margin-bottom: 30px;
    gap: 18px;
}

.chat-export-messages .message:last-child {
    margin-bottom: 0;
}

.chat-export-messages .message__card {
    line-height: 1.84;
}

.chat-export-messages .message--assistant .message__card {
    padding: 6px 28px 24px 0;
}

.chat-export-messages .message--user .message__card {
    padding: 18px 22px;
}

.chat-export-messages .message__meta {
    margin-bottom: 14px;
}

.chat-export-messages .message__content--markdown p,
.chat-export-messages .message__content--markdown ul,
.chat-export-messages .message__content--markdown ol,
.chat-export-messages .message__content--markdown table,
.chat-export-messages .message__content--markdown blockquote,
.chat-export-messages .message__content--markdown hr,
.chat-export-messages .message__content--markdown h1,
.chat-export-messages .message__content--markdown h2,
.chat-export-messages .message__content--markdown h3,
.chat-export-messages .message__content--markdown h4,
.chat-export-messages .message__content--markdown h5,
.chat-export-messages .message__content--markdown h6,
.chat-export-messages .message__content--markdown .message-code-block,
.chat-export-messages .message__content--markdown .message-table-scroll {
    margin: 0 0 20px;
}

.chat-export-messages .message__content--markdown li + li {
    margin-top: 10px;
}

.chat-export-messages .message__content--markdown blockquote {
    padding: 14px 18px;
}

.chat-export-messages .message-code-block__pre {
    padding: 18px 20px;
}

@media (max-width: 820px) {
    .chat-export-page {
        padding: 18px 12px 34px;
    }

    .chat-export-header {
        padding: 24px 20px;
    }

    .chat-export-shell {
        gap: 28px;
    }

    .chat-export-messages {
        padding-bottom: 24px;
    }

    .chat-export-messages .message {
        margin-bottom: 24px;
    }

    .chat-export-messages .message--assistant .message__card {
        padding-right: 0;
    }

    .message {
        width: 100%;
    }
}`);
    }

    return exportStylesPromise;
}
