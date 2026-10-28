# 🔥 Forge

**Forge** is a friendly personal AI assistant that lives in your terminal. Ask it anything (questions, homework, Linux help, ideas, writing) and it can also code, edit files and run tasks for you. It and runs **100% locally and offline** through [Ollama](https://ollama.com). No cloud, no API keys, everything stays on your machine.

## ✨ Features

- **Slash menu** – type `/` to get a pop-up menu of commands.
- **Natural-language commands** – say things like "undo that", "start over", "which model", "show my todo" instead of slash commands.
- **Model routing** – `qwen3:1.7b` for fast chat and planning, `qwen3:8b` for code, file reading, edits and deep thinking.
- **Deep-think** – `/deep` makes Forge reason step by step.
- **Commands**: `/run` (shell command, asks y/n), `/search` (search the project), `/web` (web search with links), `/plan` & `/todo` (task lists), `/agent` (works on a task by itself, asking before changes), `/read`, `/undo`, `/model`, `/clear`, `/help`, `/bye`.
- **Multi-file edits** with a diff preview and **y/n** confirmation, with automatic backups and `/undo`.
- **Self-editing** – ask Forge to add a feature to itself; it backs up first and auto-restores if the change breaks it.
- **Typing predictions** – grey ghost text suggests what you're typing from your history; press → to accept.
- **Memory** – remembers useful facts about you and your projects in `~/Forge/memory`.

## 📦 Install

1. Install Ollama: https://ollama.com/download
2. Pull the models:
   ```bash
   ollama pull qwen3:1.7b
   ollama pull qwen3:8b
   ```
3. Install the Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   (or run `./install.sh` to create a venv and add a `forge` alias)
4. Run it:
   ```bash
   python forge.py
   ```

## ⚙️ Config

Forge calls you "friend" by default. Set your name with an environment variable:
```bash
export FORGE_USER="YourName"
```
or in `~/.forge/config.json`:
```json
{"user_name": "YourName"}
```
Forge uses `ollama` from your PATH (falls back to `~/.local/ollama/bin/ollama`) and starts it automatically if it isn't running. Memory and backups are stored in `~/Forge/memory` and `~/Forge/backups` (created automatically).

## 🔒 Offline & private

Everything runs locally. The only network access is the optional web search (`/web`), which you trigger.

## 👤 Author

Made by [MagicBuss69](https://github.com/MagicBuss69). Licensed under MIT.
