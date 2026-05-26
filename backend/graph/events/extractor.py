"""
backend/events/extractor.py
--------------------------
Ollama-based event and event-relationship extraction with a regex-based heuristic fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.extraction.ollama_client import (
    OllamaClient,
    OllamaTimeoutError,
    OllamaUnavailableError,
    ollama_client,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema for Extraction Outputs
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = {
    "deployment",
    "incident",
    "outage",
    "escalation",
    "release",
    "onboarding_issue",
    "support_spike",
    "customer_complaint",
    "infrastructure_failure",
    "workflow_change",
    "security_event",
    "decision",
    "migration",
    "rollback",
    "performance_issue",
}

VALID_RELATIONSHIP_TYPES = {
    "caused_by",
    "triggered_by",
    "affects",
    "escalated_to",
    "resolved_by",
    "related_to",
    "occurred_after",
    "occurred_before",
}


class ExtractedEvent(BaseModel):
    """Event representation extracted by LLM/Regex."""

    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    severity: Optional[str] = None
    confidence: float = 0.8
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v_lower = v.lower().strip()
        if v_lower in VALID_EVENT_TYPES:
            return v_lower
        # Fallback default type
        return "incident" if "incident" in v_lower or "outage" in v_lower else "decision"

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_lower = v.lower().strip()
        if v_lower in {"low", "medium", "high", "critical"}:
            return v_lower
        return None


class ExtractedEventRelationship(BaseModel):
    """Directed connection between extracted events."""

    source_title: str
    target_title: str
    relationship_type: str
    confidence: float = 0.8

    @field_validator("relationship_type")
    @classmethod
    def validate_rel_type(cls, v: str) -> str:
        v_lower = v.lower().strip().replace(" ", "_").replace("-", "_")
        if v_lower in VALID_RELATIONSHIP_TYPES:
            return v_lower
        return "related_to"


class EventExtractionResponse(BaseModel):
    """Full extraction output with events and event relationships."""

    events: List[ExtractedEvent] = Field(default_factory=list)
    relationships: List[ExtractedEventRelationship] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relationships(self) -> EventExtractionResponse:
        # Ensure relationships only reference extracted events by title
        event_titles = {e.title.lower().strip() for e in self.events}
        self.relationships = [
            r
            for r in self.relationships
            if r.source_title.lower().strip() in event_titles
            and r.target_title.lower().strip() in event_titles
        ]
        return self


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EVENT_EXTRACTION_PROMPT = """\
You are an organizational operational intelligence system. Your task is to analyze organizational texts (logs, Slack updates, alerts, decision logs, wiki pages) and extract structured events and relationships.

────────────────────────────────────────────────────────────────────────────
EVENT TYPES
────────────────────────────────────────────────────────────────────────────
  deployment              - Software deploy, rollout, update, infrastructure release
  incident                - Alert, exception, bug, failure, incident ticket
  outage                  - Service down, system unreachable, high severity outage
  escalation              - Incident escalation, raising to platform or on-call team
  release                 - App release, customer version release
  onboarding_issue        - Issues onboarding a user, customer, or employee
  support_spike           - Support ticket spike, queue overload
  customer_complaint      - Explicit customer feedback, complaints, bug reports
  infrastructure_failure  - AWS down, server hardware failure, network disconnect
  workflow_change         - Process change, code review policy, sprint timeline adjustment
  security_event          - Security vulnerability, audit finding, breach alert, token rotation
  decision                - Tech stack decision, architectural pattern chosen, product decision
  migration               - DB schema migration, cloud vendor migration, library upgrade
  rollback                - Rolling back a deployment or change
  performance_issue       - Memory leak, slow queries, high latency, high CPU load

────────────────────────────────────────────────────────────────────────────
EVENT RELATIONSHIP TYPES (directed from source to target)
────────────────────────────────────────────────────────────────────────────
  caused_by        - Source event was caused by target event (e.g. Outage caused_by Deployment)
  triggered_by     - Source event was triggered by target event
  affects          - Source event affects target event or system
  escalated_to     - Source event was escalated to target event / team escalation
  resolved_by      - Source event was resolved by target event (e.g. Incident resolved_by Rollback)
  related_to       - Loose correlation
  occurred_after   - Source event occurred after target event in time
  occurred_before  - Source event occurred before target event in time

