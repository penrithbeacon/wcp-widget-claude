# WCP Claude Analytics

> **Experimental** &mdash; published as a reference implementation and tutorial

A [Widget Context Protocol](https://widgetcontextprotocol.com) (WCP) widget providing Claude Code usage analytics, session history, and system environment information. Part of [Penrith Beacon](https://penrithbeacon.com).

This widget is certified **WCP 2.1.0** compliant.

---

## Experimental Status

| Component | Status | Notes |
|-----------|--------|-------|
| Local: Environment | Production | Fully tested |
| Local: Sessions | Production | Fully tested |
| Local: Log Viewer | Production | Fully tested |
| Settings | Production | Fully tested |
| Help | Production | Fully tested |
| API: Usage | **Untested** | Requires Anthropic Teams/Enterprise Admin API key |
| API: Productivity | **Untested** | Requires Anthropic Teams/Enterprise Admin API key |
| Host Agent (macOS Apple Silicon) | Production | Fully tested |
| Host Agent (macOS Intel) | Coming soon | &mdash; |
| Host Agent (Linux x64) | Coming soon | &mdash; |
| Host Agent (Windows x64) | Coming soon | &mdash; |

The Cloud API components are read-only and informational. They require an Anthropic Admin API key available only on Teams and Enterprise plans. They have not been tested due to account limitations. Use at your own risk.

---

## Overview

Claude Analytics has a unique architecture among WCP widgets: it pairs a standard Docker container (the widget server) with a **native host agent** that runs as a macOS menu bar application. This is necessary because the widget needs access to files on the host operating system (Claude Code session data, MCP configuration, installed plugins) which are not available from within a Docker container.

```
+-----------------+         +-------------------+         +-------------------+
|                 |         |                   |         |                   |
|   Host macOS    | <-----> |  WCP Claude Agent | <-----> |  Widget Container |
|   (files, CLI)  |  reads  |  (port 3747)      |  HTTP   |  (port 3746)      |
|                 |         |  Menu bar app     |         |  Flask server     |
+-----------------+         +-------------------+         +-------------------+
                                                                    |
                                                                    v
                                                          +-------------------+
                                                          |                   |
                                                          |  Penrith Beacon   |
                                                          |  Dashboard (host) |
                                                          |                   |
                                                          +-------------------+
```

The container communicates with the host agent via `host.docker.internal:3747`.

---

## Components

| ID | Name | Role | Default Size | Description |
|----|------|------|:------------:|-------------|
| `claude-local-environment` | Local: Environment | widget | 12 x 6 | MCP servers, plugins, system info |
| `claude-local-sessions` | Local: Sessions | widget | 12 x 4 | Recent Claude Code session history |
| `claude-api-usage` | API: Usage | widget | 12 x 6 | Token usage and cost tracking |
| `claude-api-productivity` | API: Productivity | widget | 12 x 6 | Productivity metrics over time |
| `claude-settings` | Settings | widget | 12 x 6 | Configuration, agent download |
| `claude-log-viewer` | Local: Log Viewer | widget | 12 x 8 | Live session log streaming |
| `claude-help` | Help | widget | 12 x 6 | User guide |

The API components use WCP Conditional Visibility &mdash; they are hidden from the dashboard unless an Admin API key is configured in Settings.

---

## Tutorial: Building a WCP Host Agent

This section documents the architecture and implementation of the host agent as a reference for widget developers who need to access host OS resources from within a Docker container.

### Why a Host Agent?

Docker containers are isolated from the host filesystem by design. A WCP widget running in a container cannot:
- Read files from the user's home directory
- Execute CLI tools installed on the host
- Access OS-level information (hostname, RAM, uptime)

The solution is a lightweight native application that runs on the host, reads local data, and exposes it via a localhost HTTP API that the container can reach through Docker's `host.docker.internal` hostname.

### Architecture

The WCP Claude Agent is structured as:

```
agents/mac-arm64/
  menubar_agent.py    # Main app (rumps menu bar integration)
  agent.py            # Flask server with data-reading endpoints
  config.py           # Configuration management (~/.penrith-beacon/claude-agent/)
  build-app.sh        # Build script: py2app -> .pkg installer
  setup.py            # py2app configuration
  pkg/
    distribution.xml  # macOS installer distribution descriptor
    resources/        # welcome.html, conclusion.html, license.html
    scripts/          # preinstall, postinstall shell scripts
```

### The Flask Server (`agent.py`)

The agent runs a Flask server on `127.0.0.1:3747` (localhost only &mdash; not accessible from the network). It exposes endpoints that read local Claude Code data:

| Endpoint | What it reads |
|----------|---------------|
| `GET /mcp` | `~/.claude/settings.json` &mdash; MCP server configuration |
| `GET /plugins` | `~/.claude/plugins/` &mdash; installed plugin manifests |
| `GET /system` | OS info via `platform`, `psutil`, and subprocess calls |
| `GET /sessions` | `~/.claude/projects/` &mdash; recent session metadata |
| `GET /logs/:id` | Individual session transcript (streamed) |

### Menu Bar Integration (`menubar_agent.py`)

The agent uses the [`rumps`](https://github.com/jaredks/rumps) library to create a macOS menu bar application. This provides:

- A persistent icon near the clock (top-right of screen)
- Hover tooltip showing current state ("WCP Claude Agent &mdash; Running")
- Click menu with status, port configuration, log access, and lifecycle controls
- Error badge overlay when the agent is in an error state (e.g., port conflict)

Key patterns:
- **State-driven menu rebuild:** `_build_menu()` is called after any state change, dynamically adding/removing error rows
- **Tooltip via NSStatusItem:** Access the native button via `self._nsapp.nsstatusitem.button().setToolTip_()`
- **Restart via `open -a`:** The py2app bundle cannot use `os.execv`; instead, spawn a delayed `open -a` and quit

### Building the Installer (`build-app.sh`)

The build process:

1. Create a Python virtual environment with Flask, rumps, py2app
2. Run `python setup.py py2app` to create `WCP Claude Agent.app`
3. Create a companion `Uninstall WCP Claude Agent.app` (shell script in .app wrapper)
4. Package both into a `.pkg` installer using `pkgbuild` + `productbuild`

The `.pkg` installer:
- Runs a `preinstall` script to stop any existing agent
- Copies both `.app` bundles to `/Applications`
- Runs a `postinstall` script to install a launchd plist and launch the agent

### Auto-Start via launchd

The agent creates a launchd user agent plist at:
```
~/Library/LaunchAgents/com.penrithbeacon.claude-agent.plist
```

This ensures the agent starts automatically on login with `RunAtLoad: true`.

### Container-to-Agent Communication

The Docker container reaches the host agent via:
```
http://host.docker.internal:3747
```

This is configured in `docker-compose.yml`:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

The widget's Settings component stores the agent URL and the container proxies requests to it.

### Platform Roadmap

| Platform | Status | Technology |
|----------|--------|-----------|
| macOS (Apple Silicon) | Available | rumps + py2app + .pkg |
| macOS (Intel) | Coming soon | Same as ARM, cross-compiled |
| Linux (x64) | Coming soon | Likely AppIndicator + AppImage/deb |
| Windows (x64) | Coming soon | Likely pystray + NSIS/.msi |

---

## Requirements

- Docker and Docker Compose
- (Optional) WCP Claude Agent for Local components &mdash; macOS Apple Silicon

---

## Quick Start

```bash
docker run -d \
  --name wcp-widget-claude \
  -p 3746:3746 \
  -v claude_data:/app/data \
  -e CONTAINER_NAME=wcp-widget-claude \
  --add-host host.docker.internal:host-gateway \
  --restart unless-stopped \
  penrithbeacon/wcp-widget-claude:latest
```

---

## Docker Compose

```yaml
services:
  wcp-widget-claude:
    image: penrithbeacon/wcp-widget-claude:1.1.0-wcp2.1.0
    container_name: wcp-widget-claude
    ports:
      - "3746:3746"
    volumes:
      - claude_data:/app/data
    environment:
      - CONTAINER_NAME=wcp-widget-claude
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

volumes:
  claude_data:
```

---

## Host Agent Installation

### From the Widget (recommended)

1. Add the Claude Analytics widget to your dashboard
2. Open the **Settings** component
3. Download the installer for your platform
4. Run the installer &mdash; the agent appears in your menu bar
5. Click **Test** in Settings to verify the connection

### From Source

```bash
cd agents/mac-arm64
bash build-app.sh
open WCP-Claude-Agent.pkg
```

---

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| Agent URL | Host agent address | `http://host.docker.internal:3747` |
| Admin API Key | Anthropic Admin API key (Teams/Enterprise only) | &mdash; |

---

## WCP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /widget/` | GET | Compact widget (default component) |
| `GET /widget/wcp` | GET | WCP manifest |
| `GET /widget/health` | GET | Health check |
| `GET /widget/icon.svg` | GET | Widget icon |
| `GET /widget/local` | GET | Local: Environment component |
| `GET /widget/sessions` | GET | Local: Sessions component |
| `GET /widget/usage` | GET | API: Usage component |
| `GET /widget/productivity` | GET | API: Productivity component |
| `GET /widget/settings` | GET | Settings component |
| `GET /widget/logs` | GET | Log Viewer component |
| `GET /widget/help` | GET | Help component |

---

## Tags

| Tag | Widget Version | WCP Version | Notes |
|-----|---------------|-------------|-------|
| `1.1.0-wcp2.1.0` | 1.1.0 | 2.1.0 | First public release (experimental) |
| `latest` | 1.1.0 | 2.1.0 | &mdash; |

---

## Links

- [Penrith Beacon](https://penrithbeacon.com)
- [Widget Context Protocol](https://widgetcontextprotocol.com)
- [Docker Hub](https://hub.docker.com/r/penrithbeacon/wcp-widget-claude)
- [GitHub (public)](https://github.com/penrithbeacon/wcp-widget-claude)
