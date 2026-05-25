import { elements } from "../dom.js";
import { createEmptyListItem, escapeHtml } from "../html.js";
import { getProjectConversations, getStandaloneConversations } from "../selectors.js";
import { state } from "../state.js";


export function renderProjects(onProjectSelect) {
    elements.projectCount.textContent = String(state.projects.length);

    if (!state.projects.length) {
        elements.projectsList.innerHTML = createEmptyListItem("There are no projects yet.");
        return;
    }

    elements.projectsList.innerHTML = state.projects
        .map((project) => {
            const activeClass = project.id === state.activeProjectId ? " is-active" : "";
            const projectChats = getProjectConversations(project.id).length;
            const description = projectChats
                ? `${projectChats} chat${projectChats === 1 ? "" : "s"} in the project`
                : (project.description || "No chats yet");
            return `
                <button class="list-item${activeClass}" type="button" data-project-id="${project.id}">
                    <div class="list-item__title">${escapeHtml(project.name)}</div>
                    <div class="list-item__meta">${escapeHtml(description)}</div>
                </button>
            `;
        })
        .join("");

    if (!onProjectSelect) {
        return;
    }

    elements.projectsList.querySelectorAll("[data-project-id]").forEach((element) => {
        element.addEventListener("click", () => onProjectSelect(Number(element.dataset.projectId), element));
    });
}


export function renderConversations(onConversationSelect, onConversationDelete) {
    const standaloneConversations = getStandaloneConversations();
    elements.conversationCount.textContent = String(standaloneConversations.length);

    if (!standaloneConversations.length) {
        elements.conversationsList.innerHTML = createEmptyListItem("There are no standalone chats yet.");
        return;
    }

    elements.conversationsList.innerHTML = standaloneConversations
        .map((conversation) => {
            const activeClass = conversation.id === state.activeConversationId ? " is-active" : "";
            return `
                <div class="conversation-row${activeClass}" data-conversation-row="${conversation.id}">
                    <button class="list-item conversation-row__main" type="button" data-conversation-id="${conversation.id}">
                        <div class="list-item__title">${escapeHtml(conversation.title || "New conversation")}</div>
                    </button>
                    <button
                        class="icon-button conversation-row__delete"
                        type="button"
                        data-delete-conversation-id="${conversation.id}"
                        aria-label="Delete chat"
                        title="Delete chat"
                    >
                        ×
                    </button>
                </div>
            `;
        })
        .join("");

    if (onConversationSelect) {
        elements.conversationsList.querySelectorAll("[data-conversation-id]").forEach((element) => {
            element.addEventListener("click", () => onConversationSelect(Number(element.dataset.conversationId)));
        });
    }

    if (onConversationDelete) {
        elements.conversationsList.querySelectorAll("[data-delete-conversation-id]").forEach((element) => {
            element.addEventListener("click", () => {
                onConversationDelete(Number(element.dataset.deleteConversationId));
            });
        });
    }
}
