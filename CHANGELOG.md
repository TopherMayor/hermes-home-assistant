# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.9] - 2026-06-17

### Changed
- `www/hermes-chat-card.js`: custom element renamed from `hermes-chat-card`
  to `hermes-chat-card-v3`. Dashboard config must also be updated to
  `type: custom:hermes-chat-card-v3`. This forces a clean re-registration
  when users have stale card classes cached in their browser.

## [0.1.8] - 2026-06-17

### Fixed
- `www/hermes-chat-card.js`: the `customElements.define()` call now
  checks `customElements.get()` first, so reloading the script (e.g. via
  a Lovelace resource URL change) doesn't throw "an element with this
  name is already defined".

## [0.1.7] - 2026-06-17

### Fixed
- `sensor.py`: the `model` sensor's `options` property was hardcoded
  to `["hermes-agent", "unknown"]`, which rejected the actual LLM model
  names (e.g. "MiniMax-M3") returned by `/api/sessions` in v0.1.6.
  The options are now dynamic: `[<current_value>, "unknown"]`.

## [0.1.6] - 2026-06-17

### Fixed
- `__init__.py`: the `model` sensor now shows the actual LLM in use
  (e.g. "MiniMax-M3") from the most recent session in `/api/sessions`,
  instead of the platform name "hermes-agent" returned by `/v1/capabilities`.

## [0.1.5] - 2026-06-17

### Fixed
- `www/hermes-chat-card.js`: `setConfig()` was mutating the config object
  HA passes in, which is frozen in HA 2026.6+. Trying to add a default
  property (`prominent`, etc.) threw `TypeError: cannot add property
  prominent, object is not extensible`. The fix is to build a fresh
  object instead of mutating the input.

## [0.1.4] - 2026-06-17

### Added
- `__init__.py`: coordinator now computes yesterday's cost and tokens, and
  percent-change trends:
  - `estimated_cost_yesterday`, `tokens_yesterday` — totals for sessions
    started in the 24h window before today (UTC)
  - `cost_trend_pct`, `token_trend_pct` — percent change vs yesterday;
    `None` (rendered as unknown) when yesterday is 0
- `sensor.py`: 5 new sensors for the above metrics.

### Changed
- `binary_sensor.py`: `HermesOnlineBinarySensor` simplified to read
  `coordinator.data` directly instead of tracking a separate timestamp.
  Now exposes `available` based on `coordinator.last_update_success`.
- `sensor.py`: removed `SensorDeviceClass.DATA_SIZE` from the three
  token sensors (`context_limit`, `context_pct`, `tokens_yesterday`) —
  HA 2026.6.3 rejects the `tokens` unit for DATA_SIZE. The sensors still
  report token counts as plain numeric values without device class.

### Known issue
- `binary_sensor.hermes_hermes_hermes_online` and `_connection_quality`
  may show `unknown` after `homeassistant.reload_config_entry` even
  though the underlying coordinator has fresh data. A full HA core
  restart reloads the binary sensors correctly.

## [0.1.3] - 2026-06-17

### Added
- `api.py`: new methods `async_get_sessions()`, `async_get_toolsets()`, `async_get_skills()` to fetch from the gateway's `/api/sessions`, `/v1/toolsets`, and `/v1/skills` endpoints.
- `__init__.py`: coordinator now fetches sessions, toolsets, and skills alongside health and capabilities. Computes per-session and aggregate metrics:
  - `context_limit` ← `tokens_today` (sum of all token types across sessions started today)
  - `context_pct` ← `tokens_last_session` (total tokens used by the most recent session)
  - `rss_mb` ← `active_sessions` (count of sessions without `ended_at`)

### Changed
- `sensor.py`: re-purposed the previously-unknown sensors to display the new data:
  - `context_limit` → DATA_SIZE, unit `tokens` (was DATA_SIZE/MB; now reports daily token usage)
  - `context_pct` → DATA_SIZE, unit `tokens` (was HUMIDITY/%; now reports last-session token usage)
  - `rss_mb` → unit `sessions`, no device class (was DATA_SIZE/MB; now reports active session count)
