"""
backend/insights/models.py
--------------------------
SQLAlchemy 2.0 ORM models for proactive operational insights and anomalies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.graph.db import Base


class Insight(Base):
    """Proactive operational insight or anomaly alert detected in workspace data."""

    __tablename__ = "cord_insights"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    title: str = Column(String(500), nullable=False)
    summary: str = Column(Text, nullable=False)
    insight_type: str = Column(String(100), nullable=False)
    confidence: float = Column(Float, nullable=False, default=0.8)
    severity: str = Column(String(50), nullable=False, default="medium")
    supporting_entities: list = Column(JSONB, nullable=False, default=list)
    supporting_events: list = Column(JSONB, nullable=False, default=list)
    evidence: list = Column(JSONB, nullable=False, default=list)
    workspace_id: str | None = Column(String(500), nullable=True, index=True)
    generated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_: dict = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    __table_args__ = (
        Index("ix_cord_insights_workspace_type", "workspace_id", "insight_type"),
        Index("ix_cord_insights_workspace_severity", "workspace_id", "severity"),
    )

    def __repr__(self) -> str:
        return (
            f"<Insight id={self.id!s} type={self.insight_type!r} title={self.title!r} "
            f"workspace={self.workspace_id!r}>"
        )
