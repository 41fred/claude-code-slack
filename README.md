# Claude Code Slack

Let your team talk to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) directly from Slack. Claude runs locally on your machine using your existing Claude plan — no API keys, no per-token costs. Your codebase, your CLAUDE.md, your MCP tools — all accessible through a Slack message.

```
You (Slack):  @Claude What files are in the src directory?
Bot (Slack):  Found 12 files in src/: index.ts, app.ts, config.ts...
```

Mention `@YourBot` in any channel, DM it directly, or use the optional `/claude` slash command. Reply in threads and it remembers the full conversation.

## How It Works

```
                        ┌──────────────────────────┐
                        │   Slack (your workspace)  │
                        │                          │
                        │  /claude <prompt>        │
                        │  @bot <message>          │
                        └──────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  Worker (Railway / any host)  │
                    │                              │
                    │  FastAPI webhook receiver     │
                    │  Slack signature verification │
                    │  Quick commands (help, status)│
                    │                              │
                    │  AI tasks → writes JSON to    │
                    │  GitHub tasks/ directory      │
                    └──────────────┬───────────────┘
                                   │
                          GitHub repo (tasks/)
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  Daemon (your Mac, always on) │
                    │                              │
                    │  Polls GitHub every 5s        │
                    │  Picks up task JSON files     │
                    │  Runs: claude -p "prompt"     │
                    │  Posts result to Slack        │
                    │  Deletes task file            │
                    │  Auto-commits workspace       │
                    └──────────────────────────────┘
```

**Why this architecture?**
- Claude Code CLI runs locally with your subscription (no API key costs)
- Claude has full access to your codebase, CLAUDE.md, and MCP tools
- Your workspace stays on your machine — the worker only routes messages
- Thread context is preserved (the daemon fetches Slack thread history)

## Features

