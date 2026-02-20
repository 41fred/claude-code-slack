# Roadmap

What's planned for future versions of claude-code-slack.

## v1.0 (Current)

Single-user Slack bot that runs Claude Code in your workspace via a local daemon.

- [x] Slash commands and @mentions
- [x] Thread context injection
- [x] Markdown-to-Slack conversion
- [x] Auto-commit workspace changes
- [x] macOS LaunchAgent with auto-restart
- [x] Menu bar status indicator
- [x] Workspace isolation (separate clone)

---

## v1.1 — Quality of Life

Small improvements that make daily use smoother.

- [ ] **No-tag threads** — Once a thread is started with the bot, stop requiring @mention for follow-ups. The bot should auto-respond to all messages in threads it's participating in.
- [ ] **Typing indicator** — Post a "thinking..." message that gets replaced when Claude responds (Slack doesn't support typing indicators for bots, but a temporary message works).
- [ ] **Long response splitting** — Split responses over 4000 chars into multiple messages instead of truncating.
- [ ] **Secret redaction** — Scan Claude's output for patterns matching API keys, tokens, and credentials before posting to Slack. Redact them with `[REDACTED]`.
- [ ] **Configurable prompt prefix** — Let users customize the system prompt (e.g., "You are a code reviewer" vs "You are a DevOps assistant") via a config file in the repo.
- [ ] **Emoji reactions** — React with eyes emoji when task is picked up, checkmark when complete, X on error.

## v1.2 — Multi-Project Support

Run Claude across multiple repos from one Slack workspace.

- [ ] **Project registry** — YAML config mapping Slack channels (or thread topics) to repo paths. Messages in `#backend` route to the backend repo, `#frontend` to the frontend repo.
- [ ] **Channel-aware routing** — Daemon checks which channel a message came from and runs Claude in the corresponding workspace directory.
- [ ] **Project switching** — `/claude switch backend` to change the active project in DMs.
- [ ] **Per-project CLAUDE.md** — Each project gets its own system instructions, and Claude reads them automatically.

## v2.0 — Teams

Support multiple users with access controls and usage tracking.

- [ ] **User allowlist** — Only approved Slack user IDs can interact with the bot. Configurable via env var or config file.
- [ ] **Per-user rate limiting** — Token bucket rate limiter to prevent one person from monopolizing Claude. Configurable requests/minute per user.
- [ ] **Cost tracking** — Track Claude CLI usage time per user. Daily/weekly summary posted to an admin channel.
- [ ] **Spending limits** — Set a maximum daily/weekly compute budget per user. Bot stops responding when limit is hit.
- [ ] **Audit logging** — Log every request (who, when, what prompt, how long) to a file or SQLite database. Useful for compliance and debugging.
- [ ] **Admin commands** — `/claude-admin users` to list active users, `/claude-admin limit @user 10/hour` to set limits.

## v2.1 — Session Persistence

Maintain conversation context across bot restarts and long gaps.

- [ ] **SQLite session storage** — Persist session IDs, conversation history, and metadata. Survive daemon restarts without losing context.
- [ ] **Session resume** — When a user messages in a thread the bot previously responded in, resume the Claude session with full context (not just Slack thread history).
- [ ] **Session export** — `/claude export` to get the full conversation as Markdown, JSON, or HTML.
- [ ] **Session cost summary** — Show total cost/time for a session: "This conversation used 3m 42s of Claude time across 7 messages."

## v2.2 — Event-Driven Automation

React to external events, not just Slack messages.

- [ ] **GitHub webhook handler** — Receive GitHub webhook events (PR opened, issue created, push to main) and trigger Claude tasks automatically.
- [ ] **Auto PR review** — When a PR is opened, Claude reviews the diff and posts comments. Configurable: all PRs, only PRs with a label, or only when @mentioned.
- [ ] **Scheduled tasks** — Cron-style recurring Claude tasks: "Every Monday at 9am, summarize what changed last week."
- [ ] **Event bus** — Internal async event system that decouples event sources (webhooks, scheduler, Slack) from task execution. Makes it easy to add new triggers.

## v2.3 — Better UX

Polish the Slack interaction experience.

- [ ] **Inline keyboards** — Slack Block Kit buttons for common actions: "Run Tests", "Git Status", "View Diff". Appear after each response.
- [ ] **File uploads** — Upload images or files to Slack, bot analyzes them. Screenshots for UI review, CSVs for data analysis.
- [ ] **Verbosity control** — `/claude verbose 0|1|2` to control how much tool-use detail is shown. 0 = final answer only, 1 = tool names, 2 = full tool inputs.
- [ ] **Streaming updates** — Show real-time progress as Claude works: "Reading config.py...", "Running tests...", "Writing response..."

## v3.0 — Cloud Daemon (Optional)

For teams that don't want to run a local daemon.

- [ ] **Cloud execution** — Run Claude via the Anthropic API instead of the local CLI. No local machine needed.
- [ ] **Stateless workers** — Daemon and worker merge into a single cloud service. GitHub repo is cloned on-demand for each task.
- [ ] **Linux support** — systemd unit files for running on Linux VPS/servers.
- [ ] **Docker Compose** — Single `docker-compose up` to run both worker and daemon.

---

## Contributing

If you build any of these features, PRs are welcome. Start with the v1.1 items — they're the quickest wins.

## Inspiration

- [claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram) — Full-featured Telegram bot with session persistence, event bus, and multi-user support. Many v2.0+ ideas on this roadmap are inspired by their implementation.
