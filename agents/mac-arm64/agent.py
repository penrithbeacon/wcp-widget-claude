#!/usr/bin/env python3
"""
WCP Claude Analytics — Host Agent (macOS, Apple Silicon)

Lightweight Flask app that runs natively on the host machine (not in Docker).
Provides local Claude Code data to the Claude Analytics widget container.

Endpoints:
  GET /health   — agent status check
  GET /mcp      — configured MCP servers
  GET /plugins  — installed plugins
  GET /sessions — recent Claude Code sessions (last 10)
  GET /system   — system info (CLI version, Node, platform, memory, uptime)

Port: 3747 (default)
Security: Listens on 127.0.0.1 only — not accessible from the network.
The widget container reaches it via Docker's host.docker.internal.

Install: ./install.sh (sets up launchd for auto-start)
"""

import json
import os
import platform
import subprocess
import time
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AGENT_PORT = int(os.environ.get('CLAUDE_AGENT_PORT', '3747'))
HOME = Path.home()
CLAUDE_DIR = HOME / '.claude'

# ── Helpers ────────────────────────────────��──────────────────────────────────

def _run(cmd, timeout=5):
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _read_json(path):
    """Read and parse a JSON file, returning None on failure."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _format_bytes(b):
    """Format bytes as human-readable string."""
    if b >= 1e9:
        return f'{b / 1e9:.1f} GB'
    if b >= 1e6:
        return f'{b / 1e6:.0f} MB'
    return f'{b / 1e3:.0f} KB'


def _format_uptime(seconds):
    """Format seconds into human-readable uptime."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    if days > 0:
        return f'{days}d {hours}h'
    mins = int((seconds % 3600) // 60)
    return f'{hours}h {mins}m'


# ── CORS ──────────────────────────��───────────────────────────────────────────

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


# ── Endpoints ───────────────────────���─────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'success': True, 'status': 'ok', 'agent': 'wcp-claude-agent', 'version': '1.0.0'})


@app.route('/mcp')
def mcp_servers():
    """Read MCP server configuration from Claude's settings files."""
    servers = []

    # Check multiple config locations where MCP servers can be defined
    config_paths = [
        CLAUDE_DIR / 'settings.json',
        CLAUDE_DIR / 'settings.local.json',
        HOME / '.config' / 'claude' / 'settings.json',
    ]

    # Also check project-level .claude/settings.json in common dev dirs
    seen_names = set()

    for config_path in config_paths:
        data = _read_json(config_path)
        if not data:
            continue

        mcp_config = data.get('mcpServers', {})
        for name, cfg in mcp_config.items():
            if name in seen_names:
                continue
            seen_names.add(name)

            transport = 'stdio'
            if 'url' in cfg:
                transport = 'sse'
            elif cfg.get('type'):
                transport = cfg['type']

            servers.append({
                'name': name,
                'type': transport,
                'command': cfg.get('command', ''),
                'status': 'configured',  # We can't easily check if running
            })

    return jsonify({'success': True, 'data': {'servers': servers}})


@app.route('/plugins')
def plugins():
    """Read installed plugins from Claude's plugin directories."""
    plugin_list = []

    # Check the plugins cache directory
    plugins_dir = CLAUDE_DIR / 'plugins' / 'cache'
    if plugins_dir.is_dir():
        for org_dir in sorted(plugins_dir.iterdir()):
            if not org_dir.is_dir():
                continue
            for plugin_dir in sorted(org_dir.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                # Each plugin has version subdirectories
                versions = sorted(plugin_dir.iterdir(), reverse=True)
                for ver_dir in versions:
                    if not ver_dir.is_dir():
                        continue
                    manifest = _read_json(ver_dir / 'manifest.json')
                    if manifest:
                        plugin_list.append({
                            'name': manifest.get('name', plugin_dir.name),
                            'version': manifest.get('version', ver_dir.name),
                            'description': manifest.get('description', ''),
                            'enabled': True,
                        })
                        break  # Only latest version
                    else:
                        # No manifest — infer from directory name
                        plugin_list.append({
                            'name': plugin_dir.name,
                            'version': ver_dir.name,
                            'description': '',
                            'enabled': True,
                        })
                        break

    return jsonify({'success': True, 'data': {'plugins': plugin_list}})


@app.route('/sessions')
def sessions():
    """Read recent Claude Code sessions (last 10 by modification time)."""
    session_list = []

    # Claude Code stores sessions in ~/.claude/projects/
    projects_dir = CLAUDE_DIR / 'projects'
    if not projects_dir.is_dir():
        return jsonify({'success': True, 'data': {'sessions': []}})

    # Collect all .jsonl session files across project directories
    session_files = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            if f.suffix == '.jsonl' and f.is_file():
                session_files.append((f, f.stat().st_mtime))

    # Sort by modification time, take last 10
    session_files.sort(key=lambda x: x[1], reverse=True)
    session_files = session_files[:10]

    for filepath, mtime in session_files:
        # Try to extract working directory from project dir name
        project_name = filepath.parent.name
        # Project dirs are named like "-Users-dev-myproject" (path with dashes)
        cwd = project_name.replace('-', '/', 1) if project_name.startswith('-') else project_name
        # Fix remaining dashes that were path separators
        if cwd.startswith('/'):
            # It's an encoded absolute path: "-Users-dev-project" → "/Users/dev/project"
            parts = project_name.split('-')
            # Reconstruct: first empty string (leading dash), then path components
            # Heuristic: rejoin with / since we know it started with /
            cwd = '/' + '/'.join(parts[1:]) if parts[0] == '' else project_name

        session_list.append({
            'id': filepath.stem,
            'cwd': cwd,
            'working_directory': cwd,
            'modified': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mtime)),
            'kind': 'code',
        })

    return jsonify({'success': True, 'data': {'sessions': session_list}})


