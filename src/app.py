"""
WCP Widget: Claude Analytics
Usage analytics, cost tracking, and developer productivity metrics for Claude Code.
Port: 3746  |  Specification: https://widgetcontextprotocol.com
"""

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request, Response, render_template

app = Flask(__name__)

PUBLISHED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'published', 'index.html')
SETTINGS_FILE  = '/app/data/settings.json'
AGENTS_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'agents')
CACHE_TTL      = 60  # seconds — cloud APIs are rate-limited to 1/min

os.makedirs('/app/data', exist_ok=True)

# ── Settings ──────────────────────────────────────────────────────────────────

_DEFAULT_SETTINGS = {
    'admin_api_key': '',
    'agent_url':     'http://host.docker.internal:3747',
}

def read_settings():
    try:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
        return {**_DEFAULT_SETTINGS, **s}
    except Exception:
        return dict(_DEFAULT_SETTINGS)

def write_settings(data):
    merged = {**read_settings(), **{k: data[k] for k in data if k in _DEFAULT_SETTINGS}}
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(merged, f, indent=2)
    return merged

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache = {}

def get_cache(key):
    c = _cache.get(key)
    if c and time.time() - c['t'] < CACHE_TTL:
        return c['v']
    return None

def set_cache(key, v):
    _cache[key] = {'v': v, 't': time.time()}

def clear_cache(key=None):
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_instance_id():
    iid = request.headers.get('Wcp-Instance-Id', '').strip()
    return iid or request.args.get('wcpInstanceId', '').strip()

def get_orchestration_id():
    oid = request.headers.get('Wcp-Orchestration-Id', '').strip()
    return oid or request.args.get('wcpOrchestrationId', '').strip()

def get_application_id():
    aid = request.headers.get('Wcp-Application-Id', '').strip()
    return aid or request.args.get('wcpApplicationId', '').strip()

def _admin_headers():
    key = read_settings().get('admin_api_key', '')
    if not key:
        return None
    return {
        'X-Api-Key': key,
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
    }

def _agent_url(path):
    base = read_settings().get('agent_url', '').rstrip('/')
    return f'{base}{path}' if base else None

def _fmt_tokens(n):
    """Format token count for display."""
    if n is None:
        return '0'
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)

# ── WCP Manifest ─────────────────────────────────────────────────────────────

WCP_MANIFEST = {
    'wcp':     '2.1.0',
    'uuid':    'bb43c314-4e04-49dd-8bc2-615d3138538d',
    'name':    'Claude Analytics',
    'version':     '1.2.0',
    'description': (
        'Claude Code usage analytics, cost tracking, and developer productivity metrics. '
        'Cloud data via Anthropic Admin API; local data via optional host agent.'
    ),
    'icon':    '/widget/icon.svg',
    'health':  '/widget/health',
    'container': {
        'image':            'docker.io/penrithbeacon/wcp-widget-claude',
        'source':           {'type': 'registry'},
        'tag':              '1.2.0-wcp2.1.0',
        'port':             3746,
        'volumes':          [{'name': 'claude_data', 'mountPath': '/app/data'}],
        'defaultLifecycle': 'always',
    },
    'components': [
        {
            'id': 'claude-local-environment', 'uuid': '7afca010-82a8-4652-b001-08bd05945f04',
            'name': 'Local: Environment', 'role': 'widget',
            'path': '/widget/local', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 6},
        },
        {
            'id': 'claude-local-sessions', 'uuid': '760f7625-3d5a-421e-a548-fe3d9296e019',
            'name': 'Local: Sessions', 'role': 'widget',
            'path': '/widget/sessions', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 4},
        },
        {
            'id': 'claude-api-usage', 'uuid': '6a27d3da-9c65-449c-a69b-f4d4281d4858',
            'name': 'API: Usage (Alpha)', 'role': 'widget',
            'path': '/widget/usage', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 6},
            'conditionalVisibility': True,
        },
        {
            'id': 'claude-api-productivity', 'uuid': '14d4519e-2602-44dc-b9d3-b82274355ba2',
            'name': 'API: Productivity (Alpha)', 'role': 'widget',
            'path': '/widget/productivity', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 6},
            'conditionalVisibility': True,
        },
        {
            'id': 'claude-settings', 'uuid': 'b0dc2a4d-f17c-473c-b77b-b2616e72bc58',
            'name': 'Settings', 'role': 'widget',
            'path': '/widget/settings', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 6},
        },
        {
            'id': 'claude-log-viewer', 'uuid': '3b7e92d1-a41f-4c8a-9e05-6f2d18b73c90',
            'name': 'Local: Log Viewer', 'role': 'widget',
            'path': '/widget/logs', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 8},
        },
        {
            'id': 'claude-help', 'uuid': 'e9a3f7c1-5d28-4a1b-b6e0-3c8f91d24a07',
            'name': 'Help', 'role': 'widget',
            'path': '/widget/help', 'icon': '/widget/icon.svg',
            'renderMode': 'iframe', 'defaultSize': {'w': 12, 'h': 6},
        },
    ],
}

