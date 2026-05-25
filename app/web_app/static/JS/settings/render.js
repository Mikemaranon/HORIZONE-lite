import {
    renderConversationHeader,
    renderSettingsModelsManager,
    renderSettingsProfilesManager,
    renderSettingsProvidersManager,
    renderSettingsSession,
    renderSettingsToolsManager,
} from "../app/render.js";
import { state } from "../app/state.js";

const SETTINGS_CATEGORY_MAP = {
    providers: {
        eyebrow: "Connections",
        title: "Providers",
        description: "Manage the available backends for talking to local or remote models.",
    },
    models: {
        eyebrow: "Catalog",
        title: "Models",
        description: "Configure which models exist in your installation and which provider each one points to.",
    },
    profiles: {
        eyebrow: "Behavior",
        title: "Profiles",
        description: "Define reusable prompts, temperature, and tone for each conversation.",
    },
    tools: {
        eyebrow: "Automation",
        title: "Tools",
        description: "Enable global tools and upload Python files to extend what the assistant can do.",
    },
    session: {
        eyebrow: "Local account",
        title: "Session",
        description: "Review your current user and adjust the sign-in credentials for this machine.",
    },
};

const DEFAULT_CATEGORY = "providers";


export function renderSettingsPage() {
    renderConversationHeader();
    renderSettingsSidebarAccount();
    renderSettingsProvidersManager();
    renderSettingsModelsManager();
    renderSettingsProfilesManager();
    renderSettingsToolsManager();
    renderSettingsSession();
    syncSettingsCategoryUI();
}


export function syncSettingsCategoryUI() {
    const activeCategory = getActiveSettingsCategory();
    const activeConfig = SETTINGS_CATEGORY_MAP[activeCategory];

    document.querySelectorAll("[data-settings-category]").forEach((button) => {
        const isActive = button.dataset.settingsCategory === activeCategory;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-current", isActive ? "page" : "false");
    });

    document.querySelectorAll("[data-settings-category-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.settingsCategoryPanel !== activeCategory;
    });

    document.querySelectorAll("[data-settings-category-actions]").forEach((actions) => {
        actions.hidden = actions.dataset.settingsCategoryActions !== activeCategory;
    });

    const eyebrowNode = document.getElementById("settings-panel-eyebrow");
    const titleNode = document.getElementById("settings-panel-title");
    const descriptionNode = document.getElementById("settings-panel-description");

    if (eyebrowNode) {
        eyebrowNode.textContent = activeConfig.eyebrow;
    }
    if (titleNode) {
        titleNode.textContent = activeConfig.title;
    }
    if (descriptionNode) {
        descriptionNode.textContent = activeConfig.description;
    }

    document.title = `HORIZONE lite · ${activeConfig.title}`;
}


export function getActiveSettingsCategory() {
    const rawHash = window.location.hash.replace(/^#/, "").trim().toLowerCase();

    if (Object.hasOwn(SETTINGS_CATEGORY_MAP, rawHash)) {
        return rawHash;
    }

    return DEFAULT_CATEGORY;
}


export function selectSettingsCategory(category) {
    const nextCategory = Object.hasOwn(SETTINGS_CATEGORY_MAP, category)
        ? category
        : DEFAULT_CATEGORY;

    if (window.location.hash.replace(/^#/, "") === nextCategory) {
        syncSettingsCategoryUI();
        return;
    }

    window.location.hash = nextCategory;
}


function renderSettingsSidebarAccount() {
    const accountNameNode = document.getElementById("settings-account-name");
    const accountMetaNode = document.getElementById("settings-account-meta");
    const accountAvatarNode = document.getElementById("settings-account-avatar");
    const username = state.currentUser?.username || "HORIZONE lite";
    const role = state.currentUser?.role || "local";
    const initial = String(username).trim().charAt(0).toUpperCase() || "H";

    if (accountNameNode) {
        accountNameNode.textContent = username;
    }
    if (accountMetaNode) {
        accountMetaNode.textContent = role === "admin"
            ? "Administrator account for this local installation"
            : `${role} account for this local installation`;
    }
    if (accountAvatarNode) {
        accountAvatarNode.textContent = initial;
    }
}
