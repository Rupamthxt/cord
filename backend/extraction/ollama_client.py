"""
ollama_client.py
================
Async HTTP client for the locally running Ollama inference server.

Environment variables
---------------------
OLLAMA_BASE_URL  – Base URL for Ollama (default: http://localhost:11434)
OLLAMA_MODEL     – Model name to use (default: llama3.2)
OLLAMA_TIMEOUT   – Request timeout in seconds (default: 30)
"""

from __future__ import annotations

import logging
import os
import time
from typing import List

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class OllamaUnavailableError(Exception):
    """Raised when the Ollama server cannot be reached."""


class OllamaTimeoutError(Exception):
    """Raised when a request to Ollama exceeds the configured timeout."""


class OllamaParseError(Exception):
    """Raised when the Ollama response cannot be parsed as expected JSON."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OllamaClient:
    """
    Async HTTP client for the Ollama REST API.

    Provides non-blocking ``generate`` and utility methods for health-checking
    and model discovery. All network I/O is performed with ``aiohttp`` so the
    client can be used inside any async FastAPI route or background task
    without blocking the event loop.

    Attributes
    ----------
    BASE_URL:
        Root URL of the running Ollama server, read from ``OLLAMA_BASE_URL``.
    MODEL:
        Default model name, read from ``OLLAMA_MODEL``.
    TIMEOUT:
        Per-request timeout in seconds, read from ``OLLAMA_TIMEOUT``.
    """

    BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "30"))

    # ------------------------------------------------------------------
    # Core generate
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, temperature: float = 0.0) -> str:
        """
        Send a completion request to ``/api/generate`` and return the raw
        text response.

        Parameters
        ----------
        prompt:
            The full prompt string to send to the model.
        temperature:
            Sampling temperature (0.0 = deterministic, 1.0 = creative).
            Defaults to 0.0 for deterministic extraction tasks.

        Returns
        -------
        str
            The model's text response.

        Raises
        ------
        OllamaUnavailableError
            If the Ollama server is not reachable (connection refused, DNS
            failure, etc.).
        OllamaTimeoutError
            If the request exceeds ``self.TIMEOUT`` seconds.
        OllamaParseError
            If the response JSON does not contain the expected ``"response"``
            field.
        """
        url = f"{self.BASE_URL}/api/generate"
        payload = {
            "model": self.MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 2048,
            },
        }

        timeout = aiohttp.ClientTimeout(total=self.TIMEOUT)
        start = time.perf_counter()

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)

        except aiohttp.ClientConnectorError as exc:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.BASE_URL}: {exc}"
            ) from exc

        except aiohttp.ServerTimeoutError as exc:
            raise OllamaTimeoutError(
                f"Ollama request timed out after {self.TIMEOUT}s (model={self.MODEL})"
            ) from exc

        except aiohttp.ClientResponseError as exc:
            raise OllamaUnavailableError(
                f"Ollama returned HTTP {exc.status}: {exc.message}"
            ) from exc

        elapsed = time.perf_counter() - start
        logger.info(
            "Ollama generate completed | model=%s duration=%.3fs prompt_len=%d",
            self.MODEL,
            elapsed,
            len(prompt),
        )

        try:
            return data["response"]
        except (KeyError, TypeError) as exc:
            raise OllamaParseError(
                f"Expected 'response' key in Ollama JSON; got keys: {list(data.keys()) if isinstance(data, dict) else type(data)}"
            ) from exc

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """
        Probe ``/api/tags`` to determine whether Ollama is reachable.

        Returns
        -------
        bool
            ``True`` if Ollama responds with HTTP 200, ``False`` for any
            error condition (connection refused, timeout, non-200 status,
            etc.).
        """
        url = f"{self.BASE_URL}/api/tags"
        timeout = aiohttp.ClientTimeout(total=5)  # short probe timeout
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    available = resp.status == 200
                    logger.debug(
                        "Ollama availability probe | url=%s status=%d available=%s",
                        url,
                        resp.status,
                        available,
                    )
                    return available
        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            logger.debug("Ollama unavailable: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Model listing
    # ------------------------------------------------------------------

    async def list_models(self) -> List[str]:
        """
        Return the list of locally available Ollama model names.

        Parses the ``/api/tags`` response, which has the shape::

            {
              "models": [
                {"name": "llama3.2:latest", ...},
                ...
              ]
            }

        Returns
        -------
        List[str]
            Model name strings (e.g. ``["llama3.2:latest", "mistral:7b"]``).
            Returns an empty list if Ollama is unreachable or the response is
            malformed.
        """
        url = f"{self.BASE_URL}/api/tags"
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
                    models: List[str] = [
                        m["name"]
                        for m in data.get("models", [])
                        if isinstance(m, dict) and "name" in m
                    ]
                    logger.debug("Ollama models available: %s", models)
                    return models
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to list Ollama models: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

ollama_client = OllamaClient()