WIDGET_JSONLD = json.dumps({
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    'name': WCP_MANIFEST['name'],
    'softwareVersion': WCP_MANIFEST['version'],
    'description': WCP_MANIFEST['description'],
    'identifier': WCP_MANIFEST['uuid'],
    'applicationCategory': 'WCP Widget',
    'operatingSystem': 'Web',
    'isBasedOn': {
        '@type': 'WebSite',
        'name': 'Widget Context Protocol',
        'url': 'https://widgetcontextprotocol.com',
    },
    'additionalProperty': [
        {'@type': 'PropertyValue', 'name': 'wcpVersion',    'value': WCP_MANIFEST['wcp']},
        {'@type': 'PropertyValue', 'name': 'containerImage','value': WCP_MANIFEST['container']['image']},
        {'@type': 'PropertyValue', 'name': 'containerTag',  'value': WCP_MANIFEST['container']['tag']},
        {'@type': 'PropertyValue', 'name': 'containerPort', 'value': str(WCP_MANIFEST['container']['port'])},
    ],
}, indent=2)

# ── CORS ──────────────────────────────────────────────────────────────────────

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = (
        'Content-Type, Wcp-Instance-Id, Wcp-Dashboard-Id, Wcp-Version, Wcp-Widget-Id, '
        'Wcp-Orchestration-Id, Wcp-Application-Id'
    )
    return resp

@app.route('/widget/<path:p>', methods=['OPTIONS'])
@app.route('/widget/', methods=['OPTIONS'])
@app.route('/wcp', methods=['OPTIONS'])
def cors_preflight(p=''):
    return Response('', status=204)

# ── WCP boilerplate ──────────────────────────────────────────────────────────

@app.route('/')
def published_spa():
    if os.path.exists(PUBLISHED_PATH):
        with open(PUBLISHED_PATH, 'r', encoding='utf-8') as f:
            return Response(f.read(), mimetype='text/html')
    return Response('Not Found', status=404, mimetype='text/plain')

@app.route('/widget/publish', methods=['POST'])
def publish():
    html = request.get_data(as_text=True)
    if not html:
        return jsonify({'success': False, 'error': 'Empty body'}), 400
    try:
        os.makedirs(os.path.dirname(PUBLISHED_PATH), exist_ok=True)
        with open(PUBLISHED_PATH, 'w', encoding='utf-8') as f:
            f.write(html)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/widget/publish', methods=['DELETE'])
def unpublish():
    try:
        if os.path.exists(PUBLISHED_PATH):
            os.remove(PUBLISHED_PATH)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/wcp')
def container_directory():
    return jsonify({
        'type':    'directory',
        'wcp':     '2.1.0',
        'widgets': [{
            'id':          'claude-analytics',
            'uuid':        WCP_MANIFEST['uuid'],
            'name':        WCP_MANIFEST['name'],
            'description': WCP_MANIFEST['description'],
            'icon':        WCP_MANIFEST['icon'],
            'manifest':    '/widget/wcp',
        }]
    })

@app.route('/widget/wcp')
def widget_wcp():
    m = dict(WCP_MANIFEST)
    m['web'] = {'published': os.path.exists(PUBLISHED_PATH)}
    return jsonify(m)

@app.route('/widget/index')
def widget_index():
    return render_template('index-page.html', manifest=WCP_MANIFEST, jsonld=WIDGET_JSONLD,
        wcp_instance_id=get_instance_id(),
        wcp_orchestration_id=get_orchestration_id(), wcp_application_id=get_application_id())

@app.route('/widget/health')
def widget_health():
    return jsonify({'status': 'ok', 'name': WCP_MANIFEST['name']})

# ── Template routes ──────────────────────────────────────────────────────────

def _ctx():
    s = read_settings()
    return dict(
        manifest=WCP_MANIFEST,
        jsonld=WIDGET_JSONLD,
        wcp_instance_id=get_instance_id(),
        wcp_orchestration_id=get_orchestration_id(),
        wcp_application_id=get_application_id(),
        has_api_key=bool(s.get('admin_api_key')),
        has_agent=bool(s.get('agent_url')),
    )

