"""
prompts.py
==========
Prompt templates for LLM-based entity and relationship extraction.

All prompts are class-level constants on ``ExtractionPrompts`` so they can
be imported statically without instantiation overhead. The ``format_prompt``
classmethod performs the single ``{chunk_text}`` substitution safely.
"""

from __future__ import annotations


class ExtractionPrompts:
    """
    Centralised store of carefully engineered extraction prompts.

    Design principles
    -----------------
    * Zero-temperature prompts — instructions are deterministic and tightly
      scoped to avoid hallucination.
    * Strict JSON-only output — the model is explicitly forbidden from
      producing markdown fences, prose preambles, or trailing commentary.
    * Comprehensive entity taxonomy — covers all 14 organizational entity
      types used by the Cord knowledge graph.
    * Explicit confidence semantics — instructs the model to anchor
      confidence values to textual evidence, not assumptions.
    """

    # ------------------------------------------------------------------
    # Entity & relationship extraction prompt
    # ------------------------------------------------------------------

    ENTITY_EXTRACTION_PROMPT: str = """\
You are an organizational knowledge extraction system. Your task is to read \
a passage of organizational text and extract structured entities and \
relationships from it.

────────────────────────────────────────────────────────────────────────────
ENTITY TYPES (use exactly these type strings)
────────────────────────────────────────────────────────────────────────────
  person        — Individual human being (engineer, manager, customer contact, etc.)
  team          — Named group of people with a shared function (e.g. "Platform Team")
  project       — Specific initiative with a defined scope and timeline
  product       — Software product or external-facing service offering
  system        — Technical system, internal service, API, database, or infrastructure component
  workflow      — Defined process, procedure, or repeatable sequence of steps
  incident      — Outage, failure, bug, or named issue event (e.g. "INC-204")
  deployment    — Release, rollout, or infrastructure change event
  customer      — External customer organisation or named account
  department    — High-level organisational unit (Engineering, Sales, Finance, etc.)
  document      — Specific document, specification, runbook, or report
  decision      — Recorded architectural or organisational decision
  metric        — Measurable quantity (e.g. latency, error rate, SLA percentage)
  tool          — Software tool, platform, or third-party service (Jira, Slack, GitHub, etc.)

────────────────────────────────────────────────────────────────────────────
RELATIONSHIP TYPES (use exactly these type strings)
────────────────────────────────────────────────────────────────────────────
  owns           — Entity A is the owner / responsible party for Entity B
  depends_on     — Entity A has a hard dependency on Entity B
  caused         — Entity A directly caused or triggered Entity B
  related_to     — Entity A is loosely associated with Entity B (use as last resort)
  assigned_to    — Entity A (task/project) is assigned to Entity B (person/team)
  part_of        — Entity A is a sub-component or member of Entity B
  blocked_by     — Entity A is blocked or impeded by Entity B
  affects        — Entity A has an impact on Entity B (e.g. incident affects system)
  manages        — Entity A (person/team) manages Entity B (team/project/system)
  deployed_to    — Entity A (system/product) is deployed to Entity B (environment/system)
  escalated_to   — Entity A was escalated to Entity B (person/team)
  discussed_in   — Entity A is discussed or referenced inside Entity B (document/channel)

────────────────────────────────────────────────────────────────────────────
OUTPUT FORMAT — RESPOND WITH ONLY VALID JSON, NO OTHER TEXT
────────────────────────────────────────────────────────────────────────────
Return a single JSON object exactly matching this schema. Do NOT include
markdown code fences, prose, comments, or any text outside the JSON object.

{{
  "entities": [
    {{
      "name": "<entity name as it appears in the text>",
      "type": "<one of the 14 entity types above>",
      "description": "<one sentence description, or null>"
    }}
  ],
  "relationships": [
    {{
      "source": "<name of source entity — must appear in entities list>",
      "target": "<name of target entity — must appear in entities list>",
      "type": "<one of the 12 relationship types above>",
      "evidence": "<direct quote or close paraphrase from the text supporting this relationship>",
      "confidence": 0.85
    }}
  ]
}}

────────────────────────────────────────────────────────────────────────────
RULES
────────────────────────────────────────────────────────────────────────────
1. Only extract entities EXPLICITLY mentioned in the text. Never invent or
   hallucinate entity names that do not appear in the passage.
2. Confidence is a float between 0.0 and 1.0. Use values close to 1.0 for
   relationships stated plainly ("X owns Y"), and lower values (0.5–0.7) for
   relationships that must be inferred from context.
3. If no entities or relationships can be found, return:
   {{"entities": [], "relationships": []}}
4. The "evidence" field for every relationship MUST be a direct quote or a
   close paraphrase drawn from the text — do not fabricate evidence.
5. For every relationship, both "source" and "target" MUST already appear in
   the "entities" array. Do not reference entity names in relationships that
   were not extracted as entities.
6. Entity "name" values should preserve the casing used in the source text.
7. Do not create duplicate entities. If the same entity appears multiple
   times under the same name, list it only once.
8. Prefer specific relationship types over "related_to". Only use "related_to"
   when no other type accurately describes the relationship.

────────────────────────────────────────────────────────────────────────────
TEXT TO ANALYSE
────────────────────────────────────────────────────────────────────────────
{chunk_text}
────────────────────────────────────────────────────────────────────────────
JSON OUTPUT:"""

    # ------------------------------------------------------------------
    # Classmethod API
    # ------------------------------------------------------------------

    @classmethod
    def format_prompt(cls, chunk_text: str) -> str:
        """
        Return the entity-extraction prompt with ``chunk_text`` substituted.

        Parameters
        ----------
        chunk_text:
            The raw organizational text passage to analyse.

        Returns
        -------
        str
            The fully rendered prompt string ready to be sent to the model.

        Notes
        -----
        The template uses ``{{`` / ``}}`` to escape literal braces so that
        Python's ``str.format`` does not misinterpret JSON example braces
        inside the prompt. Only ``{chunk_text}`` is a real substitution site.
        """
        if not chunk_text or not chunk_text.strip():
            raise ValueError("chunk_text must be a non-empty string")

        return cls.ENTITY_EXTRACTION_PROMPT.format(chunk_text=chunk_text.strip())
