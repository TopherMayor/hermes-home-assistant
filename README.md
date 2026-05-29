# Hermes Assistant for Home Assistant

A native Home Assistant integration that brings Hermes Agent into the Assist / Voice PE pipeline, with a Lovelace chat card, sensor entities, and automation services.

## Features

### 🌙 Assist Conversation Agent
Hermes appears as a native conversation agent in Home Assistant's Assist / Voice PE pipeline. Users can select "Hermes" as their voice assistant in **Settings → Voice Assistant** and chat with it from the HA UI or any voice pipeline.

### 💬 Lovelace Chat Card
A full-featured chat card (`hermes-chat-card`) for Lovelace dashboards. Supports:
- Streaming responses with typing indicators
- Message history (persisted in localStorage)
- Dark-themed UI matching the HA aesthetic
- Configurable names, colors, and placeholder text

### 📊 Gateway Health Sensors
Sensor entities for monitoring the Hermes gateway:
- Online/Offline status
- Model in use
- Context usage percentage
- Memory usage
- Gateway uptime

### 🔧 Automation Services
Three services for Home Assistant automations and scripts:

| Service | Use Case |
|---------|----------|
| `hermes_assistant.hermes_conversation` | Send a message and get a response (blocking) |
| `hermes_assistant.hermes_send_message` | Send a message via the Responses API (stateful) |
| `hermes_assistant.hermes_trigger_run` | Kick off a background task and get a `run_id` immediately |

### 🚀 Background Run Triggers
Trigger long-running Hermes tasks from HA automations and get notified via Home Assistant events when they complete.

## Requirements

- **Home Assistant** 2025.1.0 or later
- **Hermes Agent** gateway running with the API server platform enabled
- **Hermes API key** configured in Hermes (`HERMES_API_KEY`)
- **API Server platform** enabled in your Hermes gateway config (`hermes gateway setup`)

## Quick Start

### 1. Enable the Hermes API Server

On the machine running Hermes, enable the API Server platform:

```bash
hermes gateway setup
# Choose: api_server
# Set a port (default: 8642)
# Set an API key (or use HERMES_API_KEY env var)
```

Or add it to your `~/.hermes/config.yaml`:

```yaml
platforms:
  api_server:
    enabled: true
    key: "your-secure-api-key"
    host: "0.0.0.0"
    port: 8642
```

Then restart the gateway:

```bash
hermes gateway restart
```

### 2. Install the Integration

**Option A: HACS (coming soon)**
Once published to HACS, add via **HACS → Integrations → Explore & Download Repositories**.

**Option B: Manual**
```bash
# Copy to your HA custom_components directory
cp -r custom_components/hermes_assistant ~/.homeassistant/custom_components/
```

Then restart Home Assistant.

### 3. Configure the Integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Hermes"
3. Enter your Hermes gateway URL (default: `http://localhost:8642`)
4. Enter your API key (or leave blank to use `HERMES_API_KEY` env var)
5. Click **Submit**

The integration will:
- Register Hermes as a conversation agent
- Create sensor entities for gateway health
- Register the three automation services

### 4. Add the Lovelace Chat Card

**In your Lovelace dashboard:**

```yaml
type: custom:hermes-chat-card
gateway_url: http://localhost:8642   # Hermes API server URL
api_key: your-api-key                 # Or set HERMES_API_KEY
title: Hermes
user_name: You
assistant_name: Hermes
```

**Via the UI:**
1. Edit your dashboard
2. Add Card → Manual Card
3. Paste the YAML above

### 5. Use as Voice Assistant

1. **Settings → Voice Assistant → Add Assistant**
2. Select **Hermes** as the agent
3. Choose a wake word (if using a voice pipeline)
4. Test with "Turn off the living room lights" or any question

## Configuration Options

### Integration (Config Flow)

| Option | Default | Description |
|--------|---------|-------------|
| Gateway URL | `http://localhost:8642` | Hermes API server URL |
| API Key | env `HERMES_API_KEY` | Bearer token for auth |
| Name | `Hermes` | Friendly name for the integration |
| Poll Interval | `30` | Seconds between sensor refreshes |

### Chat Card

| Option | Default | Description |
|--------|---------|-------------|
| `gateway_url` | `http://localhost:8642` | Hermes API server URL |
| `api_key` | (from env) | API key for auth |
| `title` | `Hermes` | Card header title |
| `prominent` | `true` | Show gradient header |
| `hide_header` | `false` | Hide the header entirely |
| `user_name` | `You` | Name for user messages |
| `user_color` | `#818cf8` | Accent color for user bubbles |
| `assistant_name` | `Hermes` | Name for assistant messages |
| `assistant_color` | `#34d399` | Accent color for assistant bubbles |
| `placeholder` | `Ask Hermes anything…` | Input placeholder |
| `max_history` | `50` | Max messages to show (up to 200) |
| `disable_paste` | `false` | Disable image paste into input |

