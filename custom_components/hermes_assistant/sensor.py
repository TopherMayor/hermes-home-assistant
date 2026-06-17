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

# Sensor configuration: (key, name, device_class, unit, icon, entity_category, state_class)
SENSORS = [
    ("model", "Hermes Model", SensorDeviceClass.ENUM, None, "mdi:robot", EntityCategory.DIAGNOSTIC, None),
    ("context_pct", "Context Usage", SensorDeviceClass.HUMIDITY, "%", "mdi:memory", EntityCategory.DIAGNOSTIC, SensorStateClass.MEASUREMENT),
    ("context_limit", "Context Limit", SensorDeviceClass.DATA_SIZE, "tokens", "mdi:database", EntityCategory.DIAGNOSTIC, None),
    ("uptime_seconds", "Gateway Uptime", SensorDeviceClass.DURATION, "s", "mdi:clock-outline", EntityCategory.DIAGNOSTIC, SensorStateClass.TOTAL_INCREASING),
    ("active_threads", "Active Threads", None, "threads", "mdi:account-multiple", EntityCategory.DIAGNOSTIC, SensorStateClass.MEASUREMENT),
    ("rss_mb", "Memory Usage", SensorDeviceClass.DATA_SIZE, "MB", "mdi:memory", EntityCategory.DIAGNOSTIC, SensorStateClass.MEASUREMENT),
    ("error_count", "Error Count", SensorDeviceClass.ENUM, None, "mdi:alert-circle", EntityCategory.DIAGNOSTIC, None),  # severity enum; do not use TOTAL_INCREASING here
    ("version", "Hermes Version", SensorDeviceClass.ENUM, None, "mdi:information", EntityCategory.DIAGNOSTIC, None),
    ("provider", "LLM Provider", SensorDeviceClass.ENUM, None, "mdi:cloud", EntityCategory.DIAGNOSTIC, None),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up Hermes sensor entities from a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    entities = []
    for row in SENSORS:
        key, name, device_class, unit, icon, category, state_class = row
        entity = HermesSensorEntity(
            coordinator=coordinator,
            entry_id=entry.entry_id,
            key=key,
            name=name,
            device_class=device_class,
            unit=unit,
            icon=icon,
            entity_category=category,
            state_class=state_class,
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
        state_class: Optional[SensorStateClass] = None,
    ):
        self.coordinator = coordinator
        self.entry_id = entry_id
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        self._attr_device_class = device_class
        self._attr_state_class = state_class

        # Entity ID
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{key}"

        # Device info
        entry_data = coordinator.hass.data.get(DOMAIN, {}).get(entry_id, {})
        gateway_url = entry_data.get("gateway_url", "unknown")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"Hermes Gateway ({gateway_url})",
            "manufacturer": "Hermes Agent",
            "model": "API Gateway",
            "sw_version": entry_data.get("version", "0.14+"),
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

        # Convert uptime integer to duration seconds
        if self._key == "uptime_seconds":
            return int(value)

        return value

    @property
    def options(self) -> Optional[list[str]]:
        """Return options for enum device class sensors.

        For version and provider, the values are dynamic — the gateway
        may report a version we don't know about in advance, or a new
        LLM provider name. We include the current value plus a generic
        "unknown" fallback so HA's enum validation passes either way.
        """
        if self._key == "model":
            return ["hermes-agent", "unknown"]
        if self._key == "online":
            return ["online", "offline", "auth_failed"]
        if self._key == "error_count":
            return ["none", "low", "medium", "high"]
        if self._key == "version":
            data = self.coordinator.data or {}
            current = data.get("version") if isinstance(data, dict) else None
            opts = [v for v in (current, "unknown") if v]
            return opts or ["unknown"]
        if self._key == "provider":
            data = self.coordinator.data or {}
            provider = data.get("provider") if isinstance(data, dict) else None
            return [provider, "unknown"] if provider else ["unknown"]
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes for richer diagnostics."""
        attrs = {}
        data = self.coordinator.data or {}
        if self._key == "context_pct":
            attrs["warning_threshold"] = 80
            attrs["critical_threshold"] = 95
        if self._key == "active_threads":
            attrs["max_threads"] = data.get("max_threads", 10)
        if self._key == "rss_mb":
            attrs["swap_mb"] = data.get("swap_mb", 0)
        return attrs

    async def async_update(self):
        """Trigger a coordinator refresh."""
        await self.coordinator.async_refresh()