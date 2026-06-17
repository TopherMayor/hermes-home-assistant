"""event.py — Home Assistant event entities for Hermes.

Exposes real-time Hermes gateway events as HA event entities so automations
can react to run completions, streaming deltas, and gateway status changes.

Event types dispatched by Hermes:
  - hermes_assistant_run_completed  — fires when a background run finishes
  - hermes_assistant_response_ready — fires when a /v1/responses completes
  - hermes_assistant_streaming_delta — fires per streaming text chunk

This platform watches Hermes's SSE endpoint (/v1/runs/{run_id}/events) and
re-emits those events into the Home Assistant event bus.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, EVENT_RUN_COMPLETED, EVENT_RESPONSE_READY, EVENT_STREAMING_DELTA

_LOGGER = logging.getLogger(__name__)


class HermesRunEventEntity(Entity):
    """Event entity that watches Hermes run lifecycle events.

    Subscribes to the Hermes gateway's SSE stream for a given run_id and
    fires Home Assistant events for each lifecycle phase:
      - run.started
      - run.step_completed
      - run.approval_required
      - run.completed
      - run.failed
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_event_types: list[str] = [
        "run.started",
        "run.step_completed",
        "run.approval_required",
        "run.completed",
        "run.failed",
    ]

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        gateway_url: str,
        api_key: str,
        run_id: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._gateway_url = gateway_url.rstrip("/")
        self._api_key = api_key
        self._run_id = run_id
        self._task: Optional[asyncio.Task] = None
        self._attr_unique_id = f"{DOMAIN}_run_{run_id}"
        self._attr_name = f"Hermes Run {run_id[:8]}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Hermes {entry.data.get('name', 'Assistant')}",
            manufacturer="Hermes Agent",
            model="API Gateway",
        )

    async def async_added_to_hass(self) -> None:
        """Start listening to the Hermes run events SSE stream."""
        await super().async_added_to_hass()
        self._task = asyncio.create_task(self._watch_run_events())

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the SSE watcher when entity is removed."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_run_events(self) -> None:
        """Connect to Hermes SSE stream and fire HA events for each event received."""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }
        url = f"{self._gateway_url}/v1/runs/{self._run_id}/events"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Hermes run events stream returned status %s for run %s",
                            resp.status,
                            self._run_id,
                        )
                        return

                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue

                        try:
                            import json

                            event_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            _LOGGER.debug("Skipping non-JSON SSE data: %s", data_str[:100])
                            continue

                        event_type = event_data.get("type", "unknown")
                        payload = event_data.get("response", event_data)

                        # Map Hermes event types to HA event types
                        ha_event_type = f"{DOMAIN}_{event_type.replace('.', '_')}"
                        self._hass.bus.async_fire(
                            ha_event_type,
                            {
                                "run_id": self._run_id,
                                "gateway_url": self._gateway_url,
                                "event": event_type,
                                "data": payload,
                            },
                        )

                        _LOGGER.debug(
                            "Hermes event → HA event '%s' for run %s",
                            ha_event_type,
                            self._run_id,
                        )

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _LOGGER.error(
                "Error watching Hermes run events for run %s: %s",
                self._run_id,
                exc,
            )


class HermesGatewayEventEntity(Entity):
    """Event entity that listens to the Hermes gateway's global event stream.

    Watches /v1/capabilities or a dedicated events endpoint to capture
    gateway-level events (model changes, health status transitions, etc.)
    and fires them as Home Assistant events.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_event_types: list[str] = [
        "gateway.healthy",
        "gateway.unhealthy",
        "model.changed",
        "context.threshold_exceeded",
    ]

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        gateway_url: str,
        api_key: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._gateway_url = gateway_url.rstrip("/")
        self._api_key = api_key
        self._task: Optional[asyncio.Task] = None
        self._attr_unique_id = f"{DOMAIN}_gateway_events"
        self._attr_name = "Hermes Gateway Events"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Hermes {entry.data.get('name', 'Assistant')}",
            manufacturer="Hermes Agent",
        )

    async def async_added_to_hass(self) -> None:
        """Start listening to gateway events."""
        await super().async_added_to_hass()
        self._task = asyncio.create_task(self._watch_gateway_events())

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the event watcher when entity is removed."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_gateway_events(self) -> None:
        """Poll Hermes health endpoint and detect status transitions."""
        import aiohttp

        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._gateway_url}/health/detailed"

        was_healthy: Optional[bool] = None

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            is_healthy = data.get("status") == "ok"

                            # Fire event on status transition
                            if was_healthy is not None and is_healthy != was_healthy:
                                event_type = "gateway.healthy" if is_healthy else "gateway.unhealthy"
                                self._hass.bus.async_fire(
                                    f"{DOMAIN}_{event_type}",
                                    {
                                        "gateway_url": self._gateway_url,
                                        "status": data.get("status"),
                                        "model": data.get("model"),
                                        "uptime_seconds": data.get("uptime_seconds"),
                                    },
                                )

                            was_healthy = is_healthy
                        else:
                            if was_healthy is not None and was_healthy:
                                self._hass.bus.async_fire(
                                    f"{DOMAIN}_gateway_unhealthy",
                                    {"gateway_url": self._gateway_url, "http_status": resp.status},
                                )
                            was_healthy = False

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.debug("Gateway event polling error: %s", exc)

            await asyncio.sleep(30)  # poll every 30s


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up event platform for a config entry."""
    gateway_url = entry.data.get("gateway_url", "http://localhost:8642")
    api_key = entry.data.get("api_key", "")

    # Always add the gateway-level event watcher
    gateway_entity = HermesGatewayEventEntity(hass, entry, gateway_url, api_key)
    hass.data[DOMAIN].setdefault("entities", {})[entry.entry_id] = {
        **hass.data[DOMAIN].get(entry.entry_id, {}),
        "gateway_event_entity": gateway_entity,
    }

    # Register the gateway event entity
    @callback
    def async_add_gateway_event_entity():
        hass.helpers.entity.async_add_entities([gateway_entity])

    # Defer to platform setup complete
    hass.async_add_job(async_add_gateway_event_entity)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Clean up event entities when config entry is unloaded."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    entity = entry_data.get("gateway_event_entity")
    if entity:
        await entity.async_will_remove_from_hass()
    return True