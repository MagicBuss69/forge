# 🔥 Forge

**Forge** is a friendly personal AI assistant that lives in your terminal. Ask it anything (questions, homework, Linux help, ideas, writing) and it can also code, edit files and run tasks for you. It runs **100% locally and offline** through [Ollama](https://ollama.com). No cloud, no API keys, everything stays on your machine.

## ✨ Features

- **Slash menu** – type `/` to get a pop-up menu of commands.
- **Natural-language commands** – say things like "undo that", "start over", "which model", "show my todo" instead of slash commands.
- **Model routing**: a model per role, chat (fast answers), code (code, files, edits, deep thinking) and plan (to-do lists). Defaults: `qwen3:1.7b` chat/plan, `qwen3:8b` code.
- **`/model`**: shows the model for each role and your installed models. `/model chat <name>` / `/model code <name>` / `/model plan <name>` switch a role (saved in `~/.forge/config.json`). `/model suggest` detects your RAM, GPU and VRAM and recommends models that fit, with the `ollama pull` commands.
- **Windows, Linux and macOS**: colors and emoji in Windows Terminal/PowerShell, commands run in PowerShell on Windows and bash elsewhere.
- **Deep-think** – `/deep` makes Forge reason step by step.
- **Commands**: `/run` (shell command, asks y/n), `/search` (search the project), `/web` (web search with links), `/plan` & `/todo` (task lists), `/agent` (works on a task by itself, asking before changes), `/read`, `/undo`, `/model`, `/predict`, `/clear`, `/help`, `/bye`.
- **Multi-file edits** with a diff preview and **y/n** confirmation, with automatic backups and `/undo`.
- **Self-editing** – ask Forge to add a feature to itself; it backs up first and auto-restores if the change breaks it.
- **Typing predictions**: grey ghost text finishes what you're typing; press **→ or Tab** to accept (Tab still opens the `/` command menu when nothing is suggested). Matches from your history come first (instant); with `/predict ai` a small fast model (`qwen3:1.7b` or `qwen3:4b`) suggests the next words after a ~350 ms pause, in the background so typing never lags. `/predict ai|history|off` switches mode (saved in `~/.forge/config.json`); AI mode is on by default only with a GPU of 8 GB+ VRAM.
- **Hidden reasoning**: thinking models (qwen3, deepseek-r1) never show their raw reasoning in the answer.
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

## 🪟 Windows 10/11 install

1. Install [Python 3.10+](https://www.python.org/downloads/) (tick "Add to PATH"), [Git](https://git-scm.com/) and [Ollama](https://ollama.com/download).
2. In PowerShell:
   ```powershell
   git clone https://github.com/MagicBuss69/forge $HOME\Forge
   cd $HOME\Forge
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
   This creates a venv in `%USERPROFILE%\ai-env`, installs the packages, adds a `forge` function to your PowerShell `$PROFILE` (setting the CurrentUser execution policy to RemoteSigned if profiles are blocked) and puts a `forge.cmd` fallback in `%USERPROFILE%\.forge\bin` on your user PATH.
3. Open a **new** Windows Terminal / PowerShell tab and type `forge`.
4. Inside Forge, run `/model suggest` to see which models fit your PC, then `ollama pull` them and set them with `/model chat ...` / `/model code ...`.

Forge starts `ollama serve` in the background (no window) if it isn't already running. Data lives in `%USERPROFILE%\Forge\memory`, `backups` and `tests`.

## ⚙️ Config

Forge calls you "friend" by default. Set your name with an environment variable:
```bash
export FORGE_USER="YourName"
```
or in `~/.forge/config.json`:
```json
{"user_name": "YourName", "models": {"chat": "qwen3:4b", "code": "qwen3:14b", "plan": "qwen3:14b"}, "predict": "ai", "predict_model": "qwen3:1.7b"}
```
Forge uses `ollama` from your PATH (falls back to the standard install locations) and starts it automatically if it isn't running. Memory and backups are stored in `~/Forge/memory` and `~/Forge/backups` (created automatically).

## 🔒 Offline & private

Everything runs locally. The only network access is the optional web search (`/web`), which you trigger.

## 👤 Author

Made by [MagicBuss69](https://github.com/MagicBuss69). Licensed under MIT.
