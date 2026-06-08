#!/usr/bin/env python3
"""
WCP Claude Analytics — Host Agent (macOS Menu Bar Extra)

A menu bar app that runs the Claude Analytics host agent as a background service.
Provides a user-friendly interface for managing the agent: start/stop, change port,
view logs, auto-start on login, and uninstall.

The Flask server runs in a background thread, serving local Claude Code data
(MCP servers, plugins, sessions, system info) to the widget container.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time

import rumps

from config import (
    load_config, save_config, get_plist_path, get_app_path,
    PLIST_NAME, LOG_DIR, CONFIG_DIR
)

# ── Version ───────────────────────────────────────────────────────────────────

VERSION = '1.1.1'

# ── Flask server management ───────────────────────────────────────────────────

_server_thread = None
_server_running = False


def is_port_available(port):
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False


def start_flask(port):
    """Start the Flask agent server in a background thread."""
    global _server_thread, _server_running

    # Import here to avoid circular issues when packaged
    from agent import app as flask_app

    def run_server():
        global _server_running
        try:
            flask_app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
        except Exception:
            _server_running = False

    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()
    _server_running = True


def stop_flask():
    """Stop the Flask server (by terminating the thread on next request)."""
    global _server_running
    _server_running = False
    # Flask's dev server doesn't have a clean shutdown from another thread.
    # Since the thread is a daemon, it will die when the app exits.
    # For restart, we'll use os.execv to re-launch the entire process.


# ── Launchd management ────────────────────────────────────────────────────────

def is_login_item_installed():
    """Check if the launchd plist exists."""
    return os.path.isfile(get_plist_path())


def install_login_item(port):
    """Create a launchd plist for auto-start on login."""
    app_path = get_app_path()
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}/Contents/MacOS/WCP Claude Agent</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/stderr.log</string>
</dict>
</plist>
"""
    plist_path = get_plist_path()
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, 'w') as f:
        f.write(plist_content)


def remove_login_item():
    """Remove the launchd plist."""
    plist_path = get_plist_path()
    # Unload first
    subprocess.run(['launchctl', 'unload', plist_path],
                   capture_output=True, timeout=5)
    try:
        os.remove(plist_path)
    except FileNotFoundError:
        pass


# ── Uninstall ─────────────────────────────────────────────────────────────────

def perform_uninstall():
    """Remove all agent files, plists, and apps. Then quit."""
    # Stop the service
    remove_login_item()

    # Remove config and logs
    subprocess.run(['rm', '-rf', CONFIG_DIR], capture_output=True)

    # Remove the uninstaller app
    uninstaller_path = '/Applications/Uninstall WCP Claude Agent.app'
    if os.path.isdir(uninstaller_path):
        subprocess.run(
            ['osascript', '-e',
             f'do shell script "rm -rf \'{uninstaller_path}\'" with administrator privileges'],
            capture_output=True
        )

    # Remove this app (requires admin)
    app_path = get_app_path()
    if os.path.isdir(app_path):
        subprocess.run(
            ['osascript', '-e',
             f'do shell script "rm -rf \'{app_path}\'" with administrator privileges'],
            capture_output=True
        )

    # Forget package receipt
    subprocess.run(
        ['osascript', '-e',
         'do shell script "pkgutil --forget com.penrithbeacon.claude-agent 2>/dev/null || true" with administrator privileges'],
        capture_output=True
    )

    rumps.quit_application()


# ── Menu Bar App ──────────────────────────────────────────────────────────────

