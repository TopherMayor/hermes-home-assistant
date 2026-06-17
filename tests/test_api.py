"""Tests for HermesApiClient (api.py)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hermes_assistant'))

from api import HermesApiClient, HermesConnectionError, HermesAuthError, HermesApiError


class TestHermesApiClientInit:
    """Test HermesApiClient initialization."""

    def test_init_with_defaults(self):
        """Test client initializes with correct defaults."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        assert client.url == "http://localhost:8642"
        assert client.api_key == "test-key"
        assert client._session is None

    def test_init_with_trailing_slash(self):
        """Test URL stripping handles trailing slashes."""
        client = HermesApiClient("http://localhost:8642/", "test-key")
        assert client.url == "http://localhost:8642"

    def test_init_custom_timeout(self):
        """Test custom timeout is set."""
        client = HermesApiClient("http://localhost:8642", "test-key", timeout=60)
        assert client._timeout == 60


class TestHermesApiClientProperties:
    """Test HermesApiClient property accessors."""

    def test_headers_includes_auth(self):
        """Test Authorization header is set."""
        client = HermesApiClient("http://localhost:8642", "my-secret-key")
        assert client.headers["Authorization"] == "Bearer my-secret-key"
        assert client.headers["Content-Type"] == "application/json"


class TestHermesApiClientHealth:
    """Test health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        with patch.object(client, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await client.health_check()
            assert result is mock_response

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        """Test health check raises HermesConnectionError on connection failure."""
        client = HermesApiClient("http://localhost:8642", "test-key")

        with patch.object(client, '_request', side_effect=HermesConnectionError("Connection refused")):
            with pytest.raises(HermesConnectionError):
                await client.health_check()


class TestHermesApiClientChat:
    """Test chat completion methods."""

    @pytest.mark.asyncio
    async def test_chat_completions_success(self, sample_chat_response):
        """Test successful chat completion request."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=sample_chat_response)
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, '_request', new_callable=AsyncMock, return_value=mock_response):
            result = await client.chat_completions(messages=[{"role": "user", "content": "Hello"}])
            assert result == sample_chat_response

    @pytest.mark.asyncio
    async def test_chat_completions_with_model(self):
        """Test chat completions with explicit model."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"choices": []})
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, '_request', new_callable=AsyncMock, return_value=mock_response) as mock_req:
            await client.chat_completions(
                messages=[{"role": "user", "content": "Hi"}],
                model="minimax-m2.1"
            )
            call_args = mock_req.call_args
            # verify model is passed in request body
            body = call_args.kwargs.get('json', {})
            assert body.get('model') == "minimax-m2.1"

    @pytest.mark.asyncio
    async def test_chat_completions_auth_failure(self):
        """Test 401 raises HermesAuthError."""
        client = HermesApiClient("http://localhost:8642", "test-key")

        with patch.object(client, '_request', side_effect=HermesAuthError("Invalid token")):
            with pytest.raises(HermesAuthError):
                await client.chat_completions(messages=[{"role": "user", "content": "Hi"}])


class TestHermesApiClientStreaming:
    """Test streaming chat completion methods."""

    @pytest.mark.asyncio
    async def test_streaming_response_success(self, sample_stream_chunk):
        """Test successful streaming response parsing."""
        client = HermesApiClient("http://localhost:8642", "test-key")

        chunks = [
            b'data: {"id":"1","choices":[{"delta":{"content":"Hello"}}]}\n\n',
            b'data: {"id":"1","choices":[{"delta":{"content":" world"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]

        async def mock_generator():
            for chunk in chunks:
                yield chunk

        mock_response = AsyncMock()
        mock_response.content.iter_chunks = mock_generator

        with patch.object(client, '_post_raw', new_callable=AsyncMock, return_value=mock_response):
            collected = []
            async for chunk in client.stream_chat_completions(messages=[{"role": "user", "content": "Hi"}]):
                collected.append(chunk)
            assert len(collected) == 3

    @pytest.mark.asyncio
    async def test_streaming_with_model_param(self):
        """Test streaming passes model parameter correctly."""
        client = HermesApiClient("http://localhost:8642", "test-key")

        mock_response = AsyncMock()
        mock_response.content.iter_chunks = AsyncMock(return_value=iter([]))

        with patch.object(client, '_post_raw', new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await client.stream_chat_completions(
                messages=[{"role": "user", "content": "Hi"}],
                model="custom-model"
            )
            # verify model was in the JSON body sent
            call_body = mock_post.call_args.kwargs.get('json', {})
            assert call_body.get('model') == "custom-model"


class TestHermesApiClientErrors:
    """Test error handling in HermesApiClient."""

    @pytest.mark.asyncio
    async def test_connection_error_on_network_failure(self):
        """Test HermesConnectionError raised on network errors."""
        client = HermesApiClient("http://localhost:8642", "test-key")

        with patch.object(client, '_request', side_effect=aiohttp.ClientError("Network error")):
            with pytest.raises(HermesConnectionError):
                await client.health_check()

    @pytest.mark.asyncio
    async def test_api_error_on_500_response(self):
        """Test HermesApiError raised on 500 server errors."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        mock_response = AsyncMock()
        mock_response.status = 500

        with patch.object(client, '_request', new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(HermesApiError):
                await client.health_check()


class TestHermesApiClientTokenRefresh:
    """Test token refresh mechanism."""

    @pytest.mark.asyncio
    async def test_set_api_key_updates_headers(self):
        """Test setting new API key updates Authorization header."""
        client = HermesApiClient("http://localhost:8642", "old-key")
        assert client.headers["Authorization"] == "Bearer old-key"

        await client.set_api_key("new-key")
        assert client.api_key == "new-key"
        assert client.headers["Authorization"] == "Bearer new-key"

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test session cleanup."""
        client = HermesApiClient("http://localhost:8642", "test-key")
        client._session = AsyncMock()

        await client.close()
        client._session.close.assert_called_once()
        assert client._session is None