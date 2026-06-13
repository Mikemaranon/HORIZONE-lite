import assert from "node:assert/strict";

const utilsModuleUrl = new URL("../../app/web_app/static/JS/app/agent-mention-utils.js", import.meta.url);
const markupModuleUrl = new URL("../../app/web_app/static/JS/app/agent-mention-markup.js", import.meta.url);

const {
    createAgentMentionSegments,
    extractAgentMentionTurns,
    extractMentionedAgents,
    filterMentionAgents,
    getActiveMentionQuery,
    replaceActiveMention,
} = await import(utilsModuleUrl);
const { createMentionedContentMarkup } = await import(markupModuleUrl);

const agents = [
    {
        id: 1,
        nickname: "Coder",
        color: "#2f7df6",
        model: { name: "qwen-coder", display_name: "Qwen Coder" },
    },
    {
        id: 2,
        nickname: "Reviewer",
        model: { name: "llama-review", display_name: "Llama Review" },
    },
    {
        id: 3,
        nickname: "Long Name",
        model: { name: "long-name-model", display_name: "Long Name Model" },
    },
];

assert.deepEqual(
    filterMentionAgents("rev", agents).map((agent) => agent.id),
    [2],
    "mention search should filter by nickname and model metadata",
);

assert.deepEqual(
    getActiveMentionQuery("Ask @Rev", 8),
    { start: 4, end: 8, query: "Rev" },
    "active mention query should use the last @ before the cursor",
);

assert.deepEqual(
    replaceActiveMention("Ask @Rev please", 8, agents[1]),
    {
        value: "Ask @Reviewer please",
        cursorPosition: 14,
    },
    "selecting an option should replace the active mention token",
);

assert.deepEqual(
    createAgentMentionSegments("Ask @Coder first, then @Reviewer.", agents).map((segment) => ({
        type: segment.type,
        text: segment.text,
        color: segment.color || "",
    })),
    [
        { type: "text", text: "Ask ", color: "" },
        { type: "mention", text: "@Coder", color: "#2f7df6" },
        { type: "text", text: " first, then ", color: "" },
        { type: "mention", text: "@Reviewer", color: "#1c8b59" },
        { type: "text", text: ".", color: "" },
    ],
    "mention segments should preserve text and expose agent colors",
);

const mentionedMarkup = createMentionedContentMarkup("Ask @Coder <now>", agents);
assert.equal(
    mentionedMarkup,
    'Ask <span class="agent-mention-token" style="--agent-mention-color: #2f7df6">@Coder</span> &lt;now&gt;',
    "mention markup should color only the mention without adding whitespace or unsafe text",
);

assert.deepEqual(
    extractMentionedAgents("Start with @Coder, then ask @Reviewer.", agents).map((agent) => agent.id),
    [1, 2],
    "mentions should be extracted in message order",
);

assert.deepEqual(
    extractMentionedAgents("Ask @Long Name before @Coder.", agents).map((agent) => agent.id),
    [3, 1],
    "mentions with spaces should match full agent names",
);

assert.deepEqual(
    extractAgentMentionTurns(
        "@Reviewer is the code alright? @Coder refactor only the parser.",
        agents,
    ).map((turn) => [turn.agent.id, turn.content]),
    [
        [2, "is the code alright?"],
        [1, "refactor only the parser."],
    ],
    "each mentioned agent should receive only the text after its own mention",
);

assert.deepEqual(
    extractAgentMentionTurns(
        "Context before the call. @Reviewer review this file. @Long Name summarize it.",
        agents,
    ).map((turn) => [turn.agent.id, turn.content]),
    [
        [2, "review this file."],
        [3, "summarize it."],
    ],
    "text before the first mention should not be routed to an agent segment",
);

console.log("Agent mention utility tests passed.");
