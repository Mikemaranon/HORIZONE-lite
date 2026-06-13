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


export function createAgentMentionSegments(content, agents) {
    const text = String(content || "");
    const matches = findMentionMatches(text, agents);
    if (!matches.length) {
        return text ? [{ type: "text", text }] : [];
    }

    const segments = [];
    let cursor = 0;

    for (const match of matches) {
        if (match.start > cursor) {
            segments.push({ type: "text", text: text.slice(cursor, match.start) });
        }

        segments.push({
            type: "mention",
            text: text.slice(match.start, match.end),
            agent: match.agent,
            color: normalizeAgentColor(match.agent?.color),
        });
        cursor = match.end;
    }

    if (cursor < text.length) {
        segments.push({ type: "text", text: text.slice(cursor) });
    }

    return segments;
}


export function extractMentionedAgents(content, agents) {
    return extractAgentMentionTurns(content, agents).map((turn) => turn.agent);
}


export function extractAgentMentionTurns(content, agents) {
    const text = String(content || "");
    const matches = findMentionMatches(text, agents);
    const turns = [];

    for (let index = 0; index < matches.length; index += 1) {
        const match = matches[index];
        const nextMatch = matches[index + 1] || null;
        const turnContent = text.slice(match.end, nextMatch?.start ?? text.length).trim();
        if (!turnContent) {
            continue;
        }

        turns.push({
            agent: match.agent,
            content: turnContent,
            start: match.start,
            end: nextMatch?.start ?? text.length,
        });
    }

    return turns;
}


function findMentionMatches(text, agents) {
    const mentionableAgents = getMentionableAgents(agents);
    const matches = [];

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

            matches.push({
                agent,
                start: index,
                end: index + 1 + label.length,
            });
            break;
        }
    }

    return matches;
}


function getMentionableAgents(agents) {
    return [...(agents || [])]
        .filter((agent) => getAgentMentionLabel(agent))
        .sort((left, right) => (
            getAgentMentionLabel(right).length - getAgentMentionLabel(left).length
        ));
}


function normalize(value) {
    return String(value || "").trim().toLowerCase();
}


function normalizeAgentColor(color) {
    const normalized = String(color || "#1c8b59").trim();
    return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized.toLowerCase() : "#1c8b59";
}


function isMentionBoundary(character) {
    return !character || /[\s,.;:!?)]/.test(character);
}
