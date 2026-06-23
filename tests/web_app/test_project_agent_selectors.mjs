import assert from "node:assert/strict";

const stateModuleUrl = new URL("../../app/web_app/static/JS/app/state.js", import.meta.url);
const selectorsModuleUrl = new URL("../../app/web_app/static/JS/app/selectors.js", import.meta.url);

const { state } = await import(stateModuleUrl);
const {
    getAvailableCommandTools,
    getMentionableProjectAgents,
    getProjectAgentNameForConversation,
    getProjectAgentNameForMessage,
    getSelectedModelConfigId,
    getSelectedProfileId,
} = await import(selectorsModuleUrl);

Object.assign(state, {
    activeProjectId: 42,
    activeConversation: null,
    pendingModelConfigId: null,
    pendingProfileId: null,
    models: [
        { id: 1, name: "global-model", is_default: true },
        { id: 2, name: "agent-model", is_default: false },
    ],
    profiles: [
        { id: 10, name: "Global", is_default: true },
        { id: 20, name: "Coder", is_default: false },
    ],
    projectModels: [
        {
            id: 100,
            project_id: 42,
            model_id: 2,
            profile_id: 20,
            nickname: "Coder",
            is_default: true,
            model: { id: 2, name: "agent-model", display_name: "Agent Model" },
            profile: { id: 20, name: "Coder" },
        },
        {
            id: 101,
            project_id: 42,
            model_id: 1,
            profile_id: 10,
            nickname: "Default",
            is_default: false,
            model: { id: 1, name: "global-model", display_name: "Global Model" },
            profile: { id: 10, name: "Global" },
        },
    ],
    tools: [
        { name: "current_date", is_active: true, is_available: true },
        { name: "disabled", is_active: false, is_available: true },
    ],
    workspaceTools: [
        { name: "workspace_search", is_active: true, is_available: true },
    ],
    projectWorkspace: null,
});

assert.equal(
    getSelectedModelConfigId(),
    2,
    "project chats should select the default project agent model"
);

assert.equal(
    getSelectedProfileId(),
    20,
    "project chats should select the default project agent profile"
);

state.pendingProjectModelId = 101;

assert.equal(
    getSelectedModelConfigId(),
    1,
    "project chats without an active conversation should respect a pending project agent"
);

assert.equal(
    getSelectedProfileId(),
    10,
    "pending project agents should provide the next project chat profile"
);

state.pendingProjectModelId = null;

state.activeConversation = {
    id: 7,
    project_id: 42,
    project_model_id: 100,
    model_config_id: 2,
    profile_id: 20,
};

assert.equal(
    getProjectAgentNameForConversation(state.activeConversation),
    "Coder",
    "project conversation header should resolve the agent nickname"
);

assert.equal(
    getProjectAgentNameForMessage({ role: "assistant", model_config_id: 2, profile_id: 20 }),
    "Coder",
    "assistant message metadata should resolve the agent nickname"
);

assert.deepEqual(
    getMentionableProjectAgents(state.activeConversation).map((agent) => agent.id),
    [100, 101],
    "project chats should expose every project agent for mentions"
);

assert.deepEqual(
    getAvailableCommandTools().map((tool) => tool.name),
    ["current_date"],
    "project tools should stay hidden until the active project has a connected workspace",
);

state.projectWorkspace = { id: 9, project_id: 42 };
assert.deepEqual(
    getAvailableCommandTools().map((tool) => tool.name),
    ["current_date", "workspace_search"],
    "active project tools should become command suggestions with a connected workspace",
);

state.activeConversation = {
    id: 8,
    project_id: 42,
    project_model_id: 101,
    model_config_id: 2,
    profile_id: 20,
};

assert.equal(
    getProjectAgentNameForConversation(state.activeConversation),
    "Default",
    "project conversations should prefer their explicit project agent id"
);

assert.equal(
    getProjectAgentNameForMessage({
        role: "assistant",
        project_model_id: 101,
        project_model_name: "Default",
        model_config_id: 2,
        profile_id: 20,
    }),
    "Default",
    "assistant message metadata should prefer its explicit project agent"
);

state.activeConversation = null;
state.activeProjectId = null;

assert.equal(
    getProjectAgentNameForMessage({ role: "assistant", model_config_id: 2, profile_id: 20 }),
    "",
    "standalone chat messages should keep using model metadata"
);

console.log("Project agent selector tests passed.");
