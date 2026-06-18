<p align="center">
  <img src="app/web_app/static/assets/logos/HORIZONE_FULL_LOGO.PNG" alt="HORIZONE AI" width="650">
</p>

<p align="center">
  <a href="https://mikemaranon.github.io/HORIZONE/">
    <img src="https://img.shields.io/badge/View%20Website-HORIZONE-00BFFF?style=for-the-badge&logo=github&logoColor=white" alt="View Website">
  </a>
</p>

<p align="center">
  A local-first AI chat app built for working with different models, keeping conversations organized, and offering a simple, lightweight, pleasant experience.
</p>

## AI That Feels Close, Fast, and Yours

HORIZONE is a chat experience inspired by the comfort of modern conversational tools, but designed to give you more control. The app is meant to run in your own environment, keep your conversations organized, and let you choose how you want to work with AI at any moment.

This is not just about sending prompts back and forth. HORIZONE aims to be a space where you can think, write, explore ideas, and keep context without friction.

## What You Can Do With HORIZONE

- Chat with different models from a single interface, without switching tools.
- Choose between local and remote providers depending on what each conversation needs.
- Run local models with MLX on Apple Silicon.
- Connect to Ollama and use your local model library.
- Use OpenAI or other providers whenever you want access to cloud models.
- Create projects to separate topics, clients, ideas, or workstreams.
- Save conversations and return to them later without losing context.
- Define profiles with different instructions, tone, and generation settings.
- Adjust system prompts and preferences so the assistant fits your workflow.

## Designed To Feel Natural

The experience is designed to feel clear from the first moment: a sidebar for navigating projects and conversations, a clean central chat area, and simple controls for switching models, providers, and settings.

The goal is for it to feel light, direct, and friendly. Less friction, more continuity.

## Project Behavior

Projects group chats, project instructions, and uploaded text documents. Chats inside the same project stay independent from each other; they share the project prompt and relevant document fragments, but they do not automatically inherit messages from sibling chats.

When a project is deleted, its conversations are kept as standalone chats with no project attached. Uploaded project documents are removed with the project.

## Great For

- People who want a more private and controllable AI app.
- Anyone who prefers local models whenever possible.
- Teams or creators who need to organize conversations by project.
- Users who often switch between response styles, contexts, and models.

## Supported Providers

HORIZONE can work with multiple AI paths inside the same app:

- `MLX`: for local inference on Apple Silicon.
- `Ollama`: for connecting to models served on `localhost`.
- `OpenAI`: for using remote models with your own API key.

## Quick Start

If your environment is already set up, you can start the app like this:

```bash
source .venv/bin/activate
python app/web_server/main.py
```

Then open the interface in your browser and start creating projects, profiles, and conversations.

For a core local preview install:

```bash
pip install -r requirements-core.txt
```

For Apple Silicon MLX builds, install:

```bash
pip install -r requirements-mac.txt
```

For the optional llama.cpp Python runtime, install:

```bash
pip install -r requirements-runtime-llamacpp.txt
```

On Apple Silicon, make sure the llama.cpp runtime is built with Metal. A CPU-only
`llama-cpp-python` install can run but will be dramatically slower for models
such as 12B GGUF files.

```bash
CMAKE_ARGS="-DGGML_METAL=on" \
pip install --force-reinstall --no-cache-dir "llama-cpp-python[server]>=0.3,<0.4"
```

If you use a native `llama-server` binary through `HORIZONE_LLAMA_CPP_BINARY`,
build or install that binary with Metal enabled (`GGML_METAL=ON`). HORIZONE
passes GPU layers automatically on Apple Silicon; set
`HORIZONE_LLAMA_CPP_GPU_LAYERS=0` only when you intentionally want CPU fallback.

Windows and Linux package builds can start from `requirements-windows.txt` or `requirements-linux.txt` and add optional provider/runtime files only when needed.

By default, HORIZONE stores its runtime SQLite database in a user-level app data directory:

- macOS: `~/Library/Application Support/HORIZONE/flask.db`
- Windows: `%APPDATA%/HORIZONE/flask.db`
- Linux: `~/.local/share/horizone/flask.db`

If you need an isolated path for tests or a custom environment, set `APP_DB_PATH`. To move all default app data under a custom parent directory, set `HORIZONE_DATA_DIR`.

## In One Line

HORIZONE is a local-first, flexible, pleasant AI conversation space built to help you choose your models, organize your work, and keep the experience simple from beginning to end.
