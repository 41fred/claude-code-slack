#!/bin/bash
# Daemon startup script — sets PATH before running
# NOTE: install.sh generates a customized version of this script.
# This is the template/fallback version.

cd "$(dirname "$0")"

# Add common Node.js paths
export PATH="$HOME/.nvm/versions/node/$(ls $HOME/.nvm/versions/node/ 2>/dev/null | tail -1)/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Ensure the workspace clone exists
WORKSPACE_DIR=$(grep -E '^WORKSPACE_DIR=' .env 2>/dev/null | cut -d= -f2-)
GITHUB_REPO=$(grep -E '^GITHUB_REPO=' .env 2>/dev/null | cut -d= -f2-)

if [ -n "$WORKSPACE_DIR" ] && [ ! -d "$WORKSPACE_DIR/.git" ]; then
    echo "Workspace clone missing, attempting re-clone..."
    if command -v gh &>/dev/null && [ -n "$GITHUB_REPO" ]; then
        gh repo clone "$GITHUB_REPO" "$WORKSPACE_DIR"
    else
        echo "ERROR: Cannot clone — install gh CLI or clone manually"
    fi
fi

exec python3 main.py
