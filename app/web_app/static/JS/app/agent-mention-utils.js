export function getAgentMentionLabel(agent) {
    const model = agent?.model || {};
    return String(agent?.nickname || model.display_name || model.name || "").trim();
}


export function getActiveMentionQuery(value, cursorPosition) {
    const text = String(value || "");
    const cursor = Number.isFinite(cursorPosition) ? cursorPosition : text.length;
    const beforeCursor = text.slice(0, cursor);
    const atIndex = beforeCursor.lastIndexOf("@");

    if (atIndex === -1) {
        return null;
    }

    const query = beforeCursor.slice(atIndex + 1);
    if (/[\n\r]/.test(query)) {
        return null;
    }

    const previousCharacter = atIndex > 0 ? beforeCursor[atIndex - 1] : "";
    if (previousCharacter && !/\s|[(\[{]/.test(previousCharacter)) {
        return null;
    }

    return {
        start: atIndex,
        end: cursor,
        query,
    };
}


export function filterMentionAgents(query, agents) {
    const normalizedQuery = normalize(query);
    const uniqueAgents = [];
    const seenIds = new Set();

    for (const agent of agents || []) {
        if (!agent?.id || seenIds.has(agent.id)) {
            continue;
        }

        const label = getAgentMentionLabel(agent);
        const model = agent.model || {};
        const searchableText = normalize([
            label,
            model.display_name,
            model.name,
            model.provider_name,
            model.provider,
        ].filter(Boolean).join(" "));

        if (!normalizedQuery || searchableText.includes(normalizedQuery)) {
            uniqueAgents.push(agent);
            seenIds.add(agent.id);
        }
    }

    return uniqueAgents;
}


export function replaceActiveMention(value, cursorPosition, agent) {
    const mention = getActiveMentionQuery(value, cursorPosition);
    const label = getAgentMentionLabel(agent);
    if (!mention || !label) {
        return {
            value,
            cursorPosition,
        };
    }

    const suffix = value.slice(mention.end);
    const normalizedSuffix = /^\s/.test(suffix) ? suffix : ` ${suffix}`;
    const nextValue = `${value.slice(0, mention.start)}@${label}${normalizedSuffix}`;
    const nextCursorPosition = mention.start + label.length + 2;
    return {
        value: nextValue,
        cursorPosition: nextCursorPosition,
    };
}


export function extractMentionedAgents(content, agents) {
    const text = String(content || "");
    const mentionableAgents = [...(agents || [])]
        .filter((agent) => getAgentMentionLabel(agent))
        .sort((left, right) => (
            getAgentMentionLabel(right).length - getAgentMentionLabel(left).length
        ));
    const matchedAgents = [];

    for (let index = 0; index < text.length; index += 1) {
        if (text[index] !== "@") {
            continue;
        }

        const previousCharacter = index > 0 ? text[index - 1] : "";
        if (previousCharacter && !/\s|[(\[{]/.test(previousCharacter)) {
            continue;
        }

        const tail = text.slice(index + 1);
        const normalizedTail = normalize(tail);
        for (const agent of mentionableAgents) {
            const label = getAgentMentionLabel(agent);
            const normalizedLabel = normalize(label);
            if (!normalizedLabel || !normalizedTail.startsWith(normalizedLabel)) {
                continue;
            }

            const followingCharacter = tail[label.length] || "";
            if (!isMentionBoundary(followingCharacter)) {
                continue;
            }

            matchedAgents.push(agent);
            break;
        }
    }

    return matchedAgents;
}


function normalize(value) {
    return String(value || "").trim().toLowerCase();
}


function isMentionBoundary(character) {
    return !character || /[\s,.;:!?)]/.test(character);
}
