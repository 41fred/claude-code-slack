"""
Claude Code Slack — Worker (Railway)

Receives Slack events and slash commands via webhook,
dispatches AI tasks to the local daemon via GitHub task queue.

Deploy to Railway (or any container host) with: python main.py
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
import traceback
from contextlib import asynccontextmanager

print(f"[startup] Python {sys.version}", flush=True)

try:
    from dotenv import load_dotenv
    from fastapi import FastAPI, Request, Response

    from github_client import GitHubClient
    from job_handler import JobHandler

    print("[startup] All imports succeeded", flush=True)
except Exception as e:
    print(f"[startup] IMPORT ERROR: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("claude-code-slack.worker")

# --- Slack signature verification ---

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")


def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature (v0 HMAC-SHA256)."""
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not set — skipping verification")
        return True

    # Replay protection: reject requests older than 5 minutes
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# --- App setup ---

job_handler: JobHandler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global job_handler
    logger.info("Starting Claude Code Slack Worker...")

    github_client = GitHubClient(
        token=os.getenv("GITHUB_TOKEN", ""),
        repo=os.getenv("GITHUB_REPO", ""),
        branch=os.getenv("GITHUB_BRANCH", "main"),
    )

    job_handler = JobHandler(
        github_client=github_client,
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
    )

    logger.info(f"GitHub: repo={github_client.repo}")
    logger.info("Worker ready. Listening for Slack events.")
    yield
    logger.info("Shutting down.")


app = FastAPI(title="Claude Code Slack Worker", lifespan=lifespan)


# --- Routes ---


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle all Slack events: URL verification, slash commands, app mentions, DMs."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        return Response(content="Invalid signature", status_code=401)

    content_type = request.headers.get("content-type", "")

    # Slack sends slash commands as form-encoded
    if "application/x-www-form-urlencoded" in content_type:
        from urllib.parse import parse_qs

        form = parse_qs(body.decode("utf-8"))
        payload = {k: v[0] if len(v) == 1 else v for k, v in form.items()}
        return await handle_slash_command(payload)

    # Events API sends JSON
    payload = json.loads(body)

    # URL verification challenge (Slack sends this during setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # Event callbacks (messages, app_mentions, etc.)
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        # Ignore bot messages to prevent loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"ok": True}

        asyncio.create_task(handle_event(event))
        return {"ok": True}

    return {"ok": True}


async def handle_slash_command(payload: dict):
    """Handle slash command (e.g., /claude)."""
    text = (payload.get("text", "") or "").strip()
    user_id = payload.get("user_id", "unknown")
    channel_id = payload.get("channel_id", "")
    response_url = payload.get("response_url", "")

    logger.info(f"Slash command from {user_id}: '{text}'")

    # Execute in background, respond immediately
    asyncio.create_task(
        job_handler.dispatch(
            text=text,
            user_id=user_id,
            channel_id=channel_id,
            response_url=response_url,
        )
    )

    return Response(
        content=json.dumps({
            "response_type": "ephemeral",
            "text": f"Got it: `{text or 'help'}`\nWorking on it...",
        }),
        media_type="application/json",
    )


async def handle_event(event: dict):
    """Handle an event callback (DM or @mention)."""
    text = (event.get("text", "") or "").strip()
    user_id = event.get("user", "unknown")
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")

    # Strip bot mention prefix (e.g., "<@U123> do something" -> "do something")
    text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

    logger.info(f"Event from {user_id} in {channel_id}: '{text[:60]}'")

    await job_handler.dispatch(
        text=text,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    print(f"[startup] Starting uvicorn on port {port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