────────────────────────────────────────────────────────────────────────────
OUTPUT FORMAT — RESPOND WITH ONLY VALID JSON, NO OTHER TEXT
────────────────────────────────────────────────────────────────────────────
Return a single JSON object matching this schema. Do NOT use markdown code fences, comments, or any prose.

{{
  "events": [
    {{
      "event_type": "<one of the 15 event types>",
      "title": "<short descriptive title of the event>",
      "description": "<detailed sentence description of what happened, or null>",
      "timestamp": "<ISO-8601 string like '2026-05-25T10:00:00Z' or null>",
      "severity": "<low | medium | high | critical | null>",
      "confidence": 0.85,
      "metadata": {{}}
    }}
  ],
  "relationships": [
    {{
      "source_title": "<title of the source event>",
      "target_title": "<title of the target event>",
      "relationship_type": "<one of the 8 relationship types>",
      "confidence": 0.8
    }}
  ]
}}

────────────────────────────────────────────────────────────────────────────
RULES
────────────────────────────────────────────────────────────────────────────
1. Only extract events explicitly mentioned. Do not hallucinate.
2. Ensure timestamp is parsed properly. If the text says "May 25, 2026 at 10:00 AM", format as "2026-05-25T10:00:00Z". If no date/time is mentioned, use null.
3. Every source_title and target_title in relationships must match the title of an event in the events array exactly.

