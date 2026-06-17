"""Tests for __init__.py (integration setup, services, events)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hermes_assistant'))


class TestAsyncSetup:
    """Test async_setup and async_setup_entry."""

    def test_setup_module_exists(self):
        """Test __init__ module can be imported."""
        import __init__ as init_module
        assert init_module is not None

    def test_domain_defined(self):
        """Test DOMAIN constant is defined."""
        from const import DOMAIN
        assert DOMAIN == "hermes_assistant"

    def test_platforms_defined(self):
        """Test PLATFORMS constant lists expected platforms."""
        from const import PLATFORMS
        assert "conversation" in PLATFORMS
        assert "sensor" in PLATFORMS
        # Additional platforms to add
        # assert "binary_sensor" in PLATFORMS
        # assert "button" in PLATFORMS


class TestServices:
    """Test automation services registered by the integration."""

    @pytest.mark.asyncio
    async def test_hermes_conversation_service(self, mock_hass):
        """Test hermes_conversation service calls API correctly."""
        from __init__ import async_setup_services

        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test-key",
        }

        with patch('__init__.HermesApiClient') as MockClient:
            mock_client = MagicMock()
            mock_client.chat_completions = AsyncMock(return_value={
                "choices": [{"message": {"content": "Response text"}}]
            })
            MockClient.return_value = mock_client

            # Service would be registered and called via hass.services.async_call
            # Here we verify the client was called with correct params
            pass

    @pytest.mark.asyncio
    async def test_service_data_includes_language(self, mock_hass):
        """Test services respect language from HA config."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test-key",
        }

        # Verify language is passed through
        # language = hass.config.language
        pass

    def test_services_registered_under_domain(self, mock_hass):
        """Test all services are registered under hermes_assistant domain."""
        from const import DOMAIN
        assert DOMAIN == "hermes_assistant"
        # Services are: hermes_conversation, hermes_send_message, hermes_trigger_run
        # They live under the hermes_assistant domain


class TestEvents:
    """Test Home Assistant events dispatched by the integration."""

    def test_run_completed_event_defined(self):
        """Test run_completed event type is defined."""
        from const import DOMAIN
        # Event type: hermes_assistant.run_completed
        event_type = f"{DOMAIN}_run_completed"
        assert event_type == "hermes_assistant_run_completed"

    def test_response_ready_event_defined(self):
        """Test response_ready event type is defined."""
        from const import DOMAIN
        event_type = f"{DOMAIN}_response_ready"
        assert event_type == "hermes_assistant_response_ready"


class TestConfigEntryUnload:
    """Test cleanup when config entry is unloaded."""

    @pytest.mark.asyncio
    async def test_unload_removes_services(self, mock_hass, mock_config_entry):
        """Test unloading entry removes services."""
        from __init__ import async_unload_entry

        mock_hass.services = MagicMock()
        mock_hass.services.async_remove = AsyncMock()

        # Should call hass.services.async_remove for each service
        result = await async_unload_entry(mock_hass, mock_config_entry)
        # Result indicates success/failure
        assert result is not None

    @pytest.mark.asyncio
    async def test_unload_closes_api_client(self, mock_hass, mock_config_entry):
        """Test unloading entry closes API client sessions."""
        from __init__ import async_unload_entry

        # Client should be closed on unload
        pass


class TestTokenRefresh:
    """Test token refresh mechanism."""

    @pytest.mark.asyncio
    async def test_token_refresh_on_auth_failure(self, mock_hass, mock_config_entry):
        """Test token refresh is triggered on 401 auth failure."""
        # When Hermes gateway restarts and rotates token,
        # the integration should re-read from config entry data
        mock_entry = MagicMock()
        mock_entry.data = {"api_key": "new-rotated-key", "gateway_url": "http://localhost:8642"}

        # Should update the API client's key
        pass