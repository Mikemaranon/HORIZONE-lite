import { createAgentMentionSegments } from "./agent-mention-utils.js";
import { escapeHtml } from "./html.js";
import { createToolCommandSegments } from "./tool-command-utils.js";


export function createComposerContentMarkup(content, agents, tools) {
    return createAgentMentionSegments(content, agents).flatMap((segment) => {
        if (segment.type === "mention") {
            return [segment];
        }
        return createToolCommandSegments(segment.text, tools);
    }).map((segment) => {
        if (segment.type === "mention") {
            return `<span class="agent-mention-token" style="--agent-mention-color: ${escapeHtml(segment.color)}">${escapeHtml(segment.text)}</span>`;
        }
        if (segment.type === "command") {
            return `<span class="tool-command-token">${escapeHtml(segment.text)}</span>`;
        }
        return escapeHtml(segment.text);
    }).join("");
}
