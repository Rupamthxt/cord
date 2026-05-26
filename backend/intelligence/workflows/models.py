"""
backend/workflows/models.py
---------------------------
SQLAlchemy 2.0 ORM models for the supervised workflow coordination engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.graph.db import Base


class Workflow(Base):
    """Tracks human-in-the-loop workflows for incident response and customer escalations."""

    __tablename__ = "cord_workflows"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    title: str = Column(String(500), nullable=False)
    workflow_type: str = Column(String(100), nullable=False)
    state: str = Column(String(50), nullable=False, default="draft")
    assigned_entities: list = Column(JSONB, nullable=False, default=list)
    related_events: list = Column(JSONB, nullable=False, default=list)
    related_insights: list = Column(JSONB, nullable=False, default=list)
    priority: str = Column(String(50), nullable=False, default="medium")
    workspace_id: str | None = Column(String(500), nullable=True, index=True)
    created_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    metadata_: dict = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    __table_args__ = (
        Index("ix_cord_workflows_workspace_state", "workspace_id", "state"),
        Index("ix_cord_workflows_workspace_priority", "workspace_id", "priority"),
    )

    def __repr__(self) -> str:
        return (
            f"<Workflow id={self.id!s} type={self.workflow_type!r} state={self.state!r} "
            f"workspace={self.workspace_id!r}>"
        )
