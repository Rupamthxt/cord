"""
backend/entities/models.py
--------------------------
SQLAlchemy 2.0 ORM models for the Cord entity graph.

Tables:
    cord_entities          – canonical named entities extracted from org data
    cord_entity_aliases    – alternate names / surface forms for an entity
    cord_relationships     – directed typed edges between entities
    cord_chunk_entity_refs – Qdrant chunk ↔ entity mention cross-reference
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.graph.db import Base


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class Entity(Base):
    """Canonical entity node in the organisational knowledge graph.

    Represents a named thing that has been extracted from one or more source
    chunks (Slack messages, Notion pages, Jira tickets, …).

    Attributes:
        id:               Primary key (UUIDv4).
        name:             Canonical display name of the entity.
        type:             Semantic category (person | team | project | …).
        aliases_str:      Comma-separated alternate surface forms used as a
                          lightweight backup; prefer the ``cord_entity_aliases``
                          table for structured querying.
        description:      Free-text description synthesised or extracted from
                          source content.
        source_chunk_id:  Qdrant point ID of the chunk where the entity was
                          *first* detected.
        workspace_id:     Tenant / workspace scoping key.
        metadata_:        Arbitrary JSON bag for connector-specific attributes
                          (JIRA issue key, Slack user ID, …).
        created_at:       Record creation timestamp (UTC).
        updated_at:       Record last-update timestamp (UTC), auto-refreshed.
        embedding_id:     Qdrant point ID storing the entity's name embedding
                          used for semantic deduplication lookups.
    """

    __tablename__ = "cord_entities"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: str = Column(String(500), nullable=False)
    type: str = Column(String(100), nullable=False)
    aliases_str: str | None = Column(Text, nullable=True)
    description: str | None = Column(Text, nullable=True)
    source_chunk_id: str | None = Column(String(500), nullable=True)
    workspace_id: str | None = Column(String(500), nullable=True, index=True)
    metadata_: dict = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    embedding_id: str | None = Column(String(500), nullable=True)

    @property
    def aliases(self) -> list[str]:
        """Convert aliases_str into a list of strings for Pydantic schema validation."""
        if not self.aliases_str:
            return []
        return [a.strip() for a in self.aliases_str.split(",") if a.strip()]

    # Composite indexes
    __table_args__ = (
        Index("ix_cord_entities_workspace_type", "workspace_id", "type"),
        Index("ix_cord_entities_name_workspace", "name", "workspace_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Entity id={self.id!s} name={self.name!r} type={self.type!r} "
            f"workspace={self.workspace_id!r}>"
        )



# ---------------------------------------------------------------------------
# EntityAlias
# ---------------------------------------------------------------------------


class EntityAlias(Base):
    """Alternate surface form / alias for an :class:`Entity`.

    Storing aliases in a separate table allows efficient normalised-alias
    lookups (``ix_cord_entity_aliases_normalized``) during entity resolution.

    Attributes:
        id:         Primary key (UUIDv4).
        entity_id:  FK → :attr:`Entity.id`, cascade deletes.
        alias:      Raw alias string as it appears in source text.
        normalized: Lowercased, whitespace-stripped form used for dedup
                    and matching.
    """

    __tablename__ = "cord_entity_aliases"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    entity_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: str = Column(String(500), nullable=False)
    normalized: str = Column(String(500), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("entity_id", "normalized", name="uq_entity_alias_normalized"),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityAlias entity_id={self.entity_id!s} alias={self.alias!r}>"
        )


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


class Relationship(Base):
    """Directed typed edge between two :class:`Entity` nodes.

    Represents a semantically meaningful connection extracted from source
    text, e.g. *"Service A depends_on Service B"* or
    *"Alice manages Team X"*.

    Attributes:
        id:                  Primary key (UUIDv4).
        source_entity_id:    FK → originating entity (cascade deletes).
        target_entity_id:    FK → destination entity (cascade deletes).
        relationship_type:   Typed label from a controlled vocabulary
                             (owns | depends_on | caused | …).
        confidence:          Extraction confidence score in [0.0, 1.0].
        evidence:            Supporting text snippet used to infer this edge.
        source_chunk_id:     Qdrant point ID of the originating chunk.
        timestamp:           Optional event time carried from source data.
        workspace_id:        Tenant scoping key.
    """

    __tablename__ = "cord_relationships"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    source_entity_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: str = Column(String(100), nullable=False)
    confidence: float = Column(Float, nullable=False, default=0.8)
    evidence: str | None = Column(Text, nullable=True)
    source_chunk_id: str | None = Column(String(500), nullable=True)
    timestamp: datetime | None = Column(DateTime(timezone=True), nullable=True)
    workspace_id: str | None = Column(String(500), nullable=True, index=True)

    __table_args__ = (
        Index(
            "ix_cord_relationships_source_type",
            "source_entity_id",
            "relationship_type",
        ),
        Index(
            "ix_cord_relationships_target_type",
            "target_entity_id",
            "relationship_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Relationship {self.source_entity_id!s} "
            f"--[{self.relationship_type}]--> {self.target_entity_id!s}>"
        )


# ---------------------------------------------------------------------------
# ChunkEntityRef
# ---------------------------------------------------------------------------


class ChunkEntityRef(Base):
    """Cross-reference table linking Qdrant chunk IDs to entity IDs.

    Enables bi-directional lookup: given a chunk, find all mentioned
    entities; given an entity, find all chunks that reference it.

    Attributes:
        id:            Primary key (UUIDv4).
        chunk_id:      Qdrant point ID (string) of the source chunk.
        entity_id:     FK → :attr:`Entity.id`, cascade deletes.
        mention_text:  The exact surface form found in the chunk text.
        workspace_id:  Tenant scoping key.
    """

    __tablename__ = "cord_chunk_entity_refs"

    id: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    chunk_id: str = Column(String(500), nullable=False, index=True)
    entity_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("cord_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    mention_text: str | None = Column(String(500), nullable=True)
    workspace_id: str | None = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_cord_chunk_entity_refs_chunk_entity", "chunk_id", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChunkEntityRef chunk={self.chunk_id!r} "
            f"entity={self.entity_id!s} mention={self.mention_text!r}>"
        )
