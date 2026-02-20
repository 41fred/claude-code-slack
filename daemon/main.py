"""
Claude Code Slack — Local Daemon

Polls GitHub for task files, executes them via Claude Code CLI,
and posts results back to Slack.

Runs as a macOS LaunchAgent on your local machine.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys

from dotenv import load_dotenv

# Load .env from the daemon directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import httpx

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [daemon] %(levelname)s %(message)s",
)
logger = logging.getLogger("claude-code-slack.daemon")

GITHUB_API = "https://api.github.com"


def github_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# --- GitHub Task Queue ---


async def list_pending_tasks() -> list[dict]:
    """List task files in the tasks/ directory on GitHub."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{config.TASKS_PATH}"
    params = {"ref": config.GITHUB_BRANCH}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=github_headers(), params=params)

        if resp.status_code == 404:
            return []  # no tasks directory yet
        if resp.status_code != 200:
            logger.error(f"GitHub list error: {resp.status_code}")
            return []

        items = resp.json()
        if not isinstance(items, list):
            return []

        # Only pick up .json files (skip .gitkeep, etc.)
        return [item for item in items if item["name"].endswith(".json")]


async def read_task(path: str) -> dict | None:
    """Read a task file from GitHub."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=github_headers())
        if resp.status_code != 200:
            return None

        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        task = json.loads(content)
        task["_sha"] = data["sha"]
        task["_path"] = path
        return task


async def delete_task(path: str, sha: str):
    """Delete a completed task file from GitHub."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path}"
    payload = {
        "message": f"Task completed: {path}",
        "sha": sha,
        "branch": config.GITHUB_BRANCH,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            "DELETE", url, headers=github_headers(), json=payload
        )
        if resp.status_code in (200, 204):
            logger.info(f"Deleted task: {path}")
        else:
            logger.error(f"Failed to delete task: {resp.status_code}")


# --- Claude Code Execution ---


PROMPT_PREFIX = (
    "You are responding to a Slack command. "
    "Keep your response concise — it will be posted to a Slack channel. "
    "Format for Slack mrkdwn: use *bold* (single asterisk), _italic_, "
    "`code`, and <url|text> for links. No markdown headings.\n\n"
    "User request: "
)


def run_claude(prompt: str, context: str = "") -> str:
    """
    Run Claude Code CLI with a prompt in the workspace directory.
    Uses the local Claude subscription — no API key needed.
    """
    if context:
        full_prompt = PROMPT_PREFIX + context + "\nLatest request: " + prompt
    else:
        full_prompt = PROMPT_PREFIX + prompt
    logger.info(f"Running Claude Code: {prompt[:80]}...")

    try:
        result = subprocess.run(
            [config.CLAUDE_BIN, "-p", full_prompt],
            cwd=config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=config.CLAUDE_TIMEOUT,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Claude exited {result.returncode}: {result.stderr}")
            return f"Error: Claude Code returned exit code {result.returncode}\n{result.stderr[:500]}"

    except subprocess.TimeoutExpired:
        return f"Error: Claude Code timed out ({config.CLAUDE_TIMEOUT}s limit)"
    except FileNotFoundError:
        return "Error: Claude Code CLI not found. Is it installed and in PATH?"


# --- Markdown to Slack Conversion ---


def markdown_to_slack(text: str) -> str:
    """Convert standard markdown to Slack mrkdwn format.

    Slack uses its own markup ("mrkdwn") which differs from standard markdown:
      - Bold: *text* (single asterisk, not double)
      - Italic: _text_ (same as markdown)
      - Strikethrough: ~text~ (single tilde)
      - Code: `code` (same) and ```code``` (same)
      - Links: <url|text> (angle brackets, not [text](url))
      - Lists: only bullet supported; no ordered lists
      - No headings — use *bold* as a substitute
    """
    # Protect fenced code blocks from transformation
    parts = re.split(r"(```[\s\S]*?```)", text)
    converted = []

    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside a fenced code block — leave as-is
            converted.append(part)
            continue

        lines = part.split("\n")
        result = []

        for line in lines:
            # Headers: ## Title -> *Title*
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                result.append(f"*{header_match.group(2)}*")
                continue

            # Horizontal rules -> empty line
            if re.match(r"^---+$", line.strip()):
                result.append("")
                continue

            # Bold+italic: ***text*** -> *_text_*
            line = re.sub(r"\*\*\*(.+?)\*\*\*", r"*_\1_*", line)

            # Bold: **text** -> *text*
            line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)

            # Links: [text](url) -> <url|text>
            line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", line)

            # Images: ![alt](url) -> <url|alt>
            line = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<\2|\1>", line)

            # Strikethrough: ~~text~~ -> ~text~
            line = re.sub(r"~~(.+?)~~", r"~\1~", line)

            # Bullet list markers: convert * bullets to dot (avoid bold confusion)
            bullet_match = re.match(r"^(\s*)\*\s+(.+)$", line)
            if bullet_match:
                line = f"{bullet_match.group(1)}• {bullet_match.group(2)}"

            result.append(line)

        converted.append("\n".join(result))

    return "".join(converted)


# --- Slack Communication ---


async def post_to_slack(channel: str, text: str, thread_ts: str = ""):
    """Post a message to Slack."""
    if not config.SLACK_BOT_TOKEN:
        logger.warning("No SLACK_BOT_TOKEN — cannot post to Slack")
        return

    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"},
            json=payload,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Slack error: {data.get('error')}")


async def respond_via_url(response_url: str, text: str):
    """Respond to a slash command via response_url."""
    async with httpx.AsyncClient() as client:
        await client.post(
            response_url,
            json={"response_type": "in_channel", "text": text},
        )


