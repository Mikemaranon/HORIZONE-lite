import assert from "node:assert/strict";

const nodes = {};
const classList = {
    add() {},
    remove() {},
};
const messageArticleClassAdds = [];

function createNode(id) {
    return {
        id,
        hidden: true,
        dataset: {},
        textContent: "",
        innerHTML: "",
        scrollHeight: 0,
        scrollTop: 0,
        clientHeight: 0,
        insertedHTML: [],
        classList,
        insertAdjacentHTML(position, html) {
            this.insertedHTML.push({ position, html });
            this.innerHTML += html;
        },
    };
}

globalThis.document = {
    body: { classList },
    getElementById(id) {
        if (!nodes[id]) {
            nodes[id] = createNode(id);
        }
        return nodes[id];
    },
    querySelector(selector) {
        const messageKeyMatch = String(selector).match(/\[data-message-key="([^"]+)"\]/);
        if (messageKeyMatch) {
            return {
                classList: {
                    add(className) {
                        messageArticleClassAdds.push({
                            messageKey: messageKeyMatch[1],
                            className,
                        });
                    },
                },
            };
        }
        return null;
    },
    querySelectorAll() {
        return [];
    },
};

globalThis.window = {
    requestAnimationFrame(callback) {
        callback();
    },
    CSS: {
        escape(value) {
            return String(value);
        },
    },
};

const stateModuleUrl = new URL("../../app/web_app/static/JS/app/state.js", import.meta.url);
const messageUiModuleUrl = new URL("../../app/web_app/static/JS/app/message-ui.js", import.meta.url);

const { state } = await import(stateModuleUrl);
const {
    appendStreamingAssistantMessage,
    createMessageMarkup,
    handleToolTraceMessageClick,
} = await import(messageUiModuleUrl);

Object.assign(state, {
    activeConversation: null,
    activeMessages: [],
    models: [
        { id: 7, name: "deepseek-coder", display_name: "DeepSeek Coder" },
    ],
    profiles: [
        { id: 3, name: "Coder" },
    ],
    projectModels: [
        {
            id: 11,
            nickname: "Coder",
            model_id: 7,
            profile_id: 3,
            model: { id: 7, name: "deepseek-coder", display_name: "DeepSeek Coder" },
        },
    ],
});

function createConfirmationMessage(status) {
    return {
        id: `confirmation-${status}`,
        role: "assistant",
        content: "I need your approval before I write `random.py` in the workspace.",
        project_model_id: 11,
        project_model_name: "Coder",
        model_config_id: 7,
        model_name: "DeepSeek Coder",
        profile_id: 3,
        profile_name: "Coder",
        tool_events: [
            {
                ok: false,
                tool_name: "workspace_write_file",
                tool_display_name: "Workspace write file",
                arguments: { path: "random.py", content: "print(1)" },
                reason: "The user asked to create the file.",
                error: "This tool requires explicit confirmation before execution.",
                policy: {
                    status,
                    risk_level: "workspace_write",
                    reason: "This tool requires explicit confirmation before execution.",
                },
            },
        ],
    };
}

assert.match(
    createMessageMarkup(createConfirmationMessage("confirmation_required")),
    /Tool confirmation request: pending/,
    "pending confirmation requests should not be shown as tool failures",
);

assert.match(
    createMessageMarkup(createConfirmationMessage("confirmation_required")),
    /data-tool-confirm-action="approve"/,
    "pending confirmation requests should expose approval controls",
);

assert.doesNotMatch(
    createMessageMarkup(createConfirmationMessage("confirmation_required")),
    /Tool failed/,
    "confirmation-required events should not render the failed-tool label",
);

assert.match(
    createMessageMarkup(createConfirmationMessage("confirming")),
    /Tool confirmation request: confirmed/,
    "locally approved confirmation requests should render as confirmed",
);

assert.doesNotMatch(
    createMessageMarkup(createConfirmationMessage("confirming")),
    /data-tool-confirm-action=/,
    "approved confirmation requests should not expose approval controls after reload",
);

assert.match(
    createMessageMarkup(createConfirmationMessage("cancelled")),
    /Tool confirmation request: denied/,
    "cancelled confirmation requests should render as denied",
);

assert.doesNotMatch(
    createMessageMarkup(createConfirmationMessage("cancelled")),
    /data-tool-confirm-action=/,
    "cancelled confirmation requests should not expose approval controls after reload",
);

const pendingConfirmationMessage = createConfirmationMessage("confirmation_required");
const successfulWriteMessage = {
    role: "assistant",
    content: "The file has been created.",
    tool_events: [
        {
            ok: true,
            tool_name: "workspace_write_file",
            arguments: { path: "random.py", content: "print(1)" },
            result: {
                file: {
                    path: "random.py",
                    created: true,
                },
            },
            policy: { status: "confirmed" },
        },
    ],
};

