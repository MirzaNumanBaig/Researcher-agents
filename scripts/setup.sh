#!/usr/bin/env bash
# Installs Agent Reach + the zero-login channels (web, YouTube, RSS, Exa search).
set -euo pipefail
python3 -m venv "$HOME/.agent-reach-venv"
"$HOME/.agent-reach-venv/bin/pip" install -q \
  https://github.com/Panniantong/agent-reach/archive/main.zip "yt-dlp[default]"
export PATH="$HOME/.agent-reach-venv/bin:$PATH"
agent-reach install --env=auto --system
mkdir -p "$HOME/.config/yt-dlp"
grep -qxF -- '--js-runtimes node' "$HOME/.config/yt-dlp/config" 2>/dev/null \
  || echo '--js-runtimes node' >> "$HOME/.config/yt-dlp/config"
agent-reach doctor
