import assert from "node:assert/strict";

const markdownModuleUrl = new URL("../../app/web_app/static/JS/app/markdown.js", import.meta.url);
const { renderMarkdown } = await import(markdownModuleUrl);

assert.equal(
    renderMarkdown("hello `x`"),
    "<p>hello <code>x</code></p>",
    "single inline code span should render normally"
);

assert.equal(
    renderMarkdown("hello `x"),
    "<p>hello `x</p>",
    "unmatched opening backtick should stay as literal text"
);

assert.equal(
    renderMarkdown("``const `value` = 1`` and `another`"),
    "<p><code>const `value` = 1</code> and <code>another</code></p>",
    "multi-backtick fences should only close with the same fence length"
);

assert.equal(
    renderMarkdown("In the example, we pass `y` (which points to `x`) to increment, and inside the function, `*p` is used."),
    "<p>In the example, we pass <code>y</code> (which points to <code>x</code>) to increment, and inside the function, <code>*p</code> is used.</p>",
    "isolated inline code spans should not merge into a longer broken span"
);

console.log("Markdown inline code tests passed.");
