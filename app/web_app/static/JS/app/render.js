import { syncComposerAvailability } from "./composer-ui.js";
import { renderChatSurface, renderConversationHeader, renderMessages } from "./render/chat-render.js";
import {
    renderProjectModelsManager,
    renderProjectSpace,
    renderDocumentsFileList,
    clearProjectModelCombobox,
    closeProjectModelComboboxOptions,
    filterProjectModelComboboxOptions,
    openProjectModelComboboxOptions,
    setProjectModelComboboxSelection,
    syncProjectModelSearchClearButtons,
} from "./render/project-render.js";
import {
    filterProjectAgentSwitchOptions,
    renderChatPanel,
    renderProjectAgentSwitchModal,
    renderSettingsProvidersManager,
    renderSettingsModelsManager,
    renderSettingsProfilesManager,
    renderSettingsSession,
    renderSettingsToolsManager,
    renderSettingsSpace,
} from "./render/settings-render.js";
import { renderConversations, renderProjects } from "./render/sidebar-render.js";


export function renderAll({ onProjectSelect, onConversationSelect, onConversationDelete } = {}) {
    renderProjects(onProjectSelect);
    renderConversations(onConversationSelect, onConversationDelete);
    renderProjectSpace(onConversationSelect, onConversationDelete);
    renderProjectModelsManager();
    renderSettingsSpace();
    renderSettingsProvidersManager();
    renderSettingsModelsManager();
    renderSettingsProfilesManager();
    renderSettingsSession();
    renderSettingsToolsManager();
    renderChatPanel();
    renderChatSurface();
    renderDocumentsFileList();
    syncComposerAvailability();
}

export {
    renderConversationHeader,
    renderConversations,
    renderDocumentsFileList,
    renderMessages,
    renderChatPanel,
    renderProjectAgentSwitchModal,
    filterProjectAgentSwitchOptions,
    clearProjectModelCombobox,
    closeProjectModelComboboxOptions,
    filterProjectModelComboboxOptions,
    openProjectModelComboboxOptions,
    setProjectModelComboboxSelection,
    syncProjectModelSearchClearButtons,
    renderProjectModelsManager,
    renderProjectSpace,
    renderProjects,
    renderSettingsProvidersManager,
    renderSettingsModelsManager,
    renderSettingsProfilesManager,
    renderSettingsSession,
    renderSettingsToolsManager,
    renderSettingsSpace,
};
