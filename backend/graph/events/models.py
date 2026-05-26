"""
backend/events/models.py
------------------------
SQLAlchemy 2.0 ORM models for the Cord event memory layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.graph.db import Base


class Event(Base):
    """Structured operational event extracted from organizational text chunks."""

    __tablename__ = "cord_events"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    event_type: str = Column(String(100), nullable=False)
    title: str = Column(String(500), nullable=False)
    description: str | None = Column(Text, nullable=True)
    timestamp: datetime | None = Column(DateTime, nullable=True)
    source_chunk_id: str = Column(String(500), nullable=False)
    workspace_id: str | None = Column(String(500), nullable=True, index=True)
    severity: str | None = Column(String(50), nullable=True)
    confidence: float = Column(Float, nullable=False, default=0.8)
    metadata_: dict = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_cord_events_workspace_type", "workspace_id", "event_type"),
        Index("ix_cord_events_workspace_timestamp", "workspace_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id!s} type={self.event_type!r} title={self.title!r} "
            f"workspace={self.workspace_id!r}>"
        )


class EventRelationship(Base):
    """Directed connection between two operational events (e.g., caused_by, triggered_by)."""

    __tablename__ = "cord_event_relationships"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    source_event_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_event_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: str = Column(String(100), nullable=False)
    confidence: float = Column(Float, nullable=False, default=0.8)
    workspace_id: str | None = Column(String(500), nullable=True, index=True)
    created_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_cord_event_relationships_source", "source_event_id"),
        Index("ix_cord_event_relationships_target", "target_event_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<EventRelationship {self.source_event_id!s} "
            f"--[{self.relationship_type}]--> {self.target_event_id!s}>"
        )
