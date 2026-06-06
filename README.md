# WCP Widget: Claude Analytics

> **Tutorial Reference** — This widget serves as a worked example for building WCP widget containers that include a companion host agent. It demonstrates the full pattern: Docker container with Flask backend, multiple instrument pages, cloud API integration, host agent communication, settings management, and themed UI.

Claude Code usage analytics, cost tracking, and developer productivity metrics. Cloud data via Anthropic Admin API; local data via optional host agent.

## Architecture

```
┌────────────────────────────────────────────────────┐
│  Claude Analytics Widget (Docker, port 3746)        │
│  Flask app — 5 instruments + settings               │
│                                                      │
│  Cloud instruments ← Anthropic Admin API             │
│  Local instruments ← Host Agent (localhost:3747)     │
└────────────────────────────────────────────────────┘
         │ via host.docker.internal
┌────────────────────────────────────────────────────┐
│  Host Agent (native, port 3747)                     │
│  Reads ~/.claude/ config, runs CLI commands          │
│  Auto-starts via launchd (macOS)                    │
└────────────────────────────────────────────────────┘
```

## Instruments

| Instrument | Data Source | Description |
|:-----------|:-----------|:------------|
| **Usage** | Cloud API | Per-model token breakdown (input, output, cache) + cost summary |
| **Productivity** | Cloud API | Developer activity stats, model breakdown, terminal types |
| **Local** | Host Agent | MCP servers, installed plugins, system info |
| **Sessions** | Host Agent | Recent Claude Code sessions with working directory |
| **Settings** | Local | API key management, agent URL, test buttons, agent downloads |

## Quick Start

### 1. Run the widget container

```bash
docker compose up -d
```

The widget is now accessible at `http://localhost:3746/widget/`.

### 2. Install the host agent (optional)

Download from the widget's Settings page, or install manually:

```bash
cd agents/mac-arm64
chmod +x install.sh
./install.sh
```

The agent runs on `127.0.0.1:3747` (localhost only) and auto-starts on login.

### 3. Configure in Settings

Open the Settings instrument and:
- Add your Anthropic Admin API key (from [console.anthropic.com](https://console.anthropic.com/settings/admin-keys))
- Test the host agent connection

## Security

This widget is designed for public distribution. Security measures:

- **No secrets in code** — API keys and agent URLs are stored in the Docker volume (`/app/data/settings.json`), never in source
- **Masked credentials** — GET requests to `/widget/api/settings` return `••••••••` for the API key
- **Host agent is localhost-only** — binds to `127.0.0.1`, not accessible from the network
- **Non-root container** — the Docker image runs as `appuser`, not root
- **No credential forwarding** — the widget never sends stored credentials to any third party; it proxies requests server-side

## WCP Specification

This widget implements [Widget Context Protocol 2.1.0](https://widgetcontextprotocol.com):

- **Manifest**: `GET /widget/wcp` — full WCP manifest with 5 components
- **Health**: `GET /widget/health` — container health check
- **Directory**: `GET /wcp` — container-level widget directory
- **Theme**: Responds to `wcp:theme` and `wcp:request-theme` postMessage events
- **Ready**: Posts `wcp:ready` on instrument load
- **Publish/Unpublish**: `POST/DELETE /widget/publish` — SPA hosting support

## Project Structure

```
widgets/claude/
├── Dockerfile                 # Multi-stage build
├── docker-compose.yml         # Container orchestration
├── requirements.txt           # Python dependencies (flask, requests)
├── src/
│   ├── app.py                 # Flask app — routes, WCP manifest, API proxies
│   ├── templates/
│   │   ├── widget.html        # Landing page (instrument selector)
│   │   ├── usage.html         # Token usage + cost cards
│   │   ├── productivity.html  # Developer activity + model breakdown
│   │   ├── local.html         # MCP servers + plugins + system
│   │   ├── sessions.html      # Recent sessions list
│   │   └── settings.html      # API key + agent config + downloads
│   └── published/             # SPA output directory (auto-managed)
├── agents/
│   └── mac-arm64/
│       ├── agent.py           # Host agent Flask app
│       ├── install.sh         # launchd installer
│       └── requirements.txt   # Agent dependencies (flask only)
└── README.md                  # This file
```

## Tutorial: Building a WCP Widget with a Host Agent

### Pattern 1: Cloud API Proxy

The widget proxies cloud API calls through its Flask backend rather than calling from the browser. This keeps API keys server-side:

```python
@app.route('/widget/api/cloud/usage')
def api_cloud_usage():
    headers = _admin_headers()  # Reads key from settings file
    if not headers:
        return jsonify({'success': False, 'error': 'Not configured'})
    r = requests.get('https://api.anthropic.com/v1/...', headers=headers)
    return jsonify({'success': True, 'data': r.json()})
```

### Pattern 2: Host Agent Communication

The container can't access the host filesystem directly. A lightweight agent running natively bridges this gap:

```
Container (port 3746) → host.docker.internal:3747 → Agent → ~/.claude/
```

The agent only binds to localhost — Docker's `host.docker.internal` DNS lets the container reach it without exposing it to the network.

### Pattern 3: Graceful Degradation

Each instrument checks what's configured and shows appropriate UI:

- **Both configured** → Full data
- **Only cloud API** → Cloud cards populate; local cards show "Install agent" prompt
- **Only agent** → Local cards populate; cloud cards show "Add API key" prompt
- **Neither** → All cards show setup prompts linking to Settings

### Pattern 4: WCP Theme Integration

Every template includes the standard WCP theme boilerplate:

```javascript
function _applyThemeVars(vars) {
  for (const [k, v] of Object.entries(vars))
    document.documentElement.style.setProperty(k, v);
}
window.parent?.postMessage({ type: 'wcp:ready' }, '*');
window.parent?.postMessage({ type: 'wcp:request-theme' }, '*');
window.addEventListener('message', e => {
  if (e.data?.type === 'wcp:theme' && e.data.vars) _applyThemeVars(e.data.vars);
});
```

All CSS uses `var(--wcp-color-*, fallback)` so themes apply instantly.

## Development

```bash
# Run locally without Docker (for development)
cd src && python app.py

# Run agent locally
cd agents/mac-arm64 && python agent.py

# Build Docker image
docker compose build

# View logs
docker compose logs -f
```

## License

MIT
