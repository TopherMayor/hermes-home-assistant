# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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