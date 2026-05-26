"""
backend/events/schema.py
------------------------
Pydantic v2 schemas for the Cord event and temporal API layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Controlled Vocabulary for Events
# ---------------------------------------------------------------------------

EventType = Literal[
    "deployment",
    "incident",
    "outage",
    "escalation",
    "release",
    "onboarding_issue",
    "support_spike",
    "customer_complaint",
    "infrastructure_failure",
    "workflow_change",
    "security_event",
    "decision",
    "migration",
    "rollback",
    "performance_issue",
]

EventRelationshipType = Literal[
    "caused_by",
    "triggered_by",
    "affects",
    "escalated_to",
    "resolved_by",
    "related_to",
    "occurred_after",
    "occurred_before",
]

# ---------------------------------------------------------------------------
# Event Schemas
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """Payload for creating a new operational event."""

    event_type: EventType = Field(..., description="The category/type of the event")
    title: str = Field(..., min_length=1, max_length=500, description="Short title describing the event")
    description: Optional[str] = Field(default=None, description="Detailed description of the event")
    timestamp: Optional[datetime] = Field(default=None, description="When the event occurred")
    source_chunk_id: str = Field(..., max_length=500, description="Originating Qdrant chunk ID")
    workspace_id: Optional[str] = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )
    severity: Optional[Literal["low", "medium", "high", "critical"]] = Field(
        default=None,
        description="Severity of the event if applicable",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence of event extraction",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom event metadata",
    )


class EventRead(BaseModel):
    """Full operational event representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_chunk_id: str
    workspace_id: Optional[str] = None
    severity: Optional[str] = None
    confidence: float
    metadata_: Dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime


# ---------------------------------------------------------------------------
# Event Relationship Schemas
# ---------------------------------------------------------------------------


class EventRelationshipCreate(BaseModel):
    """Payload for creating a relationship/link between two events."""

    source_event_id: uuid.UUID = Field(..., description="UUID of the source event")
    target_event_id: uuid.UUID = Field(..., description="UUID of the target event")
    relationship_type: EventRelationshipType = Field(
        ...,
        description="Type of directed connection (e.g. caused_by, occurred_after)",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level of relationship inference",
    )
    workspace_id: Optional[str] = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )


class EventRelationshipRead(BaseModel):
    """Full representation of a relationship between two events."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_event_id: uuid.UUID
    target_event_id: uuid.UUID
    relationship_type: str
    confidence: float
    workspace_id: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Event Query / Search Schemas
# ---------------------------------------------------------------------------


class EventSearchRequest(BaseModel):
    """Request query options for events."""

    workspace_id: str = Field(default="default_workspace", description="Tenant workspace identifier")
    event_types: Optional[List[EventType]] = Field(default=None, description="Filter by event types")
    severities: Optional[List[Literal["low", "medium", "high", "critical"]]] = Field(
        default=None,
        description="Filter by severity levels",
    )
    start_time: Optional[datetime] = Field(default=None, description="Start range for event timestamp")
    end_time: Optional[datetime] = Field(default=None, description="End range for event timestamp")
    limit: int = Field(default=50, ge=1, le=500, description="Max number of results to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
