"""API client for the Hermes gateway OpenAI-compatible API server."""

import asyncio
import json
import logging
import os
import ssl
from typing import Any, Dict, List, Optional

import urllib3.util
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HermesApiError(Exception):
    """General API error."""
    pass


class HermesConnectionError(Exception):
    """Cannot connect to Hermes gateway."""
    pass


class HermesAuthError(Exception):
    """Authentication failed with Hermes gateway."""
    pass


class HermesApiClient:
    """Client for the Hermes gateway OpenAI-compatible REST API.

    The Hermes API server exposes the same endpoints as OpenAI's API:
    - POST /v1/chat/completions  — streaming or non-streaming chat
    - POST /v1/runs              — start a background agent run
    - GET  /v1/runs/{run_id}     — get run status
    - GET  /v1/runs/{run_id}/events  — SSE stream of run events
    - GET  /health               — simple health check
    - GET  /health/detailed      — rich status including model, context

    Auth: Bearer token in Authorization header (set via api_key or HERMES_API_KEY env var).
    SSL: Uses system CA certs by default. Set HERMES_SSL_NO_VERIFY=1 to disable.
    """

    def __init__(
        self,
        gateway_url: str,
        api_key: str,
        name: str = "Hermes",
        timeout: int = 300,
    ):
        self._gateway_url = gateway_url.rstrip("/")
        self._api_key = api_key or os.getenv("HERMES_API_KEY", "")
        self._name = name
        self._timeout = timeout
        self._session: Optional[asyncio.AbstractConnector] = None
        self._ssl_context: Optional[ssl.SSLContext] = None

        # Respect SSL env var
        if os.getenv("HERMES_SSL_NO_VERIFY") == "1":
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    def _get_ssl(self) -> Optional[ssl.SSLContext]:
        return self._ssl_context

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        timeout: Optional[int] = None,
        stream: bool = False,
    ) -> Any:
        """Make an HTTP request to the Hermes API server."""
        import aiohttp

        url = f"{self._gateway_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if timeout is None:
            timeout = self._timeout

        connector = aiohttp.TCPConnector(ssl=self._get_ssl())
        timeout_obj = aiohttp.ClientTimeout(total=timeout, sock_read=120)

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
                async with session.request(
                    method, url, json=json_data, headers=headers
                ) as response:
                    if response.status == 401:
                        raise HermesAuthError(
                            f"Invalid API key for {url}. "
                            "Set HERMES_API_KEY or configure it in the integration settings."
                        )
                    if response.status == 403:
                        raise HermesAuthError(
                            f"Access forbidden to {url}. Check your API key permissions."
                        )
                    if response.status >= 400:
                        body = await response.text()
                        raise HermesApiError(
                            f"API error {response.status} for {path}: {body[:500]}"
                        )

                    if stream:
                        return response

                    text = await response.text()
                    if text:
                        return json.loads(text)
                    return None

        except asyncio.TimeoutError:
            raise HermesConnectionError(f"Request to {path} timed out after {timeout}s")
        except aiohttp.ClientError as e:
            raise HermesConnectionError(f"Connection error for {path}: {e}")

    async def async_close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    # -------------------------------------------------------------------------
    # Health & Status
    # -------------------------------------------------------------------------

    async def async_get_health(self) -> Dict[str, Any]:
        """Get simple health status."""
        result = await self._request("GET", "/health")
        return result or {}

    async def async_get_detailed_health(self) -> Dict[str, Any]:
        """Get detailed health status (includes model, context info)."""
        result = await self._request("GET", "/health/detailed")
        return result or {}

    async def async_get_capabilities(self) -> Dict[str, Any]:
        """Get gateway capabilities (model, features, runtime, etc.).

        Returns an empty dict on connection/auth errors.
        """
        try:
            result = await self._request("GET", "/v1/capabilities")
            return result or {}
        except (HermesConnectionError, HermesAuthError, HermesApiError):
            return {}

    async def async_get_status(self) -> Dict[str, Any]:
        """Get current gateway status (used by sensor entity)."""
        try:
            return await self.async_get_detailed_health()
        except HermesConnectionError:
            # Gateway is down
            return {"online": False, "error": "gateway_offline"}
        except HermesAuthError:
            return {"online": False, "error": "auth_failed"}

    # -------------------------------------------------------------------------
    # Conversation (OpenAI Chat Completions compatible)
    # -------------------------------------------------------------------------

    async def async_converse(
        self,
        message: str,
        agent_id: str = "default",
        conversation_id: Optional[str] = None,
        stream: bool = False,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a conversation message to Hermes.

        Uses the OpenAI-compatible /v1/chat/completions endpoint.
        Pass stream=True to get an async iterator of response chunks.

        Args:
            message: The user's message
            agent_id: Which Hermes agent/role to use (default: "default")
            conversation_id: Optional conversation ID for session continuity
            stream: Whether to stream the response
            system_prompt: Optional system prompt override

        Returns:
            The full response text (non-streaming), or an async iterator (streaming)
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": agent_id,
            "messages": messages,
            "stream": stream,
        }

        if conversation_id:
            payload["extra_headers"] = {
                "X-Hermes-Session-Id": conversation_id
            }

        response = await self._request(
            "POST",
            "/v1/chat/completions",
            json_data=payload,
        )

        if stream:
            return response  # Caller handles SSE streaming

        # Non-streaming: extract content from OpenAI response format
        if response and "choices" in response:
            delta = response["choices"][0].get("message", {})
            return delta.get("content", "")
        elif response and "error" in response:
            raise HermesApiError(response["error"].get("message", "Unknown error"))
        return ""

    async def async_send_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """Send a message via the OpenAI Responses API.

        This uses the /v1/responses endpoint which is stateful via
        previous_response_id and supports X-Hermes-Session-Key for
        long-term memory scoping.

        Args:
            message: The message to send
            session_id: Optional session ID for context continuity
            stream: Whether to stream the response

        Returns:
            The response text
        """
        payload = {
            "model": "hermes-agent",
            "input": message,
            "stream": stream,
        }

        headers = {}
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id

        # Build request with extra_headers support
        url = f"{self._gateway_url}/v1/responses"
        import aiohttp
        headers["Authorization"] = f"Bearer {self._api_key}"
        headers["Content-Type"] = "application/json"

        connector = aiohttp.TCPConnector(ssl=self._get_ssl())
        timeout_obj = aiohttp.ClientTimeout(total=self._timeout, sock_read=120)

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
                async with session.request(
                    "POST", url, json=payload, headers=headers
                ) as response:
                    if response.status == 401:
                        raise HermesAuthError("Invalid API key")
                    if response.status >= 400:
                        body = await response.text()
                        raise HermesApiError(f"API error: {body[:500]}")

                    if stream:
                        return response

                    text = await response.text()
                    if text:
                        data = json.loads(text)
                        output = data.get("output", [])
                        if isinstance(output, list) and output:
                            return output[0].get("content", [{}])[0].get("text", "")
                        return str(data)
                    return ""
        except asyncio.TimeoutError:
            raise HermesConnectionError(f"Send message timed out after {self._timeout}s")
        except aiohttp.ClientError as e:
            raise HermesConnectionError(f"Connection error: {e}")

    # -------------------------------------------------------------------------
    # Background Runs
    # -------------------------------------------------------------------------

    async def async_trigger_run(
        self,
        goal: str,
        agent_id: str = "default",
        session_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a background Hermes agent run.

        Returns immediately with run_id. Use async_get_run_status()
        to poll for completion or async_get_run_events() for SSE stream.

        Args:
            goal: The task/goal for the agent
            agent_id: Which agent to use (maps to Hermes profile/skill config)
            session_key: Optional session key for memory scoping

        Returns:
            {"run_id": "...", "status": "queued|pending"}
        """
        payload = {
            "goal": goal,
            "agent_id": agent_id,
        }
        headers = {}
        if session_key:
            headers["X-Hermes-Session-Key"] = session_key

        url = f"{self._gateway_url}/v1/runs"
        import aiohttp
        hdrs = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        hdrs.update(headers)

        connector = aiohttp.TCPConnector(ssl=self._get_ssl())
        timeout_obj = aiohttp.ClientTimeout(total=30)

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
                async with session.request("POST", url, json=payload, headers=hdrs) as response:
                    if response.status == 401:
                        raise HermesAuthError("Invalid API key")
                    if response.status == 429:
                        raise HermesApiError("Rate limited — try again later")
                    if response.status >= 400:
                        body = await response.text()
                        raise HermesApiError(f"Run trigger failed: {body[:500]}")

                    data = await response.json()
                    return {
                        "run_id": data.get("run_id", ""),
                        "status": data.get("status", "unknown"),
                    }
        except asyncio.TimeoutError:
            raise HermesConnectionError("Run trigger timed out")
        except aiohttp.ClientError as e:
            raise HermesConnectionError(f"Connection error: {e}")

    async def async_get_run_status(self, run_id: str) -> Dict[str, Any]:
        """Get the status of a background run."""
        result = await self._request("GET", f"/v1/runs/{run_id}")
        return result or {}

    async def async_approve_run(self, run_id: str) -> Dict[str, Any]:
        """Approve a pending run (for approval-gated workflows)."""
        result = await self._request("POST", f"/v1/runs/{run_id}/approval")
        return result or {}

    async def async_stop_run(self, run_id: str) -> Dict[str, Any]:
        """Stop an in-progress run."""
        result = await self._request("POST", f"/v1/runs/{run_id}/stop")
        return result or {}