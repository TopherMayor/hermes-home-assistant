"""Hermes conversation agent for Home Assistant Assist / Voice PE.

This implements the HA conversation platform so Hermes appears as a
native Assist agent — users can select "Hermes" in HA's voice assistant
settings and talk to it directly from the HA UI or voice pipelines.
"""

import asyncio
import json
import logging
from typing import Optional

from homeassistant.components.conversation import ATTR_TEXT, ATTR_AGENT_ID, AbstractConversationAgent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .api import HermesApiClient, HermesApiError, HermesConnectionError, HermesAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Max chat history entries stored in memory per agent_id
_MAX_HISTORY = 200


class HermesConversationAgent(AbstractConversationAgent):
    """Hermes as a native HA Assist conversation agent.

    This registers Hermes as an Assist provider that HA's voice pipelines
    can route to. Users select it in Home Assistant → Voice Assistant →
    the agent for their assistant.

    Internally, it sends conversation messages to the Hermes gateway via
    the OpenAI-compatible /v1/chat/completions endpoint. Session continuity
    is maintained via X-Hermes-Session-Id header using a stable agent-namespace
    conversation ID.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self._conversation_contexts: dict[str, list] = {}  # conversation_id -> history
        self._agent_id = "default"

    @property
    def conversation_agent_platform(self) -> str:
        return DOMAIN

    @property
    def agent_name(self) -> str:
        """Return the friendly name for this agent."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
        return entry_data.get("name", "Hermes")

    @property
    def supported_languages(self) -> Optional[list[str]]:
        """Return all supported languages — Hermes is language-agnostic."""
        return None  # None = all languages

    async def async_process(
        self,
        user_input: intent.ConversationInput,
    ) -> intent.ConversationResult:
        """Process a conversation turn from HA Assist / Voice PE.

        This is the main entry point — called by HA's conversation pipeline
        when a user speaks to the Hermes agent via the HA UI or voice commands.
        """
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
        client: Optional[HermesApiClient] = entry_data.get("client")
        gateway_url = entry_data.get("gateway_url", "")

        if not client:
            _LOGGER.error("No Hermes API client found for entry_id=%s", self.entry_id)
            return self._make_error_result(
                user_input.agent_id,
                "Hermes is not configured. Please check your integration settings.",
                conversation_id=user_input.conversation_id,
            )

        text = user_input.text.strip()
        if not text:
            return self._make_error_result(
                user_input.agent_id,
                "I didn't receive any text.",
                conversation_id=user_input.conversation_id,
            )

        # Build a stable conversation ID from the HA conversation context
        # We namespace by agent_id so different HA agents get separate histories
        conv_id = user_input.conversation_id or f"ha_{self._agent_id}"
        conv_id = f"hermes_ha_{conv_id}"

        try:
            # Get conversation history for context
            history = self._conversation_contexts.get(conv_id, [])

            # Build messages including history for context
            messages = self._build_messages(history, text)

            # Call Hermes via OpenAI-compatible API
            response_text = await client.async_converse(
                message=text,
                agent_id=self._agent_id,
                conversation_id=conv_id,
                stream=False,
            )

            # Update history (keep last _MAX_HISTORY entries)
            self._update_history(conv_id, text, response_text)

            # Strip any tool-call artifacts from response
            response_text = self._strip_tool_calls(response_text)

            _LOGGER.debug(
                "Hermes conversation response for conv=%s: %s",
                conv_id[:40],
                response_text[:200],
            )

            return intent.ConversationResult(
                response=intent.IntentResponse(
                    agent_name=self.agent_name,
                    language=user_input.language or "en",
                ),
                conversation_id=conv_id,
                toolbar_element=None,
            ).with_speech(response_text)

        except HermesAuthError as e:
            _LOGGER.error("Hermes auth error: %s", e)
            return self._make_error_result(
                user_input.agent_id,
                "Hermes authentication failed. Please check your API key.",
                conversation_id=user_input.conversation_id,
            )
        except HermesConnectionError as e:
            _LOGGER.error("Hermes connection error: %s", e)
            return self._make_error_result(
                user_input.agent_id,
                "Cannot connect to Hermes. Please check that the Hermes gateway is running.",
                conversation_id=user_input.conversation_id,
            )
        except HermesApiError as e:
            _LOGGER.error("Hermes API error: %s", e)
            return self._make_error_result(
                user_input.agent_id,
                f"Hermes error: {e}",
                conversation_id=user_input.conversation_id,
            )
        except Exception as e:
            _LOGGER.exception("Unexpected error in Hermes conversation: %s", e)
            return self._make_error_result(
                user_input.agent_id,
                f"Unexpected error: {e}",
                conversation_id=user_input.conversation_id,
            )

    def _build_messages(
        self, history: list[tuple[str, str]], current_text: str
    ) -> list[dict[str, str]]:
        """Build message list including conversation history for context."""
        messages = []

        # System prompt for Hermes in HA context
        messages.append({
            "role": "system",
            "content": (
                "You are Hermes, an AI assistant integrated with Home Assistant. "
                "You can control lights, switches, sensors, climate, and other smart home "
                "devices through Home Assistant. Be concise and helpful. "
                "When users ask about their home state, query HA entities when available."
            ),
        })

        # Add history entries
        for user_msg, assistant_msg in history[-50:]:  # Keep last 50 turns
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})

        # Current turn
        messages.append({"role": "user", "content": current_text})

        return messages

    def _update_history(
        self, conv_id: str, user_text: str, assistant_text: str
    ) -> None:
        """Append to conversation history, trimming to max size."""
        if conv_id not in self._conversation_contexts:
            self._conversation_contexts[conv_id] = []
        self._conversation_contexts[conv_id].append((user_text, assistant_text))

        # Trim history
        if len(self._conversation_contexts[conv_id]) > _MAX_HISTORY:
            self._conversation_contexts[conv_id] = self._conversation_contexts[conv_id][
                -_MAX_HISTORY:
            ]

    def _strip_tool_calls(self, text: str) -> str:
        """Strip tool call JSON artifacts from response text.

        Hermes may include tool call markers in its response. We remove
        them so the user sees clean text.
        """
        # Remove lines that look like JSON tool call blocks
        import re

        # Remove ```tool_calls blocks
        text = re.sub(r"```tool_calls[\s\S]*?```", "", text)
        # Remove inline { "tool": ... } objects
        text = re.sub(r'\n\s*\{\s*"tool"\s*:\s*"[^"]+"\s*,[^}]+\}', "", text)
        return text.strip()

    def _make_error_result(
        self,
        agent_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> intent.ConversationResult:
        """Create an error conversation result."""
        return intent.ConversationResult(
            response=intent.IntentResponse(
                agent_name=self.agent_name,
                language="en",
            ),
            conversation_id=conversation_id,
        ).with_error(message)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Hermes conversation platform from a config entry.

    This is called by HA when the 'conversation' platform is set up via
    async_forward_entry_setups in __init__.py. We create the agent and
    register it so Assist can route to it.
    """
    agent = HermesConversationAgent(hass, entry.entry_id)
    # Store on hass.data so the agent can be retrieved by entity_id
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = hass.data[DOMAIN].get(entry.entry_id, {})
    hass.data[DOMAIN][entry.entry_id]["conversation_agent"] = agent
    return True