#!/usr/bin/env bash
# Forge installer: creates a venv, installs requirements, adds a `forge` alias.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
mkdir -p ~/Forge/memory ~/Forge/backups
if ! grep -q "alias forge=" ~/.bashrc 2>/dev/null; then
  echo "alias forge='$DIR/.venv/bin/python $DIR/forge.py'" >> ~/.bashrc
  echo "Added 'forge' alias to ~/.bashrc (run: source ~/.bashrc)"
else
  echo "'forge' alias already exists in ~/.bashrc, left it alone."
fi
command -v ollama >/dev/null || echo "Note: install Ollama from https://ollama.com, then: ollama pull qwen3:1.7b && ollama pull qwen3:8b"
echo "Done! Run: forge"