# --- Thread Context ---


async def fetch_thread_history(channel: str, thread_ts: str) -> list[dict]:
    """Fetch all messages in a Slack thread for conversation context."""
    if not config.SLACK_BOT_TOKEN:
        return []

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://slack.com/api/conversations.replies",
            headers={"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"},
            params={"channel": channel, "ts": thread_ts},
        )
        data = resp.json()
        if data.get("ok"):
            return data.get("messages", [])
        else:
            logger.error(f"Failed to fetch thread: {data.get('error')}")
            return []


def format_thread_context(messages: list[dict]) -> str:
    """Format Slack thread messages as conversation context for Claude.

    Skips the last message (that's the current request being processed).
    Returns empty string if there's no prior context.
    """
    if not messages or len(messages) <= 1:
        return ""

    lines = ["Previous conversation in this thread:"]

    for msg in messages[:-1]:  # Exclude the latest message (current request)
        text = msg.get("text", "")
        # Strip bot mentions from text
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()
        if not text:
            continue

        if msg.get("bot_id"):
            lines.append(f"Bot: {text}")
        elif not msg.get("subtype"):  # Skip system/join messages
            lines.append(f"User: {text}")

    if len(lines) <= 1:
        return ""  # No actual conversation to include

    return "\n".join(lines) + "\n"


# --- Task Processing ---


async def process_task(task: dict):
    """Execute a single task."""
    task_id = task.get("task_id", "unknown")
    prompt = task.get("prompt", "")
    channel_id = task.get("channel_id", "")
    response_url = task.get("response_url", "")
    thread_ts = task.get("thread_ts", "")

    logger.info(f"Processing task {task_id}: {prompt[:60]}...")

    # Acknowledge pickup immediately so user sees activity
    ack_text = f"Processing: `{prompt[:80]}`..."
    if response_url:
        await respond_via_url(response_url, ack_text)
    elif channel_id:
        await post_to_slack(channel_id, ack_text, thread_ts)

    # Fetch thread context if this is a threaded conversation
    context = ""
    if thread_ts and channel_id:
        messages = await fetch_thread_history(channel_id, thread_ts)
        context = format_thread_context(messages)
        if context:
            logger.info(f"Thread context: {len(messages)} messages")

    # Run Claude Code CLI (with thread context if available)
    output = await asyncio.get_running_loop().run_in_executor(
        None, run_claude, prompt, context
    )

    # Convert markdown to Slack mrkdwn format
    output = markdown_to_slack(output)

    # Truncate for Slack (4000 char limit for a single message)
    if len(output) > 3900:
        output = output[:3900] + "\n...(truncated)"

    # Post result back to Slack (in thread if applicable)
    if response_url:
        await respond_via_url(response_url, output)
    elif channel_id:
        await post_to_slack(channel_id, output, thread_ts)

    # Delete the task file
    await delete_task(task["_path"], task["_sha"])

    # Sync workspace changes to GitHub
    await sync_workspace_to_github()

    logger.info(f"Task {task_id} completed")


# --- Git Sync ---


def _run_git(*args) -> tuple[int, str]:
    """Run a git command in the workspace directory. Returns (returncode, output)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except Exception as e:
        return 1, str(e)


async def sync_workspace_to_github():
    """Commit and push any workspace changes to GitHub after a task completes."""
    loop = asyncio.get_running_loop()

    # Stage all changes (.gitignore protects secrets and build artifacts)
    rc, out = await loop.run_in_executor(None, _run_git, "add", "-A")
    if rc != 0:
        logger.warning(f"git add failed: {out}")
        return

    # Check if there's anything to commit
    rc, out = await loop.run_in_executor(None, _run_git, "diff", "--cached", "--quiet")
    if rc == 0:
        return  # Nothing staged, skip

    rc, out = await loop.run_in_executor(
        None, _run_git, "commit", "-m", "auto: sync workspace changes from Slack"
    )
    if rc != 0:
        logger.warning(f"git commit failed: {out}")
        return

    rc, out = await loop.run_in_executor(None, _run_git, "push", "origin", config.GITHUB_BRANCH)
    if rc != 0:
        # Pull and retry once (task deletions may have created remote commits)
        await loop.run_in_executor(None, _run_git, "pull", "--rebase", "origin", config.GITHUB_BRANCH)
        rc, out = await loop.run_in_executor(None, _run_git, "push", "origin", config.GITHUB_BRANCH)
        if rc != 0:
            logger.warning(f"git push failed after rebase: {out}")
            return

    logger.info("Synced workspace changes to GitHub")


async def git_pull():
    """Pull latest changes from GitHub before processing tasks."""
    loop = asyncio.get_running_loop()
    rc, out = await loop.run_in_executor(None, _run_git, "pull", "--rebase", "origin", config.GITHUB_BRANCH)
    if rc != 0:
        logger.warning(f"git pull failed: {out}")


# --- Main Loop ---


async def poll_loop():
    """Main polling loop."""
    logger.info(f"Daemon started. Polling {config.GITHUB_REPO}/{config.TASKS_PATH} every {config.POLL_INTERVAL}s")
    logger.info(f"Workspace: {config.WORKSPACE_DIR}")
    logger.info(f"Claude binary: {config.CLAUDE_BIN}")

    while True:
        try:
            pending = await list_pending_tasks()

            if pending:
                # Pull latest before processing
                await git_pull()

            for item in pending:
                task = await read_task(item["path"])
                if task:
                    await process_task(task)

        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)

        await asyncio.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(poll_loop())
