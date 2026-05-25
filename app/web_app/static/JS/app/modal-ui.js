import { elements } from "./dom.js";


function openModal(modal) {
    if (!modal) {
        return;
    }

    modal.hidden = false;
    modal.dataset.state = "closed";
    document.body.classList.add("is-modal-open", "modal-open");

    window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
            modal.dataset.state = "open";
        });
    });
}


function closeModal(modal) {
    if (!modal) {
        return;
    }

    if (modal.hidden || modal.dataset.state === "closing") {
        return;
    }

    modal.dataset.state = "closing";

    window.setTimeout(() => {
        modal.hidden = true;
        modal.dataset.state = "closed";

        const anyModalOpen = [...document.querySelectorAll(".modal")].some((item) => !item.hidden);

        if (!anyModalOpen) {
            document.body.classList.remove("is-modal-open", "modal-open");
        }
    }, 240);
}


export function openProfileSwitchModal() {
    openModal(elements.profileSwitchModal);
}


export function closeProfileSwitchModal() {
    closeModal(elements.profileSwitchModal);
}


export function openModelSwitchModal() {
    openModal(elements.modelSwitchModal);
}


export function closeModelSwitchModal() {
    closeModal(elements.modelSwitchModal);
}


export function openProfileModal() {
    openModal(elements.profileModal);
}


export function closeProfileModal() {
    closeModal(elements.profileModal);
}


export function openChatExportModal() {
    openModal(elements.chatExportModal);
}


export function closeChatExportModal() {
    closeModal(elements.chatExportModal);
}


export function openSessionProfileModal() {
    openModal(elements.sessionProfileModal);
}


export function closeSessionProfileModal() {
    closeModal(elements.sessionProfileModal);
}


export function openModelModal() {
    openModal(elements.modelModal);
}


export function closeModelModal() {
    closeModal(elements.modelModal);
}


export function openProviderModal() {
    openModal(elements.providerModal);
}


export function closeProviderModal() {
    closeModal(elements.providerModal);
}


export function openProjectCustomizeModal() {
    openModal(elements.projectCustomizeModal);
}


export function closeProjectCustomizeModal() {
    closeModal(elements.projectCustomizeModal);
}


export function openDocumentsModal() {
    openModal(elements.documentsModal);
}


export function closeDocumentsModal() {
    closeModal(elements.documentsModal);
}


export function openToolUploadModal() {
    openModal(elements.toolUploadModal);
}


export function closeToolUploadModal() {
    closeModal(elements.toolUploadModal);
}