- `extra_state_attributes` updated for these sensors to describe what they now report (via a `metric` key).

## [0.1.2] - 2026-06-17

### Added
- `api.py`: new `async_get_capabilities()` method that calls the gateway's `/v1/capabilities` endpoint and returns model, platform, auth type, features, and runtime info.
- `__init__.py`: coordinator now fetches both `/health/detailed` AND `/v1/capabilities` and merges the responses into a single data dict. This populates sensor entities that were previously stuck on "unknown":
  - `model` ← `/v1/capabilities.model` (e.g. "hermes-agent")
  - `provider` ← `/v1/capabilities.auth.type` (e.g. "bearer")
  - `uptime_seconds` ← computed from `/health/detailed.updated_at` (approximates gateway start as 24h before the first-seen updated_at; tracks start time on the client object so subsequent polls use the same baseline)
  - `active_threads` ← mapped from `/health/detailed.active_agents`
  - `error_count` ← count of `platforms` whose state is not "connected" (proxy for gateway-level connection errors)

### Changed
- `sensor.py`: `error_count` sensor is now a numeric sensor (`SensorStateClass.MEASUREMENT`, unit "errors") rather than an enum/categorical, since it now reports an actual integer count. Removed the categorical `options` list for this sensor.

## [0.1.1] - 2026-06-17

### Fixed
- `sensor.py`: HA 2026.6.3+ strict sensor validation rejected the `version` and `provider` sensors because their `options` lists were hardcoded (`["0.14.0+", "unknown"]`) and didn't include the actual values returned by some gateway versions. `options` is now dynamic — it includes the current value plus a generic `"unknown"` fallback, so HA's enum validation passes regardless of the gateway-reported value.
- `sensor.py`: removed `SensorStateClass.TOTAL_INCREASING` from the `error_count` sensor. It's a categorical severity enum (`["none", "low", "medium", "high"]`), not a counter; the `TOTAL_INCREASING` state class contradicted the `SensorDeviceClass.ENUM` device class and could trigger validation errors in future HA releases.

### Changed
- `README.md`: replaced example private IP addresses in the documentation with generic placeholders (e.g. `<hermes-host>`) so the documentation is suitable for any user's network.
- `docs/api/openapi.yaml`: replaced the example server URL with `localhost` and a generic description so the OpenAPI spec is reusable.

### Security
- No secrets, API keys, or private network information is included in this release. The integration is fully configured at runtime via the config flow (gateway URL + API key).

## [Unreleased]

### Added
- `event.py`: HermesRunEventEntity and HermesGatewayEventEntity — SSE watcher that fires HA events (`hermes_assistant_run_started`, `hermes_assistant_run_completed`, `hermes_assistant_gateway_healthy`, etc.)
- `binary_sensor.py`: HermesOnlineBinarySensor (online/offline) and HermesConnectionQualitySensor (degraded detection)
- `button.py`: RefreshSensors, HealthCheck, ClearHistory, and optional Restart buttons
- `const.py`: PLATFORMS expanded to 5 platforms; EVENT_RUN_COMPLETED/RESPONSE_READY/STREAMING_DELTA constants
- `manifest.json`: all 5 supported_platforms registered; codeowners updated to @TopherMayor

### Changed
- `sensor.py`: expanded from 6 to 9 sensors (added context_limit, error_count, version, provider); added SensorStateClass (MEASUREMENT for context/threads/memory, TOTAL_INCREASING for uptime/errors); added extra_state_attributes for context thresholds, max_threads, swap_mb; updated manufacturer to "Hermes Agent"
- `manifest.json`: documentation/issue_tracker URLs now point to github.com/TopherMayor/hermes-home-assistant

<!-- templates
## [0.1.0] - YYYY-MM-DD

### Added
- Feature A
- Feature B

### Changed
- Changed X to improve Y

### Fixed
- Fixed bug where Z happened

### Deprecated
- Deprecated Y (remove in v0.2.0)

### Removed
- Removed deprecated Y

### Security
- Fixed vulnerability in X
-->