- **Slash commands** — `/claude <anything>` from any channel
- **@mentions** — `@YourBot summarize the README` in channels
- **DMs** — Message the bot directly for private conversations
- **Thread context** — Reply in threads and the bot sees prior messages
- **Markdown conversion** — Claude's markdown output is converted to Slack's mrkdwn format
- **Auto-sync** — Workspace changes are committed and pushed after each task
- **Menu bar status** — Green/red circle shows daemon health at a glance (macOS)
- **Workspace isolation** — Claude runs in a separate clone, not your working directory

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| macOS | 10.15+ | `sw_vers` |
| Python | 3.9+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| Claude Code CLI | Latest | `claude --version` |
| GitHub CLI | Latest | `gh --version` |
| A Slack workspace | — | You must be an admin or able to install apps |
| A Railway account | — | [railway.app](https://railway.app) — free tier works, or use any container host |

### Install prerequisites

```bash
# Node.js (via nvm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install --lts

# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# GitHub CLI
brew install gh   # or download from https://github.com/cli/cli/releases
gh auth login

# Python dependencies (daemon)
pip3 install httpx python-dotenv rumps
```

## Setup

### 1. Create a GitHub repo for your workspace

This is the repo Claude Code will operate on. It can be an existing project or a new one.

```bash
# Option A: Use an existing repo
# Just note the owner/name, e.g. "youruser/my-project"

# Option B: Create a dedicated workspace repo
gh repo create my-claude-workspace --private
```

Create a `tasks/` directory with a `.gitkeep`:

```bash
cd my-claude-workspace
mkdir tasks
touch tasks/.gitkeep
git add tasks/.gitkeep && git commit -m "Add tasks directory" && git push
```

### 2. Clone the workspace (for the daemon)

The daemon needs a **separate clone** — not your working directory. This prevents Claude from accessing personal files.

```bash
gh repo clone youruser/my-project ~/claude-workspace
```

### 3. Create a GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. **Generate new token (classic)** with `repo` scope
3. Copy the token — you'll need it for both daemon and worker

### 4. Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name it (e.g., "Claude Code") and select your workspace

#### Bot Token Scopes

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Respond when @mentioned |
| `chat:write` | Post messages to channels |
| `commands` | Handle slash commands |
| `im:history` | Read DM history |
| `im:read` | Access DMs |
| `im:write` | Send DMs |

#### Event Subscriptions

Navigate to **Event Subscriptions**:

1. Toggle **Enable Events** to On
2. Set **Request URL** to: `https://your-railway-url.up.railway.app/slack/events`
   (You'll get this URL after deploying the worker — come back to this step)
3. Under **Subscribe to bot events**, add:
   - `app_mention`
   - `message.im`

#### Slash Commands

Navigate to **Slash Commands** and create one:

| Field | Value |
|-------|-------|
| Command | `/claude` (or whatever you prefer) |
| Request URL | `https://your-railway-url.up.railway.app/slack/events` |
| Description | Talk to Claude Code |
| Usage Hint | `[your question or command]` |

#### Install the App

1. Navigate to **Install App**
2. Click **Install to Workspace**
3. Copy the **Bot User OAuth Token** (`xoxb-...`)
4. Go to **Basic Information** and copy the **Signing Secret**

### 5. Deploy the Worker (Railway)

Railway is the easiest option, but any container host works (Fly.io, Render, etc.).

#### Option A: Railway (recommended)

1. Fork or push this repo to GitHub
2. Go to https://railway.app and create a new project
3. Select **Deploy from GitHub repo**
4. Set the **Root Directory** to `worker/`
5. Add environment variables:

| Variable | Value |
|----------|-------|
| `PORT` | `8080` |
| `GITHUB_TOKEN` | `ghp_...` (your PAT) |
| `GITHUB_REPO` | `youruser/your-repo` |
| `GITHUB_BRANCH` | `main` |
| `SLACK_BOT_TOKEN` | `xoxb-...` |
| `SLACK_SIGNING_SECRET` | From Slack app Basic Info |

6. Deploy. Copy the public URL (e.g., `https://your-app.up.railway.app`)
7. Go back to your Slack app settings and update the **Request URL** for both Events and Slash Commands to: `https://your-app.up.railway.app/slack/events`

#### Option B: Docker (self-hosted)

```bash
cd worker
docker build -t claude-code-slack-worker .
docker run -p 8080:8080 --env-file .env claude-code-slack-worker
```

### 6. Set Up the Local Daemon

```bash
cd daemon

# Create .env from template
cp .env.example .env

# Edit with your values
# IMPORTANT: Set WORKSPACE_DIR to the CLONED repo path, not your working directory
nano .env
```

#### Install as macOS LaunchAgent (recommended)

```bash
pip3 install -r requirements.txt
chmod +x install.sh start-daemon.sh
./install.sh
```

This will:
- Copy daemon files to `~/claude-code-slack/`
- Auto-detect Claude CLI and Node.js paths
- Generate LaunchAgent plists
- Start the daemon and status bar

#### Manual start (alternative)

```bash
# Must set PATH to include node
PATH="$(dirname $(which node)):$PATH" python3 main.py
```

### 7. Test It

1. Check the menu bar for a green circle (daemon running)
2. In Slack, type: `/claude what files do you see?`
3. You should get a response within 10-30 seconds

## Configuration Reference

### Daemon (.env)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` scope |
| `GITHUB_REPO` | Yes | — | `owner/repo` format |
| `GITHUB_BRANCH` | No | `main` | Branch to watch for tasks |
| `SLACK_BOT_TOKEN` | Yes | — | Slack bot token (`xoxb-...`) |
| `WORKSPACE_DIR` | Yes | — | Path to cloned repo |
| `CLAUDE_BIN` | No | `claude` | Full path to Claude CLI |
| `CLAUDE_TIMEOUT` | No | `300` | Max seconds per task |
| `POLL_INTERVAL` | No | `5` | Seconds between task checks |

### Worker (.env)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `8080` | Server port |
| `GITHUB_TOKEN` | Yes | — | Same PAT as daemon |
| `GITHUB_REPO` | Yes | — | Same repo as daemon |
| `GITHUB_BRANCH` | No | `main` | Same branch as daemon |
| `SLACK_BOT_TOKEN` | Yes | — | Same token as daemon |
| `SLACK_SIGNING_SECRET` | Yes | — | From Slack app settings |

## Troubleshooting

### Daemon won't start

| Symptom | Cause | Fix |
|---------|-------|-----|
| `env: node: No such file or directory` | PATH not set for LaunchAgent | Re-run `install.sh` — it auto-detects Node.js path |
| `Claude Code CLI not found` | `CLAUDE_BIN` not set or wrong path | Set full path: `which claude` |
| Menu bar shows red | Daemon process crashed | Check logs: `tail -f ~/Library/Logs/claude-code-slack-daemon.log` |
| Daemon starts then immediately exits | Missing or invalid `.env` | Verify all required vars are set in `~/claude-code-slack/.env` |

### Worker issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Slack says "dispatch_failed" | Worker URL wrong or not deployed | Verify Railway URL in Slack app settings |
| 401 on every request | Signing secret wrong | Copy signing secret from Slack > Basic Information |
| Railway deploy fails | Missing requirements | Check `worker/requirements.txt` is committed |
| Port conflict on Railway | PORT not set | Railway sets PORT automatically — ensure your code reads `os.getenv("PORT", 8080)` |

### Slack issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bot doesn't respond to @mentions | Missing `app_mentions:read` scope | Add scope, reinstall app |
| Bot doesn't respond in DMs | Missing `im:history` + `im:read` scopes | Add scopes, reinstall app |
| "not_in_channel" error | Bot not in the channel | Invite bot: `/invite @YourBot` |
| Slash command shows nothing | Worker not responding within 3s | Worker must send immediate acknowledgment |

### GitHub issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Tasks not picked up | Daemon not running or wrong repo | Check daemon logs and `GITHUB_REPO` in both `.env` files |
| Multiple responses | Multiple daemon processes running | Kill extras: `pkill -f "python3.*main.py"` |
| Git push fails | Clone is stale or has conflicts | Re-clone: `rm -rf ~/claude-workspace && gh repo clone ...` |
| 404 on task file | Task already deleted | Usually harmless — means another process handled it |

### macOS-specific

| Symptom | Cause | Fix |
|---------|-------|-----|
| LaunchAgent not starting after reboot | Plist not loaded | `launchctl load ~/Library/LaunchAgents/com.claude-code-slack.daemon.plist` |
| "Operation not permitted" | macOS privacy settings | System Preferences > Privacy > Full Disk Access > Terminal |
| Status bar icon missing | Statusbar LaunchAgent not loaded | Check: `launchctl list | grep claude-code-slack` |

## Managing the Daemon

```bash
# View logs
tail -f ~/Library/Logs/claude-code-slack-daemon.log

# Restart daemon
launchctl kickstart -k gui/$(id -u)/com.claude-code-slack.daemon

# Stop daemon
launchctl unload ~/Library/LaunchAgents/com.claude-code-slack.daemon.plist

# Start daemon
launchctl load ~/Library/LaunchAgents/com.claude-code-slack.daemon.plist

# Full uninstall
cd daemon && ./install.sh uninstall
```

## How Thread Context Works

When you reply in a Slack thread, the daemon fetches the full thread history and injects it as context for Claude. This means Claude "sees" the prior conversation:

```
User:  @Bot What does the auth module do?
Bot:   The auth module handles JWT token generation and validation...

User:  (in thread) Can you refactor it to use sessions instead?
Bot:   Based on our discussion about the auth module, here's how to
       refactor from JWT to sessions...
```

The context is reconstructed from Slack's API on each request — no local state needed.

## Security Considerations

- **Workspace isolation** — Always point `WORKSPACE_DIR` at a separate clone, not your working directory. This prevents Claude from accessing personal files, credentials, or other repos.
- **Slack signature verification** — The worker validates every request using Slack's HMAC-SHA256 signature. Never disable this in production.
- **GitHub token scope** — Use a fine-grained PAT scoped to only the repos you need.
- **No secrets in responses** — Be mindful that Claude's output is posted to Slack. If your codebase contains secrets, Claude might reference them. Use `.gitignore` and `.env` files properly.

## License

MIT

---

Built by [Alcanah Partners](https://alcanah.ai) — AI operations for growing businesses.
