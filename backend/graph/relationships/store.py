"""
backend/relationships/store.py
------------------------------
Async data-access layer for Relationship records in the Cord PostgreSQL database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.graph.entities.models import Relationship
from backend.graph.relationships.schema import RelationshipCreate

logger = logging.getLogger(__name__)


class RelationshipStore:
    """Async CRUD store for Relationship records. All operations are workspace-isolated."""

    async def create_relationship(
        self, session: AsyncSession, data: RelationshipCreate
    ) -> Relationship:
        """Create and persist a new relationship."""
        rel = Relationship(
            id=uuid.uuid4(),
            source_entity_id=data.source_entity_id,
            target_entity_id=data.target_entity_id,
            relationship_type=data.relationship_type,
            confidence=data.confidence,
            evidence=data.evidence,
            source_chunk_id=data.source_chunk_id,
            timestamp=datetime.now(timezone.utc),
            workspace_id=data.workspace_id or "default_workspace",
        )
        session.add(rel)
        try:
            await session.flush()
            logger.debug(
                "Created relationship: %s --[%s]--> %s",
                rel.source_entity_id,
                rel.relationship_type,
                rel.target_entity_id,
            )
            return rel
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.create_relationship failed: %s", exc, exc_info=True)
            raise

    async def get_relationship_by_id(
        self, session: AsyncSession, rel_id: uuid.UUID
    ) -> Optional[Relationship]:
        """Fetch a single relationship by primary key."""
        try:
            stmt = select(Relationship).where(Relationship.id == rel_id).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.get_relationship_by_id failed: %s", exc, exc_info=True)
            raise

    async def upsert_relationship(
        self, session: AsyncSession, data: RelationshipCreate
    ) -> Tuple[Relationship, bool]:
        """Upsert a relationship record based on source, target, type, and workspace."""
        try:
            workspace_id = data.workspace_id or "default_workspace"
            stmt = select(Relationship).where(
                Relationship.source_entity_id == data.source_entity_id,
                Relationship.target_entity_id == data.target_entity_id,
                Relationship.relationship_type == data.relationship_type,
                Relationship.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            rel = result.scalar_one_or_none()

            if rel is not None:
                # Update confidence to the max of both
                rel.confidence = max(rel.confidence, data.confidence)
                if data.evidence:
                    # Append or update evidence
                    if rel.evidence:
                        if data.evidence not in rel.evidence:
                            rel.evidence = f"{rel.evidence}\n{data.evidence}"
                    else:
                        rel.evidence = data.evidence
                await session.flush()
                return rel, False
            else:
                new_rel = await self.create_relationship(session, data)
                return new_rel, True
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.upsert_relationship failed: %s", exc, exc_info=True)
            raise

    async def get_outgoing_relationships(
        self, session: AsyncSession, entity_id: uuid.UUID, rel_type: Optional[str] = None
    ) -> List[Relationship]:
        """Get all relationships where the given entity is the source."""
        try:
            stmt = select(Relationship).where(Relationship.source_entity_id == entity_id)
            if rel_type:
                stmt = stmt.where(Relationship.relationship_type == rel_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.get_outgoing_relationships failed: %s", exc, exc_info=True)
            raise

    async def get_incoming_relationships(
        self, session: AsyncSession, entity_id: uuid.UUID, rel_type: Optional[str] = None
    ) -> List[Relationship]:
        """Get all relationships where the given entity is the target."""
        try:
            stmt = select(Relationship).where(Relationship.target_entity_id == entity_id)
            if rel_type:
                stmt = stmt.where(Relationship.relationship_type == rel_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.get_incoming_relationships failed: %s", exc, exc_info=True)
            raise

    async def get_relationships_by_workspace(
        self, session: AsyncSession, workspace_id: str, rel_type: Optional[str] = None, limit: int = 50
    ) -> List[Relationship]:
        """Fetch all relationships for a given workspace."""
        try:
            stmt = select(Relationship).where(Relationship.workspace_id == workspace_id).limit(limit)
            if rel_type:
                stmt = stmt.where(Relationship.relationship_type == rel_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("RelationshipStore.get_relationships_by_workspace failed: %s", exc, exc_info=True)
            raise

    async def get_neighborhood(
        self, session: AsyncSession, entity_id: uuid.UUID, depth: int = 1
    ) -> Dict[str, List[Relationship]]:
        """Get incoming and outgoing relationships within the specified depth."""
        # Cap depth at 2 for performance
        effective_depth = min(max(depth, 1), 2)
        
        outgoing = []
        incoming = []
        
        # Track visited node IDs to avoid cycles
        visited_nodes = {entity_id}
        
        # Queue/Level traversal
        current_level_nodes = {entity_id}
        
        for d in range(effective_depth):
            if not current_level_nodes:
                break
            
            # Fetch outgoing
            stmt_out = select(Relationship).where(Relationship.source_entity_id.in_(current_level_nodes))
            res_out = await session.execute(stmt_out)
            level_outgoing = res_out.scalars().all()
            
            # Fetch incoming
            stmt_in = select(Relationship).where(Relationship.target_entity_id.in_(current_level_nodes))
            res_in = await session.execute(stmt_in)
            level_incoming = res_in.scalars().all()
            
            next_level_nodes = set()
            for r in level_outgoing:
                if r.id not in {x.id for x in outgoing}:
                    outgoing.append(r)
                if r.target_entity_id not in visited_nodes:
                    next_level_nodes.add(r.target_entity_id)
                    visited_nodes.add(r.target_entity_id)
            
            for r in level_incoming:
                if r.id not in {x.id for x in incoming}:
                    incoming.append(r)
                if r.source_entity_id not in visited_nodes:
                    next_level_nodes.add(r.source_entity_id)
                    visited_nodes.add(r.source_entity_id)
                    
            current_level_nodes = next_level_nodes
            
        return {
            "outgoing": outgoing,
            "incoming": incoming,
        }


relationship_store = RelationshipStore()