@app.route('/system')
def system_info():
    """Gather system information."""
    # Claude CLI version
    claude_ver = _run('claude --version') or 'Not installed'

    # Node version
    node_ver = _run('node --version') or 'Not installed'

    # Platform
    arch = platform.machine()
    plat = f'macOS {platform.mac_ver()[0]} ({arch})'

    # Hostname
    hostname = platform.node()

    # Memory
    try:
        import psutil
        mem = psutil.virtual_memory()
        memory = f'{_format_bytes(mem.available)} free / {_format_bytes(mem.total)}'
    except ImportError:
        # Fallback: use sysctl on macOS
        total_raw = _run('sysctl -n hw.memsize')
        if total_raw:
            total = int(total_raw)
            # Get free pages from vm_stat
            vm_stat = _run('vm_stat')
            free = 0
            if vm_stat:
                for line in vm_stat.split('\n'):
                    if 'Pages free' in line:
                        free = int(line.split(':')[1].strip().rstrip('.')) * 4096
                        break
            memory = f'{_format_bytes(free)} free / {_format_bytes(total)}'
        else:
            memory = 'N/A'

    # Uptime
    uptime_raw = _run('sysctl -n kern.boottime')
    uptime = 'N/A'
    if uptime_raw:
        try:
            # Format: { sec = 1234567890, usec = 0 } ...
            sec_str = uptime_raw.split('sec = ')[1].split(',')[0]
            boot_time = int(sec_str)
            uptime = _format_uptime(time.time() - boot_time)
        except (IndexError, ValueError):
            pass

    return jsonify({
        'success': True,
        'data': {
            'claude_version': claude_ver,
            'node_version': node_ver,
            'platform': plat,
            'hostname': hostname,
            'memory': memory,
            'uptime': uptime,
        }
    })


# ── Run ──────────────────────────────────��────────────────────────────────────

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=AGENT_PORT, debug=False)
