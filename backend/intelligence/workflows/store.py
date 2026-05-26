"""
backend/workflows/store.py
--------------------------
Async repository store for tracking supervised workflows in PostgreSQL.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.workflows.models import Workflow
from backend.intelligence.workflows.schema import WorkflowCreate, WorkflowUpdate

logger = logging.getLogger(__name__)


class WorkflowStore:
    """Async CRUD operations on Workflow objects with state transition logging."""

    async def get_by_id(
        self,
        session: AsyncSession,
        workflow_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Workflow]:
        """Fetch a single workflow by ID, isolated by workspace."""
        try:
            stmt = select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error("WorkflowStore.get_by_id failed: %s", exc, exc_info=True)
            raise

    async def list_workflows(
        self,
        session: AsyncSession,
        workspace_id: str = "default_workspace",
        states: Optional[List[str]] = None,
        priorities: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Workflow]:
        """List workflows matching status and priority filters."""
        try:
            stmt = select(Workflow).where(Workflow.workspace_id == workspace_id)

            if states:
                stmt = stmt.where(Workflow.state.in_(states))

            if priorities:
                stmt = stmt.where(Workflow.priority.in_(priorities))

            stmt = stmt.order_by(Workflow.updated_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.error("WorkflowStore.list_workflows failed: %s", exc, exc_info=True)
            raise

    async def create_workflow(
        self,
        session: AsyncSession,
        payload: WorkflowCreate,
    ) -> Workflow:
        """Create and persist a new supervised workflow."""
        metadata = dict(payload.metadata)
        metadata.setdefault("state_transitions", [])
        # Record initial creation state transition
        metadata["state_transitions"].append({
            "from_state": None,
            "to_state": payload.state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notes": "Workflow created.",
        })

        workflow = Workflow(
            id=uuid.uuid4(),
            title=payload.title.strip(),
            workflow_type=payload.workflow_type,
            state=payload.state,
            assigned_entities=[dict(e) for e in payload.assigned_entities],
            related_events=[str(ev_id) for ev_id in payload.related_events],
            related_insights=[str(i_id) for i_id in payload.related_insights],
            priority=payload.priority,
            workspace_id=payload.workspace_id or "default_workspace",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata_=metadata,
        )
        session.add(workflow)
        try:
            await session.flush()
        except SQLAlchemyError as exc:
            logger.error("WorkflowStore.create_workflow failed: %s", exc, exc_info=True)
            raise
        logger.debug(
            "Created workflow id=%s type=%r state=%r ws=%r",
            workflow.id,
            workflow.workflow_type,
            workflow.state,
            workflow.workspace_id,
        )
        return workflow

    async def update_workflow(
        self,
        session: AsyncSession,
        workflow_id: uuid.UUID,
        payload: WorkflowUpdate,
        workspace_id: str = "default_workspace",
    ) -> Optional[Workflow]:
        """Update an existing workflow's properties and state with transition logging."""
        try:
            workflow = await self.get_by_id(session, workflow_id, workspace_id)
            if not workflow:
                return None

            transitioned = False
            old_state = workflow.state

            if payload.title is not None:
                workflow.title = payload.title
            if payload.priority is not None:
                workflow.priority = payload.priority
            if payload.assigned_entities is not None:
                workflow.assigned_entities = [dict(e) for e in payload.assigned_entities]
            if payload.related_events is not None:
                workflow.related_events = [str(ev_id) for ev_id in payload.related_events]
            if payload.related_insights is not None:
                workflow.related_insights = [str(i_id) for i_id in payload.related_insights]

            if payload.state is not None and payload.state != workflow.state:
                old_state = workflow.state
                workflow.state = payload.state
                transitioned = True

            # Merge metadata
            if payload.metadata is not None:
                merged = dict(workflow.metadata_)
                # Preserve state transitions list
                transitions = merged.get("state_transitions", [])
                merged.update(payload.metadata)
                merged["state_transitions"] = transitions
                workflow.metadata_ = merged

            # If state transitioned, log it in metadata audit log
            if transitioned:
                # Need to update metadata JSONB directly
                metadata_copy = dict(workflow.metadata_)
                transitions = list(metadata_copy.get("state_transitions", []))
                transitions.append({
                    "from_state": old_state,
                    "to_state": workflow.state,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "notes": "State updated via patch update.",
                })
                metadata_copy["state_transitions"] = transitions
                workflow.metadata_ = metadata_copy

            workflow.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return workflow
        except SQLAlchemyError as exc:
            logger.error("WorkflowStore.update_workflow failed: %s", exc, exc_info=True)
            raise

    async def update_workflow_state(
        self,
        session: AsyncSession,
        workflow_id: uuid.UUID,
        state: str,
        user_notes: Optional[str] = None,
        workspace_id: str = "default_workspace",
    ) -> Optional[Workflow]:
        """Helper to quickly transition the workflow status with user approval notes."""
        try:
            workflow = await self.get_by_id(session, workflow_id, workspace_id)
            if not workflow:
                return None

            if workflow.state != state:
                old_state = workflow.state
                workflow.state = state

                # Update state transitions log
                metadata_copy = dict(workflow.metadata_)
                transitions = list(metadata_copy.get("state_transitions", []))
                transitions.append({
                    "from_state": old_state,
                    "to_state": state,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "notes": user_notes or "State transitioned.",
                })
                metadata_copy["state_transitions"] = transitions
                workflow.metadata_ = metadata_copy

                workflow.updated_at = datetime.now(timezone.utc)
                await session.flush()

            return workflow
        except SQLAlchemyError as exc:
            logger.error("WorkflowStore.update_workflow_state failed: %s", exc, exc_info=True)
            raise


# Module singleton
workflow_store = WorkflowStore()
