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

import glob
import json
import logging
import os
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AGENT_PORT = int(os.environ.get('CLAUDE_AGENT_PORT', '3747'))
HOME = Path.home()
CLAUDE_DIR = HOME / '.claude'
LOG_DIR = HOME / '.penrith-beacon' / 'claude-agent' / 'logs'
SESSIONS_LOG_DIR = LOG_DIR / 'sessions'
MAX_LOG_SIZE = 50 * 1024  # 50 KB per log file — keeps them quick to load
MAX_LOG_FILES = 100       # per log type — old ones get rotated out

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


def _decode_project_dir(name):
    """Decode a Claude project directory name back to a filesystem path.

    Claude encodes paths as: /Volumes/dashboard → -Volumes-dashboard
    We try progressively building the path, checking which directories exist,
    to handle cases where directory names contain literal dashes.
    Falls back to simple replacement if no path can be verified.
    """
    if not name.startswith('-'):
        return name

    # Simple approach: replace all - with /
    simple = '/' + name[1:].replace('-', '/')

    # Try to verify by walking segments and checking existence
    segments = name[1:].split('-')
    if not segments:
        return simple

    # Greedy: try to match the longest existing path segments
    best_path = '/'
    i = 0
    while i < len(segments):
        # Try accumulating segments with dashes (for dirs with dashes in names)
        found = False
        for j in range(len(segments), i, -1):
            candidate_segment = '-'.join(segments[i:j])
            candidate_path = os.path.join(best_path, candidate_segment)
            if os.path.isdir(candidate_path):
                best_path = candidate_path
                i = j
                found = True
                break
        if not found:
            # No existing dir found — append remaining as /-separated
            remaining = '/'.join(segments[i:])
            best_path = os.path.join(best_path, remaining)
            break

    # If we verified at least some of the path, use it; otherwise fallback
    return best_path if best_path != '/' else simple


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
        # Claude encodes project paths by replacing / with -
        # e.g. "/Volumes/dashboard" → "-Volumes-dashboard"
        project_name = filepath.parent.name
        cwd = _decode_project_dir(project_name)

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
    # Claude CLI version — check common install locations
    claude_ver = (
        _run('claude --version') or
        _run(os.path.expanduser('~/.local/bin/claude') + ' --version') or
        _run('/usr/local/bin/claude --version') or
        'Not installed'
    )

    # Node version
    node_ver = (
        _run('node --version') or
        _run('/usr/local/bin/node --version') or
        _run('/opt/homebrew/bin/node --version') or
        'Not installed'
    )

    # Platform
    arch = platform.machine()
    plat = f'macOS {platform.mac_ver()[0]} ({arch})'

    # Hostname — use ComputerName (user-friendly) rather than platform.node()
    hostname = _run('scutil --get ComputerName') or platform.node()

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


# ── Session Monitor ──────────────────────────────────────────────────────────

_session_monitor_known = set()


def _get_current_log_path():
    """Get the current session log file path, rotating if too large."""
    SESSIONS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Current log is the most recently named file
    existing = sorted(SESSIONS_LOG_DIR.glob('sessions-*.md'), reverse=True)
    if existing:
        latest = existing[0]
        if latest.stat().st_size < MAX_LOG_SIZE:
            return latest
    # Create new log file
    ts = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    return SESSIONS_LOG_DIR / f'sessions-{ts}.md'


def _log_session(session_id, cwd, modified):
    """Append a session entry to the current log file."""
    log_path = _get_current_log_path()
    is_new = not log_path.exists()
    with open(log_path, 'a', encoding='utf-8') as f:
        if is_new:
            f.write(f'# Claude Code Sessions Log\n\n')
            f.write(f'*Agent: WCP Claude Analytics | Started: {datetime.now().strftime("%Y-%m-%d %H:%M")}*\n\n')
            f.write('---\n\n')
        f.write(f'## {modified}\n\n')
        f.write(f'- **Path:** `{cwd}`\n')
        f.write(f'- **Session:** `{session_id}`\n\n')
    # Prune old log files
    existing = sorted(SESSIONS_LOG_DIR.glob('sessions-*.md'), reverse=True)
    for old in existing[MAX_LOG_FILES:]:
        old.unlink(missing_ok=True)


def _scan_sessions():
    """Scan for new/updated sessions and log them."""
    projects_dir = CLAUDE_DIR / 'projects'
    if not projects_dir.is_dir():
        return
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            if f.suffix != '.jsonl' or not f.is_file():
                continue
            key = str(f)
            mtime = f.stat().st_mtime
            entry = f'{key}:{mtime}'
            if entry not in _session_monitor_known:
                if _session_monitor_known:  # Skip initial scan (don't log everything)
                    cwd = _decode_project_dir(project_dir.name)
                    mod_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    _log_session(f.stem, cwd, mod_str)
                _session_monitor_known.add(entry)


def _session_monitor_loop():
    """Background thread: scans for session changes every 30 seconds."""
    while True:
        try:
            _scan_sessions()
        except Exception:
            pass
        time.sleep(30)


def start_session_monitor():
    """Start the background session monitor thread."""
    t = threading.Thread(target=_session_monitor_loop, daemon=True)
    t.start()


# ── Log Endpoints ────────────────────────────────────────────────────────────

LOG_TYPES = {
    'sessions': {'dir': 'sessions', 'pattern': 'sessions-*.md', 'label': 'Sessions'},
}


@app.route('/logs/list')
def logs_list():
    """List available log files, optionally filtered by type."""
    log_type = request.args.get('type', 'sessions')
    if log_type not in LOG_TYPES:
        return jsonify({'success': False, 'error': f'Unknown log type: {log_type}'})

    info = LOG_TYPES[log_type]
    log_dir = LOG_DIR / info['dir']
    files = []

    if log_dir.is_dir():
        for f in sorted(log_dir.glob(info['pattern']), reverse=True):
            stat = f.stat()
            files.append({
                'name': f.name,
                'type': log_type,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'size_label': _format_bytes(stat.st_size),
            })

    return jsonify({
        'success': True,
        'data': {
            'type': log_type,
            'types': [{'id': k, 'label': v['label']} for k, v in LOG_TYPES.items()],
            'files': files,
        }
    })


@app.route('/logs/read')
def logs_read():
    """Read contents of a specific log file."""
    log_type = request.args.get('type', 'sessions')
    name = request.args.get('name', '')

    if log_type not in LOG_TYPES:
        return jsonify({'success': False, 'error': f'Unknown log type'})

    # Sanitise filename — prevent path traversal
    if not name or '/' in name or '\\' in name or '..' in name:
        return jsonify({'success': False, 'error': 'Invalid filename'})

    info = LOG_TYPES[log_type]
    log_path = LOG_DIR / info['dir'] / name

    if not log_path.is_file():
        return jsonify({'success': False, 'error': 'File not found'})

    try:
        content = log_path.read_text(encoding='utf-8')
        return jsonify({'success': True, 'data': {'name': name, 'content': content}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    start_session_monitor()
    app.run(host='127.0.0.1', port=AGENT_PORT, debug=False)
