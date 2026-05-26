"""
backend/graph/router.py
-----------------------
FastAPI router containing all Entity, Relationship, and Graph query/mutation endpoints.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from backend.graph.entities.schema import (
    EntityNeighborhood,
    EntityRead,
    EntitySearchRequest,
    EntitySearchResult,
    EntityType,
)
from backend.graph.entities.store import entity_store
from backend.extraction.pipeline import extraction_pipeline
from backend.graph.db import get_db_session
from backend.graph.retriever import graph_retriever
from backend.graph.relationships.schema import (
    RelationshipRead,
    RelationshipSearchRequest,
)
from backend.graph.relationships.store import relationship_store
from backend.graph.entities.models import Relationship, Entity
from backend.intelligence.retrieval.search import search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Graph"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class EntityMergeRequest(BaseModel):
    canonical_id: uuid.UUID
    duplicate_id: uuid.UUID
    workspace_id: str = "default_workspace"


class GraphSearchRequest(BaseModel):
    query: str
    limit: int = 5
    sources: Optional[List[str]] = None
    author: Optional[str] = None
    team: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    hierarchy_scope: Optional[str] = None
    entities: Optional[List[str]] = None
    workspace_id: Optional[str] = "default_workspace"


class ExtractChunkRequest(BaseModel):
    text: str
    chunk_id: str
    workspace_id: str = "default_workspace"


# ---------------------------------------------------------------------------
# Entity Routes
# ---------------------------------------------------------------------------

@router.get("/entities/{entity_id}", response_model=Dict[str, Any])
async def get_entity(
    entity_id: uuid.UUID,
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Retrieve details of a canonical entity and its total relationship count."""
    try:
        async with get_db_session() as session:
            entity = await entity_store.get_by_id(session, entity_id, workspace_id)
            if not entity:
                raise HTTPException(status_code=404, detail="Entity not found")
            
            # Count relations
            stmt_out = select(func.count(Relationship.id)).where(
                Relationship.source_entity_id == entity_id,
                Relationship.workspace_id == workspace_id,
            )
            stmt_in = select(func.count(Relationship.id)).where(
                Relationship.target_entity_id == entity_id,
                Relationship.workspace_id == workspace_id,
            )
            
            out_count = (await session.execute(stmt_out)).scalar() or 0
            in_count = (await session.execute(stmt_in)).scalar() or 0
            
            return {
                "entity": EntityRead.model_validate(entity).model_dump(),
                "relationships_count": out_count + in_count,
            }
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in get_entity: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


@router.post("/entities/search", response_model=List[EntitySearchResult])
async def search_entities(req: EntitySearchRequest):
    """Search for entities matching a case-insensitive prefix/substring query."""
    try:
        async with get_db_session() as session:
            entities = await entity_store.fuzzy_search(
                session,
                query=req.query,
                workspace_id=req.workspace_id,
                entity_type=req.entity_type,
                limit=req.limit,
            )
            
            results = []
            for e in entities:
                # Retrieve chunk refs
                chunk_ids = await entity_store.get_chunks_for_entity(
                    session, e.id, req.workspace_id, limit=50
                )
                
                # Count relationships
                stmt_out = select(func.count(Relationship.id)).where(
                    Relationship.source_entity_id == e.id,
                    Relationship.workspace_id == req.workspace_id,
                )
                stmt_in = select(func.count(Relationship.id)).where(
                    Relationship.target_entity_id == e.id,
                    Relationship.workspace_id == req.workspace_id,
                )
                out_count = (await session.execute(stmt_out)).scalar() or 0
                in_count = (await session.execute(stmt_in)).scalar() or 0
                
                results.append(
                    EntitySearchResult(
                        entity=EntityRead.model_validate(e),
                        score=1.0,  # score not computed by fuzzy postgres search
                        chunk_refs=chunk_ids,
                        relationships_count=out_count + in_count,
                    )
                )
            return results
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in search_entities: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


@router.post("/entities/merge")
async def merge_entities(req: EntityMergeRequest):
    """Merge duplicate entity into canonical entity, reassigning all links."""
    try:
        async with get_db_session() as session:
            # Verify both exist
            canonical = await entity_store.get_by_id(session, req.canonical_id, req.workspace_id)
            duplicate = await entity_store.get_by_id(session, req.duplicate_id, req.workspace_id)
            if not canonical or not duplicate:
                raise HTTPException(status_code=404, detail="Canonical or duplicate entity not found")
            
            await entity_store.merge_entities(
                session, req.canonical_id, req.duplicate_id, req.workspace_id
            )
            return {
                "status": "merged",
                "canonical_id": req.canonical_id,
                "duplicate_id": req.duplicate_id,
            }
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in merge_entities: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


