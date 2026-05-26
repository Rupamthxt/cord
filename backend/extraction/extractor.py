"""
extractor.py
============
Main OllamaEntityExtractor — the single entry point for all entity and
relationship extraction in the Cord pipeline.

Architecture
------------
* **Primary path**: async LLM extraction via ``OllamaClient`` + ``ExtractionPrompts``
  + ``parse_llm_response`` validation.
* **Fallback path**: synchronous regex-based ``EntityExtractor`` when Ollama is
  unreachable or the LLM returns empty results for substantial text.
* **Availability caching**: Ollama reachability is cached for
  ``AVAILABILITY_CHECK_INTERVAL`` seconds to avoid hammering the probe endpoint
  on every call.
* **Batch support**: ``extract_batch`` fans out concurrently with
  ``asyncio.gather`` while applying a small inter-request delay to prevent
  Ollama overload.

Module-level singleton ``extractor`` is imported by the ingestion pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from backend.connectors.ingestion.entity_extractor import EntityExtractor
from backend.extraction.ollama_client import (
    OllamaClient,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ollama_client,
)
from backend.extraction.prompts import ExtractionPrompts
from backend.extraction.validator import (
    ExtractedEntity,
    ExtractionResponse,
    parse_llm_response,
)

logger = logging.getLogger(__name__)

# Minimum delay (seconds) between successive Ollama requests in batch mode.
# Helps avoid overwhelming a single-GPU Ollama instance.
_BATCH_INTER_REQUEST_DELAY: float = float(
    __import__("os").getenv("OLLAMA_BATCH_DELAY", "0.1")
)


class OllamaEntityExtractor:
    """
    LLM-powered entity and relationship extractor using local Ollama inference.
    Falls back to regex-based ``EntityExtractor`` if Ollama is unavailable.

    Parameters
    ----------
    (none — configuration is read from environment variables via the
    ``OllamaClient`` and module-level constants)

    Attributes
    ----------
    ollama:
        The ``OllamaClient`` instance used for LLM calls.
    fallback:
        The regex-based ``EntityExtractor`` used when Ollama is unavailable.
    _ollama_available:
        Cached availability flag; ``None`` means "not yet checked".
    _last_availability_check:
        Unix timestamp of the last successful availability probe.
    AVAILABILITY_CHECK_INTERVAL:
        Seconds between re-probing Ollama's health. Default 60 s.
    """

    AVAILABILITY_CHECK_INTERVAL: float = 60.0

    def __init__(self) -> None:
        self.ollama: OllamaClient = ollama_client
        self.fallback: EntityExtractor = EntityExtractor()
        self._ollama_available: Optional[bool] = None
        self._last_availability_check: float = 0.0

    # ------------------------------------------------------------------
    # Availability caching
    # ------------------------------------------------------------------

    async def _check_availability(self) -> bool:
        """
        Return whether Ollama is reachable, using a cached result that
        refreshes every ``AVAILABILITY_CHECK_INTERVAL`` seconds.

        The cache avoids a network probe on every single extraction call,
        while still detecting Ollama coming back online after a restart.

        Returns
        -------
        bool
            ``True`` if Ollama is reachable and healthy.
        """
        now = time.monotonic()
        cache_expired = (
            now - self._last_availability_check
        ) > self.AVAILABILITY_CHECK_INTERVAL

        if self._ollama_available is None or cache_expired:
            self._ollama_available = await self.ollama.is_available()
            self._last_availability_check = now
            logger.info(
                "Ollama availability (re-)checked: available=%s",
                self._ollama_available,
            )

        return self._ollama_available

    # ------------------------------------------------------------------
    # Primary extraction
    # ------------------------------------------------------------------

    async def extract(self, chunk_text: str) -> ExtractionResponse:
        """
        Extract entities and relationships from a single text chunk.

        The method attempts LLM extraction first. If Ollama is unavailable it
        falls back to regex extraction immediately. If Ollama returns an empty
        result for a chunk that has substantial content (> 50 characters) it
        also triggers the fallback to maximise recall.

        Parameters
        ----------
        chunk_text:
            Raw organizational text (a document chunk, message, ticket body,
            etc.). Passing an empty string returns an empty
            ``ExtractionResponse`` immediately.

        Returns
        -------
        ExtractionResponse
            Validated entities and relationships (may be empty but never
            raises).
        """
        if not chunk_text or not chunk_text.strip():
            logger.debug("extract() received empty chunk_text — returning empty response")
            return ExtractionResponse()

        t_start = time.perf_counter()

        # --- Route: Ollama unavailable → fallback immediately ---------------
        ollama_available = await self._check_availability()
        if not ollama_available:
            logger.info(
                "Ollama unavailable — using regex fallback for chunk (len=%d)",
                len(chunk_text),
            )
            result = self._fallback_extract(chunk_text)
            self._log_result(result, source="regex-fallback", elapsed=time.perf_counter() - t_start)
            return result

        # --- Route: Ollama available → LLM extraction -----------------------
        try:
            prompt = ExtractionPrompts.format_prompt(chunk_text)
            raw_response = await self.ollama.generate(prompt, temperature=0.0)
        except OllamaUnavailableError as exc:
            logger.warning(
                "Ollama became unavailable mid-request (%s) — switching to fallback",
                exc,
            )
            # Invalidate cache immediately so the next call re-probes
            self._ollama_available = False
            result = self._fallback_extract(chunk_text)
            self._log_result(result, source="regex-fallback", elapsed=time.perf_counter() - t_start)
            return result

        except OllamaTimeoutError as exc:
            logger.warning(
                "Ollama request timed out (%s) — switching to fallback", exc
            )
            result = self._fallback_extract(chunk_text)
            self._log_result(result, source="regex-fallback-timeout", elapsed=time.perf_counter() - t_start)
            return result

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unexpected error during Ollama generate: %s — switching to fallback",
                exc,
                exc_info=True,
            )
            result = self._fallback_extract(chunk_text)
            self._log_result(result, source="regex-fallback-error", elapsed=time.perf_counter() - t_start)
            return result

        # --- Validate LLM output -------------------------------------------
        result = parse_llm_response(raw_response)

        # --- Empty-result fallback for substantial chunks -------------------
        if not result.entities and len(chunk_text.strip()) > 50:
            logger.debug(
                "LLM returned no entities for chunk of %d chars — trying regex fallback",
                len(chunk_text),
            )
            fallback_result = self._fallback_extract(chunk_text)
            if fallback_result.entities:
                logger.info(
                    "Regex fallback recovered %d entities that LLM missed",
                    len(fallback_result.entities),
                )
                self._log_result(fallback_result, source="llm-empty-regex-fallback", elapsed=time.perf_counter() - t_start)
                return fallback_result

        self._log_result(result, source="llm", elapsed=time.perf_counter() - t_start)
        return result

    # ------------------------------------------------------------------
    # Fallback extraction
    # ------------------------------------------------------------------

    def _fallback_extract(self, chunk_text: str) -> ExtractionResponse:
        """
        Run the regex-based ``EntityExtractor`` and convert its output into
        an ``ExtractionResponse``.

        The regex extractor does not produce relationship information, so
        ``relationships`` will always be empty in fallback mode.

        Parameters
        ----------
        chunk_text:
            The raw text to extract entities from.

        Returns
        -------
        ExtractionResponse
            Contains ``entities`` derived from regex matches and an empty
            ``relationships`` list.
        """
        try:
            raw = self.fallback.extract(chunk_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Regex EntityExtractor raised an error: %s", exc, exc_info=True)
            return ExtractionResponse()

        # raw = {"entities": List[str], "details": List[{"name": str, "type": str}]}
        details = raw.get("details", [])
        entities: List[ExtractedEntity] = []

        for item in details:
            name = item.get("name", "").strip()
            entity_type = item.get("type", "document").strip()

            if len(name) < 2:
                continue

            try:
                entity = ExtractedEntity(name=name, type=entity_type, description=None)
                entities.append(entity)
            except Exception as exc:  # noqa: BLE001 — Pydantic validation failure
                logger.debug(
                    "Skipping invalid fallback entity name=%r type=%r: %s",
                    name,
                    entity_type,
                    exc,
                )

        logger.debug(
            "Regex fallback extracted %d entities (no relationships)", len(entities)
        )
        return ExtractionResponse(entities=entities, relationships=[])

    # ------------------------------------------------------------------
    # Batch extraction
    # ------------------------------------------------------------------

    async def extract_batch(self, chunks: List[str]) -> List[ExtractionResponse]:
        """
        Extract entities and relationships from a list of text chunks
        concurrently.

        All chunks are dispatched in a single ``asyncio.gather`` call so they
        run concurrently up to the event loop's concurrency limits. A small
        staggered delay (``OLLAMA_BATCH_DELAY`` env var, default 0.1 s) is
        inserted between task starts to avoid thundering-herd pressure on
        Ollama when processing large batches.

        Parameters
        ----------
        chunks:
            Ordered list of text chunks to process. Empty strings are
            handled gracefully by ``extract()``.

        Returns
        -------
        List[ExtractionResponse]
            Extraction results in the same order as the input ``chunks`` list.
            Never shorter or longer than the input.
        """
        if not chunks:
            return []

        logger.info("extract_batch starting | chunk_count=%d", len(chunks))
        t_start = time.perf_counter()

        async def _delayed_extract(index: int, text: str) -> ExtractionResponse:
            """Extract with a staggered start delay based on position."""
            if index > 0 and _BATCH_INTER_REQUEST_DELAY > 0:
                await asyncio.sleep(index * _BATCH_INTER_REQUEST_DELAY)
            return await self.extract(text)

        tasks = [
            _delayed_extract(i, chunk)
            for i, chunk in enumerate(chunks)
        ]

        results: List[ExtractionResponse] = await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - t_start
        total_entities = sum(len(r.entities) for r in results)
        total_rels = sum(len(r.relationships) for r in results)

        logger.info(
            "extract_batch completed | chunks=%d total_entities=%d "
            "total_relationships=%d elapsed=%.3fs",
            len(chunks),
            total_entities,
            total_rels,
            elapsed,
        )

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_result(
        result: ExtractionResponse, *, source: str, elapsed: float
    ) -> None:
        """Emit a structured INFO log line summarising an extraction result."""
        logger.info(
            "Extraction complete | source=%s entities=%d relationships=%d elapsed=%.3fs",
            source,
            len(result.entities),
            len(result.relationships),
            elapsed,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

extractor = OllamaEntityExtractor()