### Services

#### `hermes_assistant.hermes_conversation`

Send a message and wait for a response. Use from automations:

```yaml
service: hermes_assistant.hermes_conversation
data:
  message: "What's the current temperature in the living room?"
  agent_id: "default"
```

Returns: `{"response": "The living room is currently 72°F."}`

#### `hermes_assistant.hermes_trigger_run`

Kick off a background task and return immediately with a `run_id`:

```yaml
service: hermes_assistant.hermes_trigger_run
data:
  goal: "Check all lights are off and report back"
  agent_id: "default"
```

Returns: `{"run_id": "abc123", "status": "queued"}`

Then in HA automations, listen for the `hermes_assistant.run_completed` event:

```yaml
trigger:
  platform: event
  event_type: hermes_assistant.run_completed
  event_data:
    run_id: "abc123"
```

## Architecture

```
Home Assistant                          Hermes Agent
┌──────────────────────────────────┐    ┌─────────────────────────────────┐
│  hermes_assistant integration     │    │  Hermes Gateway                 │
│  ┌────────────────────────────┐  │    │  ┌────────────────────────────┐ │
│  │  conversation.py           │  │    │  │  api_server platform       │ │
│  │  (Assist agent)             │──┼──► │  │  (OpenAI-compatible API)   │ │
│  │  ↳ /v1/chat/completions     │  │    │  │  ↳ POST /v1/chat/completions│ │
│  └────────────────────────────┘  │    │  │  ↳ POST /v1/runs            │ │
│  ┌────────────────────────────┐  │    │  │  ↳ GET  /health/detailed   │ │
│  │  sensor.py                 │  │    │  └────────────────────────────┘ │
│  │  (gateway health sensors)   │──┼──► │                                 │
│  │  ↳ /health/detailed         │  │    │                                 │
│  └────────────────────────────┘  │    │  ┌────────────────────────────┐ │
│  ┌────────────────────────────┐  │    │  │  homeassistant platform     │ │
│  │  __init__.py (services)    │  │    │  │  (WebSocket → HA events)    │ │
│  │  ↳ hermes_conversation     │  │    │  └────────────────────────────┘ │
│  │  ↳ hermes_send_message     │  │    │                                 │
│  │  ↳ hermes_trigger_run      │  │    │                                 │
│  └────────────────────────────┘  │    └─────────────────────────────────┘
└──────────────────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │  Hermes Agent Core   │
                              │  (LLM + Tools)       │
                              │  ↳ ha_list_entities  │
                              │  ↳ ha_call_service   │
                              │  ↳ terminal, file,    │
                              │    delegation, etc.  │
                              └──────────────────────┘
```

## Security Notes

- The API key is stored in Home Assistant's `config/.storage` (not plain text)
- The Lovelace chat card sends the API key to the Hermes gateway via `Authorization: Bearer` header
- For external access, run the Hermes API server behind HTTPS or a VPN
- The `hermes_assistant` services are only available within HA — no separate API exposure
- Token refresh: if the Hermes gateway token rotates (e.g. addon restart), update the integration config

## Troubleshooting

**"Cannot connect to Hermes" error**
- Verify the Hermes gateway is running: `curl http://localhost:8642/health`
- Check the API server platform is enabled: `hermes gateway status`
- Verify the API key is correct

**Assist agent not appearing in Voice Assistant settings**
- Ensure Home Assistant 2025.1.0 or later
- Restart HA after installing the integration
- Check the log: **Settings → System → Logs** → search for `hermes_assistant`

**Chat card shows "Invalid API key"**
- The Hermes gateway requires a Bearer token
- Set `HERMES_API_KEY` in your Hermes `.env` or pass `api_key` in the card config
- Verify: `curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8642/health`

**Sensor entities show "offline"**
- The coordinator retries with exponential backoff
- If Hermes restarts, sensors will recover automatically
- Check `hermes gateway status` on the Hermes host

## File Structure

```
custom_components/hermes_assistant/
├── manifest.json         # Integration metadata
├── __init__.py          # Setup entry point + services
├── api.py               # Hermes API client
├── config_flow.py       # Config flow UI
├── conversation.py       # Assist conversation agent
├── sensor.py            # Gateway health sensors
├── const.py             # Constants (DOMAIN, PLATFORMS, defaults)
└── www/
    └── hermes-chat-card.js   # Lovelace chat card
```