# Hermes Assistant for Home Assistant

[![CI](https://github.com/TopherMayor/hermes-home-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/TopherMayor/hermes-home-assistant/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A native Home Assistant integration that brings Hermes Agent into the **Assist / Voice PE pipeline**, with a full-featured Lovelace chat card, health sensors, event entities, buttons, and automation services.

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Platforms](#platforms)
- [Services](#services)
- [Events](#events)
- [Lovelace Card](#lovelace-chat-card)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Changelog](./CHANGELOG.md)

---

## Features

### 🌙 Assist Conversation Agent
Hermes appears as a native `conversation` agent in Home Assistant's Assist / Voice PE pipeline. Select **Hermes** as your voice assistant in **Settings → Voice Assistants** and chat from the HA UI or any voice-enabled surface.

### 💬 Lovelace Chat Card
A full-featured streaming chat card for Lovelace dashboards:
- **Markdown rendering** — headers, bold, italic, lists, blockquotes, links
- **Code blocks** — fenced code blocks with language labels and per-block copy buttons
- **Message copy** — per-message copy-to-clipboard on hover
- **Streaming responses** — SSE with typing indicator
- **Timestamps** — optional per-message time display
- **Token counter** — optional live character count during streaming
- **Dark theme** — matches the HA aesthetic; fully configurable colors and names
- **localStorage history** — conversation persists across page reloads

### 📡 Event Entities
Real-time Hermes run lifecycle events exposed as Home Assistant event entities:

| HA Event | Trigger |
|----------|---------|
| `hermes_assistant_run_started` | Background run begins |
| `hermes_assistant_run_completed` | Run finishes successfully |
| `hermes_assistant_run_failed` | Run errors out |
| `hermes_assistant_run_approval_required` | Approval needed before proceeding |
| `hermes_assistant_gateway_healthy` | Gateway transitions to healthy |
| `hermes_assistant_gateway_unhealthy` | Gateway transitions to unhealthy |
| `hermes_assistant_health_check_completed` | Manual health check button pressed |

Use these in automations to react when Hermes tasks finish or when the gateway status changes.

### 📊 Diagnostic Sensors (9 entities)
Gateway health sensors available in HA's entity picker:

| Sensor | Description | Device Class |
|--------|-------------|--------------|
| Hermes Model | Active LLM model name | `enum` |
| Context Usage | Context window utilization % | `percentage` |
| Context Limit | Total context window tokens | `data_size` |
| Gateway Uptime | Seconds since gateway started | `duration` |
| Active Threads | Currently running conversation threads | — |
| Memory Usage | RSS memory in MB | `data_size` |
| Error Count | Errors since gateway start | `enum` |
| Hermes Version | Gateway software version | `enum` |
| LLM Provider | Current provider name | `enum` |

### 🔘 Control Buttons
Available in HA's developer-tools → Services panel or as实体 buttons on a dashboard:

| Button | Action |
|--------|--------|
| **Refresh Sensors** | Force an immediate coordinator refresh |
| **Health Check** | Hit `/health/detailed`, fire `health_check_completed/failed` events |
| **Clear Conversation History** | Wipe the conversation agent's tracked history |
| **Restart Gateway** *(optional)* | SSH to the Hermes host and run `hermes gateway restart` |

### 🔌 Automation Services
Three services for scripts and automations:

| Service | Description |
|---------|-------------|
| `hermes_assistant.hermes_conversation` | Send a message and receive the full response synchronously |
| `hermes_assistant.hermes_send_message` | Send via the Responses API with conversation tracking |
| `hermes_assistant.hermes_trigger_run` | Start a background run, get a `run_id` for later polling |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           Home Assistant (panda / .30.196)           │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  hermes_assistant integration                  │  │
│  │                                                 │  │
│  │  ┌───────────────┐  ┌──────────────────────┐  │  │
│  │  │ api.py         │  │  config_flow.py     │  │  │
│  │  │ HermesApiClient│  │  Manual URL + key   │  │  │
│  │  │ GET /health    │  │  connection test    │  │  │
│  │  │ POST /v1/runs  │  └──────────────────────┘  │  │
│  │  │ POST /v1/resps  │                           │  │
│  │  └───────┬─────────┘                           │  │
│  │          │                                     │  │
│  │  ┌───────┴──────────────────────────────────┐ │  │
│  │  │  conversation.py — Assist agent (NATIVE)  │ │  │
│  │  │  sensor.py     — 9 health sensors        │ │  │
│  │  │  binary_sensor.py — online/offline + quality│ │  │
│  │  │  button.py     — 4 control buttons       │ │  │
│  │  │  event.py      — gateway/run event entities│ │  │
│  │  │  __init__.py   — 3 HA services           │ │  │
│  │  └───────────────────────────────────────────┘ │  │
│  │          │                                     │  │
│  │  ┌───────┴──────────┐                         │  │
│  │  │ www/              │                         │  │
│  │  │ hermes-chat-card.js  ← Lovelace chat UI     │  │
│  │  └──────────────────┘                         │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                │ HTTP :8642 / Bearer token
                ▼
┌─────────────────────────────────────────────────────┐
│         Hermes Agent Gateway (WSL / hyte-hermes)     │
│                                                      │
│  ┌──────────────────────────────────────────────────┐│
│  │  api_server.py  — Express API platform           ││
│  │  POST /v1/responses   → /v1/responses/stream     ││
│  │  POST /v1/runs        → /v1/runs/{id}/events     ││
│  │  GET  /health/detailed → resource + model status  ││
│  └──────────────────────────────────────────────────┘│
│                         │                            │
│                         ▼                            │
│  ┌──────────────────────────────────────────────────┐│
│  │  Hermes Agent Core (LLM + tool execution)         ││
│  │  ↳ ha_list_entities, ha_call_service, terminal,  ││
│  │    file, delegation, kanban, github, home_assist,││
│  │    spotify, ...                                  ││
│  └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## Requirements

- **Home Assistant** 2025.1.0 or later
- **Hermes Agent** with the `api_server` platform enabled (port 8642)
- **Hermes API key** set in your `~/.hermes/.env` as `HERMES_API_KEY`
- Network access from HA to the Hermes gateway (same LAN or VPN)

---

## Installation

### Option A — Manual (recommended for now)

1. Copy `custom_components/hermes_assistant/` into your HA config's `custom_components/` folder
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for **Hermes Assistant** and configure:
   - **Gateway URL** — e.g. `http://<hermes-host>:8642` (the Hermes host)
   - **API Key** — the value of `HERMES_API_KEY` from your Hermes `.env`
   - **Name** — friendly label (default: "Hermes")

### Option B — Git (keep up to date)

```bash
cd $HA_CONFIG/custom_components
git clone https://github.com/TopherMayor/hermes-home-assistant.git hermes_assistant
```

Then pull updates with `git pull` and restart HA.

---

## Configuration

### Gateway URL
The base URL of your Hermes gateway. If Hermes runs on the same machine as HA, use `http://localhost:8642`. If Hermes is on another machine (e.g. your WSL/Proxmox host), use the LAN IP.

### API Key
Found in your Hermes `~/.hermes/.env` as `HERMES_API_KEY`. This is the token sent as `Authorization: Bearer <key>` on every request.

### Optional: SSH for Restart Button
If you want the **Restart Gateway** button to work, add these to the integration config:

| Field | Value |
|-------|-------|
| `ssh_host` | IP or hostname of the machine running Hermes (e.g. `192.168.1.<lan-ip>`) |
| `ssh_user` | SSH username (default: `root`) |
| `ssh_key_path` | Path to private SSH key (e.g. `/root/.ssh/id_rsa`) |

The SSH key must be authorized on the Hermes host.

---

## Platforms

| Platform | Entities Created | Config Entry |
|----------|-----------------|--------------|
| `conversation` | 1 Assist agent | ✅ |
| `sensor` | 9 health sensors | ✅ |
| `binary_sensor` | Online/offline + connection quality | ✅ |
| `button` | 4 buttons (restart requires SSH config) | ✅ |
| `event` | Run lifecycle + gateway events | ✅ |

---

## Services

All three services are under the `hermes_assistant` domain in HA's developer-tools → Services panel.

### `hermes_conversation`

Blocking send-and-wait. Returns the full response text.

```yaml
service: hermes_assistant.hermes_conversation
data:
  message: "Turn off the living room lights"
  system_prompt: "You are a smart home assistant."
```

Response: a `conversation_completed` event is fired with `text` and `tool_calls`.

### `hermes_send_message`

Stateful send via the Responses API. Tracks conversation context.

```yaml
service: hermes_assistant.hermes_send_message
data:
  message: "What's the weather like?"
```

### `hermes_trigger_run`

Fire-and-forget background task. Returns a `run_id` immediately.

```yaml
service: hermes_assistant.hermes_trigger_run
data:
  message: "List all my Home Assistant entities"
  metadata:
    source: "automation"
    triggered_by: "morning_routine"
```

After completion, HA fires `hermes_assistant_run_completed` with the run result.

---

## Events

Subscribe to Hermes events in automations using the **Event** entity:

```yaml
trigger:
  - platform: event
    event_type: hermes_assistant_run_completed

action:
  - alias: "Log the response"
    logger.info:
      message: "Hermes run done: {{ trigger.event.data }}"
```

### Gateway Event Polling

`event.py` polls `GET /health/detailed` every 30 seconds and fires `gateway_healthy` / `gateway_unhealthy` events on status transitions — useful for network-resilient automation.

---

## Lovelace Chat Card

### Installation

**Method 1 — File copy (recommended):**
```bash
cp custom_components/hermes_assistant/www/hermes-chat-card.js \
   $HA_CONFIG/www/hermes-chat-card.js
```

**Method 2 — Resource URL:**
1. Go to **Settings → Dashboards → Resources**
2. Add new → URL: `https://github.com/TopherMayor/hermes-home-assistant/raw/main/custom_components/hermes_assistant/www/hermes-chat-card.js`
3. Set type to **JavaScript Module**

### Card Configuration

Add in Lovelace via **Add Card → Manual Card**:

```yaml
type: custom:hermes-chat-card
gateway_url: http://<hermes-host>:8642
api_key: your-hermes-api-key
title: Hermes
enable_markdown: true
enable_timestamps: false
show_token_count: false
```

### All Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `gateway_url` | string | `http://localhost:8642` | Hermes gateway base URL |
| `api_key` | string | `""` | Bearer token |
| `title` | string | `"Hermes"` | Card header title |
| `user_name` | string | `"You"` | Label for user messages |
| `user_color` | string | `#818cf8` | User bubble accent color |
| `assistant_name` | string | `"Hermes"` | Label for assistant messages |
| `assistant_color` | string | `#34d399` | Assistant bubble accent color |
| `placeholder` | string | `"Ask Hermes anything…"` | Input placeholder |
| `max_history` | number | `50` | Max messages to persist (max 200) |
| `enable_markdown` | boolean | `true` | Render markdown in responses |
| `enable_timestamps` | boolean | `false` | Show per-message timestamps |
| `show_token_count` | boolean | `false` | Live character count during streaming |
| `disable_paste` | boolean | `false` | Disable image paste into input |

---

## Troubleshooting

### "Cannot connect to Hermes"
```bash
# Test connectivity from the HA machine
curl http://<hermes-host>:8642/health

# Or from WSL (Hermes host)
curl http://localhost:8642/health
```
If this fails, the API server platform is not running on Hermes. Enable it with `hermes gateway setup`.

### "Invalid API key" in the chat card
```bash
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8642/health/detailed
```
Should return JSON. If 401, the `HERMES_API_KEY` in `.env` is wrong or not set. Restart Hermes after changing the key.

### Assist agent not appearing in Voice Assistant settings
- Requires HA 2025.1.0 or later
- Restart HA after installing the integration
- Check **Settings → System → Logs** for `hermes_assistant` errors

### Sensors stuck on "offline"
- The coordinator retries with exponential backoff
- If Hermes restarts, sensors recover automatically after the next successful poll
- Run a **Health Check** button press to force a immediate retry

### Restart button not appearing
- Requires `ssh_host` configured in the integration config
- Ensure the SSH key is authorized on the Hermes host:
  ```bash
  # From the HA machine:
  ssh -i /path/to/key.pem ssh_user@hermes_host "echo ok"
  ```

### "No module named 'asyncssh'" in restart button
```bash
pip install asyncssh
```
The restart button requires `asyncssh` on the HA machine.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). All contributions welcome — open an issue first for significant changes.

---

## License

MIT — see [LICENSE](./LICENSE)