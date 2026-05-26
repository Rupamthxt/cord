"""
backend/workflows/schema.py
---------------------------
Pydantic v2 schemas for the supervised workflow coordination engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

WorkflowState = Literal[
    "draft",
    "pending_review",
    "approved",
    "in_progress",
    "blocked",
    "completed",
    "escalated",
    "archived",
]

WorkflowPriority = Literal["low", "medium", "high", "critical"]

WorkflowType = Literal[
    "incident_response",
    "customer_escalation",
    "deployment_verification",
    "workflow_coordination",
]


class WorkflowCreate(BaseModel):
    """Payload for creating a new supervised workflow."""

    title: str = Field(..., min_length=1, max_length=500, description="Short descriptive title of the workflow")
    workflow_type: WorkflowType = Field(..., description="The category/type of the workflow")
    state: WorkflowState = Field(default="draft", description="The initial state of the workflow")
    assigned_entities: List[Dict[str, Any]] = Field(default_factory=list, description="List of entity assignees")
    related_events: List[uuid.UUID] = Field(default_factory=list, description="List of linked operational event IDs")
    related_insights: List[uuid.UUID] = Field(default_factory=list, description="List of linked insight IDs")
    priority: WorkflowPriority = Field(default="medium", description="Priority level of the workflow")
    workspace_id: Optional[str] = Field(default="default_workspace", description="Tenant workspace isolation key")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata and state log transitions")


class WorkflowUpdate(BaseModel):
    """Payload for modifying an existing supervised workflow state or details."""

    title: Optional[str] = Field(default=None, max_length=500)
    state: Optional[WorkflowState] = Field(default=None)
    assigned_entities: Optional[List[Dict[str, Any]]] = Field(default=None)
    related_events: Optional[List[uuid.UUID]] = Field(default=None)
    related_insights: Optional[List[uuid.UUID]] = Field(default=None)
    priority: Optional[WorkflowPriority] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)


class WorkflowRead(BaseModel):
    """Supervised workflow representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    title: str
    workflow_type: str
    state: str
    assigned_entities: List[Dict[str, Any]]
    # Store list of UUID strings/objects for DB retrieval
    related_events: List[uuid.UUID]
    related_insights: List[uuid.UUID]
    priority: str
    workspace_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    metadata_: Dict[str, Any] = Field(default_factory=dict, alias="metadata")
