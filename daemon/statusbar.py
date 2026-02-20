"""
Claude Code Slack — Menu Bar Status

Lightweight macOS menu bar app that shows whether the daemon is running.
Uses rumps for the menu bar integration.

Green circle = daemon running
Red circle = daemon stopped
"""

import os
import subprocess
import rumps

LOG_FILE = os.path.expanduser("~/Library/Logs/claude-code-slack-daemon.log")
PLIST_LABEL = "com.claude-code-slack.daemon"
POLL_SECONDS = 10


def get_daemon_pid():
    """Check if the daemon is running. Returns PID or None."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python3.*main\\.py"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split("\n")
        pids = [p for p in pids if p]
        return pids[0] if pids else None
    except Exception:
        return None


def get_last_log_line():
    """Get the last meaningful line from the daemon log."""
    if not os.path.exists(LOG_FILE):
        return "No log file found"
    try:
        result = subprocess.run(
            ["tail", "-1", LOG_FILE],
            capture_output=True, text=True, timeout=5,
        )
        line = result.stdout.strip()
        return line[:120] if line else "Log is empty"
    except Exception:
        return "Could not read log"


class StatusBarApp(rumps.App):
    def __init__(self):
        super().__init__("CCS", quit_button=None)
        self._dock_hidden = False
        self.pid = None
        self.update_status()

        # Menu items
        self.status_item = rumps.MenuItem("Checking...")
        self.log_item = rumps.MenuItem("Last log: ...")
        self.restart_item = rumps.MenuItem("Restart Daemon")
        self.logs_item = rumps.MenuItem("View Logs")
        self.quit_item = rumps.MenuItem("Quit")

        self.menu = [
            self.status_item,
            self.log_item,
            None,  # separator
            self.restart_item,
            self.logs_item,
            None,  # separator
            self.quit_item,
        ]

    def update_status(self):
        """Check daemon status and update the icon."""
        self.pid = get_daemon_pid()
        if self.pid:
            self.title = "\U0001F7E2"  # green circle
        else:
            self.title = "\U0001F534"  # red circle

    @rumps.timer(POLL_SECONDS)
    def poll(self, _):
        """Periodically check daemon status."""
        if not self._dock_hidden:
            try:
                from AppKit import NSApplication
                NSApplication.sharedApplication().setActivationPolicy_(1)
                self._dock_hidden = True
            except Exception:
                pass
        self.update_status()
        if self.pid:
            self.status_item.title = f"Running (PID {self.pid})"
        else:
            self.status_item.title = "Stopped"
        self.log_item.title = f"Log: {get_last_log_line()}"

    @rumps.clicked("Restart Daemon")
    def restart(self, _):
        """Restart the daemon via launchctl."""
        try:
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{PLIST_LABEL}"],
                capture_output=True, timeout=10,
            )
            rumps.notification(
                "Claude Code Slack", "", "Daemon restarted", sound=False
            )
        except Exception:
            plist_path = os.path.expanduser(
                f"~/Library/LaunchAgents/{PLIST_LABEL}.plist"
            )
            subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
            subprocess.run(["launchctl", "load", plist_path], capture_output=True)
            rumps.notification(
                "Claude Code Slack", "", "Daemon restarted (fallback)", sound=False
            )

    @rumps.clicked("View Logs")
    def view_logs(self, _):
        """Open the daemon log in Console.app."""
        subprocess.run(["open", "-a", "Console", LOG_FILE])

    @rumps.clicked("Quit")
    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    StatusBarApp().run()
