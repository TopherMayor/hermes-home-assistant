"""Home Assistant integration for Hermes Agent.

Provides:
- Conversation agent for Assist / Voice PE (hermes_assistant.conversation)
- Sensor entities for Hermes gateway health status (hermes_assistant.sensor)
- Services and events for deep Hermes integration
"""

import asyncio
import logging
import os
from datetime import timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HermesApiClient, HermesConnectionError, HermesAuthError, HermesApiError
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Hermes Assistant integration via YAML (no config flow)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hermes Assistant from a config entry."""
    _LOGGER.info("Setting up Hermes Assistant integration")

    # Get configuration
    gateway_url = entry.data.get("gateway_url", "http://localhost:8642")
    api_key = entry.data.get("api_key", os.getenv("HERMES_API_KEY", ""))
    name = entry.data.get("name", "Hermes")
    poll_interval = entry.data.get("poll_interval", 30)

    # Create API client
    client = HermesApiClient(gateway_url, api_key, name)

    # Verify connection
    try:
        health = await client.async_get_health()
        _LOGGER.info("Connected to Hermes gateway at %s: %s", gateway_url, health)
    except HermesAuthError as e:
        _LOGGER.error("Authentication failed with Hermes gateway: %s", e)
        raise ConfigEntryNotReady(f"Authentication failed: {e}")
    except HermesConnectionError as e:
        _LOGGER.warning("Cannot connect to Hermes gateway at %s: %s", gateway_url, e)
        # Don't fail setup — coordinator will retry with backoff
    except Exception as e:
        _LOGGER.error("Unexpected error connecting to Hermes gateway: %s", e)
        raise ConfigEntryNotReady(f"Connection error: {e}")

    # Create update coordinator for sensor entity
    async def async_update():
        """Fetch gateway health and status."""
        try:
            data = await client.async_get_status()
            return data or {}
        except HermesAuthError:
            # Token may have rotated — force re-fetch on next interval
            return {"error": "auth_failed"}
        except HermesConnectionError:
            return {"error": "connection_failed"}
        except Exception as e:
            _LOGGER.debug("Status update error: %s", e)
            return {"error": str(e)}

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update,
        update_interval=timedelta(seconds=poll_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    # Store in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "gateway_url": gateway_url,
        "api_key": api_key,
        "name": name,
    }

    # Register services
    await _register_services(hass, client, entry.entry_id)

    # Forward discovery so Hermes gateway gets HA events
    # (Hermes HomeAssistant adapter watches state_changed via WebSocket)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Hermes Assistant")

    unload_ok = await hass.config_entries.async_unload_entry_setups(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        client: Optional[HermesApiClient] = entry_data.get("client")
        if client:
            await client.async_close()

        # Remove services
        for service_name in [
            "hermes_conversation",
            "hermes_send_message",
            "hermes_trigger_run",
        ]:
            hass.services.async_remove(DOMAIN, service_name)

    return unload_ok


async def _register_services(
    hass: HomeAssistant, client: HermesApiClient, entry_id: str
) -> None:
    """Register custom services for deep Hermes integration."""

    async def hermes_conversation_service(call: ServiceCall) -> dict:
        """Send a conversation message to Hermes and return the response.

        Usage from HA automations:
          service: hermes_assistant.hermes_conversation
          data:
            message: "Turn off the living room lights"
            agent_id: "default"  # optional
        """
        message = call.data.get("message", "")
        agent_id = call.data.get("agent_id", "default")
        conversation_id = call.data.get("conversation_id")

        if not message:
            return {"error": "message is required"}

        try:
            response = await client.async_converse(
                message=message,
                agent_id=agent_id,
                conversation_id=conversation_id or None,
            )
            return {"response": response}
        except HermesAuthError as e:
            return {"error": f"Authentication failed: {e}"}
        except HermesApiError as e:
            return {"error": f"API error: {e}"}
        except Exception as e:
            _LOGGER.error("Conversation service error: %s", e)
            return {"error": str(e)}

    async def hermes_send_message_service(call: ServiceCall) -> dict:
        """Send a structured message to Hermes via the API server.

        Usage from HA automations:
          service: hermes_assistant.hermes_send_message
          data:
            message: "What's the temperature in the kitchen?"
            session_id: "abc123"  # optional
        """
        message = call.data.get("message", "")
        session_id = call.data.get("session_id")

        if not message:
            return {"error": "message is required"}

        try:
            response = await client.async_send_message(
                message=message,
                session_id=session_id or None,
            )
            return {"response": response}
        except HermesApiError as e:
            return {"error": f"API error: {e}"}
        except Exception as e:
            _LOGGER.error("Send message service error: %s", e)
            return {"error": str(e)}

    async def hermes_trigger_run_service(call: ServiceCall) -> dict:
        """Trigger a background run in Hermes and return immediately.

        Usage from HA automations:
          service: hermes_assistant.hermes_trigger_run
          data:
            goal: "Check all lights are off and report back"
            agent_id: "default"
        """
        goal = call.data.get("goal", "")
        agent_id = call.data.get("agent_id", "default")

        if not goal:
            return {"error": "goal is required"}

        try:
            result = await client.async_trigger_run(
                goal=goal,
                agent_id=agent_id,
            )
            return {"run_id": result.get("run_id"), "status": result.get("status")}
        except HermesApiError as e:
            return {"error": f"API error: {e}"}
        except Exception as e:
            _LOGGER.error("Trigger run service error: %s", e)
            return {"error": str(e)}

    hass.services.async_register(
        DOMAIN, "hermes_conversation", hermes_conversation_service
    )
    hass.services.async_register(
        DOMAIN, "hermes_send_message", hermes_send_message_service
    )
    hass.services.async_register(
        DOMAIN, "hermes_trigger_run", hermes_trigger_run_service
    )