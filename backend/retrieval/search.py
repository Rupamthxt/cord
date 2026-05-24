import logging
from typing import List, Optional, Dict, Any
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range

from backend.models.setup_client import client
from backend.embeddings.model import get_embedding
from backend.retrieval.ranker import Ranker

logger = logging.getLogger(__name__)
COLLECTION_NAME = "workspace_memory"
ranker = Ranker()


def search(
    query: str,
    limit: int = 5,
    sources: Optional[List[str]] = None,
    author: Optional[str] = None,
    team: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    hierarchy_scope: Optional[str] = None,
    entities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Performs vector similarity search combined with metadata-aware filters
    and multi-dimensional ranking boosts.
    
    Returns structured results:
    {
        "query": "...",
        "results": [
            {
                "content": "...",
                "score": float,
                "source": "...",
                "source_type": "...",
                "author": "...",
                "timestamp": "...",
                "url": "...",
                "hierarchy": [...],
                "entities": [...],
                "metadata": {...}
            }
        ]
    }
    """
    logger.info(
        f"Retrieval started: query='{query}' filters: sources={sources}, "
        f"author={author}, team={team}, range=({start_time} to {end_time}), "
        f"hierarchy={hierarchy_scope}, entities={entities}"
    )

    query_embedding = get_embedding(query)
    filter_conditions = []

    # 1. Source filtering
    if sources:
        filter_conditions.append(
            FieldCondition(key="source", match=MatchAny(any=sources))
        )

    # 2. Author filtering
    if author:
        filter_conditions.append(
            FieldCondition(key="author", match=MatchValue(value=author))
        )

    # 3. Team filtering
    if team:
        filter_conditions.append(
            FieldCondition(key="team", match=MatchValue(value=team))
        )

    # 4. Temporal range filtering
    if start_time or end_time:
        filter_conditions.append(
            FieldCondition(
                key="timestamp",
                range=Range(gte=start_time, lte=end_time)
            )
        )

    # 5. Hierarchy path filtering
    if hierarchy_scope:
        scope_parts = [p for p in hierarchy_scope.split("/") if p]
        if scope_parts:
            # Require the document hierarchy to contain the last folder of scope
            filter_conditions.append(
                FieldCondition(key="hierarchy", match=MatchValue(value=scope_parts[-1]))
            )

    # 6. Entity filtering
    if entities:
        for entity in entities:
            filter_conditions.append(
                FieldCondition(key="entities", match=MatchValue(value=entity))
            )

    qdrant_filter = Filter(must=filter_conditions) if filter_conditions else None

    # Retrieve candidate points from Qdrant (fetch more than limit to allow ranking re-ordering)
    candidates_limit = max(limit * 3, 20)
    
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=qdrant_filter,
        limit=candidates_limit
    )

    # Apply modular ranking pipeline
    ranked_results = ranker.rank_results(
        query=query,
        results=results.points or [],
        hierarchy_scope=hierarchy_scope,
        entity_filters=entities
    )

    # Limit to requested count
    final_results = ranked_results[:limit]

    # Standardize result objects (remove diagnostic logs for clean output, but keep in logging)
    output_results = []
    for item in final_results:
        # Log ranking diagnostics for observability
        logger.debug(f"Result scoring diagnostics: content_preview='{item['content'][:60]}', score={item['score']}, details={item['diagnostics']}")
        
        # Remove diagnostics field from public search response
        clean_item = item.copy()
        clean_item.pop("diagnostics", None)
        output_results.append(clean_item)

    response = {
        "query": query,
        "results": output_results
    }

    logger.info(f"Retrieval complete: returned {len(output_results)} results.")
    return response