@app.route('/widget/')
@app.route('/widget/index.html')
def widget_root():
    return render_template('widget.html', **_ctx())

@app.route('/widget/usage')
def widget_usage():
    return render_template('usage.html', **_ctx())

@app.route('/widget/productivity')
def widget_productivity():
    return render_template('productivity.html', **_ctx())

@app.route('/widget/local')
def widget_local():
    return render_template('local.html', **_ctx())

@app.route('/widget/sessions')
def widget_sessions():
    return render_template('sessions.html', **_ctx())

@app.route('/widget/settings')
def widget_settings():
    s = read_settings()
    return render_template('settings.html', settings=s, **_ctx())

@app.route('/widget/logs')
def widget_logs():
    return render_template('logs.html', **_ctx())

@app.route('/widget/help')
def widget_help():
    return render_template('help.html', **_ctx())

# ── Cloud API: Usage (tokens) ────────────────────────────────────────────────

@app.route('/widget/api/cloud/usage')
def api_cloud_usage():
    cached = get_cache('cloud:usage')
    if cached:
        return jsonify(cached)
    headers = _admin_headers()
    if not headers:
        return jsonify({'success': False, 'error': 'Admin API key not configured'})
    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00Z')
        r = requests.get(
            'https://api.anthropic.com/v1/organizations/usage_report/messages',
            params={
                'starting_at': start,
                'bucket_width': '1d',
                'group_by[]': 'model',
            },
            headers=headers,
            timeout=15,
        )
        if r.status_code == 401:
            return jsonify({'success': False, 'error': 'Invalid Admin API key'})
        if r.status_code == 403:
            return jsonify({'success': False, 'error': 'API key lacks admin permissions'})
        r.raise_for_status()
        result = {'success': True, 'data': r.json()}
        set_cache('cloud:usage', result)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach Anthropic API'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Cloud API: Cost ──────────────────────────────────────────────────────────

