"""
backend/relationships/schema.py
--------------------------------
Pydantic v2 schemas for the Cord relationship API layer.

Covers relationship creation, structured read responses, and search/filter
requests.  ``RelationshipType`` is imported from the entities schema to keep
the controlled vocabulary in a single authoritative location.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.graph.entities.schema import RelationshipType

# ---------------------------------------------------------------------------
# Relationship schemas
# ---------------------------------------------------------------------------


class RelationshipCreate(BaseModel):
    """Payload for creating a new directed relationship between two entities.

    Attributes:
        source_entity_id:  UUID of the originating (subject) entity.
        target_entity_id:  UUID of the destination (object) entity.
        relationship_type: Typed label from the controlled vocabulary
                           (e.g. ``"owns"``, ``"depends_on"``).
        confidence:        Extraction confidence in [0.0, 1.0].
        evidence:          Supporting text snippet used to infer this edge.
        source_chunk_id:   Qdrant point ID of the originating chunk.
        workspace_id:      Tenant scoping key; defaults to
                           ``"default_workspace"``.
    """

    source_entity_id: uuid.UUID = Field(
        ...,
        description="UUID of the source / subject entity",
    )
    target_entity_id: uuid.UUID = Field(
        ...,
        description="UUID of the target / object entity",
    )
    relationship_type: RelationshipType = Field(
        ...,
        description="Typed relationship label from the controlled vocabulary",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Source text snippet that supports this relationship",
    )
    source_chunk_id: Optional[str] = Field(
        default=None,
        description="Qdrant point ID of the chunk this relationship was extracted from",
    )
    workspace_id: Optional[str] = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )


class RelationshipRead(BaseModel):
    """Full relationship representation returned from API endpoints.

    ``from_attributes=True`` enables direct construction from
    :class:`~backend.graph.entities.models.Relationship` ORM instances.

    Attributes:
        id:                Primary key of the relationship record.
        source_entity_id:  UUID of the source entity.
        target_entity_id:  UUID of the target entity.
        relationship_type: String label (may be any stored value, not
                           constrained to the Literal here so that
                           reads remain forward-compatible).
        confidence:        Stored confidence score.
        evidence:          Supporting text, if captured.
        source_chunk_id:   Originating Qdrant chunk ID, if captured.
        workspace_id:      Tenant scoping key.
        timestamp:         Optional event timestamp carried from source data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship_type: str
    confidence: float
    evidence: Optional[str] = None
    source_chunk_id: Optional[str] = None
    workspace_id: Optional[str] = None
    timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Relationship search / filter schema
# ---------------------------------------------------------------------------


class RelationshipSearchRequest(BaseModel):
    """Query parameters for filtering relationships.

    At least one of ``relationship_type`` or ``entity_id`` should be
    provided; omitting both returns unfiltered (paginated) results up to
    ``limit``.

    Attributes:
        relationship_type: Optional type label to filter by.
        entity_id:         Optional entity UUID; returns all edges where
                           this entity appears as source **or** target.
        workspace_id:      Tenant scoping key.
        limit:             Maximum number of results (1–200).
    """

    relationship_type: Optional[str] = Field(
        default=None,
        description="Filter by relationship type label",
    )
    entity_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Return edges incident on this entity (source or target)",
    )
    workspace_id: str = Field(
        default="default_workspace",
        description="Tenant workspace identifier",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum number of results to return",
    )
