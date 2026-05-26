"""
backend/timelines/builder.py
----------------------------
Aggregates sequences of chronological events, filters them, and performs
sequence and interval analysis.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.graph.entities.models import ChunkEntityRef, Entity
from backend.graph.events.models import Event
from backend.graph.events.store import event_store

logger = logging.getLogger(__name__)


class TimelineEvent(BaseModel):
    """Represent an event enriched with entity references for timeline presentation."""

    id: uuid.UUID
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    severity: Optional[str] = None
    confidence: float
    source_chunk_id: str
    workspace_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    entities: List[Dict[str, Any]] = Field(default_factory=list)


class TimelineSequenceItem(BaseModel):
    """An event along with temporal delta relative to the previous event in the timeline."""

    event: TimelineEvent
    time_since_previous_seconds: Optional[float] = None
    time_since_previous_str: Optional[str] = None


class TimelineResponse(BaseModel):
    """Structured response containing chronological sequence items."""

    workspace_id: str
    events: List[TimelineSequenceItem] = Field(default_factory=list)
    total_count: int = 0


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60.0
    if hours < 24:
        return f"{int(hours)}h {int(minutes % 60)}m"
    days = hours / 24.0
    return f"{int(days)}d {int(hours % 24)}h"


class TimelineBuilder:
    """Aggregates and formats operational events into sequence-analyzed timelines."""

    async def build_timeline(
        self,
        session: Any,
        workspace_id: str = "default_workspace",
        event_types: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        entity_ids: Optional[List[uuid.UUID]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TimelineResponse:
        """Fetch, filter, and sequence-analyze events for a workspace timeline."""
        try:
            # 1. Fetch events matching basic filters
            events = await event_store.list_events(
                session=session,
                workspace_id=workspace_id,
                event_types=event_types,
                severities=severities,
                start_time=start_time,
                end_time=end_time,
                limit=limit * 2,  # Oversample to allow entity filtering if needed
                offset=offset,
            )

            # 2. Filter by entity_ids if specified
            if entity_ids:
                # Find chunks linked to these entities
                chunk_stmt = select(ChunkEntityRef.chunk_id).where(
                    ChunkEntityRef.entity_id.in_(entity_ids)
                )
                chunk_result = await session.execute(chunk_stmt)
                linked_chunk_ids = {row[0] for row in chunk_result.all()}

                # Filter events whose source_chunk_id matches
                events = [
                    e for e in events if e.source_chunk_id in linked_chunk_ids
                ]

            # Limit back to user-specified size
            events = events[:limit]

            if not events:
                return TimelineResponse(workspace_id=workspace_id, events=[], total_count=0)

            # 3. Fetch linked entities for these events' source_chunk_ids
            chunk_ids = [e.source_chunk_id for e in events if e.source_chunk_id]
            entities_by_chunk: Dict[str, List[Dict[str, Any]]] = {}

            if chunk_ids:
                ref_stmt = (
                    select(ChunkEntityRef.chunk_id, Entity.id, Entity.name, Entity.type)
                    .join(Entity, ChunkEntityRef.entity_id == Entity.id)
                    .where(ChunkEntityRef.chunk_id.in_(chunk_ids))
                )
                ref_result = await session.execute(ref_stmt)
                for chunk_id, ent_id, ent_name, ent_type in ref_result.all():
                    if chunk_id not in entities_by_chunk:
                        entities_by_chunk[chunk_id] = []
                    entities_by_chunk[chunk_id].append({
                        "id": ent_id,
                        "name": ent_name,
                        "type": ent_type,
                    })

            # 4. Convert to rich TimelineEvent and sort ascending (oldest first)
            timeline_events: List[TimelineEvent] = []
            for e in events:
                linked_ents = entities_by_chunk.get(e.source_chunk_id, [])
                timeline_events.append(
                    TimelineEvent(
                        id=e.id,
                        event_type=e.event_type,
                        title=e.title,
                        description=e.description,
                        timestamp=e.timestamp,
                        severity=e.severity,
                        confidence=e.confidence,
                        source_chunk_id=e.source_chunk_id,
                        workspace_id=e.workspace_id or workspace_id,
                        metadata=e.metadata_ or {},
                        entities=linked_ents,
                    )
                )

            # Sort by timestamp ascending for sequential delta calculation
            # If timestamp is None, sort by created_at
            timeline_events.sort(
                key=lambda x: x.timestamp.replace(tzinfo=None)
                if x.timestamp
                else datetime.min
            )

            # 5. Compute chronological sequences and time deltas
            sequence_items: List[TimelineSequenceItem] = []
            prev_timestamp: Optional[datetime] = None

            for t_ev in timeline_events:
                item = TimelineSequenceItem(event=t_ev)
                if prev_timestamp and t_ev.timestamp:
                    # Calculate difference
                    delta = (t_ev.timestamp - prev_timestamp).total_seconds()
                    item.time_since_previous_seconds = delta
                    item.time_since_previous_str = format_duration(delta)

                sequence_items.append(item)
                if t_ev.timestamp:
                    prev_timestamp = t_ev.timestamp

            return TimelineResponse(
                workspace_id=workspace_id,
                events=sequence_items,
                total_count=len(sequence_items),
            )

        except Exception as exc:
            logger.error("TimelineBuilder.build_timeline failed: %s", exc, exc_info=True)
            raise


# Module singleton
timeline_builder = TimelineBuilder()
