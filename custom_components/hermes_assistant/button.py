"""button.py — Hermes gateway control buttons.

Provides HA button entities for:
  - Restart gateway (POST /v1/runs/{run_id}/stop + restart signal)
  - Refresh sensors (force immediate coordinator refresh)
  - Trigger health check (hit /health/detailed on demand)
  - Clear conversation history (invalidate conversation tracking)
"""

import logging
from typing import Any, Dict

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HermesRefreshSensorsButton(ButtonEntity):
    """Button to force an immediate sensor refresh."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
        gateway_url: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._gateway_url = gateway_url
        self._attr_unique_id = f"{DOMAIN}_refresh_sensors"
        self._attr_name = "Refresh Sensors"

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
        )

    async def async_press(self) -> None:
        """Trigger immediate coordinator refresh."""
        await self._coordinator.async_refresh()
        _LOGGER.debug("Manual sensor refresh triggered via button")


class HermesHealthCheckButton(ButtonEntity):
    """Button to trigger a Hermes gateway health check."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.IDENTIFY
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        gateway_url: str,
        api_key: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._gateway_url = gateway_url
        self._api_key = api_key
        self._attr_unique_id = f"{DOMAIN}_health_check"
        self._attr_name = "Health Check"

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
        )

    async def async_press(self) -> None:
        """Hit /health/detailed and log the result."""
        import aiohttp

        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._gateway_url}/health/detailed"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()
                    _LOGGER.info(
                        "Manual health check result for %s: status=%s model=%s uptime=%s",
                        self._gateway_url,
                        data.get("status"),
                        data.get("model"),
                        data.get("uptime_seconds"),
                    )
                    # Fire an event so automations can react
                    self._hass.bus.async_fire(
                        f"{DOMAIN}_health_check_completed",
                        {
                            "gateway_url": self._gateway_url,
                            "status": data.get("status"),
                            "model": data.get("model"),
                            "uptime_seconds": data.get("uptime_seconds"),
                            "active_threads": data.get("active_threads"),
                            "context_pct": data.get("context_pct"),
                        },
                    )
        except Exception as exc:
            _LOGGER.warning("Health check button failed: %s", exc)
            self._hass.bus.async_fire(
                f"{DOMAIN}_health_check_failed",
                {"gateway_url": self._gateway_url, "error": str(exc)},
            )


class HermesClearHistoryButton(ButtonEntity):
    """Button to clear conversation history tracked by the integration."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_icon = "mdi:history-clear"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_clear_history"
        self._attr_name = "Clear Conversation History"

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
        )

    async def async_press(self) -> None:
        """Clear conversation history from the integration."""
        from .conversation import HermesConversationAgent

        # Access the conversation agent from hass.data if it exists
        entry_data = self._hass.data[DOMAIN].get(self._entry.entry_id, {})
        agent = entry_data.get("conversation_agent")

        if agent and hasattr(agent, "_conversation_history"):
            agent._conversation_history.clear()
            _LOGGER.info("Conversation history cleared via button")
            self._hass.bus.async_fire(
                f"{DOMAIN}_history_cleared",
                {"entry_id": self._entry.entry_id},
            )
        else:
            _LOGGER.debug("No conversation history to clear")


class HermesRestartButton(ButtonEntity):
    """Button to request Hermes gateway restart via Hermes local SSH.

    This button SSHs to the Hermes host and runs `hermes gateway restart`.
    Requires the SSH credentials to be configured in the integration config.
    """

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:restart"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_restart_gateway"
        self._attr_name = "Restart Gateway"

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
        )

    async def async_press(self) -> None:
        """SSH to Hermes host and run `hermes gateway restart`."""
        ssh_host = self._entry.data.get("ssh_host")
        ssh_user = self._entry.data.get("ssh_user")
        ssh_key_path = self._entry.data.get("ssh_key_path")

        if not ssh_host:
            _LOGGER.warning(
                "Restart button pressed but SSH host not configured. "
                "Set 'ssh_host' in the integration configuration."
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_restart_failed",
                {"reason": "ssh_host not configured", "entry_id": self._entry.entry_id},
            )
            return

        import asyncio
        import asyncssh

        try:
            async with asyncssh.connect(
                host=ssh_host,
                username=ssh_user or "root",
                key_filename=ssh_key_path,
            ) as conn:
                result = await conn.run("hermes gateway restart", check=True)
                _LOGGER.info(
                    "Gateway restart initiated via button: %s",
                    result.stdout.strip() or "command sent",
                )
                self._hass.bus.async_fire(
                    f"{DOMAIN}_restart_initiated",
                    {"ssh_host": ssh_host, "entry_id": self._entry.entry_id},
                )
        except Exception as exc:
            _LOGGER.error("Gateway restart button failed: %s", exc)
            self._hass.bus.async_fire(
                f"{DOMAIN}_restart_failed",
                {"ssh_host": ssh_host, "error": str(exc), "entry_id": self._entry.entry_id},
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up button entities for a config entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")
    gateway_url = entry.data.get("gateway_url", "http://localhost:8642")
    api_key = entry.data.get("api_key", "")

    buttons = [
        HermesRefreshSensorsButton(hass, entry, coordinator, gateway_url),
        HermesHealthCheckButton(hass, entry, gateway_url, api_key),
        HermesClearHistoryButton(hass, entry),
    ]

    # Only add restart button if SSH host is configured
    if entry.data.get("ssh_host"):
        buttons.append(HermesRestartButton(hass, entry))

    @property
    def async_add_buttons():
        hass.helpers.entity.async_add_entities(buttons)

    hass.async_add_job(async_add_buttons)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload button entities."""
    return True