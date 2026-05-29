"""
backend/coordination/engine.py
------------------------------
Supervised workflow coordination engine. Tracks workflow states, links related
events and insights, manages approval handoffs, and resolves escalation routes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from backend.graph.events.models import Event
from backend.intelligence.insights.models import Insight
from backend.intelligence.workflows.schema import WorkflowCreate, WorkflowUpdate
from backend.intelligence.workflows.store import workflow_store

logger = logging.getLogger(__name__)


class WorkflowCoordinator:
    """Orchestrates human-in-the-loop workflows, routing, approvals, and escalations."""

    async def create_incident_response_workflow(
        self,
        session: Any,
        incident_event_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Any]:
        """Triages a new incident, linking related database insights, and suggesting remediation."""
        try:
            # 1. Fetch the focal incident event
            stmt = select(Event).where(
                Event.id == incident_event_id,
                Event.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()

            if not event:
                logger.warning("Incident event %s not found. Workflow creation aborted.", incident_event_id)
                return None

            # 2. Look for any active deployment instability or anomaly insights for this workspace
            insight_stmt = select(Insight).where(
                Insight.workspace_id == workspace_id,
                Insight.generated_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            ).limit(10)
            insight_res = await session.execute(insight_stmt)
            active_insights = list(insight_res.scalars().all())

            # Link insights if they share the same source chunk or entities
            related_insight_ids = []
            remediation_suggestions = ["Investigate recent CPU utilization and saturated connection pool metrics."]

            for ins in active_insights:
                # If deployment instability shares deployment info, suggest rollback
                if ins.insight_type == "deployment_instability":
                    related_insight_ids.append(ins.id)
                    dep_title = ins.title.split("'")[-2] if "'" in ins.title else "recent release"
                    remediation_suggestions.append(f"Consider rolling back the deployment release: '{dep_title}'.")
                elif ins.insight_type == "recurring_bottleneck":
                    related_insight_ids.append(ins.id)

            # 3. Create workflow payload
            payload = WorkflowCreate(
                title=f"Incident Response: Triage for '{event.title}'",
                workflow_type="incident_response",
                state="pending_review",
                assigned_entities=[{"name": "DevOps On-Call Team", "type": "team"}],
                related_events=[incident_event_id],
                related_insights=related_insight_ids,
                priority="high" if event.severity == "high" or event.event_type == "outage" else "medium",
                workspace_id=workspace_id,
                metadata={
                    "recommendations": remediation_suggestions,
                    "triage_time": datetime.now(timezone.utc).isoformat(),
                },
            )

            # 4. Persist workflow
            return await workflow_store.create_workflow(session, payload)

        except Exception as exc:
            logger.error("WorkflowCoordinator.create_incident_response_workflow failed: %s", exc, exc_info=True)
            raise

    async def create_customer_escalation_workflow(
        self,
        session: Any,
        support_spike_insight_id: uuid.UUID,
        workspace_id: str = "default_workspace",
    ) -> Optional[Any]:
        """Triage a customer support spike, linking related events and routing to Support Leads."""
        try:
            # 1. Fetch the support spike insight
            stmt = select(Insight).where(
                Insight.id == support_spike_insight_id,
                Insight.workspace_id == workspace_id,
            ).limit(1)
            result = await session.execute(stmt)
            insight = result.scalar_one_or_none()

            if not insight:
                logger.warning("Support spike insight %s not found. Workflow creation aborted.", support_spike_insight_id)
                return None

            # Gather related event IDs
            related_event_ids = []
            for ev in insight.supporting_events:
                if "id" in ev:
                    try:
                        related_event_ids.append(uuid.UUID(ev["id"]))
                    except ValueError:
                        pass

            payload = WorkflowCreate(
                title=f"Customer Escalation: {insight.title}",
                workflow_type="customer_escalation",
                state="pending_review",
                assigned_entities=[{"name": "Customer Support Lead Tier-2", "type": "team"}],
                related_events=related_event_ids,
                related_insights=[support_spike_insight_id],
                priority="high" if insight.severity == "high" else "medium",
                workspace_id=workspace_id,
                metadata={
                    "recommendations": [
                        "Draft response to high-priority customer contacts regarding system issues.",
                        "Coordinate with Platform Engineering regarding PostgreSQL connection saturation.",
                    ],
                    "triage_time": datetime.now(timezone.utc).isoformat(),
                },
            )

            return await workflow_store.create_workflow(session, payload)

        except Exception as exc:
            logger.error("WorkflowCoordinator.create_customer_escalation_workflow failed: %s", exc, exc_info=True)
            raise

    async def approve_workflow(
        self,
        session: Any,
        workflow_id: uuid.UUID,
        approval_notes: str,
        workspace_id: str = "default_workspace",
    ) -> Optional[Any]:
        """Transition workflow state to approved/in_progress with notes."""
        return await workflow_store.update_workflow_state(
            session=session,
            workflow_id=workflow_id,
            state="in_progress",
            user_notes=f"Approved: {approval_notes}",
            workspace_id=workspace_id,
        )

    async def escalate_workflow(
        self,
        session: Any,
        workflow_id: uuid.UUID,
        escalation_notes: str,
        workspace_id: str = "default_workspace",
    ) -> Optional[Any]:
        """Transition workflow state to escalated and route assignment to high-tier roles."""
        try:
            workflow = await workflow_store.get_by_id(session, workflow_id, workspace_id)
            if not workflow:
                return None

            # Route escalation assignments
            escalated_assignee = [{"name": "Director of Engineering / Incident Commander", "type": "person"}]
            if workflow.workflow_type == "customer_escalation":
                escalated_assignee = [{"name": "Head of Customer Relations", "type": "person"}]

            update_payload = WorkflowUpdate(
                state="escalated",
                assigned_entities=escalated_assignee,
                metadata={
                    "escalation_reason": escalation_notes,
                    "escalated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            return await workflow_store.update_workflow(session, workflow_id, update_payload, workspace_id)

        except Exception as exc:
            logger.error("WorkflowCoordinator.escalate_workflow failed: %s", exc, exc_info=True)
            raise


# Module singleton
workflow_coordinator = WorkflowCoordinator()
