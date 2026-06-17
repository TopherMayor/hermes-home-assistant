"""Constants for the Hermes Assistant Home Assistant integration."""

from typing import List

DOMAIN = "hermes_assistant"

DEFAULT_NAME = "Hermes"
DEFAULT_URL = "http://localhost:8642"
DEFAULT_PORT = 8642

PLATFORMS: List[str] = ["conversation", "sensor", "binary_sensor", "button", "event"]

# Event types dispatched by this integration
EVENT_RUN_COMPLETED = f"{DOMAIN}_run_completed"
EVENT_RESPONSE_READY = f"{DOMAIN}_response_ready"
EVENT_STREAMING_DELTA = f"{DOMAIN}_streaming_delta"