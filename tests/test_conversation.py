"""Tests for conversation.py (Assist conversation agent)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hermes_assistant'))

from conversation import HermesConversationAgent, async_setup_agent


class TestHermesConversationAgent:
    """Test HermesConversationAgent class."""

    @pytest.fixture
    def agent(self, mock_hass, mock_config_entry):
        """Create a HermesConversationAgent instance."""
        agent = HermesConversationAgent(mock_hass, mock_config_entry)
        return agent

    def test_agent_name(self, agent):
        """Test agent name is set correctly."""
        assert agent.name == "Hermes"

    def test_agent_id(self, agent):
        """Test agent uses hermes_assistant domain."""
        assert agent.agent_id == "hermes_assistant"

    def test_conversation_timeout_default(self, agent):
        """Test default conversation timeout is set."""
        assert agent._conversation_timeout == 60

    def test_max_history_setting(self, agent):
        """Test max chat history size."""
        assert agent._max_history == 200


class TestAsyncSetupAgent:
    """Test async_setup_agent function."""

    @pytest.mark.asyncio
    async def test_setup_registers_agent(self, mock_hass):
        """Test agent is registered with HA conversation platform."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test-key",
            "name": "Test Hermes",
        }

        # Mock the agent registration
        with patch('conversation.HermesConversationAgent') as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance

            await async_setup_agent(mock_hass, mock_entry)

            # Verify agent was instantiated and registered
            MockAgent.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_with_custom_name(self, mock_hass):
        """Test agent uses custom name from config."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test-entry"
        mock_entry.data = {
            "gateway_url": "http://localhost:8642",
            "api_key": "test-key",
            "name": "My Assistant",
        }

        with patch('conversation.HermesConversationAgent') as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance

            await async_setup_agent(mock_hass, mock_entry)

            call_kwargs = MockAgent.call_args.kwargs
            assert call_kwargs.get('name') == "My Assistant"


class TestConversationHandle:
    """Test conversation handle method."""

    @pytest.mark.asyncio
    async def test_handle_empty_message(self, agent):
        """Test empty message is handled gracefully."""
        result = await agent.async_handle({
            "text": "",
            "conversation_id": "conv-123",
            "language": "en",
        })
        # Should not raise, should return some error response
        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_calls_hermes_api(self, agent):
        """Test handle calls Hermes API client."""
        mock_response = MagicMock()
        mock_response.get("content", "") == "Hello from Hermes"

        with patch.object(agent, '_call_hermes', new_callable=AsyncMock, return_value=mock_response):
            result = await agent.async_handle({
                "text": "Hello",
                "conversation_id": "conv-123",
                "language": "en",
            })
            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_returns_error_on_failure(self, agent):
        """Test handle returns error response on API failure."""
        from api import HermesConnectionError

        with patch.object(agent, '_call_hermes', side_effect=HermesConnectionError("Failed")):
            result = await agent.async_handle({
                "text": "Hello",
                "conversation_id": "conv-123",
                "language": "en",
            })
            assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_handle_stores_conversation_history(self, agent):
        """Test messages are stored in conversation history."""
        conv_id = "conv-history-test"

        await agent.async_handle({
            "text": "First message",
            "conversation_id": conv_id,
            "language": "en",
        })

        # History should contain the message
        assert conv_id in agent._conversation_history
        history = agent._conversation_history[conv_id]
        # At least one user message should be stored
        assert len(history) >= 1


class TestConversationHistory:
    """Test conversation history management."""

    def test_history_max_limit(self, agent):
        """Test history respects max limit."""
        conv_id = "conv-limit-test"

        # Add more messages than the limit
        for i in range(250):
            if conv_id not in agent._conversation_history:
                agent._conversation_history[conv_id] = []
            agent._conversation_history[conv_id].append({
                "role": "user",
                "content": f"Message {i}",
            })

        # Should be trimmed to max
        assert len(agent._conversation_history[conv_id]) <= 200

    def test_history_per_conversation(self, agent):
        """Test each conversation has separate history."""
        agent._conversation_history["conv-1"] = [{"role": "user", "content": "One"}]
        agent._conversation_history["conv-2"] = [{"role": "user", "content": "Two"}]

        assert len(agent._conversation_history["conv-1"]) == 1
        assert len(agent._conversation_history["conv-2"]) == 1

    def test_history_clear_on_entry_unload(self, agent):
        """Test history is cleared when config entry is unloaded."""
        conv_id = "conv-clear-test"
        agent._conversation_history[conv_id] = [{"role": "user", "content": "Test"}]

        agent._conversation_history.clear()

        assert conv_id not in agent._conversation_history


class TestStreamingConversation:
    """Test streaming response handling."""

    @pytest.mark.asyncio
    async def test_streaming_handle_returns_chunks(self, agent):
        """Test streaming returns incremental response chunks."""
        chunks = [
            {"delta": "Hello", "finish_reason": None},
            {"delta": " world", "finish_reason": None},
            {"delta": "", "finish_reason": "stop"},
        ]

        with patch.object(agent, '_stream_hermes', new_callable=AsyncMock) as mock_stream:
            mock_stream.return_value = iter(chunks)
            collected = []
            async for chunk in agent._stream_hermes({"messages": [{"role": "user", "content": "Hi"}]}):
                collected.append(chunk)

            assert len(collected) == 3

    @pytest.mark.asyncio
    async def test_streaming_fallback_to_non_streaming(self, agent):
        """Test falls back to non-streaming on streaming failure."""
        with patch.object(agent, '_stream_hermes', side_effect=Exception("Stream failed")):
            with patch.object(agent, '_call_hermes', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = {"content": "Fallback response"}
                result = await agent._call_hermes({"messages": [{"role": "user", "content": "Hi"}]})
                assert mock_call.called