# Claude Analytics — Specification

## Overview
Claude Code usage analytics, cost tracking, and developer productivity metrics. Cloud data via Anthropic Admin API; local data via optional host agent.

- **Port:** 3746
- **Container:** `wcp-widget-claude`
- **Image:** `docker.io/penrithbeacon/wcp-widget-claude`

## Version
- **Widget:** 1.2.0
- **WCP:** 2.1.0
- **Docker tag:** `1.2.0-wcp2.1.0`

## Controls (HTML Templates)

| Template | Route | Purpose | Default Size |
|----------|-------|---------|--------------|
| widget.html | `/widget/` | Compact overview with navigation grid | (compact) |
| local.html | `/widget/local` | Local environment info (MCP servers, plugins) | 12×6 |
| sessions.html | `/widget/sessions` | Recent Claude Code sessions | 12×4 |
| usage.html | `/widget/usage` | API token usage and cost (Alpha) | 12×6 |
| productivity.html | `/widget/productivity` | Developer activity metrics (Alpha) | 12×6 |
| settings.html | `/widget/settings` | Host agent and API key config | 12×6 |
| logs.html | `/widget/logs` | Session history and activity logs | 12×8 |
| help.html | `/widget/help` | Setup guide and troubleshooting | 12×6 |

## Components

| ID | Name | Role | Size | Notes |
|----|------|------|------|-------|
| claude-local-environment | Local: Environment | widget | 12×6 | |
| claude-local-sessions | Local: Sessions | widget | 12×4 | |
| claude-api-usage | API: Usage (Alpha) | widget | 12×6 | conditionalVisibility |
| claude-api-productivity | API: Productivity (Alpha) | widget | 12×6 | conditionalVisibility |
| claude-settings | Settings | widget | 12×6 | |
| claude-log-viewer | Local: Log Viewer | widget | 12×8 | |
| claude-help | Help | widget | 12×6 | |

## API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/wcp` | Container directory |
| GET | `/widget/wcp` | Widget manifest |
| GET | `/widget/index` | Widget index directory |
| GET | `/widget/` | Compact navigation view |
| GET | `/widget/local` | Local environment |
| GET | `/widget/sessions` | Sessions view |
| GET | `/widget/usage` | API usage (Alpha) |
| GET | `/widget/productivity` | Productivity metrics (Alpha) |
| GET | `/widget/settings` | Settings view |
| GET | `/widget/logs` | Log viewer |
| GET | `/widget/help` | Help view |
| GET | `/widget/health` | Health check |
| GET | `/widget/icon.svg` | Widget icon |
| GET | `/widget/api/guids` | Component UUIDs |
| GET | `/widget/export.wcp` | WCP export package |
| GET | `/widget/api/cloud/usage` | Fetch API usage data |
| GET | `/widget/api/cloud/cost` | Fetch API cost data |
| GET | `/widget/api/cloud/productivity` | Fetch productivity data |
| GET | `/widget/api/agent/<endpoint>` | Proxy to host agent |
| GET | `/widget/api/agents/<platform>` | List available agents |
| GET | `/widget/api/settings` | Get settings |
| POST | `/widget/api/settings` | Save settings |
| POST | `/widget/api/settings/test-agent` | Test host agent connection |
| POST | `/widget/api/settings/test-api` | Test Anthropic API key |
| POST | `/widget/publish` | Publish SPA |
| DELETE | `/widget/publish` | Remove published SPA |
| GET | `/` | Serve published SPA |

## Features
- Local environment inspection (MCP servers, plugins, system info)
- Recent Claude Code session listing
- API usage analytics with token counts (Alpha — requires Admin API key)
- API cost tracking (Alpha)
- Developer productivity metrics (Alpha)
- Session log viewer with history
- Host agent configuration and testing
- Anthropic Admin API key configuration
- Conditional visibility — API components hidden when no admin key configured
- `wcp:set-component-visibility` postMessage for dynamic dashboard integration
- Publish to Web support

## Configuration
- Host agent URL (via settings)
- Anthropic Admin API key (via settings)
- Persisted via `/widget/api/settings`

## Data Persistence
- Settings stored in container
- No named data volume

## Dependencies
- Python: `flask`, `requests`
- Optional: Host agent (local Claude Code data)
- Optional: Anthropic Admin API (cloud data, requires API key)
