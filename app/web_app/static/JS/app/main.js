import { bindUI, bootApp, ensureAuthenticated } from "./controller.js";
import { showStatus } from "./status-ui.js";


document.addEventListener("DOMContentLoaded", () => {
    if (!ensureAuthenticated()) {
        return;
    }

    bindUI();
    bootApp().catch((error) => {
        showStatus(error.message || "The application could not be initialized.", true);
    });
});
