import assert from "node:assert/strict";

const utilsModuleUrl = new URL("../../app/web_app/static/JS/app/tool-command-utils.js", import.meta.url);
const markupModuleUrl = new URL("../../app/web_app/static/JS/app/composer-content-markup.js", import.meta.url);
const {
    createToolCommandSegments,
    extractToolCommandDirectives,
    filterCommandTools,
    getActiveToolCommandQuery,
    replaceActiveToolCommand,
} = await import(utilsModuleUrl);
const { createComposerContentMarkup } = await import(markupModuleUrl);

const tools = [
    { name: "current", display_name: "Current", is_active: true, is_available: true },
    { name: "current_date", display_name: "Current date", is_active: true, is_available: true },
    { name: "web_search", display_name: "Web search", description: "Search the web", is_active: true },
    { name: "disabled_tool", display_name: "Disabled", is_active: false },
];

assert.deepEqual(
    getActiveToolCommandQuery("Ask /web_se", 11),
    { start: 4, end: 11, query: "web_se" },
    "the active command query should start at a valid slash boundary",
);
assert.equal(getActiveToolCommandQuery("https://example.com", 19), null);
assert.equal(getActiveToolCommandQuery("path/to", 7), null);

assert.deepEqual(
    filterCommandTools("search", tools).map((tool) => tool.name),
    ["web_search"],
    "autocomplete should search metadata and omit inactive tools",
);

assert.deepEqual(
    replaceActiveToolCommand("Ask /web_se later", 11, tools[2]),
    { value: "Ask /web_search later", cursorPosition: 16 },
    "selection should replace the query and keep following text",
);

const directives = extractToolCommandDirectives(
    "/current_date tell me today's date. /web_search use that date for the latest KOI match",
    tools,
);
assert.deepEqual(
    directives.map(({ tool_name, instruction, start, end, is_available }) => ({
        tool_name, instruction, start, end, is_available,
    })),
    [
        {
            tool_name: "current_date",
            instruction: "tell me today's date.",
            start: 0,
            end: 36,
            is_available: true,
        },
        {
            tool_name: "web_search",
            instruction: "use that date for the latest KOI match",
            start: 36,
            end: 86,
            is_available: true,
        },
    ],
    "directives should retain order and stop at the next command",
);

assert.deepEqual(
    extractToolCommandDirectives("/unknown do it /disabled_tool no /web_search", tools)
        .map(({ tool_name, instruction, is_available }) => ({ tool_name, instruction, is_available })),
    [
        { tool_name: "unknown", instruction: "do it", is_available: false },
        { tool_name: "disabled_tool", instruction: "no", is_available: false },
        { tool_name: "web_search", instruction: "", is_available: true },
    ],
    "unknown, inactive, repeated, and empty directives remain explicit for backend validation",
);

assert.deepEqual(
    extractToolCommandDirectives("/current now /current_date later /current again", tools)
        .map(({ tool_name, instruction }) => ({ tool_name, instruction })),
    [
        { tool_name: "current", instruction: "now" },
        { tool_name: "current_date", instruction: "later" },
        { tool_name: "current", instruction: "again" },
    ],
    "prefixed and repeated tool names should parse independently",
);

assert.deepEqual(
    createToolCommandSegments("Use /web_search <query>", tools).map(({ type, text }) => ({ type, text })),
    [
        { type: "text", text: "Use " },
        { type: "command", text: "/web_search" },
        { type: "text", text: " <query>" },
    ],
);

const agents = [{ id: 1, nickname: "Coder", color: "#2f7df6", model: {} }];
assert.equal(
    createComposerContentMarkup("@Coder use /web_search <now>", agents, tools),
    '<span class="agent-mention-token" style="--agent-mention-color: #2f7df6">@Coder</span> use <span class="tool-command-token">/web_search</span> &lt;now&gt;',
    "combined markup should safely render mentions and commands",
);

console.log("Tool command utility tests passed.");
