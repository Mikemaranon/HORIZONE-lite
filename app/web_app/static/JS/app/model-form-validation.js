export function isRuntimeModelPayload(modelPayload, models = []) {
    const modelId = Number(modelPayload?.id || 0);
    if (!modelId) {
        return false;
    }

    const model = (models || []).find((item) => Number(item.id) === modelId);
    return model?.provider === "llama_cpp" || model?.provider_type === "llama_cpp";
}


export function requiresProviderSelection(modelPayload, models = []) {
    return !isRuntimeModelPayload(modelPayload, models);
}
