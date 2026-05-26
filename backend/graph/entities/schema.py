"""
backend/entities/schema.py
--------------------------
Pydantic v2 schemas for the Cord entity API layer.

Covers entity CRUD, semantic search requests/responses, and the
neighbourhood (ego-graph) response structure used by graph traversal APIs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Controlled-vocabulary type aliases
# ---------------------------------------------------------------------------

EntityType = Literal[
    "person",
    "team",
    "project",
    "product",
    "system",
    "workflow",
    "incident",
    "deployment",
    "customer",
    "department",
    "document",
    "decision",
    "metric",
    "tool",
]

RelationshipType = Literal[
    "owns",
    "depends_on",
    "caused",
    "related_to",
    "assigned_to",
    "part_of",
    "blocked_by",
    "affects",
    "manages",
    "deployed_to",
    "escalated_to",
    "discussed_in",
]

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------


class EntityCreate(BaseModel):
    """Payload for creating a new entity.

    Attributes:
        name:            Canonical display name (required).
        type:            Semantic category from the controlled vocabulary.
        aliases:         Zero or more alternate surface forms.
        description:     Optional free-text summary of the entity.
        source_chunk_id: Qdrant point ID of the originating chunk.
        workspace_id:    Tenant scoping key; defaults to ``"default_workspace"``.
        metadata:        Arbitrary connector-specific key-value pairs.
    """

    name: str = Field(..., min_length=1, max_length=500, description="Canonical entity name")
    type: EntityType = Field(..., description="Entity semantic category")
    aliases: List[str] = Field(default_factory=list, description="Alternate names / surface forms")
    description: Optional[str] = Field(default=None, description="Free-text description")
    source_chunk_id: Optional[str] = Field(default=None, description="Originating Qdrant chunk ID")
    workspace_id: Optional[str] = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary connector-specific metadata",
    )


class EntityRead(BaseModel):
    """Full entity representation returned from API endpoints.

    Attributes mirror the :class:`~backend.graph.entities.models.Entity` ORM model.
    ``from_attributes=True`` allows construction directly from ORM instances.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    source_chunk_id: Optional[str] = None
    workspace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ---------------------------------------------------------------------------
# Entity search schemas
# ---------------------------------------------------------------------------


class EntitySearchRequest(BaseModel):
    """Request body for semantic entity search.

    Attributes:
        query:       Natural-language search string (embedded at query time).
        entity_type: Optional filter to restrict results to a single type.
        workspace_id: Tenant scoping key.
        limit:       Maximum number of results to return (1–100).
    """

    query: str = Field(..., min_length=1, description="Search query string")
    entity_type: Optional[EntityType] = Field(
        default=None,
        description="Restrict results to this entity type",
    )
    workspace_id: str = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results")


class EntitySearchResult(BaseModel):
    """Single item in the entity search result list.

    Attributes:
        entity:              The matched entity.
        score:               Semantic similarity score (0.0–1.0).
        chunk_refs:          Qdrant chunk IDs that mention this entity.
        relationships_count: Total number of edges incident on this entity.
    """

    entity: EntityRead
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    chunk_refs: List[str] = Field(
        default_factory=list,
        description="Qdrant chunk IDs referencing this entity",
    )
    relationships_count: int = Field(
        default=0,
        ge=0,
        description="Number of graph edges incident on this entity",
    )


# ---------------------------------------------------------------------------
# Graph neighbourhood schema
# ---------------------------------------------------------------------------


class EntityNeighborhood(BaseModel):
    """Ego-graph response: a focal entity plus its immediate neighbours.

    Attributes:
        entity:   The focal entity whose neighbourhood was requested.
        outgoing: Edges where this entity is the source (list of serialised
                  relationship dicts).
        incoming: Edges where this entity is the target.
        depth:    Traversal depth used to build this neighbourhood (default 1).
    """

    entity: EntityRead
    outgoing: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Relationships originating from this entity",
    )
    incoming: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Relationships pointing to this entity",
    )
    depth: int = Field(default=1, ge=1, description="Graph traversal depth")
