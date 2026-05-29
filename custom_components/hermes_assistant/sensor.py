"""Sensor entities for Hermes gateway health monitoring."""

import logging
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .api import HermesApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Sensor configuration: (key, name, device_class, unit, icon, entity_category)
SENSORS = [
    ("model", "Hermes Model", SensorDeviceClass.ENUM, None, "mdi:robot", EntityCategory.DIAGNOSTIC),
    ("context_pct", "Context Usage", SensorDeviceClass.PERCENTAGE, "%", "mdi:memory", EntityCategory.DIAGNOSTIC),
    ("uptime_seconds", "Gateway Uptime", SensorDeviceClass.DURATION, "s", "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
    ("active_threads", "Active Threads", None, "threads", "mdi:account-multiple", EntityCategory.DIAGNOSTIC),
    ("rss_mb", "Memory Usage", SensorDeviceClass.DATA_SIZE, "MB", "mdi:memory", EntityCategory.DIAGNOSTIC),
    ("online", "Gateway Online", SensorDeviceClass.ENUM, None, "mdi:lan-connect", EntityCategory.DIAGNOSTIC),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up Hermes sensor entities from a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    entities = []
    for (key, name, device_class, unit, icon, category) in SENSORS:
        entity = HermesSensorEntity(
            coordinator=coordinator,
            entry_id=entry.entry_id,
            key=key,
            name=name,
            device_class=device_class,
            unit=unit,
            icon=icon,
            entity_category=category,
        )
        entities.append(entity)

    async_add_entities(entities)


class HermesSensorEntity(SensorEntity):
    """A sensor entity exposing Hermes gateway health and status."""

    _attr_attribution = "Hermes Agent Gateway"

    def __init__(
        self,
        coordinator,
        entry_id: str,
        key: str,
        name: str,
        device_class: Optional[SensorDeviceClass],
        unit: Optional[str],
        icon: str,
        entity_category: EntityCategory,
    ):
        self.coordinator = coordinator
        self.entry_id = entry_id
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        self._attr_device_class = device_class

        # Entity ID
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"

        # Device info
        entry_data = coordinator.hass.data.get(DOMAIN, {}).get(entry_id, {})
        gateway_url = entry_data.get("gateway_url", "unknown")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"Hermes Gateway ({gateway_url})",
            "manufacturer": "Nous Research",
            "model": "Hermes Agent",
            "sw_version": "0.14.0+",
        }

    @property
    def available(self) -> bool:
        """Return True if the coordinator has data."""
        return self.coordinator.data is not None

    @property
    def native_value(self):
        """Return the current sensor value from coordinator data."""
        data = self.coordinator.data or {}

        # Error states
        if "error" in data:
            if data["error"] == "gateway_offline":
                return "offline"
            elif data["error"] == "auth_failed":
                return "auth_failed"

        value = data.get(self._key)
        if value is None:
            return None

        # Convert uptime integer to HumanReadable
        if self._key == "uptime_seconds":
            return int(value)

        return value

    @property
    def options(self) -> Optional[list[str]]:
        """Return options for enum device class sensors."""
        if self._key == "model":
            return ["hermes-agent"]
        if self._key == "online":
            return ["online", "offline", "auth_failed"]
        return None

    async def async_update(self):
        """Trigger a coordinator refresh."""
        await self.coordinator.async_refresh()