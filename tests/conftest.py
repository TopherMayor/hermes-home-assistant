"""pytest fixtures and shared test utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp.ClientSession for API tests."""
    session = AsyncMock()
    session.post = AsyncMock()
    session.get = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_hass():
    """Mock hass object for Home Assistant integration tests."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.services = MagicMock()
    hass.bus = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Mock a config entry for the Hermes integration."""
    entry = MagicMock()
    entry.entry_id = "test_entry_123"
    entry.data = {
        "gateway_url": "http://localhost:8642",
        "api_key": "test-api-key",
        "name": "Hermes",
    }
    entry.options = {}
    return entry


@pytest.fixture
def hermes_gateway_url():
    """Standard Hermes gateway URL for tests."""
    return "http://localhost:8642"


@pytest.fixture
def hermes_api_key():
    """Standard Hermes API key for tests."""
    return "test-hermes-api-key-12345"


@pytest.fixture
def sample_health_response():
    """Sample /health/detailed response from Hermes gateway."""
    return {
        "status": "ok",
        "uptime_seconds": 86400,
        "model": "minimax-m2.1",
        "context_pct": 45.2,
        "active_threads": 3,
        "rss_mb": 512,
        "version": "1.2.0",
    }


@pytest.fixture
def sample_chat_response():
    """Sample /v1/chat/completions response."""
    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "created": 1704067200,
        "model": "minimax-m2.1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


@pytest.fixture
def sample_stream_chunk():
    """Sample SSE chunk from streaming response."""
    return b'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1704067200,"model":"minimax-m2.1","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'