"""
backend/insights/router.py
--------------------------
FastAPI router containing all endpoints for events, timelines, pattern detection,
and multi-hop reasoning.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from backend.intelligence.analytics.patterns import pattern_detector
from backend.graph.events.pipeline import event_extraction_pipeline
from backend.graph.events.schema import EventRead, EventSearchRequest
from backend.graph.events.store import event_store
from backend.graph.db import get_db_session
from backend.intelligence.reasoning.pipeline import multi_hop_reasoning_pipeline
from backend.intelligence.timelines.builder import timeline_builder, TimelineResponse

from backend.intelligence.insights.schema import InsightRead
from backend.intelligence.workflows.schema import WorkflowCreate, WorkflowUpdate, WorkflowRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Insights"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class ReasoningQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The query to analyze")
    workspace_id: str = Field(default="default_workspace", description="Tenant workspace identifier")
    limit: int = Field(default=5, ge=1, le=20, description="Max search results to retrieve")


class ExtractEventsRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text chunk to analyze")
    chunk_id: str = Field(..., description="The ID of the originating chunk")
    workspace_id: str = Field(default="default_workspace", description="Tenant workspace identifier")


# ---------------------------------------------------------------------------
# Events search Route
# ---------------------------------------------------------------------------


@router.post("/events/search", response_model=List[EventRead])
async def search_events(req: EventSearchRequest):
    """Query and search for operational events with filters."""
    try:
        async with get_db_session() as session:
            # Map EventSearchRequest fields to store call
            events = await event_store.list_events(
                session=session,
                workspace_id=req.workspace_id,
                event_types=[t for t in req.event_types] if req.event_types else None,
                severities=[s for s in req.severities] if req.severities else None,
                start_time=req.start_time,
                end_time=req.end_time,
                limit=req.limit,
                offset=req.offset,
            )
            return [EventRead.model_validate(e) for e in events]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in search_events: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to search events: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Timeline Route
# ---------------------------------------------------------------------------


@router.get("/timelines", response_model=TimelineResponse)
async def get_timeline(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    severities: Optional[List[str]] = Query(None, description="Filter by severity levels"),
    start_time: Optional[str] = Query(None, description="Start date/time ISO format"),
    end_time: Optional[str] = Query(None, description="End date/time ISO format"),
    limit: int = Query(50, ge=1, le=200, description="Max timeline events"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List chronological sequence of events with intervals."""
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")) if start_time else None
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00")) if end_time else None

        async with get_db_session() as session:
            timeline = await timeline_builder.build_timeline(
                session=session,
                workspace_id=workspace_id,
                event_types=event_types,
                severities=severities,
                start_time=start_dt,
                end_time=end_dt,
                limit=limit,
                offset=offset,
            )
            return timeline
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_timeline: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to build timeline: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Analytics / Patterns Route
# ---------------------------------------------------------------------------


@router.get("/analytics/patterns")
async def get_patterns(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier")
):
    """Analyze timeline and retrieve recurring patterns and correlation anomalies."""
    try:
        async with get_db_session() as session:
            analysis = await pattern_detector.analyze_patterns(
                session=session,
                workspace_id=workspace_id,
            )
            # Serialize datetimes to string
            return {
                "workspace_id": analysis["workspace_id"],
                "temporal_clusters": [
                    {
                        **cluster,
                        "start_time": cluster["start_time"].isoformat() if cluster["start_time"] else None,
                        "end_time": cluster["end_time"].isoformat() if cluster["end_time"] else None,
                        "events": [
                            {
                                **ev,
                                "timestamp": ev["timestamp"].isoformat() if ev["timestamp"] else None,
                            }
                            for ev in cluster["events"]
                        ],
                    }
                    for cluster in analysis["temporal_clusters"]
                ],
                "incident_frequencies": analysis["incident_frequencies"],
                "deployment_incidents": [
                    {
                        **dep_inc,
                        "deployment": {
                            **dep_inc["deployment"],
                            "timestamp": dep_inc["deployment"]["timestamp"].isoformat(),
                        },
                        "incident": {
                            **dep_inc["incident"],
                            "timestamp": dep_inc["incident"]["timestamp"].isoformat(),
                        },
                    }
                    for dep_inc in analysis["deployment_incidents"]
                ],
                "generated_at": analysis["generated_at"].isoformat(),
            }
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_patterns: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to detect patterns: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Multi-Hop Reasoning Route
# ---------------------------------------------------------------------------


