"""binary_sensor.py — Hermes gateway online/offline status sensors."""

import logging
from typing import Optional

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HermesOnlineBinarySensor(CoordinatorEntity):
    """Binary sensor that tracks Hermes gateway online/offline state.

    Mirrors the pattern from OpenClaw's binary_sensor for addon status.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
        gateway_url: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._gateway_url = gateway_url
        self._attr_unique_id = f"{DOMAIN}_online"
        self._attr_name = "Hermes Online"
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
            model="API Gateway",
        )

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if Hermes gateway is online."""
        if self.coordinator.data is None:
            return None
        # Error markers mean offline
        if self.coordinator.data.get("error") in ("auth_failed", "connection_failed"):
            return False
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        attrs = {}
        if self.coordinator.data:
            attrs["gateway_url"] = self._gateway_url
            if "error" in self.coordinator.data:
                attrs["last_error"] = self.coordinator.data["error"]
        return attrs


class HermesConnectionQualitySensor(CoordinatorEntity):
    """Binary sensor tracking connection quality — Good / Degraded.

    Based on poll failure rate and response latency from the coordinator.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
        gateway_url: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._gateway_url = gateway_url
        self._attr_unique_id = f"{DOMAIN}_connection_quality"
        self._attr_name = "Hermes Connection Quality"
        self._failure_count = 0
        self._success_count = 0
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", "Assistant")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Hermes {name}",
            manufacturer="Hermes Agent",
        )

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if connection quality is Good.

        Degraded if failure rate > 20% over last 10 polls.
        """
        total = self._failure_count + self._success_count
        if total < 3:
            return None  # Not enough data

        failure_rate = self._failure_count / total
        return failure_rate < 0.2

    def update_success(self) -> None:
        """Record a successful poll."""
        self._success_count += 1
        self._trim_counts()

    def update_failure(self) -> None:
        """Record a failed poll."""
        self._failure_count += 1
        self._trim_counts()

    def _trim_counts(self) -> None:
        """Keep counts bounded to last 10 polls."""
        if self._success_count + self._failure_count > 10:
            # Halve both to keep sliding window
            self._success_count //= 2
            self._failure_count //= 2

    @property
    def extra_state_attributes(self) -> dict:
        """Return connection quality attributes."""
        total = self._success_count + self._failure_count
        return {
            "gateway_url": self._gateway_url,
            "total_polls": total,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up binary sensor entities for a config entry."""
    from . import HermesApiClient

    gateway_url = entry.data.get("gateway_url", "http://localhost:8642")
    api_key = entry.data.get("api_key", "")

    # Get the coordinator from hass.data (set up in __init__.py)
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    if coordinator is None:
        _LOGGER.warning("No coordinator found for binary sensor setup")
        return False

    online_sensor = HermesOnlineBinarySensor(
        hass, entry, coordinator, gateway_url
    )
    quality_sensor = HermesConnectionQualitySensor(
        hass, entry, coordinator, gateway_url
    )

    @property
    def async_add_binary_sensors():
        hass.helpers.entity.async_add_entities([online_sensor, quality_sensor])

    hass.async_add_job(async_add_binary_sensors)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload binary sensor entities."""
    return True