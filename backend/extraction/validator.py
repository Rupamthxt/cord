"""
validator.py
============
Pydantic v2 validation layer for LLM extraction responses.

Responsibilities
----------------
* Define the canonical ``ExtractedEntity``, ``ExtractedRelationship``, and
  ``ExtractionResponse`` Pydantic models with field-level validation.
* Expose ``parse_llm_response`` — a fault-tolerant function that accepts the
  raw LLM text output, extracts JSON by several fallback strategies, validates
  it, and always returns a well-formed ``ExtractionResponse`` (never raises).

Design decisions
----------------
* Invalid entity/relationship types are normalised (not rejected) so that the
  pipeline keeps running even when the model produces slightly off-spec output.
* ``model_validator(mode='after')`` removes dangling relationships whose
  source or target are not in the entity list (enforces referential integrity).
* ``parse_llm_response`` is intentionally silent on errors — it logs and
  returns an empty response rather than propagating exceptions, so callers do
  not need try/except blocks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid vocabulary constants
# ---------------------------------------------------------------------------

_VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "person",
        "team",
        "project",
        "product",
        "system",
        "workflow",
        "incident",
        "deployment",
        "customer",
        "department",
        "document",
        "decision",
        "metric",
        "tool",
    }
)

_VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "owns",
        "depends_on",
        "caused",
        "related_to",
        "assigned_to",
        "part_of",
        "blocked_by",
        "affects",
        "manages",
        "deployed_to",
        "escalated_to",
        "discussed_in",
    }
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExtractedEntity(BaseModel):
    """
    A single organisational entity extracted from a text chunk.

    Attributes
    ----------
    name:
        The entity name as it appears in the source text (case-preserved).
        Must be between 2 and 200 characters after stripping whitespace.
    type:
        One of the 14 recognised entity types. Unrecognised values are
        normalised to ``"document"`` with a logged warning.
    description:
        Optional one-sentence description. ``None`` if the model did not
        produce one.
    """

    name: str
    type: str
    description: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: Any) -> str:
        """
        Strip surrounding whitespace and enforce length constraints.

        Raises
        ------
        ValueError
            If the cleaned name is shorter than 2 characters.
        """
        if not isinstance(v, str):
            v = str(v)
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError(
                f"Entity name is too short (must be ≥ 2 chars): {v!r}"
            )
        if len(cleaned) > 200:
            cleaned = cleaned[:200]
            logger.debug("Entity name truncated to 200 chars: %s…", cleaned[:40])
        return cleaned

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: Any) -> str:
        """
        Normalise entity type to lowercase and validate against the known set.

        Unknown types are silently coerced to ``"document"`` and a warning
        is emitted so analysts can refine the prompt over time.
        """
        if not isinstance(v, str):
            v = str(v)
        normalised = v.lower().strip()
        if normalised not in _VALID_ENTITY_TYPES:
            logger.warning(
                "Unknown entity type %r — defaulting to 'document'", v
            )
            return "document"
        return normalised


class ExtractedRelationship(BaseModel):
    """
    A directed relationship between two extracted entities.

    Attributes
    ----------
    source:
        Name of the source entity (must appear in the parent
        ``ExtractionResponse.entities`` list).
    target:
        Name of the target entity (must appear in the parent
        ``ExtractionResponse.entities`` list).
    type:
        One of the 12 recognised relationship types. Unrecognised values
        are normalised to ``"related_to"``.
    evidence:
        A direct quote or close paraphrase from the source text supporting
        this relationship. Optional.
    confidence:
        Float in [0.0, 1.0] indicating extraction confidence. Clamped
        automatically if out of range.
    """

    source: str
    target: str
    type: str
    evidence: Optional[str] = None
    confidence: float = 0.8

    @field_validator("type", mode="before")
    @classmethod
    def validate_rel_type(cls, v: Any) -> str:
        """
        Normalise relationship type string.

        Normalisation steps:
        1. Lowercase and strip whitespace.
        2. Replace spaces and hyphens with underscores.
        3. Validate against the known set; fall back to ``"related_to"``.
        """
        if not isinstance(v, str):
            v = str(v)
        normalised = v.lower().strip().replace(" ", "_").replace("-", "_")
        if normalised not in _VALID_RELATIONSHIP_TYPES:
            logger.warning(
                "Unknown relationship type %r — defaulting to 'related_to'", v
            )
            return "related_to"
        return normalised

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        """Clamp confidence to [0.0, 1.0] regardless of model output."""
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            logger.debug("Invalid confidence value %r — defaulting to 0.8", v)
            return 0.8

    @field_validator("source", "target", mode="before")
    @classmethod
    def strip_endpoint_names(cls, v: Any) -> str:
        """Strip whitespace from source / target names."""
        if not isinstance(v, str):
            v = str(v)
        return v.strip()


class ExtractionResponse(BaseModel):
    """
    The top-level extraction result holding all entities and relationships
    found in a single text chunk.

    Post-validation, the ``relationships`` list is pruned so that it only
    contains entries whose ``source`` and ``target`` both appear in
    ``entities``. This enforces referential integrity across the graph.
    """

    entities: List[ExtractedEntity] = []
    relationships: List[ExtractedRelationship] = []

    @model_validator(mode="after")
    def validate_relationships(self) -> "ExtractionResponse":
        """
        Remove relationships that reference entity names not present in the
        extracted entity list. Comparison is case-insensitive.
        """
        entity_names_lower: set[str] = {e.name.lower() for e in self.entities}

        valid_relationships: List[ExtractedRelationship] = []
        for rel in self.relationships:
            source_ok = rel.source.lower() in entity_names_lower
            target_ok = rel.target.lower() in entity_names_lower
            if source_ok and target_ok:
                valid_relationships.append(rel)
            else:
                logger.debug(
                    "Dropped relationship (%r → %r) — endpoint not in entities",
                    rel.source,
                    rel.target,
                )

        self.relationships = valid_relationships
        return self


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------


def _extract_json_from_raw(raw: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to locate and parse a JSON object from ``raw`` using multiple
    strategies in order of preference.

    Strategy 1 — Direct parse
        Attempt ``json.loads(raw.strip())``.

    Strategy 2 — Brace scanning
        Find the first ``{`` and the last ``}`` and attempt to parse the
        substring between them (handles models that prepend/append prose).

    Strategy 3 — Markdown code fence
        Extract the content of a ``\`\`\`json ... \`\`\``` or
        ``\`\`\` ... \`\`\``` block and attempt to parse it.

    Returns
    -------
    dict or None
        The parsed dictionary on success, or ``None`` if all strategies fail.
    """
    stripped = raw.strip()

    # Strategy 1 — direct parse
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2 — brace scanning
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = stripped[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                logger.debug("JSON extracted via brace-scanning strategy")
                return parsed
        except json.JSONDecodeError:
            pass

    # Strategy 3 — markdown code fence
    fence_pattern = re.compile(
        r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
    )
    match = fence_pattern.search(stripped)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                logger.debug("JSON extracted via markdown code-fence strategy")
                return parsed
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Public parse function
# ---------------------------------------------------------------------------


def parse_llm_response(raw_response: str) -> ExtractionResponse:
    """
    Parse and validate the raw text output from an LLM extraction call.

    This function is intentionally fault-tolerant: it never raises. On any
    error condition it logs the issue and returns an empty
    ``ExtractionResponse``.

    Parameters
    ----------
    raw_response:
        The raw string returned by ``OllamaClient.generate()``.

    Returns
    -------
    ExtractionResponse
        A validated response object. May have empty ``entities`` and
        ``relationships`` lists if parsing or validation fails.

    Notes
    -----
    The parse pipeline is:
    1. Attempt to extract JSON via three successive strategies
       (direct, brace-scan, code-fence).
    2. On JSON extraction failure → log and return empty response.
    3. On Pydantic ``ValidationError`` → log and return empty response.
    """
    if not raw_response or not raw_response.strip():
        logger.warning("parse_llm_response received empty raw_response")
        return ExtractionResponse()

    parsed_json = _extract_json_from_raw(raw_response)

    if parsed_json is None:
        logger.error(
            "Failed to extract JSON from LLM response (all strategies exhausted). "
            "First 200 chars of raw: %r",
            raw_response[:200],
        )
        return ExtractionResponse()

    try:
        result = ExtractionResponse.model_validate(parsed_json)
        logger.debug(
            "LLM response parsed: %d entities, %d relationships",
            len(result.entities),
            len(result.relationships),
        )
        return result

    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError or unexpected
        logger.error(
            "Pydantic validation failed for LLM response: %s | parsed_json=%r",
            exc,
            str(parsed_json)[:300],
        )
        return ExtractionResponse()
