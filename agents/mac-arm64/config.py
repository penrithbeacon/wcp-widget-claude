"""
Configuration management for the WCP Claude Agent menu bar app.
Reads/writes ~/.penrith-beacon/claude-agent/config.json
"""

import json
import os

CONFIG_DIR = os.path.expanduser('~/.penrith-beacon/claude-agent')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
LOG_DIR = os.path.join(CONFIG_DIR, 'logs')

DEFAULT_CONFIG = {
    'port': 3747,
    'start_at_login': True,
}

PLIST_NAME = 'com.penrithbeacon.claude-agent'


def ensure_dirs():
    """Create config and log directories if they don't exist."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def load_config():
    """Load config from disk, returning defaults if file doesn't exist."""
    ensure_dirs()
    try:
        with open(CONFIG_FILE, 'r') as f:
            stored = json.load(f)
        return {**DEFAULT_CONFIG, **stored}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(config):
    """Write config to disk."""
    ensure_dirs()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_plist_path():
    """Return the path to the launchd plist for auto-start."""
    return os.path.expanduser(f'~/Library/LaunchAgents/{PLIST_NAME}.plist')


def get_app_path():
    """Return the installed .app path."""
    return '/Applications/WCP Claude Agent.app'
