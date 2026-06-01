# Libraries

## Frontend Libraries

This project intentionally avoids package managers, bundlers and external build systems for the frontend layer.

Frontend dependencies are included manually as local vendor files under:

```txt
app/web_app/static/vendor/
```

This keeps HORIZONE Lite simple, portable and easy to run in local environments without requiring `npm`, `node_modules`, Vite, Webpack or similar tooling.

---

### Highlight.js

**Library:** Highlight.js  
**Purpose:** Syntax highlighting for code blocks rendered inside chat messages.  
**License:** BSD 3-Clause  
**Website:** https://highlightjs.org/  
**Repository:** https://github.com/highlightjs/highlight.js  

#### Local files

```txt
app/web_app/static/vendor/highlight/highlight.min.js
app/web_app/static/vendor/highlight/github-dark.min.css
app/web_app/static/vendor/highlight/LICENSE.txt
```

#### Usage in HORIZONE Lite

HORIZONE Lite already includes its own Markdown renderer in:

```txt
app/web_app/static/JS/app/markdown.js
```

The Markdown renderer generates fenced code blocks as HTML using the following structure:

```html
<pre class="message-code-block__pre">
  <code class="message-code-block__code language-python">
    ...
  </code>
</pre>
```

Highlight.js is used only after the Markdown has been rendered, applying syntax highlighting to existing `<pre><code>` blocks.

The integration is handled by:

```txt
app/web_app/static/JS/app/syntax-highlight.js
```

This module detects code blocks inside chat messages and applies Highlight.js when available.

#### Design decision

Highlight.js is vendored locally instead of installed through `npm`.

Reasons:

- No frontend build step required.
- No dependency on `node_modules`.
- Easier offline/local execution.
- Easier auditing of third-party code.
- Fits the lightweight philosophy of HORIZONE Lite.

#### Notes

If Highlight.js is missing or fails to load, the chat must continue working normally. Code blocks should still render as plain escaped text without syntax colors.

The Markdown parser itself must not depend on Highlight.js.