class WCPClaudeAgentApp(rumps.App):
    """macOS Menu Bar Extra for the WCP Claude Analytics host agent."""

    def __init__(self):
        super().__init__('WCP Agent', quit_button=None)
        self.config = load_config()
        self.port = self.config.get('port', 3747)
        self.agent_running = False
        self.port_error = False

        # Build initial menu
        self._build_menu()

        # Start the Flask server
        self._start_agent()

    def _build_menu(self):
        """Rebuild the menu items based on current state."""
        self.menu.clear()

        # Agent name label
        name_label = rumps.MenuItem('WCP Claude Agent', callback=None)
        self.menu.add(name_label)

        # Status line
        if self.port_error:
            status = rumps.MenuItem(f'● Port {self.port} unavailable', callback=None)
        elif self.agent_running:
            status = rumps.MenuItem(f'● Running on port {self.port}', callback=None)
        else:
            status = rumps.MenuItem('● Stopped', callback=None)
        self.menu.add(status)
        self.menu.add(rumps.separator)

        # Dynamic error row — only visible when there is an error
        if self.port_error:
            error_item = rumps.MenuItem(
                f'⚠ Port {self.port} is already in use — change port to resolve',
                callback=self._change_port
            )
            self.menu.add(error_item)
            self.menu.add(rumps.separator)

        # Actions
        self.menu.add(rumps.MenuItem('Change Port…', callback=self._change_port))
        self.menu.add(rumps.MenuItem('View Logs', callback=self._view_logs))
        self.menu.add(rumps.separator)

        if self.agent_running:
            self.menu.add(rumps.MenuItem('Restart Agent', callback=self._restart_agent))
            self.menu.add(rumps.MenuItem('Stop Agent', callback=self._stop_agent))
        else:
            self.menu.add(rumps.MenuItem('Start Agent', callback=self._start_agent_menu))
        self.menu.add(rumps.separator)

        # Start at Login toggle
        login_item = rumps.MenuItem('Start at Login', callback=self._toggle_login)
        login_item.state = is_login_item_installed()
        self.menu.add(login_item)
        self.menu.add(rumps.separator)

        # About, Uninstall, Quit
        self.menu.add(rumps.MenuItem('About', callback=self._about))
        self.menu.add(rumps.MenuItem('Uninstall…', callback=self._uninstall))
        self.menu.add(rumps.MenuItem('Quit', callback=self._quit))
        self.menu.add(rumps.separator)

        # Version (disabled)
        ver = rumps.MenuItem(f'v{VERSION}', callback=None)
        self.menu.add(ver)

        # Update icon and tooltip
        self._update_title_and_tooltip()

    def _update_title_and_tooltip(self):
        """Update the menu bar icon text and hover tooltip based on current state."""
        if self.port_error:
            self.title = '●!'
            tooltip = f'WCP Claude Agent — Port {self.port} unavailable'
        elif self.agent_running:
            self.title = '●'
            tooltip = f'WCP Claude Agent — Running'
        else:
            self.title = '○'
            tooltip = 'WCP Claude Agent — Stopped'

        # Set the native tooltip on the NSStatusItem button
        try:
            button = self._nsapp.nsstatusitem.button()
            button.setToolTip_(tooltip)
        except (AttributeError, TypeError):
            pass  # App not fully initialised yet; tooltip set on next _build_menu

    def _start_agent(self):
        """Start the Flask agent on the configured port."""
        if not is_port_available(self.port):
            self.port_error = True
            self.agent_running = False
            self._build_menu()
            return

        self.port_error = False
        start_flask(self.port)
        # Start session monitor (logs session activity to .md files)
        from agent import start_session_monitor
        start_session_monitor()
        self.agent_running = True
        self._build_menu()

    def _change_port(self, _):
        """Show dialog to change the agent port."""
        msg = 'Enter a new port number (1024–65535):'
        if self.port_error:
            msg = f'Port {self.port} is already in use.\n\n{msg}'

        w = rumps.Window(
            message=msg,
            title='Change Agent Port',
            default_text=str(self.port),
            ok='Save & Restart',
            cancel='Cancel',
            dimensions=(220, 24)
        )
        response = w.run()

        if response.clicked:
            text = response.text.strip()
            try:
                new_port = int(text)
                if new_port < 1024 or new_port > 65535:
                    raise ValueError
            except (ValueError, TypeError):
                rumps.alert(
                    title='Invalid Port',
                    message='Please enter a number between 1024 and 65535.'
                )
                return

            self.port = new_port
            self.config['port'] = new_port
            save_config(self.config)

            # Restart the app process to rebind the port
            self._do_restart()

    def _view_logs(self, _):
        """Open the logs directory in Finder."""
        os.makedirs(LOG_DIR, exist_ok=True)
        subprocess.run(['open', LOG_DIR])

    def _restart_agent(self, _):
        """Restart the agent process."""
        self._do_restart()

    def _stop_agent(self, _):
        """Stop the agent."""
        global _server_running
        _server_running = False
        self.agent_running = False
        self._build_menu()
        # Quit the app (launchd won't restart since KeepAlive is false)
        rumps.quit_application()

    def _start_agent_menu(self, _):
        """Start the agent from menu (when stopped)."""
        self._start_agent()

    def _toggle_login(self, sender):
        """Toggle auto-start on login."""
        if sender.state:
            remove_login_item()
            sender.state = False
            self.config['start_at_login'] = False
        else:
            install_login_item(self.port)
            sender.state = True
            self.config['start_at_login'] = True
        save_config(self.config)

    def _about(self, _):
        """Show about dialog."""
        rumps.alert(
            title='WCP Claude Agent',
            message=(
                f'Version {VERSION}\n\n'
                f'Host agent for the Claude Analytics WCP widget.\n'
                f'Provides local Claude Code data (MCP servers, plugins, sessions, system info).\n\n'
                f'Port: {self.port}\n'
                f'Config: ~/.penrith-beacon/claude-agent/\n\n'
                f'Part of Penrith Beacon — widgetcontextprotocol.com'
            )
        )

    def _uninstall(self, _):
        """Confirm and perform uninstall."""
        response = rumps.alert(
            title='Uninstall WCP Claude Agent',
            message=(
                'This will completely remove the WCP Claude Agent from your Mac.\n\n'
                'The following will be removed:\n'
                '• Agent service (stops immediately)\n'
                '• Application from /Applications\n'
                '• Configuration and logs\n'
                '• Uninstaller app\n\n'
                'This cannot be undone.'
            ),
            ok='Uninstall',
            cancel='Cancel'
        )
        if response == 1:  # OK/Uninstall clicked
            perform_uninstall()

    def _quit(self, _):
        """Quit the menu bar app (agent stops)."""
        rumps.quit_application()

    def _do_restart(self):
        """Restart the entire app process to rebind port."""
        app_path = get_app_path()
        # Launch a new instance after a short delay (gives this process time to quit)
        subprocess.Popen(
            ['bash', '-c', f'sleep 1 && open -a "{app_path}"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        rumps.quit_application()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = WCPClaudeAgentApp()
    app.run()
