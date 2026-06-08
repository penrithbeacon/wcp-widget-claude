# WCP Claude Analytics

> **Experimental** &mdash; Local components production-ready; Cloud API components untested

Claude Code usage analytics, session history, and system environment information as a WCP 2.1.0 widget. Part of [Penrith Beacon](https://penrithbeacon.com).

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

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CONTAINER_NAME` | Yes | Must be `wcp-widget-claude` (used by health endpoint) |

## Ports

| Port | Description |
|------|-------------|
| 3746 | Widget HTTP server |

## Volumes

| Mount | Description |
|-------|-------------|
| `/app/data` | Persistent settings and cached data |

## Host Agent

The **Local** components (Environment, Sessions, Log Viewer) require a companion host agent running on the host OS. The agent provides access to Claude Code's local files and system information.

Download the agent installer from the widget's Settings component, or build from source (`agents/mac-arm64/build-app.sh`).

Currently available for macOS (Apple Silicon). Intel, Linux, and Windows coming soon.

## Components

- **Local: Environment** &mdash; MCP servers, plugins, system info
- **Local: Sessions** &mdash; Recent Claude Code session history
- **Local: Log Viewer** &mdash; Live session log streaming
- **API: Usage** &mdash; Token usage and cost tracking (requires Admin API key)
- **API: Productivity** &mdash; Productivity metrics (requires Admin API key)
- **Settings** &mdash; Configuration and agent download
- **Help** &mdash; User guide

## Links

- [Full Documentation (GitHub)](https://github.com/penrithbeacon/wcp-widget-claude)
- [Widget Context Protocol](https://widgetcontextprotocol.com)
- [Penrith Beacon](https://penrithbeacon.com)