────────────────────────────────────────────────────────────────────────────
TEXT TO ANALYZE
────────────────────────────────────────────────────────────────────────────
{chunk_text}
────────────────────────────────────────────────────────────────────────────
JSON OUTPUT:"""


# ---------------------------------------------------------------------------
# Extractor Class
# ---------------------------------------------------------------------------


class OllamaEventExtractor:
    """Extracts operational events and relationships from raw text using Ollama or a regex fallback."""

    def __init__(self) -> None:
        self.ollama: OllamaClient = ollama_client
        self._ollama_available: Optional[bool] = None
        self._last_availability_check: float = 0.0
        self.AVAILABILITY_CHECK_INTERVAL: float = 60.0

        # Heuristic keywords for event types
        self.patterns = {
            "outage": re.compile(
                r"\b(outage|downtime|system down|unreachable|service down|offline|crash|db crash)\b",
                re.IGNORECASE,
            ),
            "rollback": re.compile(r"\b(rollback|rolled back|revert)\b", re.IGNORECASE),
            "deployment": re.compile(
                r"\b(deploy|deployment|deployed|rollout|updated production|shipped)\b",
                re.IGNORECASE,
            ),
            "migration": re.compile(
                r"\b(migration|migrated|schema upgrade|db upgrade|db migration)\b",
                re.IGNORECASE,
            ),
            "incident": re.compile(
                r"\b(incident|inc[-_ ][0-9]+|bug|alert|exception|error|prod alert|sev[-_ ][0-9])\b",
                re.IGNORECASE,
            ),
            "escalation": re.compile(
                r"\b(escalated|paged|page|alerted oncall|notified lead)\b", re.IGNORECASE
            ),
            "release": re.compile(r"\b(release|released|v[0-9]+\.[0-9]+)\b", re.IGNORECASE),
            "security_event": re.compile(
                r"\b(security|vulnerability|cve|leak|rotated key|breach)\b", re.IGNORECASE
            ),
            "performance_issue": re.compile(
                r"\b(latency|slow|memory leak|high cpu|high memory|timeout|throttling|cpu spike)\b",
                re.IGNORECASE,
            ),
            "decision": re.compile(
                r"\b(decided|decision|choice|opted to|we will use|adr)\b", re.IGNORECASE
            ),
        }

    async def _check_availability(self) -> bool:
        now = time.monotonic()
        if (
            self._ollama_available is None
            or (now - self._last_availability_check) > self.AVAILABILITY_CHECK_INTERVAL
        ):
            self._ollama_available = await self.ollama.is_available()
            self._last_availability_check = now
            logger.info("Ollama availability checked: %s", self._ollama_available)
        return self._ollama_available

    async def extract(self, chunk_text: str) -> EventExtractionResponse:
        """Extract events and relationships from a text chunk."""
        if not chunk_text or not chunk_text.strip():
            return EventExtractionResponse()

        t_start = time.perf_counter()
        ollama_available = await self._check_availability()

        if not ollama_available:
            logger.info("Ollama unavailable, falling back to regex event extraction.")
            result = self._fallback_extract(chunk_text)
            logger.info("Regex extraction done in %.3fs", time.perf_counter() - t_start)
            return result

        try:
            prompt = EVENT_EXTRACTION_PROMPT.format(chunk_text=chunk_text.strip())
            raw_response = await self.ollama.generate(prompt, temperature=0.0)
            result = self._parse_llm_response(raw_response)

            # If LLM returned nothing but chunk is long, use regex fallback to maximize recall
            if not result.events and len(chunk_text.strip()) > 50:
                logger.warning(
                    "Ollama returned no events for chunk (len=%d). Triggering regex fallback.",
                    len(chunk_text),
                )
                fallback_res = self._fallback_extract(chunk_text)
                if fallback_res.events:
                    return fallback_res

            logger.info(
                "Ollama event extraction complete: %d events, %d relationships in %.3fs",
                len(result.events),
                len(result.relationships),
                time.perf_counter() - t_start,
            )
            return result

        except (OllamaUnavailableError, OllamaTimeoutError) as exc:
            logger.warning(
                "Ollama connection issue (%s) — falling back to regex event extraction.", exc
            )
            self._ollama_available = False
            return self._fallback_extract(chunk_text)
        except Exception as exc:
            logger.error(
                "Unexpected error during Ollama event extraction: %s — switching to fallback.",
                exc,
                exc_info=True,
            )
            return self._fallback_extract(chunk_text)

    def _parse_llm_response(self, raw_response: str) -> EventExtractionResponse:
        """Parse raw response from LLM into verified EventExtractionResponse."""
        if not raw_response:
            return EventExtractionResponse()

        parsed_json = None
        # Attempt to clean code fences or markdown block
        clean_text = raw_response.strip()
        if clean_text.startswith("```"):
            # Find the first line break to strip format name like json
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        # Try to find JSON object bounds { ... }
        match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1)

        try:
            parsed_json = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON from Ollama event extraction: %s", exc)
            logger.debug("Raw Ollama output: %r", raw_response)
            return EventExtractionResponse()

        try:
            return EventExtractionResponse.model_validate(parsed_json)
        except Exception as exc:
            logger.error("Pydantic validation failed for Ollama event response: %s", exc)
            return EventExtractionResponse()

    def _fallback_extract(self, chunk_text: str) -> EventExtractionResponse:
        """Fallback regex-based heuristic extractor for events."""
        events: List[ExtractedEvent] = []
        relationships: List[ExtractedEventRelationship] = []

        lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
        for line in lines:
            # Check for matches
            matched_type = None
            for event_type, pattern in self.patterns.items():
                if pattern.search(line):
                    matched_type = event_type
                    break

            if matched_type:
                # Clean up line to serve as title (max 100 chars)
                title = line
                if len(title) > 100:
                    title = title[:97] + "..."

                # Try to extract date/time pattern (e.g. YYYY-MM-DD or similar)
                timestamp = None
                date_match = re.search(
                    r"\b(20\d{2}[-/]\d{2}[-/]\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\b", line
                )
                if date_match:
                    try:
                        timestamp = datetime.fromisoformat(
                            date_match.group(1).replace("/", "-")
                        )
                    except ValueError:
                        pass

                events.append(
                    ExtractedEvent(
                        event_type=matched_type,
                        title=title,
                        description=line,
                        timestamp=timestamp,
                        confidence=0.6,
                        severity="high"
                        if matched_type in {"outage", "security_event"}
                        else "medium",
                        metadata={"extraction_method": "regex_fallback"},
                    )
                )

        # Build chronological relationship heuristics if multiple events found
        if len(events) > 1:
            for i in range(len(events) - 1):
                relationships.append(
                    ExtractedEventRelationship(
                        source_title=events[i + 1].title,
                        target_title=events[i].title,
                        relationship_type="occurred_after",
                        confidence=0.5,
                    )
                )

        return EventExtractionResponse(events=events, relationships=relationships)


# Module-level singleton
event_extractor = OllamaEventExtractor()
