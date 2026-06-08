import { getDefaultModelConfigId, getModelConfigById, getSelectedModelConfigId } from "./selectors.js";
import { state } from "./state.js";

const PROVIDER_TYPE_LABELS = {
    cloud: "Cloud",
    llama_cpp: "llama.cpp",
    mlx: "MLX",
    ollama: "Ollama",
};


export function getProviderTypeDisplayName(providerType) {
    return PROVIDER_TYPE_LABELS[String(providerType || "").toLowerCase()] || providerType || "Provider";
}


export function normalizeProviderValue(value) {
    return String(value || "").trim().toLowerCase();
}


export function getProviderConfigById(providerId) {
    if (!providerId) {
        return null;
    }

    return state.providers.find((provider) => provider.id === Number(providerId)) || null;
}


export function getProviderDisplayName(providerOrType) {
    const provider = state.providers.find((item) => (
        item.name === providerOrType || item.provider_type === providerOrType
    ));
    return provider?.name || getProviderTypeDisplayName(providerOrType);
}


export function getDefaultModelConfig() {
    return getModelConfigById(getDefaultModelConfigId());
}


export function getSelectedModelConfig() {
    return getModelConfigById(getSelectedModelConfigId())
        || inferModelConfigFromConversation()
        || getDefaultModelConfig();
}


export function getSelectedModel() {
    return getSelectedModelConfig()?.name || state.activeConversation?.model || "";
}


export function getSelectedModelDisplayName() {
    const selectedModelConfig = getSelectedModelConfig();
    if (selectedModelConfig) {
        return selectedModelConfig.display_name || selectedModelConfig.name || "";
    }

    return state.activeConversation?.model || "";
}


export function getActualProvider() {
    return getSelectedModelConfig()?.provider
        || state.activeConversation?.provider
        || getDefaultModelConfig()?.provider
        || "ollama";
}


export function getModelNameById(modelConfigId) {
    return getModelConfigById(modelConfigId)?.name || "no model";
}


function inferModelConfigFromConversation() {
    const provider = state.activeConversation?.provider;
    const modelName = state.activeConversation?.model;
    if (!provider || !modelName) {
        return null;
    }

    return state.models.find((model) => (
        model.provider === provider
        && model.name === modelName
    )) || null;
}
