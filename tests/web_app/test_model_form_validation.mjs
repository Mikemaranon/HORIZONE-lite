import assert from "node:assert/strict";

const validationModuleUrl = new URL(
    "../../app/web_app/static/JS/app/model-form-validation.js",
    import.meta.url
);
const {
    isRuntimeModelPayload,
    requiresProviderSelection,
} = await import(validationModuleUrl);

const models = [
    { id: 1, provider: "mlx", provider_type: "mlx" },
    { id: 10, provider: "llama_cpp", provider_type: "llama_cpp" },
];

assert.equal(
    isRuntimeModelPayload({ id: 10 }, models),
    true,
    "installed HORIZONE runtime models should be detected from the current model list"
);

assert.equal(
    requiresProviderSelection({ id: 10 }, models),
    false,
    "runtime model edits should not require a configurable provider selection"
);

assert.equal(
    requiresProviderSelection({ id: 1 }, models),
    true,
    "normal model edits should still require a provider selection"
);

assert.equal(
    requiresProviderSelection({}, models),
    true,
    "new model creation should still require a provider selection"
);

console.log("Model form validation tests passed.");
