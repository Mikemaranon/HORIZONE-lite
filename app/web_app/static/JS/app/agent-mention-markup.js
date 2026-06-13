import { createAgentMentionSegments } from "./agent-mention-utils.js";
import { escapeHtml } from "./html.js";


export function createMentionedContentMarkup(content, agents) {
    return createAgentMentionSegments(content, agents).map((segment) => {
        if (segment.type !== "mention") {
            return escapeHtml(segment.text);
        }

        return `<span class="agent-mention-token" style="--agent-mention-color: ${escapeHtml(segment.color)}">${escapeHtml(segment.text)}</span>`;
    }).join("");
}
