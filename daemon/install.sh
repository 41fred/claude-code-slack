#!/bin/bash
# Install/uninstall the claude-code-slack daemon as a macOS LaunchAgent.
#
# The daemon scripts are copied to ~/claude-code-slack/ and LaunchAgents
# reference that local path. This avoids issues with iCloud Drive or
# other synced directories that launchctl can't access.
#
# Usage:
#   ./install.sh           Install and start the daemon + status bar
#   ./install.sh uninstall Uninstall and stop both

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_DIR="$HOME/claude-code-slack"
DAEMON_LABEL="com.claude-code-slack.daemon"
STATUSBAR_LABEL="com.claude-code-slack.statusbar"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

# Files to copy to the local runtime directory
RUNTIME_FILES="main.py config.py statusbar.py start-daemon.sh .env requirements.txt"

# Auto-detect paths
detect_paths() {
    # Find Claude CLI
    CLAUDE_PATH=$(which claude 2>/dev/null || echo "")
    if [ -z "$CLAUDE_PATH" ]; then
        # Check common nvm locations
        for dir in "$HOME/.nvm/versions/node"/*/bin; do
            if [ -f "$dir/claude" ]; then
                CLAUDE_PATH="$dir/claude"
                break
            fi
        done
    fi

    # Find Node.js directory (needed for PATH in plist)
    NODE_DIR=$(dirname "$(which node 2>/dev/null || echo "")" 2>/dev/null || echo "")

    # Find Python3
    PYTHON3_PATH=$(which python3 2>/dev/null || echo "/usr/bin/python3")

    echo "  Detected paths:"
    echo "    Claude CLI: ${CLAUDE_PATH:-NOT FOUND}"
    echo "    Node dir:   ${NODE_DIR:-NOT FOUND}"
    echo "    Python3:    $PYTHON3_PATH"
}

generate_plist() {
    local label="$1"
    local program="$2"
    local working_dir="$3"
    local log_file="$4"
    local interpreter="${5:-}"

    local path_value="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    if [ -n "$NODE_DIR" ]; then
        path_value="$NODE_DIR:$path_value"
    fi

    local program_args=""
    if [ -n "$interpreter" ]; then
        program_args="        <string>$interpreter</string>
        <string>$program</string>"
    else
        program_args="        <string>/bin/bash</string>
        <string>$program</string>"
    fi

    cat > "$LAUNCH_AGENTS_DIR/$label.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>

    <key>ProgramArguments</key>
    <array>
$program_args
    </array>

    <key>WorkingDirectory</key>
    <string>$working_dir</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$path_value</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$log_file</string>

    <key>StandardErrorPath</key>
    <string>$log_file</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST
}

generate_start_script() {
    local path_value="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    if [ -n "$NODE_DIR" ]; then
        path_value="$NODE_DIR:$path_value"
    fi

    cat > "$LOCAL_DIR/start-daemon.sh" << SCRIPT
#!/bin/bash
# Daemon startup script — sets PATH before running

cd "\$(dirname "\$0")"

export PATH="$path_value"

# Ensure the workspace clone exists
WORKSPACE_DIR=\$(grep -E '^WORKSPACE_DIR=' .env 2>/dev/null | cut -d= -f2-)
GITHUB_REPO=\$(grep -E '^GITHUB_REPO=' .env 2>/dev/null | cut -d= -f2-)

if [ -n "\$WORKSPACE_DIR" ] && [ ! -d "\$WORKSPACE_DIR/.git" ]; then
    echo "Workspace clone missing, attempting re-clone..."
    if command -v gh &>/dev/null && [ -n "\$GITHUB_REPO" ]; then
        gh repo clone "\$GITHUB_REPO" "\$WORKSPACE_DIR"
    else
        echo "ERROR: Cannot clone — install gh CLI or clone manually"
        echo "  gh repo clone \$GITHUB_REPO \$WORKSPACE_DIR"
    fi
fi

exec python3 main.py
SCRIPT
    chmod +x "$LOCAL_DIR/start-daemon.sh"
}

install() {
    echo "Installing claude-code-slack..."
    echo ""

    detect_paths

    if [ -z "$CLAUDE_PATH" ]; then
        echo ""
        echo "  WARNING: Claude CLI not found in PATH."
        echo "  Make sure CLAUDE_BIN is set correctly in daemon/.env"
        echo ""
    fi

    # Copy daemon scripts to local directory
    mkdir -p "$LOCAL_DIR"
    for f in $RUNTIME_FILES; do
        if [ -f "$SCRIPT_DIR/$f" ]; then
            cp "$SCRIPT_DIR/$f" "$LOCAL_DIR/$f"
        fi
    done
    echo ""
    echo "  Copied runtime files to $LOCAL_DIR"

    # Generate start script with detected paths
    generate_start_script
    echo "  Generated start-daemon.sh"

    # Generate and install plists
    mkdir -p "$LAUNCH_AGENTS_DIR"

    generate_plist "$DAEMON_LABEL" \
        "$LOCAL_DIR/start-daemon.sh" \
        "$LOCAL_DIR" \
        "$HOME/Library/Logs/claude-code-slack-daemon.log"
    echo "  Generated $DAEMON_LABEL.plist"

    generate_plist "$STATUSBAR_LABEL" \
        "$LOCAL_DIR/statusbar.py" \
        "$LOCAL_DIR" \
        "$HOME/Library/Logs/claude-code-slack-statusbar.log" \
        "$PYTHON3_PATH"
    echo "  Generated $STATUSBAR_LABEL.plist"

    # Kill any existing processes
    pkill -f "python3.*claude-code-slack.*main\.py" 2>/dev/null || true
    pkill -f "python3.*claude-code-slack.*statusbar\.py" 2>/dev/null || true
    sleep 1

    # Load agents
    launchctl load "$LAUNCH_AGENTS_DIR/$DAEMON_LABEL.plist" 2>/dev/null || true
    echo "  Loaded $DAEMON_LABEL"
    launchctl load "$LAUNCH_AGENTS_DIR/$STATUSBAR_LABEL.plist" 2>/dev/null || true
    echo "  Loaded $STATUSBAR_LABEL"

    echo ""
    echo "Done! Next steps:"
    echo "  1. Edit $LOCAL_DIR/.env with your credentials"
    echo "  2. Restart: launchctl kickstart -k gui/\$(id -u)/$DAEMON_LABEL"
    echo ""
    echo "Check status:"
    echo "  Daemon log: tail -f ~/Library/Logs/claude-code-slack-daemon.log"
    echo "  Menu bar:   Look for green/red circle"
}

uninstall() {
    echo "Uninstalling claude-code-slack..."

    for label in "$DAEMON_LABEL" "$STATUSBAR_LABEL"; do
        if [ -f "$LAUNCH_AGENTS_DIR/$label.plist" ]; then
            launchctl unload "$LAUNCH_AGENTS_DIR/$label.plist" 2>/dev/null || true
            rm "$LAUNCH_AGENTS_DIR/$label.plist"
            echo "  Removed $label"
        fi
    done

    if [ -d "$LOCAL_DIR" ]; then
        echo "  Note: $LOCAL_DIR still exists. Remove manually if desired:"
        echo "    rm -rf $LOCAL_DIR"
    fi

    echo "Done."
}

case "${1:-install}" in
    install)   install ;;
    uninstall) uninstall ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        exit 1
        ;;
esac
