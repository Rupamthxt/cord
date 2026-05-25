"""
backend/entities/deduplicator.py
---------------------------------
Heuristic + embedding-based entity deduplication for the Cord graph layer.

The :class:`EntityDeduplicator` receives a raw extracted entity (name +
type) and attempts to resolve it to an existing canonical entity in the
PostgreSQL store before a new record is created.

Resolution strategy (applied in order):
    1. **Exact match** — case-insensitive equality on (name, type, workspace).
    2. **Alias match** — check if the name matches any stored ``aliases_str``
       token for the same type + workspace.
    3. **Token overlap** — high Jaccard similarity between tokenised names of
       the same type (threshold configurable, default 0.8).
    4. **Embedding cosine similarity** — encode both names and compute cosine;
       accept if similarity ≥ ``EMBEDDING_THRESHOLD`` (default 0.92).

If no match is found the caller is expected to create a new entity via
:class:`~backend.entities.store.EntityStore`.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.entities.models import Entity
from backend.entities.store import EntityStore, entity_store

logger = logging.getLogger(__name__)

# Cosine similarity threshold for embedding-based deduplication.
_EMBEDDING_THRESHOLD: float = 0.92

# Jaccard token overlap threshold for heuristic deduplication.
_JACCARD_THRESHOLD: float = 0.80


def _tokenise(text: str) -> set[str]:
    """Lowercase word tokenisation, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two float vectors."""
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(x * x for x in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EntityDeduplicator:
    """Resolve a raw extracted entity mention to an existing canonical entity.

    Attributes:
        store: The :class:`~backend.entities.store.EntityStore` singleton used
               for all DB queries.
        embedding_threshold: Minimum cosine similarity to consider two entity
                              names a match. Default ``0.92``.
        jaccard_threshold:   Minimum Jaccard overlap to consider a token-level
                             match. Default ``0.80``.
    """

    def __init__(
        self,
        store: Optional[EntityStore] = None,
        embedding_threshold: float = _EMBEDDING_THRESHOLD,
        jaccard_threshold: float = _JACCARD_THRESHOLD,
    ) -> None:
        self.store: EntityStore = store or entity_store
        self.embedding_threshold = embedding_threshold
        self.jaccard_threshold = jaccard_threshold

    async def resolve(
        self,
        session: AsyncSession,
        name: str,
        entity_type: str,
        workspace_id: str = "default_workspace",
    ) -> Optional[Entity]:
        """Attempt to find an existing canonical entity that matches the input.

        Runs the four-stage resolution strategy and returns the first match
        found. Returns ``None`` if no satisfactory match exists (caller should
        create a new entity).

        Args:
            session:      Active async DB session (read-only queries).
            name:         Raw entity name string to resolve.
            entity_type:  Semantic category of the entity.
            workspace_id: Workspace isolation key.

        Returns:
            The matched :class:`~backend.entities.models.Entity` ORM instance,
            or ``None`` if no match was found.
        """
        name = name.strip()
        if not name:
            return None

        # ----------------------------------------------------------------
        # Stage 1: Exact name match
        # ----------------------------------------------------------------
        match = await self.store.get_by_name(session, name, entity_type, workspace_id)
        if match is not None:
            logger.debug(
                "Dedup: exact match '%s' → entity %s", name, match.id
            )
            return match

        # ----------------------------------------------------------------
        # Stage 2: Alias match
        # ----------------------------------------------------------------
        alias_match = await self._resolve_by_alias(
            session, name, entity_type, workspace_id
        )
        if alias_match is not None:
            logger.debug(
                "Dedup: alias match '%s' → entity %s", name, alias_match.id
            )
            return alias_match

        # ----------------------------------------------------------------
        # Stage 3: Token overlap (Jaccard)
        # ----------------------------------------------------------------
        candidates = await self.store.list_entities(
            session,
            workspace_id=workspace_id,
            entity_type=entity_type,
            limit=200,
        )
        name_tokens = _tokenise(name)
        best_jaccard: float = 0.0
        best_jaccard_entity: Optional[Entity] = None

        for candidate in candidates:
            cand_tokens = _tokenise(candidate.name)
            score = _jaccard(name_tokens, cand_tokens)
            if score > best_jaccard:
                best_jaccard = score
                best_jaccard_entity = candidate

        if best_jaccard >= self.jaccard_threshold and best_jaccard_entity is not None:
            logger.debug(
                "Dedup: jaccard match '%s' → '%s' (score=%.3f)",
                name,
                best_jaccard_entity.name,
                best_jaccard,
            )
            return best_jaccard_entity

        # ----------------------------------------------------------------
        # Stage 4: Embedding cosine similarity
        # ----------------------------------------------------------------
        embedding_match = await self._resolve_by_embedding(
            session, name, entity_type, workspace_id, candidates
        )
        if embedding_match is not None:
            logger.debug(
                "Dedup: embedding match '%s' → entity %s",
                name,
                embedding_match.id,
            )
            return embedding_match

        logger.debug("Dedup: no match found for '%s' (type=%s)", name, entity_type)
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_by_alias(
        self,
        session: AsyncSession,
        name: str,
        entity_type: str,
        workspace_id: str,
    ) -> Optional[Entity]:
        """Check if ``name`` matches any alias token in stored entities.

        Aliases are stored as a comma-separated string in ``aliases_str``;
        we tokenise and compare case-insensitively.
        """
        candidates = await self.store.list_entities(
            session,
            workspace_id=workspace_id,
            entity_type=entity_type,
            limit=200,
        )
        name_lower = name.strip().lower()
        for entity in candidates:
            if not entity.aliases_str:
                continue
            aliases = [a.strip().lower() for a in entity.aliases_str.split(",") if a.strip()]
            if name_lower in aliases:
                return entity
        return None

    async def _resolve_by_embedding(
        self,
        session: AsyncSession,
        name: str,
        entity_type: str,
        workspace_id: str,
        candidates: list[Entity],
    ) -> Optional[Entity]:
        """Embed ``name`` and compare against candidate entity names.

        Uses the same ``get_embedding`` function as the rest of the Cord
        stack (BAAI/bge-small-en-v1.5, 384-dim).
        """
        try:
            from backend.embeddings.model import get_embedding

            name_vec = get_embedding(name)
            best_score: float = 0.0
            best_entity: Optional[Entity] = None

            for candidate in candidates:
                cand_vec = get_embedding(candidate.name)
                score = _cosine(name_vec, cand_vec)
                if score > best_score:
                    best_score = score
                    best_entity = candidate

            if best_score >= self.embedding_threshold and best_entity is not None:
                return best_entity
            return None
        except Exception as exc:
            # Embedding failures are non-fatal — fall through to "no match"
            logger.warning(
                "Dedup: embedding resolution failed for '%s': %s", name, exc
            )
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

entity_deduplicator = EntityDeduplicator()
