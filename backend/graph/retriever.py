"""
backend/graph/retriever.py
--------------------------
GraphAwareRetriever fetches entity and relationship context from PostgreSQL
to enrich vector search results, search by entity, and get neighborhoods.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.entities.models import ChunkEntityRef, Entity, Relationship
from backend.entities.schema import EntityRead
from backend.relationships.schema import RelationshipRead
from backend.entities.store import entity_store
from backend.relationships.store import relationship_store
from backend.graph.db import get_db_session
from backend.models.setup_client import client

logger = logging.getLogger(__name__)
COLLECTION_NAME = "workspace_memory"


class GraphAwareRetriever:
    """Enriches semantic search with structured graph information from PostgreSQL."""

    async def enrich_results(
        self,
        search_results: Dict[str, Any],
        workspace_id: str = "default_workspace",
        include_relationships: bool = True,
        max_entities_per_chunk: int = 5,
    ) -> Dict[str, Any]:
        """Enriches the provided search_results with entities and relationships from PostgreSQL.

        If PostgreSQL is down or an error occurs, it returns the results unchanged.
        """
        results_list = search_results.get("results")
        if not results_list:
            return search_results

        try:
            async with get_db_session() as session:
                for item in results_list:
                    chunk_id = item.get("id")
                    if not chunk_id:
                        continue

                    # 1. Fetch ChunkEntityRefs
                    stmt = select(ChunkEntityRef).where(
                        ChunkEntityRef.chunk_id == chunk_id,
                        ChunkEntityRef.workspace_id == workspace_id,
                    )
                    res = await session.execute(stmt)
                    refs = res.scalars().all()

                    graph_entities = []
                    graph_relationships = []
                    seen_entity_ids = set()

                    # 2. Fetch Entity details (up to limit)
                    for ref in refs[:max_entities_per_chunk]:
                        entity = await entity_store.get_by_id(
                            session, ref.entity_id, workspace_id
                        )
                        if entity:
                            graph_entities.append(
                                EntityRead.model_validate(entity).model_dump()
                            )
                            seen_entity_ids.add(entity.id)

                    # 3. Fetch relationships if requested
                    if include_relationships and seen_entity_ids:
                        for ent_id in seen_entity_ids:
                            # 1-hop outgoing and incoming
                            nb = await relationship_store.get_neighborhood(
                                session, ent_id, depth=1
                            )
                            
                            for r in nb["outgoing"]:
                                rel_dump = RelationshipRead.model_validate(r).model_dump()
                                # Enrich with target name
                                target = await entity_store.get_by_id(
                                    session, r.target_entity_id, workspace_id
                                )
                                if target:
                                    rel_dump["target_entity_name"] = target.name
                                    rel_dump["target_entity_type"] = target.type
                                if rel_dump["id"] not in {x["id"] for x in graph_relationships}:
                                    graph_relationships.append(rel_dump)
                                    
                            for r in nb["incoming"]:
                                rel_dump = RelationshipRead.model_validate(r).model_dump()
                                # Enrich with source name
                                source = await entity_store.get_by_id(
                                    session, r.source_entity_id, workspace_id
                                )
                                if source:
                                    rel_dump["source_entity_name"] = source.name
                                    rel_dump["source_entity_type"] = source.type
                                if rel_dump["id"] not in {x["id"] for x in graph_relationships}:
                                    graph_relationships.append(rel_dump)

                    # Attach graph metadata to search results
                    item["graph_entities"] = graph_entities
                    item["graph_relationships"] = graph_relationships

        except Exception as exc:
            logger.warning(
                "Failed to enrich search results with graph context (PG database may be unavailable): %s",
                exc,
            )

        return search_results

    async def search_by_entity(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        workspace_id: str = "default_workspace",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Finds all Qdrant chunks referencing a given entity name."""
        try:
            async with get_db_session() as session:
                # Find entity (case-insensitive exact or fuzzy prefix match)
                entity = await entity_store.get_by_name(
                    session, entity_name, entity_type, workspace_id
                )
                if not entity:
                    # Try fuzzy prefix search
                    fuzzy = await entity_store.fuzzy_search(
                        session, entity_name, workspace_id, entity_type, limit=1
                    )
                    if fuzzy:
                        entity = fuzzy[0]

                if not entity:
                    return {"entity": None, "results": []}

                # Get linked chunk IDs
                chunk_ids = await entity_store.get_chunks_for_entity(
                    session, entity.id, workspace_id, limit=limit
                )

                if not chunk_ids:
                    return {
                        "entity": EntityRead.model_validate(entity).model_dump(),
                        "results": [],
                    }

                # Fetch payload data from Qdrant
                qdrant_points = client.retrieve(
                    collection_name=COLLECTION_NAME,
                    ids=chunk_ids,
                )

                results = []
                for point in qdrant_points:
                    payload = point.payload or {}
                    metadata = payload.get("metadata", {})
                    results.append(
                        {
                            "id": str(point.id),
                            "content": payload.get("text", ""),
                            "score": 1.0,  # default score for direct match
                            "source": payload.get("source", "unknown"),
                            "source_type": payload.get("source_type", "document"),
                            "workspace_id": payload.get("workspace_id", workspace_id),
                            "author": payload.get("author", "unknown"),
                            "timestamp": payload.get("timestamp", ""),
                            "url": payload.get("url", ""),
                            "hierarchy": payload.get("hierarchy", []),
                            "entities": payload.get("entities", []),
                            "relationships": payload.get("relationships", []),
                            "metadata": metadata,
                            "diagnostics": {
                                "cosine_similarity": 1.0,
                                "recency_boost": 0.0,
                                "hierarchy_boost": 0.0,
                                "entity_boost": 0.0,
                                "source_boost": 0.0,
                            },
                        }
                    )

                return {
                    "entity": EntityRead.model_validate(entity).model_dump(),
                    "results": results,
                }

        except Exception as exc:
            logger.error("search_by_entity failed: %s", exc, exc_info=True)
            raise

    async def get_entity_neighborhood(
        self,
        entity_id: uuid.UUID,
        depth: int = 1,
        workspace_id: str = "default_workspace",
    ) -> Dict[str, Any]:
        """Gets detail, outgoing/incoming relationships, and linked chunks for an entity."""
        try:
            async with get_db_session() as session:
                entity = await entity_store.get_by_id(session, entity_id, workspace_id)
                if not entity:
                    return {}

                nb = await relationship_store.get_neighborhood(session, entity_id, depth)

                outgoing_enriched = []
                incoming_enriched = []

                for r in nb["outgoing"]:
                    r_dict = RelationshipRead.model_validate(r).model_dump()
                    target = await entity_store.get_by_id(
                        session, r.target_entity_id, workspace_id
                    )
                    if target:
                        r_dict["target_entity"] = EntityRead.model_validate(target).model_dump()
                    outgoing_enriched.append(r_dict)

                for r in nb["incoming"]:
                    r_dict = RelationshipRead.model_validate(r).model_dump()
                    source = await entity_store.get_by_id(
                        session, r.source_entity_id, workspace_id
                    )
                    if source:
                        r_dict["source_entity"] = EntityRead.model_validate(source).model_dump()
                    incoming_enriched.append(r_dict)

                chunk_ids = await entity_store.get_chunks_for_entity(
                    session, entity_id, workspace_id, limit=50
                )

                return {
                    "entity": EntityRead.model_validate(entity).model_dump(),
                    "outgoing": outgoing_enriched,
                    "incoming": incoming_enriched,
                    "depth": depth,
                    "linked_chunk_ids": chunk_ids,
                }

        except Exception as exc:
            logger.error("get_entity_neighborhood failed: %s", exc, exc_info=True)
            raise


graph_retriever = GraphAwareRetriever()
