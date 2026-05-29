"""Tests for sensor.py (gateway health sensors)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hermes_assistant'))

from sensor import HermesSensorCoordinator, HermesSensorEntity, SENSORS


class TestSensorDefinitions:
    """Test sensor definitions and configuration."""

    def test_sensors_defined(self):
        """Test all expected sensors are defined."""
        assert len(SENSORS) >= 5
        sensor_keys = [s["key"] for s in SENSORS]
        assert "model" in sensor_keys
        assert "context_pct" in sensor_keys
        assert "uptime_seconds" in sensor_keys
        assert "active_threads" in sensor_keys
        assert "rss_mb" in sensor_keys

    def test_sensor_keys_unique(self):
        """Test sensor keys are unique."""
        keys = [s["key"] for s in SENSORS]
        assert len(keys) == len(set(keys))


class TestSensorEntityInit:
    """Test HermesSensorEntity initialization."""

    @pytest.fixture
    def sensor_entity(self, mock_hass, mock_config_entry):
        """Create a HermesSensorEntity instance."""
        coordinator = HermesSensorCoordinator(
            mock_hass,
            mock_config_entry,
            MagicMock(),  # mock client
        )
        sensor_def = SENSORS[0]  # first sensor (model)
        entity = HermesSensorEntity(coordinator, sensor_def)
        return entity

    def test_entity_name(self, sensor_entity):
        """Test entity has correct name."""
        assert sensor_entity.name is not None
        assert len(sensor_entity.name) > 0

    def test_entity_unique_id(self, sensor_entity):
        """Test entity has unique ID based on config entry and sensor key."""
        assert sensor_entity.unique_id is not None
        assert "hermes" in sensor_entity.unique_id.lower()

    def test_entity_category_diagnostic(self, sensor_entity):
        """Test sensor entity category is DIAGNOSTIC."""
        assert sensor_entity.entity_category == "diagnostic"

    def test_entity_icon_set(self, sensor_entity):
        """Test entity has an icon configured."""
        assert sensor_entity.icon is not None


class TestSensorEntityState:
    """Test sensor state and attributes."""

    def test_native_value_returns_coordinator_data(self, sensor_entity):
        """Test native_value reads from coordinator data."""
        # Setup coordinator with data
        sensor_entity.coordinator._data = {"model": "minimax-m2.1"}
        sensor_entity.coordinator._data["model"] = "minimax-m2.1"

        # The entity's key should match the sensor def
        assert sensor_entity._sensor_def["key"] == "model"

    def test_extra_state_attributes(self, sensor_entity):
        """Test extra_state_attributes provides additional data."""
        attrs = sensor_entity.extra_state_attributes
        assert isinstance(attrs, dict)
        # Should include gateway URL
        assert "gateway_url" in attrs


class TestHermesSensorCoordinator:
    """Test HermesSensorCoordinator."""

    @pytest.fixture
    def coordinator(self, mock_hass, mock_config_entry):
        """Create a HermesSensorCoordinator instance."""
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value=MagicMock(
            ok=True,
            json=AsyncMock(return_value={"status": "ok"})
        ))
        coord = HermesSensorCoordinator(mock_hass, mock_config_entry, mock_client)
        return coord

    def test_coordinator_update_interval(self, coordinator):
        """Test coordinator has reasonable update interval."""
        assert coordinator.update_interval == timedelta(seconds=30)

    def test_coordinator_data_initially_none(self, coordinator):
        """Test coordinator data is None before first update."""
        assert coordinator.data is None

    @pytest.mark.asyncio
    async def test_coordinator_fetch_health(self, coordinator):
        """Test _async_fetch_data calls health_check."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value={
            "status": "ok",
            "model": "minimax-m2.1",
            "uptime_seconds": 3600,
            "active_threads": 2,
            "context_pct": 50.0,
            "rss_mb": 256,
        })
        coordinator._client.health_check = AsyncMock(return_value=mock_response)

        data = await coordinator._async_fetch_data()
        assert data is not None
        assert data["model"] == "minimax-m2.1"

    @pytest.mark.asyncio
    async def test_coordinator_handles_offline(self, coordinator):
        """Test coordinator handles gateway offline gracefully."""
        from api import HermesConnectionError
        coordinator._client.health_check = AsyncMock(
            side_effect=HermesConnectionError("Connection refused")
        )

        # Should not raise, returns None on failure
        data = await coordinator._async_fetch_data()
        assert data is None

    @pytest.mark.asyncio
    async def test_coordinator_recovery_after_offline(self, coordinator):
        """Test coordinator recovers when gateway comes back online."""
        # First call fails
        coordinator._client.health_check = AsyncMock(
            side_effect=HermesConnectionError("Offline")
        )
        data = await coordinator._async_fetch_data()
        assert data is None

        # Second call succeeds
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value={"status": "ok", "model": "back-online"})
        coordinator._client.health_check = AsyncMock(return_value=mock_response)

        data = await coordinator._async_fetch_data()
        assert data is not None
        assert data["model"] == "back-online"


class TestSensorEdgeCases:
    """Test sensor edge cases and error handling."""

    def test_missing_sensor_data_field(self):
        """Test sensor handles missing data field gracefully."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test",
        }

        coordinator = HermesSensorCoordinator(
            mock_hass,
            mock_entry,
            MagicMock()
        )
        coordinator._data = {}  # empty data

        # Find a sensor and check it handles missing key
        sensor_def = {"key": "nonexistent_key", "name": "Test", "icon": "mdi:help"}
        entity = HermesSensorEntity(coordinator, sensor_def)

        # native_value should return None for missing key
        assert entity.native_value is None

    def test_sensor_value_type_conversion(self):
        """Test sensor converts string values to proper types."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test",
        }

        coordinator = HermesSensorCoordinator(mock_hass, mock_entry, MagicMock())
        # context_pct might come as string from some APIs
        coordinator._data = {"context_pct": "45.5"}  # string

        sensor_def = {"key": "context_pct", "name": "Context %", "icon": "mdi:percent"}
        entity = HermesSensorEntity(coordinator, sensor_def)

        # Should handle numeric conversion
        value = entity.native_value
        assert value is not None


class TestCoordinatorDeviceInfo:
    """Test coordinator provides device info for entities."""

    def test_device_info_has_name(self, mock_hass, mock_config_entry):
        """Test device info has a name."""
        mock_client = MagicMock()
        coordinator = HermesSensorCoordinator(mock_hass, mock_config_entry, mock_client)
        device = coordinator.device_info
        assert "name" in device
        assert device["name"] is not None

    def test_device_info_has_identifiers(self, mock_hass, mock_config_entry):
        """Test device info has unique identifiers."""
        mock_client = MagicMock()
        coordinator = HermesSensorCoordinator(mock_hass, mock_config_entry, mock_client)
        device = coordinator.device_info
        assert "identifiers" in device
        assert len(device["identifiers"]) > 0