"""
backend/insights/store.py
-------------------------
Async repository store for managing proactive operational insights in PostgreSQL.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.insights.models import Insight
from backend.intelligence.insights.schema import InsightCreate

logger = logging.getLogger(__name__)


class InsightStore:
    """Async CRUD operations on Insight objects with strict workspace isolation."""

    async def get_by_id(
        self,
        session: AsyncSession,
        insight_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Insight]:
        """Fetch a single insight by primary key."""
        try:
            stmt = select(Insight).where(
                Insight.id == insight_id,
                Insight.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("InsightStore.get_by_id failed: %s", exc, exc_info=True)
            raise

    async def list_insights(
        self,
        session: AsyncSession,
        workspace_id: str = "default_workspace",
        insight_types: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Insight]:
        """Query and filter insights from the database."""
        try:
            stmt = select(Insight).where(Insight.workspace_id == workspace_id)

            if insight_types:
                stmt = stmt.where(Insight.insight_type.in_(insight_types))

            if severities:
                stmt = stmt.where(Insight.severity.in_(severities))

            stmt = stmt.order_by(Insight.generated_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("InsightStore.list_insights failed: %s", exc, exc_info=True)
            raise

    async def create_insight(
        self,
        session: AsyncSession,
        payload: InsightCreate,
    ) -> Insight:
        """Create and persist a new proactive insight."""
        insight = Insight(
            id=uuid.uuid4(),
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            insight_type=payload.insight_type,
            confidence=payload.confidence,
            severity=payload.severity,
            supporting_entities=[dict(e) for e in payload.supporting_entities],
            supporting_events=[dict(ev) for ev in payload.supporting_events],
            evidence=list(payload.evidence),
            workspace_id=payload.workspace_id or "default_workspace",
            generated_at=datetime.now(timezone.utc),
            metadata_=payload.metadata,
        )
        session.add(insight)
        try:
            await session.flush()
        except SQLAlchemyError as exc:
            logger.error("InsightStore.create_insight failed: %s", exc, exc_info=True)
            raise
        logger.debug(
            "Created operational insight id=%s type=%r title=%r ws=%r",
            insight.id,
            insight.insight_type,
            insight.title,
            insight.workspace_id,
        )
        return insight

    async def upsert_insight(
        self,
        session: AsyncSession,
        payload: InsightCreate,
    ) -> Tuple[Insight, bool]:
        """Upsert an insight to avoid exact duplicates (same title and category in workspace)."""
        try:
            workspace_id = payload.workspace_id or "default_workspace"
            stmt = select(Insight).where(
                func.lower(Insight.title) == payload.title.strip().lower(),
                Insight.insight_type == payload.insight_type,
                Insight.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # Update details with higher confidence
                existing.summary = payload.summary.strip()
                existing.confidence = max(existing.confidence, payload.confidence)
                existing.severity = payload.severity
                existing.supporting_entities = [dict(e) for e in payload.supporting_entities]
                existing.supporting_events = [dict(ev) for ev in payload.supporting_events]
                existing.evidence = list(payload.evidence)
                # Merge metadata
                if payload.metadata:
                    merged = dict(existing.metadata_)
                    merged.update(payload.metadata)
                    existing.metadata_ = merged
                existing.generated_at = datetime.now(timezone.utc)
                await session.flush()
                return existing, False

            insight = await self.create_insight(session, payload)
            return insight, True
        except SQLAlchemyError as exc:
            logger.error("InsightStore.upsert_insight failed: %s", exc, exc_info=True)
            raise

    async def delete_insight(
        self,
        session: AsyncSession,
        insight_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> bool:
        """Delete an insight from PostgreSQL."""
        try:
            insight = await self.get_by_id(session, insight_id, workspace_id)
            if insight is not None:
                await session.delete(insight)
                await session.flush()
                return True
            return False
        except SQLAlchemyError as exc:
            logger.error("InsightStore.delete_insight failed: %s", exc, exc_info=True)
            raise


# Module singleton
insight_store = InsightStore()
