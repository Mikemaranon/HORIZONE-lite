export function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}


export function createEmptyListItem(message) {
    return `<div class="list-item list-item--empty">${escapeHtml(message)}</div>`;
}


export function createMetaChipsMarkup(chips) {
    return chips.map((chip) => `
        <span class="selection-chip selection-chip--static" data-group="${escapeHtml(chip.group)}">
            <span class="selection-chip__group">${escapeHtml(chip.label)}</span>
            <span class="selection-chip__value">${escapeHtml(chip.value)}</span>
        </span>
    `).join("");
}


export function createModelAvatarMarkup(modelName, iconImage, className = "model-avatar") {
    const classes = [className];
    const normalizedIcon = String(iconImage || "").trim();
    const fallbackText = getModelAvatarFallback(modelName);

    if (normalizedIcon) {
        classes.push(`${className}--image`);
        return `
            <span class="${classes.join(" ")}">
                <img src="${escapeHtml(normalizedIcon)}" alt="${escapeHtml(modelName || "Model")}" loading="lazy">
            </span>
        `;
    }

    return `<span class="${classes.join(" ")}">${escapeHtml(fallbackText)}</span>`;
}


function getModelAvatarFallback(modelName) {
    const normalized = String(modelName || "")
        .replace(/[^a-z0-9]+/gi, " ")
        .trim();

    if (!normalized) {
        return "AI";
    }

    const parts = normalized.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }

    return normalized.slice(0, 2).toUpperCase();
}
