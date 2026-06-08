#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# WCP Claude Agent — Build macOS Menu Bar App + .pkg Installer
#
# Steps:
#   1. Create venv, install dependencies
#   2. Build .app with py2app
#   3. Build Uninstall .app
#   4. Wrap both in a .pkg installer
#
# Output: WCP-Claude-Agent.pkg
# Requires: macOS, Python 3.9+, Xcode Command Line Tools
# ──────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="/tmp/wcp-claude-agent-build"
DIST_DIR="/tmp/wcp-claude-agent-dist"
VENV_DIR="/tmp/wcp-claude-agent-venv"
PKG_BUILD_DIR="${BUILD_DIR}/pkg-payload"
PKG_ID="com.penrithbeacon.claude-agent"
PKG_VERSION="1.1.1"
OUTPUT="${SCRIPT_DIR}/WCP-Claude-Agent.pkg"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  WCP Claude Agent — Build                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Clean ─────────────────────────────────────────────────────────────────────

echo "→ Cleaning previous builds…"
rm -rf "$BUILD_DIR" "$DIST_DIR" "$OUTPUT"

# ── Create venv and install deps ──────────────────────────────────────────────

echo "→ Creating build environment…"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip setuptools
pip install --quiet flask rumps py2app

# ── Build .app with py2app ────────────────────────────────────────────────────

echo "→ Building WCP Claude Agent.app…"
cd "$SCRIPT_DIR"
python setup.py py2app --dist-dir "$DIST_DIR" 2>&1 | grep -v "^$" | tail -5

APP_PATH="$DIST_DIR/WCP Claude Agent.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: py2app build failed — .app not found"
    exit 1
fi
echo "  Built: $APP_PATH"

# ── Build Uninstall .app ──────────────────────────────────────────────────────

echo "→ Building Uninstall app…"
UNINSTALL_APP="$DIST_DIR/Uninstall WCP Claude Agent.app"
mkdir -p "$UNINSTALL_APP/Contents/MacOS"
mkdir -p "$UNINSTALL_APP/Contents/Resources"

cat > "$UNINSTALL_APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>uninstall</string>
    <key>CFBundleIdentifier</key>
    <string>com.penrithbeacon.claude-agent-uninstaller</string>
    <key>CFBundleName</key>
    <string>Uninstall WCP Claude Agent</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$UNINSTALL_APP/Contents/MacOS/uninstall" << 'SCRIPT'
#!/bin/bash
PLIST_NAME="com.penrithbeacon.claude-agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
APP_PATH="/Applications/WCP Claude Agent.app"
UNINSTALL_PATH="/Applications/Uninstall WCP Claude Agent.app"
CONFIG_DIR="$HOME/.penrith-beacon/claude-agent"

RESPONSE=$(osascript -e 'display dialog "This will completely remove the WCP Claude Agent from your Mac.\n\nThe following will be removed:\n• Agent service (stops immediately)\n• WCP Claude Agent app\n• Configuration and logs\n• This uninstaller" with title "Uninstall WCP Claude Agent" buttons {"Cancel", "Uninstall"} default button "Cancel" with icon caution')

if [[ "$RESPONSE" != *"Uninstall"* ]]; then exit 0; fi

# Stop service
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi
rm -f "$PLIST_PATH" 2>/dev/null

# Kill running agent
pkill -f "WCP Claude Agent" 2>/dev/null || true

# Remove files (admin required for /Applications)
osascript -e "do shell script \"rm -rf '$APP_PATH' '$UNINSTALL_PATH'\" with administrator privileges" 2>/dev/null

# Remove config/logs
rm -rf "$CONFIG_DIR" 2>/dev/null
[ -d "$HOME/.penrith-beacon" ] && [ -z "$(ls -A "$HOME/.penrith-beacon")" ] && rmdir "$HOME/.penrith-beacon"

# Forget receipt
osascript -e 'do shell script "pkgutil --forget com.penrithbeacon.claude-agent 2>/dev/null || true" with administrator privileges' 2>/dev/null

osascript -e 'display dialog "The WCP Claude Agent has been completely removed from your Mac." with title "Uninstall Complete" buttons {"OK"} default button "OK" with icon note'
SCRIPT

chmod +x "$UNINSTALL_APP/Contents/MacOS/uninstall"
echo "  Built: $UNINSTALL_APP"

# ── Assemble .pkg payload ─────────────────────────────────────────────────────

echo "→ Assembling installer payload…"
mkdir -p "$PKG_BUILD_DIR/Applications"
cp -R "$APP_PATH" "$PKG_BUILD_DIR/Applications/"
cp -R "$UNINSTALL_APP" "$PKG_BUILD_DIR/Applications/"

# ── Build .pkg ────────────────────────────────────────────────────────────────

echo "→ Building .pkg installer…"
chmod +x "${SCRIPT_DIR}/pkg/scripts/preinstall"
chmod +x "${SCRIPT_DIR}/pkg/scripts/postinstall"

COMPONENT_PKG="${BUILD_DIR}/claude-agent.pkg"
pkgbuild \
    --root "$PKG_BUILD_DIR" \
    --identifier "$PKG_ID" \
    --version "$PKG_VERSION" \
    --install-location "/" \
    --scripts "${SCRIPT_DIR}/pkg/scripts" \
    "$COMPONENT_PKG"

productbuild \
    --distribution "${SCRIPT_DIR}/pkg/distribution.xml" \
    --resources "${SCRIPT_DIR}/pkg/resources" \
    --package-path "$BUILD_DIR" \
    "$OUTPUT"

# ── Clean up build artifacts ──────────────────────────────────────────────────

deactivate 2>/dev/null || true
rm -rf "$BUILD_DIR" "$DIST_DIR" "$VENV_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✓ Built: WCP-Claude-Agent.pkg                              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Size: $(du -h "$OUTPUT" | cut -f1)                                              ║"
echo "║  Test: open WCP-Claude-Agent.pkg                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
