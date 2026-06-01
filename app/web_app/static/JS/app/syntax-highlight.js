export function applySyntaxHighlighting(rootElement) {
    if (!rootElement || typeof rootElement.querySelectorAll !== "function") {
        return;
    }

    if (typeof window === "undefined" || !window.hljs?.highlightElement) {
        return;
    }

    rootElement.querySelectorAll("pre code").forEach((codeBlock) => {
        if (codeBlock.dataset.highlighted) {
            return;
        }

        try {
            window.hljs.highlightElement(codeBlock);
            codeBlock.dataset.highlighted = "true";
        } catch (error) {
            // Highlighting should never interrupt chat rendering.
        }
    });
}
