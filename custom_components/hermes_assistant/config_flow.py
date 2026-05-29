"""Config flow for Hermes Assistant integration."""

import os
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, DEFAULT_NAME, DEFAULT_URL, DEFAULT_PORT

# Re-use the HermesApiClient for connection testing
from .api import HermesApiClient, HermesConnectionError, HermesAuthError


def _validate_url(url: str) -> tuple[str, int]:
    """Parse and validate a Hermes gateway URL.

    Returns (normalized_url, port).
    Raises vol.Invalid if the URL is malformed.
    """
    url = url.strip().rstrip("/")

    # Auto-append scheme
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"

    # Validate URL format
    if not re.match(r"^https?://[\w\-\.]+(:\d+)?/?$", url):
        raise vol.Invalid(
            "Invalid URL format. Use format: http://hostname:port or https://hostname"
        )

    # Extract port from URL
    port_match = re.search(r":(\d+)", url)
    port = int(port_match.group(1)) if port_match else DEFAULT_PORT

    return url, port


class HermesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Hermes Assistant.

    Supports three discovery modes:
    1. Manual — user provides gateway URL + API key
    2. Environment — auto-detect from HERMES_API_KEY and HERMES_GATEWAY_URL env vars
    3. Local scan — check localhost:8642 (default Hermes API server port)
    """

    VERSION = 1

    async def async_step_user(self, user_input: dict = None):
        """Handle a manual configuration flow."""
        errors = {}

        if user_input is not None:
            # Validate URL
            try:
                gateway_url, port = _validate_url(user_input.get(CONF_URL, ""))
            except vol.Invalid as e:
                errors[CONF_URL] = str(e)
                gateway_url = None

            if gateway_url and not errors:
                # Test connection
                api_key = user_input.get("api_key", os.getenv("HERMES_API_KEY", ""))
                name = user_input.get(CONF_NAME, DEFAULT_NAME)

                try:
                    client = HermesApiClient(gateway_url, api_key, name)
                    await client.async_get_health()
                except HermesAuthError:
                    # Auth failed — but gateway is reachable
                    # Store and continue
                    pass
                except HermesConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    errors["base"] = f"unexpected_error: {e}"

            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        "gateway_url": gateway_url,
                        "api_key": api_key,
                        "name": name,
                        "poll_interval": user_input.get("poll_interval", 30),
                    },
                )

        # Show form
        data_schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_URL, default=os.getenv("HERMES_GATEWAY_URL", DEFAULT_URL)): str,
                vol.Optional("api_key", default=os.getenv("HERMES_API_KEY", "")): str,
                vol.Optional("poll_interval", default=30): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "default_port": str(DEFAULT_PORT),
                "api_key_env": "HERMES_API_KEY",
                "gateway_url_env": "HERMES_GATEWAY_URL",
            },
        )

    async def async_step_env(self, user_input: dict = None):
        """Auto-detect configuration from environment variables.

        This step is shown when HERMES_API_KEY is set but no config entry exists yet.
        """
        gateway_url = os.getenv("HERMES_GATEWAY_URL", DEFAULT_URL)
        api_key = os.getenv("HERMES_API_KEY", "")
        name = os.getenv("HERMES_NAME", DEFAULT_NAME)

        try:
            url, port = _validate_url(gateway_url)
        except vol.Invalid:
            return await self.async_step_user()

        # Test connection
        try:
            client = HermesApiClient(url, api_key, name)
            await client.async_get_health()
        except (HermesConnectionError, HermesAuthError):
            pass  # Fall through to manual

        return self.async_create_entry(
            title=name,
            data={
                "gateway_url": url,
                "api_key": api_key,
                "name": name,
                "poll_interval": 30,
            },
        )