@router.get("/entities", response_model=List[EntityRead])
async def list_entities(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
    entity_type: Optional[EntityType] = Query(None, description="Optional type filter"),
    limit: int = Query(100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List entities in a workspace, optionally filtered by type."""
    try:
        async with get_db_session() as session:
            entities = await entity_store.list_entities(
                session, workspace_id, entity_type, limit, offset
            )
            return [EntityRead.model_validate(e) for e in entities]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in list_entities: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


# ---------------------------------------------------------------------------
# Relationship Routes
# ---------------------------------------------------------------------------

@router.get("/relationships/{relationship_id}", response_model=RelationshipRead)
async def get_relationship(relationship_id: uuid.UUID):
    """Fetch relationship details by ID."""
    try:
        async with get_db_session() as session:
            rel = await relationship_store.get_relationship_by_id(session, relationship_id)
            if not rel:
                raise HTTPException(status_code=404, detail="Relationship not found")
            return RelationshipRead.model_validate(rel)
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in get_relationship: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


@router.post("/relationships/search", response_model=List[RelationshipRead])
async def search_relationships(req: RelationshipSearchRequest):
    """Search for relationships by type and incident entities."""
    try:
        async with get_db_session() as session:
            stmt = select(Relationship).where(Relationship.workspace_id == req.workspace_id)
            if req.relationship_type:
                stmt = stmt.where(Relationship.relationship_type == req.relationship_type)
            if req.entity_id:
                stmt = stmt.where(
                    (Relationship.source_entity_id == req.entity_id)
                    | (Relationship.target_entity_id == req.entity_id)
                )
            stmt = stmt.limit(req.limit)
            res = await session.execute(stmt)
            rels = res.scalars().all()
            return [RelationshipRead.model_validate(r) for r in rels]
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in search_relationships: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


# ---------------------------------------------------------------------------
# Graph Routes
# ---------------------------------------------------------------------------

@router.get("/graph/neighborhood/{entity_id}", response_model=EntityNeighborhood)
async def get_neighborhood(
    entity_id: uuid.UUID,
    depth: int = Query(1, ge=1, le=2, description="Traversal depth"),
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier"),
):
    """Fetch the graph neighborhood centered around an entity."""
    try:
        data = await graph_retriever.get_entity_neighborhood(entity_id, depth, workspace_id)
        if not data:
            raise HTTPException(status_code=404, detail="Entity not found")
        return EntityNeighborhood.model_validate(data)
    except HTTPException:
        raise
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in get_neighborhood: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")
    except Exception as exc:
        logger.error("Failed to build neighborhood: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/stats")
async def get_graph_stats(
    workspace_id: str = Query("default_workspace", description="Tenant workspace identifier")
):
    """Fetch entity and relationship statistics for a workspace."""
    try:
        async with get_db_session() as session:
            entity_counts = await entity_store.count_by_type(session, workspace_id)
            total_entities = sum(entity_counts.values())
            
            stmt = (
                select(Relationship.relationship_type, func.count(Relationship.id))
                .where(Relationship.workspace_id == workspace_id)
                .group_by(Relationship.relationship_type)
            )
            res = await session.execute(stmt)
            rel_counts = {row[0]: row[1] for row in res.all()}
            total_relationships = sum(rel_counts.values())
            
            return {
                "entity_counts_by_type": entity_counts,
                "relationship_counts_by_type": rel_counts,
                "total_entities": total_entities,
                "total_relationships": total_relationships,
                "workspace_id": workspace_id,
            }
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("DB connection error in get_graph_stats: %s", exc)
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable")


@router.post("/graph/search")
async def graph_enriched_search(req: GraphSearchRequest):
    """Run semantic search on memory collection, then enrich with graph context."""
    # 1. Call standard semantic search
    semantic_results = search(
        query=req.query,
        limit=req.limit,
        sources=req.sources,
        author=req.author,
        team=req.team,
        start_time=req.start_time,
        end_time=req.end_time,
        hierarchy_scope=req.hierarchy_scope,
        entities=req.entities,
        workspace_id=req.workspace_id,
    )
    
    # 2. Enrich results with PostgreSQL graph context
    enriched = await graph_retriever.enrich_results(
        search_results=semantic_results,
        workspace_id=req.workspace_id or "default_workspace",
        include_relationships=True,
    )
    return enriched


# ---------------------------------------------------------------------------
# Extraction Trigger
# ---------------------------------------------------------------------------

@router.post("/extract/chunk")
async def extract_chunk(req: ExtractChunkRequest):
    """Trigger entity and relationship extraction on a raw text chunk."""
    summary = await extraction_pipeline.process_chunk(
        chunk_text=req.text,
        chunk_id=req.chunk_id,
        workspace_id=req.workspace_id,
    )
    if summary.get("error"):
        raise HTTPException(status_code=500, detail=summary["error"])
    return summary
