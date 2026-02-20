"""
Daemon configuration — all values come from environment variables.
"""

import os

# GitHub polling
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # e.g. "youruser/your-repo"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
TASKS_PATH = "tasks"  # directory in repo where tasks are queued

# Local workspace (the cloned repo where Claude Code runs)
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "")

# Claude Code CLI
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "300"))  # 5 minutes

# Slack
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

# Polling
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds
