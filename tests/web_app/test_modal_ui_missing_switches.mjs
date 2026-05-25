import assert from "node:assert/strict";

globalThis.document = {
    body: {
        classList: {
            add() {},
            remove() {},
        },
    },
    getElementById() {
        return null;
    },
    querySelector() {
        return null;
    },
    querySelectorAll() {
        return [];
    },
};

const modalUiModuleUrl = new URL("../../app/web_app/static/JS/app/modal-ui.js", import.meta.url);
const {
    closeModelSwitchModal,
    closeProfileSwitchModal,
} = await import(modalUiModuleUrl);

assert.doesNotThrow(
    () => closeModelSwitchModal(),
    "closing a missing model switch modal should be a safe no-op"
);

assert.doesNotThrow(
    () => closeProfileSwitchModal(),
    "closing a missing profile switch modal should be a safe no-op"
);

console.log("Modal UI missing-switch tests passed.");