@router.post("/reasoning/query")
async def execute_reasoning(req: ReasoningQueryRequest):
    """Execute multi-hop search, timeline synthesis, pattern detection, and LLM reasoning."""
    try:
        result = await multi_hop_reasoning_pipeline.execute_reasoning(
            query=req.query,
            workspace_id=req.workspace_id,
            limit=req.limit,
        )
        return result
    except Exception as exc:
        logger.error("Failed executing reasoning pipeline: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Extraction Route
# ---------------------------------------------------------------------------


@router.post("/extract/events")
async def extract_events(req: ExtractEventsRequest):
    """Trigger event extraction on a text chunk, saving events/relationships to PostgreSQL."""
    try:
        summary = await event_extraction_pipeline.process_chunk(
            chunk_text=req.text,
            chunk_id=req.chunk_id,
            workspace_id=req.workspace_id,
        )
        if summary.get("error"):
            raise HTTPException(status_code=500, detail=summary["error"])
        return summary
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to extract events: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Supervised Operational Insights & Anomaly Detection Routes
# ---------------------------------------------------------------------------


@router.post("/run-detector", response_model=List[InsightRead])
async def run_detector(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier")
):
    """Manual trigger to run proactive anomaly detection."""
    from backend.intelligence.anomalies.detector import anomaly_detector
    try:
        async with get_db_session() as session:
            insights = await anomaly_detector.run_detection(session, workspace_id)
            return [InsightRead.model_validate(i) for i in insights]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in run_detector: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to run detector: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/active", response_model=List[InsightRead])
async def get_active_insights(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
    insight_type: Optional[List[str]] = Query(None, description="Filter by insight types"),
    severity: Optional[List[str]] = Query(None, description="Filter by severities"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List active insights by severity and type."""
    from backend.intelligence.insights.store import insight_store
    try:
        async with get_db_session() as session:
            insights = await insight_store.list_insights(
                session=session,
                workspace_id=workspace_id,
                insight_types=insight_type,
                severities=severity,
                limit=limit,
                offset=offset,
            )
            return [InsightRead.model_validate(i) for i in insights]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_active_insights: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to list active insights: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Supervised Workflow Coordination Routes
# ---------------------------------------------------------------------------


@router.post("/workflows", response_model=WorkflowRead)
async def create_workflow(
    payload: WorkflowCreate,
):
    """Create a new supervised workflow."""
    from backend.intelligence.workflows.store import workflow_store
    try:
        async with get_db_session() as session:
            workflow = await workflow_store.create_workflow(session, payload)
            return WorkflowRead.model_validate(workflow)
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in create_workflow: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to create workflow: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(
    workflow_id: uuid.UUID,
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Retrieve a single workflow by ID."""
    from backend.intelligence.workflows.store import workflow_store
    try:
        async with get_db_session() as session:
            workflow = await workflow_store.get_by_id(session, workflow_id, workspace_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return WorkflowRead.model_validate(workflow)
    except HTTPException:
        raise
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_workflow: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to get workflow: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/workflows/{workflow_id}", response_model=WorkflowRead)
async def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Update state, assignee, or priority on an existing workflow."""
    from backend.intelligence.workflows.store import workflow_store
    try:
        async with get_db_session() as session:
            workflow = await workflow_store.update_workflow(session, workflow_id, payload, workspace_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return WorkflowRead.model_validate(workflow)
    except HTTPException:
        raise
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in update_workflow: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to update workflow: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class ApproveRequest(BaseModel):
    notes: str = Field(..., description="Approval justification notes")


@router.post("/workflows/{workflow_id}/approve", response_model=WorkflowRead)
async def approve_workflow_endpoint(
    workflow_id: uuid.UUID,
    req: ApproveRequest,
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Transition state to approved with notes."""
    from backend.intelligence.coordination.engine import workflow_coordinator
    try:
        async with get_db_session() as session:
            workflow = await workflow_coordinator.approve_workflow(session, workflow_id, req.notes, workspace_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return WorkflowRead.model_validate(workflow)
    except HTTPException:
        raise
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in approve_workflow_endpoint: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to approve workflow: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class EscalateRequest(BaseModel):
    notes: str = Field(..., description="Escalation reasoning")


@router.post("/workflows/{workflow_id}/escalate", response_model=WorkflowRead)
async def escalate_workflow_endpoint(
    workflow_id: uuid.UUID,
    req: EscalateRequest,
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Escalation routing to higher-tier roles."""
    from backend.intelligence.coordination.engine import workflow_coordinator
    try:
        async with get_db_session() as session:
            workflow = await workflow_coordinator.escalate_workflow(session, workflow_id, req.notes, workspace_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return WorkflowRead.model_validate(workflow)
    except HTTPException:
        raise
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in escalate_workflow_endpoint: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to escalate workflow: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows", response_model=List[WorkflowRead])
async def get_workflows(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
    state: Optional[List[str]] = Query(None, description="Filter by states"),
    priority: Optional[List[str]] = Query(None, description="Filter by priorities"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List workflows with filtering support."""
    from backend.intelligence.workflows.store import workflow_store
    try:
        async with get_db_session() as session:
            workflows = await workflow_store.list_workflows(
                session=session,
                workspace_id=workspace_id,
                states=state,
                priorities=priority,
                limit=limit,
                offset=offset,
            )
            return [WorkflowRead.model_validate(w) for w in workflows]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_workflows: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to list workflows: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Digests & Notifications Routes
# ---------------------------------------------------------------------------


@router.get("/digests")
async def get_digests(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
    digest_type: str = Query("daily", description="daily or weekly engineering/incidents digest"),
    hours_lookback: int = Query(24, description="Lookback window in hours"),
):
    """Query formatted daily/weekly HTML and Slack digests."""
    from backend.intelligence.digests.generator import digest_generator
    try:
        async with get_db_session() as session:
            slack_payload = await digest_generator.generate_slack_digest(
                session=session,
                workspace_id=workspace_id,
                digest_type=digest_type,
                hours_lookback=hours_lookback,
            )
            email_payload = await digest_generator.generate_email_digest(
                session=session,
                workspace_id=workspace_id,
                digest_type=digest_type,
                hours_lookback=hours_lookback,
            )
            return {
                "workspace_id": workspace_id,
                "digest_type": digest_type,
                "slack": slack_payload,
                "email": email_payload,
            }
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database connection error in get_digests: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error")
