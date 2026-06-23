const TOOL_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;


export function getToolCommandName(tool) {
    return String(tool?.name || "").trim();
}


export function getActiveToolCommandQuery(value, cursorPosition) {
    const text = String(value || "");
    const cursor = Number.isFinite(cursorPosition) ? cursorPosition : text.length;
    const beforeCursor = text.slice(0, cursor);
    const slashIndex = beforeCursor.lastIndexOf("/");

    if (slashIndex === -1) {
        return null;
    }

    const previousCharacter = slashIndex > 0 ? beforeCursor[slashIndex - 1] : "";
    if (previousCharacter && !isCommandStartBoundary(previousCharacter)) {
        return null;
    }

    const query = beforeCursor.slice(slashIndex + 1);
    if (!/^[a-z0-9_]*$/i.test(query)) {
        return null;
    }

    return {
        start: slashIndex,
        end: cursor,
        query,
    };
}


export function filterCommandTools(query, tools) {
    const normalizedQuery = normalize(query);
    const uniqueTools = [];
    const seenNames = new Set();

    for (const tool of tools || []) {
        const name = getToolCommandName(tool);
        if (
            !TOOL_NAME_PATTERN.test(name)
            || seenNames.has(name)
            || tool?.is_active === false
            || tool?.is_available === false
        ) {
            continue;
        }

        const searchableText = normalize([
            name,
            tool?.display_name,
            tool?.description,
        ].filter(Boolean).join(" "));
        if (!normalizedQuery || searchableText.includes(normalizedQuery)) {
            uniqueTools.push(tool);
            seenNames.add(name);
        }
    }

    return uniqueTools;
}


export function replaceActiveToolCommand(value, cursorPosition, tool) {
    const command = getActiveToolCommandQuery(value, cursorPosition);
    const name = getToolCommandName(tool);
    if (!command || !TOOL_NAME_PATTERN.test(name)) {
        return { value, cursorPosition };
    }

    const suffix = String(value || "").slice(command.end);
    const normalizedSuffix = /^\s/.test(suffix) ? suffix : ` ${suffix}`;
    const nextValue = `${String(value || "").slice(0, command.start)}/${name}${normalizedSuffix}`;
    return {
        value: nextValue,
        cursorPosition: command.start + name.length + 2,
    };
}


export function extractToolCommandDirectives(content, tools = []) {
    const text = String(content || "");
    const toolByName = new Map(
        (tools || [])
            .map((tool) => [getToolCommandName(tool), tool])
            .filter(([name]) => TOOL_NAME_PATTERN.test(name)),
    );
    const matches = findCommandMatches(text);

    return matches.map((match, index) => {
        const nextMatch = matches[index + 1] || null;
        const end = nextMatch?.start ?? text.length;
        const tool = toolByName.get(match.tool_name) || null;
        return {
            tool_name: match.tool_name,
            instruction: text.slice(match.command_end, end).trim(),
            start: match.start,
            end,
            is_available: Boolean(
                tool
                && tool.is_active !== false
                && tool.is_available !== false
            ),
            tool,
        };
    });
}


export function createToolCommandSegments(content, tools = []) {
    const text = String(content || "");
    const availableNames = new Set(
        filterCommandTools("", tools).map((tool) => getToolCommandName(tool)),
    );
    const matches = findCommandMatches(text).filter((match) => availableNames.has(match.tool_name));
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
            type: "command",
            text: text.slice(match.start, match.command_end),
            tool_name: match.tool_name,
        });
        cursor = match.command_end;
    }
    if (cursor < text.length) {
        segments.push({ type: "text", text: text.slice(cursor) });
    }
    return segments;
}


function findCommandMatches(text) {
    const matches = [];
    const commandPattern = /\/([a-z][a-z0-9_]*)/gi;
    let match = null;

    while ((match = commandPattern.exec(text)) !== null) {
        const start = match.index;
        const previousCharacter = start > 0 ? text[start - 1] : "";
        const followingCharacter = text[commandPattern.lastIndex] || "";
        if (
            (previousCharacter && !isCommandStartBoundary(previousCharacter))
            || (followingCharacter && !isCommandEndBoundary(followingCharacter))
        ) {
            continue;
        }

        matches.push({
            tool_name: match[1].toLowerCase(),
            start,
            command_end: commandPattern.lastIndex,
        });
    }

    return matches;
}


function isCommandStartBoundary(character) {
    return /\s|[(\[{]/.test(character);
}


function isCommandEndBoundary(character) {
    return /\s|[,.;:!?)]/.test(character);
}


function normalize(value) {
    return String(value || "").trim().toLowerCase();
}
