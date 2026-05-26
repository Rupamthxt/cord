"""
backend/entities/store.py
--------------------------
Async data-access layer for canonical Entity and ChunkEntityRef records in
the Cord PostgreSQL graph database.

All public methods accept a ``workspace_id`` parameter and enforce strict
tenant isolation — no query ever crosses workspace boundaries.

Usage::

    async with get_db_session() as session:
        entity = await entity_store.get_or_create(
            session,
            name="Alice Johnson",
            entity_type="person",
            workspace_id="acme_corp",
        )
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.graph.entities.models import ChunkEntityRef, Entity
from backend.graph.entities.schema import EntityCreate

logger = logging.getLogger(__name__)


class EntityStore:
    """Async CRUD + dedup-aware store for :class:`~backend.graph.entities.models.Entity`.

    All mutating methods rely on the caller-supplied ``session``; the store
    itself is stateless and can be used as a singleton.
    """

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Entity]:
        """Fetch a single entity by primary key, scoped to workspace.

        Args:
            session:      Active async DB session.
            entity_id:    UUID primary key.
            workspace_id: Workspace isolation key.

        Returns:
            The :class:`Entity` ORM instance, or ``None`` if not found.
        """
        try:
            stmt = (
                select(Entity)
                .where(Entity.id == entity_id, Entity.workspace_id == workspace_id)
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("EntityStore.get_by_id failed: %s", exc, exc_info=True)
            raise

    async def get_by_name(
        self,
        session: AsyncSession,
        name: str,
        entity_type: Optional[str],
        workspace_id: str = "default_workspace",
    ) -> Optional[Entity]:
        """Exact-match lookup on (name, type, workspace).

        Args:
            session:      Active async DB session.
            name:         Canonical entity name (case-sensitive stored value).
            entity_type:  Optional type filter; if ``None``, matches any type.
            workspace_id: Workspace isolation key.

        Returns:
            The matching :class:`Entity`, or ``None``.
        """
        try:
            stmt = select(Entity).where(
                func.lower(Entity.name) == name.strip().lower(),
                Entity.workspace_id == workspace_id,
            )
            if entity_type:
                stmt = stmt.where(Entity.type == entity_type)
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("EntityStore.get_by_name failed: %s", exc, exc_info=True)
            raise

    async def list_entities(
        self,
        session: AsyncSession,
        workspace_id: str = "default_workspace",
        entity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """Paginated listing of entities filtered by workspace and optional type.

        Args:
            session:      Active async DB session.
            workspace_id: Workspace isolation key.
            entity_type:  Optional type filter.
            limit:        Maximum rows to return (default 100).
            offset:       Row offset for pagination (default 0).

        Returns:
            List of :class:`Entity` ORM instances.
        """
        try:
            stmt = (
                select(Entity)
                .where(Entity.workspace_id == workspace_id)
                .order_by(Entity.name)
                .limit(limit)
                .offset(offset)
            )
            if entity_type:
                stmt = stmt.where(Entity.type == entity_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("EntityStore.list_entities failed: %s", exc, exc_info=True)
            raise

    async def fuzzy_search(
        self,
        session: AsyncSession,
        query: str,
        workspace_id: str = "default_workspace",
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Entity]:
        """Substring / ILIKE search on entity name.

        Uses PostgreSQL ``ILIKE`` for case-insensitive partial matching.
        For semantic (embedding-based) matching the caller should use the
        deduplicator or a vector search layer on top.

        Args:
            session:      Active async DB session.
            query:        Search string (will be wrapped in ``%…%``).
            workspace_id: Workspace isolation key.
            entity_type:  Optional type filter.
            limit:        Maximum rows to return.

        Returns:
            List of matching :class:`Entity` instances ordered by name.
        """
        try:
            pattern = f"%{query.strip()}%"
            stmt = (
                select(Entity)
                .where(
                    Entity.workspace_id == workspace_id,
                    Entity.name.ilike(pattern),
                )
                .order_by(Entity.name)
                .limit(limit)
            )
            if entity_type:
                stmt = stmt.where(Entity.type == entity_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("EntityStore.fuzzy_search failed: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create(
        self,
        session: AsyncSession,
        payload: EntityCreate,
    ) -> Entity:
        """Create and persist a new entity.

        Args:
            session: Active async DB session.
            payload: Validated :class:`~backend.graph.entities.schema.EntityCreate`.

        Returns:
            Newly created :class:`Entity` ORM instance (flushed, not yet
            committed — caller controls the transaction).

        Raises:
            IntegrityError: If a duplicate (name, type, workspace) already exists.
        """
        entity = Entity(
            id=uuid.uuid4(),
            name=payload.name.strip(),
            type=payload.type,
            aliases_str=",".join(payload.aliases) if payload.aliases else None,
            description=payload.description,
            source_chunk_id=payload.source_chunk_id,
            workspace_id=payload.workspace_id or "default_workspace",
            metadata_=payload.metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(entity)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            logger.warning(
                "EntityStore.create IntegrityError (duplicate?): %s", exc
            )
            raise
        logger.debug(
            "Created entity id=%s name=%r type=%r ws=%r",
            entity.id,
            entity.name,
            entity.type,
            entity.workspace_id,
        )
        return entity

    async def get_or_create(
        self,
        session: AsyncSession,
        name: str,
        entity_type: str,
        workspace_id: str = "default_workspace",
        source_chunk_id: Optional[str] = None,
        description: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
    ) -> tuple[Entity, bool]:
        """Fetch an existing entity or create it if absent.

        Uses an upsert-style pattern: attempts a SELECT first, then INSERT
        if not found, handling the race-condition case via
        :exc:`IntegrityError` catch-and-retry.

        Args:
            session:        Active async DB session.
            name:           Canonical entity name.
            entity_type:    Semantic category.
            workspace_id:   Workspace isolation key.
            source_chunk_id: Qdrant chunk ID where entity was first seen.
            description:    Optional description.
            aliases:        Alternate surface forms.
            metadata:       Extra metadata dict.
            confidence:     Extraction confidence.

        Returns:
            ``(entity, created)`` tuple where ``created`` is ``True`` if a
            new record was inserted, ``False`` if an existing one was found.
        """
        # Step 1: try SELECT
        existing = await self.get_by_name(session, name, entity_type, workspace_id)
        if existing is not None:
            # Bump updated_at and source_count on re-encounter
            existing.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return existing, False

        # Step 2: INSERT
        payload = EntityCreate(
            name=name,
            type=entity_type,  # type: ignore[arg-type]
            aliases=aliases or [],
            description=description,
            source_chunk_id=source_chunk_id,
            workspace_id=workspace_id,
            metadata=metadata or {},
        )
        try:
            entity = await self.create(session, payload)
            return entity, True
        except IntegrityError:
            # Race: another concurrent writer inserted first; re-fetch
            await session.rollback()
            existing = await self.get_by_name(session, name, entity_type, workspace_id)
            if existing is not None:
                return existing, False
            raise

    async def upsert_chunk_entity_ref(
        self,
        session: AsyncSession,
        chunk_id: str,
        entity_id: uuid.UUID,
        workspace_id: str,
        mention_text: str,
    ) -> ChunkEntityRef:
        """Create or silently skip a ChunkEntityRef record.

        Uses PostgreSQL ``INSERT … ON CONFLICT DO NOTHING`` semantics so that
        repeated processing of the same chunk is idempotent.

        Args:
            session:      Active async DB session.
            chunk_id:     Qdrant point ID string for the source chunk.
            entity_id:    UUID of the canonical entity.
            workspace_id: Workspace isolation key.
            mention_text: Raw surface form seen in the chunk.

        Returns:
            The existing or newly created :class:`ChunkEntityRef` record.
        """
        # Try to find existing ref first (avoids INSERT round-trip if duplicate)
        stmt = select(ChunkEntityRef).where(
            ChunkEntityRef.chunk_id == chunk_id,
            ChunkEntityRef.entity_id == entity_id,
        ).limit(1)
        result = await session.execute(stmt)
        existing_ref = result.scalar_one_or_none()
        if existing_ref is not None:
            return existing_ref

        ref = ChunkEntityRef(
            id=uuid.uuid4(),
            chunk_id=chunk_id,
            entity_id=entity_id,
            workspace_id=workspace_id,
            mention_text=mention_text,
        )
        session.add(ref)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            # Re-fetch after rollback
            result = await session.execute(stmt)
            existing_ref = result.scalar_one_or_none()
            if existing_ref is not None:
                return existing_ref
            raise
        return ref

    async def get_chunk_entity_refs(
        self,
        session: AsyncSession,
        chunk_id: str,
        workspace_id: str = "default_workspace",
    ) -> List[ChunkEntityRef]:
        """Fetch all entity references for a given Qdrant chunk ID.

        Args:
            session:      Active async DB session.
            chunk_id:     Qdrant point ID.
            workspace_id: Workspace isolation key.

        Returns:
            List of :class:`ChunkEntityRef` records.
        """
        try:
            stmt = select(ChunkEntityRef).where(
                ChunkEntityRef.chunk_id == chunk_id,
                ChunkEntityRef.workspace_id == workspace_id,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error(
                "EntityStore.get_chunk_entity_refs failed: %s", exc, exc_info=True
            )
            raise

    async def get_chunks_for_entity(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        workspace_id: str = "default_workspace",
        limit: int = 50,
    ) -> List[str]:
        """Return all chunk_ids that mention a given entity.

        Args:
            session:      Active async DB session.
            entity_id:    UUID of the canonical entity.
            workspace_id: Workspace isolation key.
            limit:        Maximum chunk IDs to return.

        Returns:
            List of Qdrant chunk ID strings.
        """
        try:
            stmt = (
                select(ChunkEntityRef.chunk_id)
                .where(
                    ChunkEntityRef.entity_id == entity_id,
                    ChunkEntityRef.workspace_id == workspace_id,
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
        except SQLAlchemyError as exc:
            logger.error(
                "EntityStore.get_chunks_for_entity failed: %s", exc, exc_info=True
            )
            raise

    async def count_by_type(
        self,
        session: AsyncSession,
        workspace_id: str = "default_workspace",
    ) -> Dict[str, int]:
        """Return entity counts grouped by type for a workspace.

        Args:
            session:      Active async DB session.
            workspace_id: Workspace isolation key.

        Returns:
            Mapping of ``entity_type → count``.
        """
        try:
            stmt = (
                select(Entity.type, func.count(Entity.id).label("cnt"))
                .where(Entity.workspace_id == workspace_id)
                .group_by(Entity.type)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result.all()}
        except SQLAlchemyError as exc:
            logger.error(
                "EntityStore.count_by_type failed: %s", exc, exc_info=True
            )
            raise

    async def merge_entities(
        self,
        session: AsyncSession,
        canonical_id: uuid.UUID,
        duplicate_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> None:
        """Merge a duplicate entity into a canonical entity.

        Reassigns all :class:`ChunkEntityRef` records from ``duplicate_id``
        to ``canonical_id``, then deletes the duplicate :class:`Entity`.

        Args:
            session:       Active async DB session.
            canonical_id:  UUID of the authoritative entity to keep.
            duplicate_id:  UUID of the entity to be merged and deleted.
            workspace_id:  Workspace isolation key.
        """
        try:
            # Re-point chunk refs to canonical
            await session.execute(
                update(ChunkEntityRef)
                .where(
                    ChunkEntityRef.entity_id == duplicate_id,
                    ChunkEntityRef.workspace_id == workspace_id,
                )
                .values(entity_id=canonical_id)
            )
            # Delete the duplicate entity
            dup = await self.get_by_id(session, duplicate_id, workspace_id)
            if dup is not None:
                await session.delete(dup)
            await session.flush()
            logger.info(
                "Merged entity %s → %s in workspace %r",
                duplicate_id,
                canonical_id,
                workspace_id,
            )
        except SQLAlchemyError as exc:
            logger.error("EntityStore.merge_entities failed: %s", exc, exc_info=True)
            raise


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

entity_store = EntityStore()
