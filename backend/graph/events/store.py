"""
backend/events/store.py
-----------------------
Async data-access layer for Event and EventRelationship records in the Cord
PostgreSQL graph database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.graph.events.models import Event, EventRelationship
from backend.graph.events.schema import EventCreate, EventRelationshipCreate

logger = logging.getLogger(__name__)


class EventStore:
    """Async CRUD and query engine for Event and EventRelationship ORM objects."""

    # -----------------------------------------------------------------------
    # Event Reads
    # -----------------------------------------------------------------------

    async def get_by_id(
        self,
        session: AsyncSession,
        event_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Event]:
        """Fetch a single event by primary key, scoped by workspace."""
        try:
            stmt = (
                select(Event)
                .where(Event.id == event_id, Event.workspace_id == workspace_id)
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("EventStore.get_by_id failed: %s", exc, exc_info=True)
            raise

    async def list_events(
        self,
        session: AsyncSession,
        workspace_id: str = "default_workspace",
        event_types: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Event]:
        """Query and filter events from the store."""
        try:
            stmt = select(Event).where(Event.workspace_id == workspace_id)

            if event_types:
                stmt = stmt.where(Event.event_type.in_(event_types))

            if severities:
                stmt = stmt.where(Event.severity.in_(severities))

            if start_time:
                stmt = stmt.where(Event.timestamp >= start_time)

            if end_time:
                stmt = stmt.where(Event.timestamp <= end_time)

            stmt = stmt.order_by(Event.timestamp.desc(), Event.created_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("EventStore.list_events failed: %s", exc, exc_info=True)
            raise

    # -----------------------------------------------------------------------
    # Event Writes
    # -----------------------------------------------------------------------

    async def create_event(
        self,
        session: AsyncSession,
        payload: EventCreate,
    ) -> Event:
        """Insert a new event record into the database."""
        event = Event(
            id=uuid.uuid4(),
            event_type=payload.event_type,
            title=payload.title.strip(),
            description=payload.description,
            timestamp=payload.timestamp,
            source_chunk_id=payload.source_chunk_id,
            workspace_id=payload.workspace_id or "default_workspace",
            severity=payload.severity,
            confidence=payload.confidence,
            metadata_=payload.metadata,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            logger.warning("EventStore.create_event IntegrityError (duplicate?): %s", exc)
            raise
        except SQLAlchemyError as exc:
            logger.error("EventStore.create_event failed: %s", exc, exc_info=True)
            raise

        logger.debug(
            "Created event id=%s type=%r title=%r ws=%r",
            event.id,
            event.event_type,
            event.title,
            event.workspace_id,
        )
        return event

    async def upsert_event(
        self,
        session: AsyncSession,
        payload: EventCreate,
    ) -> Tuple[Event, bool]:
        """Upsert an event based on duplicate heuristics (e.g. title, event_type, timestamp, workspace).

        If an event with same title, type, and timestamp (or within a 5 min window) exists,
        it will be updated. Otherwise, a new event is created.
        """
        try:
            workspace_id = payload.workspace_id or "default_workspace"
            # Look for exact or very similar title and type
            stmt = select(Event).where(
                func.lower(Event.title) == payload.title.strip().lower(),
                Event.event_type == payload.event_type,
                Event.workspace_id == workspace_id,
            )

            # If timestamp is provided, look within a 5-minute window
            if payload.timestamp:
                stmt = stmt.where(
                    and_(
                        Event.timestamp >= payload.timestamp - datetime.resolution * 300,
                        Event.timestamp <= payload.timestamp + datetime.resolution * 300,
                    )
                )

            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # Update properties if incoming is richer
                if payload.description and not existing.description:
                    existing.description = payload.description
                if payload.severity and not existing.severity:
                    existing.severity = payload.severity
                # Take max confidence
                existing.confidence = max(existing.confidence, payload.confidence)
                # Merge metadata
                if payload.metadata:
                    merged = dict(existing.metadata_)
                    merged.update(payload.metadata)
                    existing.metadata_ = merged
                await session.flush()
                return existing, False

            # Create new
            event = await self.create_event(session, payload)
            return event, True

        except SQLAlchemyError as exc:
            logger.error("EventStore.upsert_event failed: %s", exc, exc_info=True)
            raise

    # -----------------------------------------------------------------------
    # Event Relationship Writes & Reads
    # -----------------------------------------------------------------------

    async def create_relationship(
        self,
        session: AsyncSession,
        payload: EventRelationshipCreate,
    ) -> EventRelationship:
        """Insert a new relationship between two events."""
        rel = EventRelationship(
            id=uuid.uuid4(),
            source_event_id=payload.source_event_id,
            target_event_id=payload.target_event_id,
            relationship_type=payload.relationship_type,
            confidence=payload.confidence,
            workspace_id=payload.workspace_id or "default_workspace",
            created_at=datetime.now(timezone.utc),
        )
        session.add(rel)
        try:
            await session.flush()
        except SQLAlchemyError as exc:
            logger.error("EventStore.create_relationship failed: %s", exc, exc_info=True)
            raise
        return rel

    async def upsert_relationship(
        self,
        session: AsyncSession,
        payload: EventRelationshipCreate,
    ) -> Tuple[EventRelationship, bool]:
        """Upsert a relationship to avoid duplicates."""
        try:
            workspace_id = payload.workspace_id or "default_workspace"
            stmt = select(EventRelationship).where(
                EventRelationship.source_event_id == payload.source_event_id,
                EventRelationship.target_event_id == payload.target_event_id,
                EventRelationship.relationship_type == payload.relationship_type,
                EventRelationship.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # Update confidence to max
                existing.confidence = max(existing.confidence, payload.confidence)
                await session.flush()
                return existing, False

            rel = await self.create_relationship(session, payload)
            return rel, True
        except SQLAlchemyError as exc:
            logger.error("EventStore.upsert_relationship failed: %s", exc, exc_info=True)
            raise

    async def get_event_neighborhood(
        self,
        session: AsyncSession,
        event_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Dict[str, Any]:
        """Fetch immediate outgoing and incoming event relationships and target events."""
        try:
            # Outgoing
            out_stmt = select(EventRelationship, Event).join(
                Event, EventRelationship.target_event_id == Event.id
            ).where(
                EventRelationship.source_event_id == event_id,
                EventRelationship.workspace_id == workspace_id,
            )
            out_result = await session.execute(out_stmt)
            outgoing_list = []
            for rel, target in out_result.all():
                outgoing_list.append({
                    "relationship": rel,
                    "event": target
                })

            # Incoming
            in_stmt = select(EventRelationship, Event).join(
                Event, EventRelationship.source_event_id == Event.id
            ).where(
                EventRelationship.target_event_id == event_id,
                EventRelationship.workspace_id == workspace_id,
            )
            in_result = await session.execute(in_stmt)
            incoming_list = []
            for rel, source in in_result.all():
                incoming_list.append({
                    "relationship": rel,
                    "event": source
                })

            return {
                "outgoing": outgoing_list,
                "incoming": incoming_list,
            }
        except SQLAlchemyError as exc:
            logger.error("EventStore.get_event_neighborhood failed: %s", exc, exc_info=True)
            raise


# Module singleton
event_store = EventStore()
