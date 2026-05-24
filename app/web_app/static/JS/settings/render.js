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
        eyebrow: "Conexiones",
        title: "Proveedores",
        description: "Gestiona los backends disponibles para hablar con modelos locales o remotos.",
    },
    models: {
        eyebrow: "Catálogo",
        title: "Modelos",
        description: "Configura qué modelos existen en tu instalación y a qué proveedor apunta cada uno.",
    },
    profiles: {
        eyebrow: "Comportamiento",
        title: "Perfiles",
        description: "Define prompts, temperatura y tono reutilizable para cada conversación.",
    },
    tools: {
        eyebrow: "Automatización",
        title: "Herramientas",
        description: "Activa tools globales y sube archivos Python para ampliar lo que puede hacer el asistente.",
    },
    session: {
        eyebrow: "Cuenta local",
        title: "Sesión",
        description: "Revisa tu usuario actual y ajusta las credenciales de acceso de este equipo.",
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
            ? "Cuenta administradora de esta instalación local"
            : `Cuenta ${role} de esta instalación local`;
    }
    if (accountAvatarNode) {
        accountAvatarNode.textContent = initial;
    }
}