@app.route('/widget/api/cloud/cost')
def api_cloud_cost():
    cached = get_cache('cloud:cost')
    if cached:
        return jsonify(cached)
    headers = _admin_headers()
    if not headers:
        return jsonify({'success': False, 'error': 'Admin API key not configured'})
    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00Z')
        r = requests.get(
            'https://api.anthropic.com/v1/organizations/cost_report',
            params={
                'starting_at': start,
                'bucket_width': '1d',
                'group_by[]': 'description',
            },
            headers=headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            return jsonify({'success': False, 'error': 'Invalid or insufficient API key'})
        r.raise_for_status()
        result = {'success': True, 'data': r.json()}
        set_cache('cloud:cost', result)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach Anthropic API'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Cloud API: Claude Code Analytics ─────────────────────────────────────────

@app.route('/widget/api/cloud/productivity')
def api_cloud_productivity():
    cached = get_cache('cloud:productivity')
    if cached:
        return jsonify(cached)
    headers = _admin_headers()
    if not headers:
        return jsonify({'success': False, 'error': 'Admin API key not configured'})
    try:
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        r = requests.get(
            'https://api.anthropic.com/v1/organizations/usage_report/claude_code',
            params={'starting_at': today, 'limit': 100},
            headers=headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            return jsonify({'success': False, 'error': 'Invalid or insufficient API key'})
        r.raise_for_status()
        result = {'success': True, 'data': r.json()}
        set_cache('cloud:productivity', result)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach Anthropic API'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Agent proxy: MCP, Plugins, Sessions, System ─────────────────────────────

@app.route('/widget/api/agent/<path:endpoint>')
def api_agent_proxy(endpoint):
    if endpoint not in ('mcp', 'plugins', 'sessions', 'system', 'health', 'logs', 'logs/list', 'logs/read'):
        return jsonify({'success': False, 'error': 'Invalid endpoint'}), 400
    cache_key = f'agent:{endpoint}'
    cached = get_cache(cache_key)
    if cached and endpoint not in ('health', 'logs/list', 'logs/read'):
        return jsonify(cached)
    url = _agent_url(f'/{endpoint}')
    if not url:
        return jsonify({'success': False, 'error': 'Host agent URL not configured'})
    try:
        # Forward query parameters to the agent
        r = requests.get(url, params=request.args, timeout=8)
        result = r.json()
        if result.get('success') and endpoint != 'health':
            set_cache(cache_key, result)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach host agent — is it installed and running?'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Settings API ─────────────────────────────────────────────────────────────

@app.route('/widget/api/settings', methods=['GET'])
def api_settings_get():
    s = read_settings()
    masked = {
        'admin_api_key': '••••••••' if s.get('admin_api_key') else '',
        'agent_url':     s.get('agent_url', ''),
        'admin_api_key_set': bool(s.get('admin_api_key')),
    }
    return jsonify({'success': True, 'data': masked})

@app.route('/widget/api/settings', methods=['POST'])
def api_settings_post():
    data = request.get_json(force=True) or {}
    current = read_settings()
    update = {}
    if 'admin_api_key' in data and data['admin_api_key'] != '••••••••':
        update['admin_api_key'] = data['admin_api_key'].strip()
    if 'agent_url' in data:
        update['agent_url'] = data['agent_url'].strip()
    write_settings({**current, **update})
    clear_cache()
    return jsonify({'success': True})

@app.route('/widget/api/settings/test-api', methods=['POST'])
def api_test_cloud():
    data = request.get_json(force=True) or {}
    key = data.get('key', '').strip()
    if not key:
        key = read_settings().get('admin_api_key', '')
    if not key:
        return jsonify({'success': False, 'error': 'No API key provided'})
    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
        r = requests.get(
            'https://api.anthropic.com/v1/organizations/usage_report/messages',
            params={'starting_at': start, 'limit': 1},
            headers={
                'X-Api-Key': key,
                'anthropic-version': '2023-06-01',
            },
            timeout=10,
        )
        if r.status_code == 200:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': f'HTTP {r.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/widget/api/settings/test-agent', methods=['POST'])
def api_test_agent():
    data = request.get_json(force=True) or {}
    url = (data.get('url') or '').strip().rstrip('/')
    if not url:
        url = read_settings().get('agent_url', '').rstrip('/')
    if not url:
        return jsonify({'success': False, 'error': 'No agent URL provided'})
    try:
        r = requests.get(f'{url}/health', timeout=5)
        result = r.json()
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach agent — check URL'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Agent downloads ──────────────────────────────────────────────────────────

@app.route('/widget/api/agents/<platform>')
def download_agent(platform):
    valid = {'mac-arm64': 'mac-arm64', 'mac-x64': 'mac-x64', 'linux-x64': 'linux-x64'}
    if platform not in valid:
        return jsonify({'success': False, 'error': 'Invalid platform'}), 400
    agent_dir = os.path.join(AGENTS_DIR, valid[platform])
    if not os.path.isdir(agent_dir):
        return jsonify({'success': False, 'error': 'Agent not available for this platform'}), 404

    # Serve .pkg installer if available (macOS)
    pkg_path = os.path.join(agent_dir, 'WCP-Claude-Agent.pkg')
    if os.path.isfile(pkg_path):
        with open(pkg_path, 'rb') as f:
            data = f.read()
        resp = Response(data, mimetype='application/vnd.apple.installer+xml')
        resp.headers['Content-Disposition'] = 'attachment; filename="WCP-Claude-Agent.pkg"'
        return resp

    # Fallback: zip archive (Linux and future platforms)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(agent_dir):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, agent_dir)
                z.write(full, arcname)
    buf.seek(0)
    resp = Response(buf.read(), mimetype='application/zip')
    resp.headers['Content-Disposition'] = f'attachment; filename="wcp-claude-agent-{platform}.zip"'
    return resp

# ── Icon + export ────────────────────────────────────────────────────────────

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
  <path fill="#f0883e" d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 1.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11zM7 5v3.5l3 1.5-.5 1-3.5-1.75V5h1z"/>
</svg>"""

@app.route('/widget/icon.svg')
def widget_icon():
    return Response(ICON_SVG, mimetype='image/svg+xml')

@app.route('/widget/api/guids')
def api_guids():
    return jsonify({
        'uuid': WCP_MANIFEST['uuid'],
        'components': [{'id': c['id'], 'uuid': c['uuid'], 'name': c['name']}
                       for c in WCP_MANIFEST.get('components', [])],
    })

@app.route('/widget/export.wcp')
def export_wcp():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(WCP_MANIFEST, indent=2))
        z.writestr('icon.svg', ICON_SVG)
        z.writestr('DOCKER.md', f"""# {WCP_MANIFEST['name']} — WCP Container

## Pull
```
docker pull penrithbeacon/wcp-widget-claude
```

## Run
```
docker compose up -d
```

Port: 3746 | Spec: https://widgetcontextprotocol.com
""")
    buf.seek(0)
    resp = Response(buf.read(), mimetype='application/zip')
    resp.headers['Content-Disposition'] = 'attachment; filename="claude-analytics.wcp"'
    return resp

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3746, debug=False)
