"""Tests for config_flow.py (HA config entry flow)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import voluptuous as vol

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hermes_assistant'))

from config_flow import (
    _validate_gateway_url,
    _test_connection,
    HermesConfigFlow,
    STEP_USER_DATA_SCHEMA,
)


class TestURLValidation:
    """Test URL validation helper."""

    def test_valid_http_url(self):
        """Test valid HTTP URL passes validation."""
        url = _validate_gateway_url("http://localhost:8642")
        assert url == "http://localhost:8642"

    def test_valid_ip_with_port(self):
        """Test valid IP with port passes validation."""
        url = _validate_gateway_url("http://192.168.1.100:8642")
        assert url == "http://192.168.1.100:8642"

    def test_strips_trailing_slash(self):
        """Test trailing slash is stripped."""
        url = _validate_gateway_url("http://localhost:8642/")
        assert url == "http://localhost:8642"

    def test_invalid_url_raises(self):
        """Test invalid URL raises vol.Invalid."""
        with pytest.raises(vol.Invalid):
            _validate_gateway_url("not-a-url")

    def test_missing_scheme_raises(self):
        """Test URL without scheme raises vol.Invalid."""
        with pytest.raises(vol.Invalid):
            _validate_gateway_url("localhost:8642")

    def test_https_url_allowed(self):
        """Test HTTPS URLs are allowed."""
        url = _validate_gateway_url("https://hermes.example.com")
        assert url == "https://hermes.example.com"

    def test_ip_v6_address(self):
        """Test IPv6 addresses are handled."""
        url = _validate_gateway_url("http://[::1]:8642")
        assert url == "http://[::1]:8642"


class TestSchemaValidation:
    """Test configuration schema validation."""

    def test_schema_requires_url(self):
        """Test schema requires gateway_url field."""
        with pytest.raises(vol.MultipleInvalid):
            STEP_USER_DATA_SCHEMA({})

    def test_schema_requires_api_key(self):
        """Test schema requires api_key field."""
        with pytest.raises(vol.MultipleInvalid):
            STEP_USER_DATA_SCHEMA({"gateway_url": "http://localhost:8642"})

    def test_schema_valid_data(self):
        """Test schema accepts valid data."""
        data = STEP_USER_DATA_SCHEMA({
            "gateway_url": "http://localhost:8642",
            "api_key": "my-secret-key",
        })
        assert data["gateway_url"] == "http://localhost:8642"
        assert data["api_key"] == "my-secret-key"

    def test_schema_strips_url_whitespace(self):
        """Test schema strips whitespace from URL."""
        data = STEP_USER_DATA_SCHEMA({
            "gateway_url": "  http://localhost:8642  ",
            "api_key": "key",
        })
        assert data["gateway_url"] == "http://localhost:8642"


class TestConnectionTesting:
    """Test _test_connection helper."""

    @pytest.mark.asyncio
    async def test_connection_success(self):
        """Test successful connection returns True."""
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value=MagicMock(ok=True))

        with patch('config_flow.HermesApiClient', return_value=mock_client):
            result = await _test_connection("http://localhost:8642", "test-key")
            assert result is True

    @pytest.mark.asyncio
    async def test_connection_invalid_url(self):
        """Test connection fails gracefully on invalid URL."""
        result = await _test_connection("invalid-url", "test-key")
        assert result is False

    @pytest.mark.asyncio
    async def test_connection_auth_failure(self):
        """Test connection returns False on auth failure."""
        from api import HermesAuthError
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(side_effect=HermesAuthError("Invalid"))

        with patch('config_flow.HermesApiClient', return_value=mock_client):
            result = await _test_connection("http://localhost:8642", "bad-key")
            assert result is False

    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection returns False on timeout."""
        import aiohttp
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(side_effect=aiohttp.ServerTimeoutError())

        with patch('config_flow.HermesApiClient', return_value=mock_client):
            result = await _test_connection("http://localhost:8642", "test-key")
            assert result is False


class TestConfigFlowClass:
    """Test HermesConfigFlow class integration with HA."""

    def test_flow_shows_init_step(self):
        """Test config flow has async_step_user."""
        flow = HermesConfigFlow()
        assert hasattr(flow, 'async_step_user')
        assert callable(flow.async_step_user)

    def test_flow_has_config_schema(self):
        """Test flow has correct STEP_USER_DATA_SCHEMA."""
        assert STEP_USER_DATA_SCHEMA is not None
        # Verify it has the expected keys
        schema_dict = dict(STEP_USER_DATA_SCHEMA.schema)
        assert 'gateway_url' in schema_dict
        assert 'api_key' in schema_dict