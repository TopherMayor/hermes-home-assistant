# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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