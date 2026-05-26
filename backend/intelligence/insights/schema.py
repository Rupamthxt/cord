"""
backend/insights/schema.py
--------------------------
Pydantic v2 schemas for proactive operational insights and anomalies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

InsightType = Literal[
    "recurring_bottleneck",
    "operational_degradation",
    "support_spike",
    "deployment_instability",
    "workflow_inefficiency",
    "escalation_pattern",
    "repeated_blocker",
    "anomaly",
]

SeverityType = Literal["low", "medium", "high", "critical"]


class InsightCreate(BaseModel):
    """Payload for creating a new operational insight."""

    title: str = Field(..., min_length=1, max_length=500, description="Short descriptive title of the insight")
    summary: str = Field(..., min_length=1, description="Traceable narrative summary explaining the findings")
    insight_type: InsightType = Field(..., description="The category of insight detected")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence of the insight inference")
    severity: SeverityType = Field(default="medium", description="Severity level of the insight")
    supporting_entities: List[Dict[str, Any]] = Field(default_factory=list, description="Entities linked to this insight")
    supporting_events: List[Dict[str, Any]] = Field(default_factory=list, description="Events supporting this insight")
    evidence: List[str] = Field(default_factory=list, description="Direct text snippets or logic trace citations")
    workspace_id: Optional[str] = Field(default="default_workspace", description="Tenant workspace isolation key")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom metadata bag")


class InsightRead(BaseModel):
    """Traceable operational insight representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    title: str
    summary: str
    insight_type: str
    confidence: float
    severity: str
    supporting_entities: List[Dict[str, Any]]
    supporting_events: List[Dict[str, Any]]
    evidence: List[str]
    workspace_id: Optional[str] = None
    generated_at: datetime
    metadata_: Dict[str, Any] = Field(default_factory=dict, alias="metadata")


class InsightSearchRequest(BaseModel):
    """Request options for filtering and listing proactive insights."""

    workspace_id: str = Field(default="default_workspace", description="Tenant workspace isolation key")
    insight_types: Optional[List[InsightType]] = Field(default=None, description="Filter by specific categories")
    severities: Optional[List[SeverityType]] = Field(default=None, description="Filter by severity levels")
    limit: int = Field(default=50, ge=1, le=500, description="Max number of results to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
