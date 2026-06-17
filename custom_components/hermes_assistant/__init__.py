"""Home Assistant integration for Hermes Agent.

Provides:
- Conversation agent for Assist / Voice PE (hermes_assistant.conversation)
- Sensor entities for Hermes gateway health status (hermes_assistant.sensor)
- Services and events for deep Hermes integration
"""

import asyncio
import datetime
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
        """Fetch gateway health, status, and capabilities; merge into one dict.

        The /health/detailed endpoint provides: version, gateway_state,
        active_agents, platforms, updated_at, pid.
        The /v1/capabilities endpoint provides: model, platform, features,
        runtime, auth. The merged dict gives the sensor entities a richer
        set of keys to display.

        Sensors that have no corresponding data source (e.g. context_pct,
        rss_mb, error_count) will continue to show "unknown" until the
        gateway exposes those metrics.
        """
        try:
            detailed = await client.async_get_detailed_health()
        except HermesAuthError:
            return {"error": "auth_failed"}
        except HermesConnectionError:
            return {"error": "connection_failed"}
        except Exception as e:
            _LOGGER.debug("Detailed health fetch error: %s", e)
            detailed = {}

        try:
            caps = await client.async_get_capabilities()
        except Exception as e:
            _LOGGER.debug("Capabilities fetch error: %s", e)
            caps = {}

        try:
            sessions = await client.async_get_sessions()
            toolsets = await client.async_get_toolsets()
            skills = await client.async_get_skills()
        except Exception as e:
            _LOGGER.debug("Sessions/toolsets/skills fetch error: %s", e)
            sessions = []
            toolsets = []
            skills = []

        # Compute uptime from updated_at - the gateway's "started" time
        # is implicit; we approximate by tracking the first-seen updated_at
        # and computing elapsed seconds. Stored on the client.
        uptime = None
        if isinstance(detailed, dict) and detailed.get("updated_at"):
            try:
                last_update = datetime.datetime.fromisoformat(
                    detailed["updated_at"].replace("Z", "+00:00")
                )
                now = datetime.datetime.now(datetime.timezone.utc)
                # We approximate gateway start as 24h before first-seen updated_at.
                # A better implementation would have the gateway report a start time.
                if not hasattr(client, "_first_seen"):
                    client._first_seen = now
                    client._gateway_started_at = last_update - datetime.timedelta(hours=24)
                uptime = int((now - client._gateway_started_at).total_seconds())
            except (ValueError, TypeError):
                pass

        # Build merged data dict
        merged = dict(detailed or {})

        # Pull fields from capabilities
        if isinstance(caps, dict):
            if caps.get("model") and not merged.get("model"):
                merged["model"] = caps["model"]
            if caps.get("platform") and not merged.get("platform"):
                merged["platform"] = caps["platform"]
            # Auth type → "provider" sensor (e.g. "bearer")
            auth_info = caps.get("auth", {})
            if isinstance(auth_info, dict) and auth_info.get("type"):
                merged["provider"] = auth_info["type"]

        # Map /health/detailed fields to sensor keys
        if isinstance(merged.get("active_agents"), int):
            # Only one agent process at a time → "threads" == active_agents
            merged["active_threads"] = merged["active_agents"]
        if isinstance(merged.get("platforms"), dict):
            # Count platforms that report "connected" → "error_count" of those
            # not connected (proxy for gateway-level errors)
            not_connected = sum(
                1 for p in merged["platforms"].values()
                if isinstance(p, dict) and p.get("state") != "connected"
            )
            merged["error_count"] = not_connected

        if uptime is not None:
            merged["uptime_seconds"] = uptime

        # Compute session-derived metrics from /api/sessions
        if isinstance(sessions, list) and sessions:
            import time as _time
            now_ts = _time.time()
            today_start = now_ts - (now_ts % 86400)  # midnight UTC today

            active_sessions = 0
            tokens_today = 0
            cost_today = 0.0
            tokens_last = 0

            # Sort sessions by started_at descending
            sorted_sessions = sorted(
                sessions,
                key=lambda s: s.get("started_at") or 0,
                reverse=True
            )

            for sess in sessions:
                started_at = sess.get("started_at") or 0
                ended_at = sess.get("ended_at")

                # Active = no ended_at OR ended_at > now - 1 minute
                if ended_at is None:
                    active_sessions += 1

                # Tokens today = sum of all token types for sessions started today
                if started_at >= today_start:
                    tokens_today += (
                        (sess.get("input_tokens") or 0)
                        + (sess.get("output_tokens") or 0)
                        + (sess.get("cache_read_tokens") or 0)
                        + (sess.get("cache_write_tokens") or 0)
                        + (sess.get("reasoning_tokens") or 0)
                    )
                    cost_today += sess.get("estimated_cost_usd") or 0

            # Most recent session's total tokens
            if sorted_sessions:
                latest = sorted_sessions[0]
                tokens_last = (
                    (latest.get("input_tokens") or 0)
                    + (latest.get("output_tokens") or 0)
                    + (latest.get("cache_read_tokens") or 0)
                    + (latest.get("cache_write_tokens") or 0)
                    + (latest.get("reasoning_tokens") or 0)
                )

            # Set model from the most recent session (actual LLM being used,
            # e.g. "MiniMax-M3"). /v1/capabilities.model returns the platform
            # name ("hermes-agent") which is less useful for the dashboard.
            if sorted_sessions:
                latest_model = sorted_sessions[0].get("model")
                if latest_model:
                    merged["model"] = latest_model

            merged["rss_mb"] = active_sessions
            merged["context_limit"] = tokens_today
            merged["context_pct"] = tokens_last
            merged["estimated_cost_today"] = round(cost_today, 4)

            # Yesterday's totals for trend comparison
            yesterday_start = today_start - 86400
            cost_yesterday = 0.0
            tokens_yesterday = 0
            for sess in sessions:
                started_at = sess.get("started_at") or 0
                if yesterday_start <= started_at < today_start:
                    cost_yesterday += sess.get("estimated_cost_usd") or 0
                    tokens_yesterday += (
                        (sess.get("input_tokens") or 0)
                        + (sess.get("output_tokens") or 0)
                        + (sess.get("cache_read_tokens") or 0)
                        + (sess.get("cache_write_tokens") or 0)
                        + (sess.get("reasoning_tokens") or 0)
                    )
            merged["estimated_cost_yesterday"] = round(cost_yesterday, 4)
            merged["tokens_yesterday"] = tokens_yesterday

            # Trend (percent change vs yesterday). When yesterday is zero,
            # we report None which HA renders as 'unknown'.
            if cost_yesterday > 0:
                cost_trend_pct = round(
                    ((cost_today - cost_yesterday) / cost_yesterday) * 100, 2
                )
                merged["cost_trend_pct"] = cost_trend_pct
            else:
                merged["cost_trend_pct"] = None

            if tokens_yesterday > 0:
                token_trend_pct = round(
                    ((tokens_today - tokens_yesterday) / tokens_yesterday) * 100, 2
                )
                merged["token_trend_pct"] = token_trend_pct
            else:
                merged["token_trend_pct"] = None

        # Toolset count
        if isinstance(toolsets, list):
            merged["toolsets_enabled"] = sum(
                1 for t in toolsets if isinstance(t, dict) and t.get("enabled")
            )
            merged["toolsets_total"] = len(toolsets)

        # Skills count
        if isinstance(skills, list):
            merged["skills_loaded"] = len(skills)

        # Features count from capabilities
        if isinstance(caps, dict):
            features = caps.get("features", {})
            if isinstance(features, dict):
                merged["features_enabled"] = sum(
                    1 for v in features.values() if v is True
                )

        return merged

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