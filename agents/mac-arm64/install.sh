#!/bin/bash
# ──────────────────────────���────────────────────────���──────────────────────────
# WCP Claude Analytics — Host Agent Installer (macOS, Apple Silicon)
#
# What this script does:
#   1. Copies the agent to ~/.penrith-beacon/claude-agent/
#   2. Creates a Python virtual environment with Flask
#   3. Installs a launchd plist for auto-start on login
#   4. Starts the agent immediately
#
# The agent runs on 127.0.0.1:3747 (localhost only — not network-accessible).
# The widget container reaches it via Docker's host.docker.internal.
#
# To uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.penrithbeacon.claude-agent.plist
#   rm ~/Library/LaunchAgents/com.penrithbeacon.claude-agent.plist
#   rm -rf ~/.penrith-beacon/claude-agent
# ──────────────────────────────────────────────────────────────────────────────

set -e

AGENT_DIR="$HOME/.penrith-beacon/claude-agent"
PLIST_NAME="com.penrithbeacon.claude-agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
AGENT_PORT="${CLAUDE_AGENT_PORT:-3747}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔═════════════════════════════════════════════���════════════════╗"
echo "║  WCP Claude Analytics — Host Agent Installer                 ║"
echo "╚═══════════════════════��═══════════════════════════════���══════╝"
echo ""

# ── Stop existing agent if running ──────────────────────��─────────────────────

if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    echo "→ Stopping existing agent…"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# ── Copy agent files ──────────────────────────────────────────────────────��───

echo "→ Installing agent to $AGENT_DIR"
mkdir -p "$AGENT_DIR"
cp "$SCRIPT_DIR/agent.py" "$AGENT_DIR/agent.py"
cp "$SCRIPT_DIR/requirements.txt" "$AGENT_DIR/requirements.txt" 2>/dev/null || true

# ── Create virtual environment ───────────────��────────────────────────────────

echo "→ Setting up Python environment…"
if [ ! -d "$AGENT_DIR/venv" ]; then
    python3 -m venv "$AGENT_DIR/venv"
fi
"$AGENT_DIR/venv/bin/pip" install --quiet --upgrade pip
"$AGENT_DIR/venv/bin/pip" install --quiet flask

# ── Create launchd plist ──────────────────────────────────────────────────────

echo "→ Installing launchd service…"
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$AGENT_DIR/logs"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${AGENT_DIR}/venv/bin/python3</string>
        <string>${AGENT_DIR}/agent.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CLAUDE_AGENT_PORT</key>
        <string>${AGENT_PORT}</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${AGENT_DIR}/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${AGENT_DIR}/logs/stderr.log</string>
    <key>WorkingDirectory</key>
    <string>${AGENT_DIR}</string>
</dict>
</plist>
EOF

# ── Start the agent ────────────────────���──────────────────────────────���───────

echo "→ Starting agent on port ${AGENT_PORT}…"
launchctl load "$PLIST_PATH"

# Wait briefly and verify
sleep 2
if curl -s "http://127.0.0.1:${AGENT_PORT}/health" | grep -q '"success"' 2>/dev/null; then
    echo ""
    echo "╔══════════════════��═══════════════════════════════════════════╗"
    echo "║  ✓ Agent installed and running on port ${AGENT_PORT}              ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  The agent starts automatically on login.                    ║"
    echo "║  Logs: ~/.penrith-beacon/claude-agent/logs/                  ║"
    echo "║                                                              ║"
    echo "║  Test: curl http://localhost:${AGENT_PORT}/health                  ║"
    echo "╚════════════════════════════════════════════════════��═════════╝"
else
    echo ""
    echo "⚠  Agent may not have started. Check logs:"
    echo "   cat $AGENT_DIR/logs/stderr.log"
    echo ""
    echo "   You can also start manually:"
    echo "   $AGENT_DIR/venv/bin/python3 $AGENT_DIR/agent.py"
fi
