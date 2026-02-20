"""
Job handler — routes Slack requests to the right handler.

Quick commands (status, help) are handled directly by the worker.
Everything else is dispatched to the local daemon via the GitHub task queue.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

from github_client import GitHubClient

logger = logging.getLogger("claude-code-slack.jobs")


class JobHandler:
    def __init__(self, github_client: GitHubClient, slack_bot_token: str = ""):
        self.github = github_client
        self.slack_bot_token = slack_bot_token

    async def dispatch(
        self,
        text: str,
        user_id: str,
        channel_id: str = "",
        response_url: str = "",
        thread_ts: str = "",
    ):
        """Route a request to the appropriate handler."""
        text_lower = text.lower().strip()

        # Built-in commands (handled instantly by the worker)
        if text_lower in ("help", ""):
            result = self._handle_help()
            await self._respond(channel_id, result, response_url, thread_ts)
            return

        if text_lower in ("status", "ping"):
            result = "Bot is running. Daemon connectivity: checking via GitHub..."
            await self._respond(channel_id, result, response_url, thread_ts)
            return

        # Everything else → dispatch to local daemon via GitHub task queue
        await self._dispatch_to_daemon(
            text=text,
            user_id=user_id,
            channel_id=channel_id,
            response_url=response_url,
            thread_ts=thread_ts,
        )

    async def _dispatch_to_daemon(
        self,
        text: str,
        user_id: str,
        channel_id: str,
        response_url: str = "",
        thread_ts: str = "",
    ):
        """Write a task file to GitHub tasks/ directory for the daemon to pick up."""
        task_id = str(uuid.uuid4())[:8]
        task = {
            "task_id": task_id,
            "prompt": text,
            "requested_by": user_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "response_url": response_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        task_path = f"tasks/{task_id}.json"
        task_json = json.dumps(task, indent=2)
        commit_msg = f"Task {task_id}: {text[:50]}"

        success = await self.github.write_file(task_path, task_json, commit_msg)

        if success:
            logger.info(f"Dispatched task {task_id} to daemon")
        else:
            error_msg = "Failed to dispatch task. Check GitHub token permissions."
            await self._respond(channel_id, error_msg, response_url, thread_ts)

    def _handle_help(self) -> str:
        return (
            "*Claude Code Slack*\n\n"
            "Send any message and it will be processed by Claude Code "
            "running in your workspace.\n\n"
            "*Built-in commands:*\n"
            "`help` — This message\n"
            "`status` — Check if the bot is running\n\n"
            "*Examples:*\n"
            "• `What files are in the src/ directory?`\n"
            "• `Summarize the README`\n"
            "• `Run the tests and tell me what failed`\n"
        )

    async def _respond(
        self,
        channel_id: str,
        text: str,
        response_url: str = "",
        thread_ts: str = "",
    ):
        """Send a response back to Slack."""
        if response_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    response_url,
                    json={"response_type": "in_channel", "text": text},
                )
        elif channel_id and self.slack_bot_token:
            payload = {"channel": channel_id, "text": text}
            if thread_ts:
                payload["thread_ts"] = thread_ts
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.slack_bot_token}"},
                    json=payload,
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error(f"Slack error: {data.get('error')}")