assert.doesNotMatch(
    createMessageMarkup(pendingConfirmationMessage, {
        messages: [pendingConfirmationMessage, successfulWriteMessage],
        messageIndex: 0,
    }),
    /data-tool-confirm-action=/,
    "pending confirmation controls should disappear once a matching write succeeds later in the conversation",
);

assert.match(
    createMessageMarkup(pendingConfirmationMessage, {
        messages: [pendingConfirmationMessage, successfulWriteMessage],
        messageIndex: 0,
    }),
    /Tool confirmation request: confirmed/,
    "pending confirmation status should render as confirmed once a matching write succeeds later in the conversation",
);

assert.match(
    createMessageMarkup({
        ...createConfirmationMessage("confirmed"),
        tool_events: [
            {
                ok: true,
                tool_name: "workspace_write_file",
                arguments: { path: "random.py" },
                result: {
                    file: {
                        path: "random.py",
                        created: true,
                    },
                },
                policy: { status: "confirmed" },
            },
        ],
    }),
    /File created: random\.py/,
    "executed confirmed tools should still render their workspace result",
);

const firstAssistantMessage = {
    role: "assistant",
    content: "I need approval.",
    project_model_id: 11,
    project_model_name: "Coder",
    model_config_id: 7,
    model_name: "DeepSeek Coder",
    profile_id: 3,
    profile_name: "Coder",
};
const secondAssistantMessage = {
    role: "assistant",
    content: "The file has been created.",
    project_model_id: 11,
    project_model_name: "Coder",
    model_config_id: 7,
    model_name: "DeepSeek Coder",
    profile_id: 3,
    profile_name: "Coder",
};

assert.match(
    createMessageMarkup(firstAssistantMessage, { nextMessage: secondAssistantMessage }),
    /message--assistant-continues/,
    "the first assistant message should drop its bottom divider when another same-agent message follows",
);

assert.match(
    createMessageMarkup(secondAssistantMessage, { previousMessage: firstAssistantMessage }),
    /message--assistant-continuation/,
    "the second same-agent assistant message should render as a continuation",
);

state.activeMessages = [firstAssistantMessage, secondAssistantMessage];
nodes["messages-container"].insertedHTML = [];

appendStreamingAssistantMessage(secondAssistantMessage);

assert.match(
    nodes["messages-container"].insertedHTML.at(-1).html,
    /message--assistant-continuation/,
    "a same-agent streaming assistant message should render as a continuation immediately",
);
assert.deepEqual(
    messageArticleClassAdds.at(-1),
    {
        messageKey: firstAssistantMessage.__clientKey,
        className: "message--assistant-continues",
    },
    "starting a same-agent stream should mark the previous assistant message as continuing",
);

const modalMessage = createConfirmationMessage("cancelled");
state.activeMessages = [modalMessage];

handleToolTraceMessageClick({
    target: {
        closest(selector) {
            if (selector !== "[data-tool-trace-button]") {
                return null;
            }

            return {
                dataset: {
                    messageKey: `message-${modalMessage.id}`,
                    toolEventIndex: "0",
                },
            };
        },
    },
});

assert.equal(
    nodes["tool-trace-modal-eyebrow"].textContent,
    "Confirmation",
    "confirmation events should open a confirmation-specific modal",
);
assert.equal(
    nodes["tool-trace-modal-title"].textContent,
    "Tool confirmation request",
    "confirmation modals should not use the generic tool title",
);
assert.match(
    nodes["tool-trace-modal-content"].innerHTML,
    /Request status/,
    "confirmation modals should render the request status details",
);

state.activeMessages = [pendingConfirmationMessage, successfulWriteMessage];

handleToolTraceMessageClick({
    target: {
        closest(selector) {
            if (selector !== "[data-tool-trace-button]") {
                return null;
            }

            return {
                dataset: {
                    messageKey: `message-${pendingConfirmationMessage.id}`,
                    toolEventIndex: "0",
                },
            };
        },
    },
});

assert.equal(
    nodes["tool-trace-modal-title"].textContent,
    "Tool confirmation request",
    "reconciled confirmation traces should still open the confirmation modal",
);
assert.match(
    nodes["tool-trace-modal-summary"].textContent,
    /Confirmed before running/,
    "reconciled confirmation modals should report a confirmed request",
);
assert.match(
    nodes["tool-trace-modal-content"].innerHTML,
    /confirmed/,
    "reconciled confirmation modal details should include the confirmed status",
);

console.log("Message UI tool confirmation tests passed.");
