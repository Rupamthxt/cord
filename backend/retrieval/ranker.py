import math
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.ingestion.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)
extractor = EntityExtractor()


class Ranker:
    """
    Production-grade modular ranking pipeline for organizational search results.
    Combines semantic cosine similarity with metadata relevance boosts:
    - Recency decay
    - Hierarchy scope relevance
    - Entity overlap with the search query
    - Authoritative source weighting
    """

    def __init__(
        self,
        recency_weight: float = 0.12,
        hierarchy_weight: float = 0.15,
        entity_weight: float = 0.15,
        source_weights: Optional[Dict[str, float]] = None,
    ):
        self.recency_weight = recency_weight
        self.hierarchy_weight = hierarchy_weight
        self.entity_weight = entity_weight
        
        # Default source weights: give official wikis (Notion) a small edge over informal chats (Slack)
        self.source_weights = source_weights or {
            "notion": 0.05,
            "slack": 0.0,
            "unknown": 0.0
        }

    def rank_results(
        self,
        query: str,
        results: List[Any],
        hierarchy_scope: Optional[str] = None,
        entity_filters: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Applies metadata relevance boosts to vector similarity scores.
        
        Args:
            query: The user query string.
            results: Qdrant query results (list of ScoredPoint).
            hierarchy_scope: Optional path prefix to boost (e.g., '/Engineering/Incidents').
            entity_filters: Optional list of entities to boost.
            
        Returns:
            List of dicts representing the sorted and enriched search results.
        """
        # Extract query entities to check for overlap
        query_extraction = extractor.extract(query)
        query_entities = set(query_extraction["entities"])
        if entity_filters:
            for entity in entity_filters:
                query_entities.add(entity)

        now = datetime.now(timezone.utc)
        ranked_results = []

        for point in results:
            payload = point.payload or {}
            score_cosine = point.score
            
            # 1. Recency Boost
            # Calculate exponential decay on difference in days
            boost_recency = 0.0
            timestamp_str = payload.get("timestamp")
            if timestamp_str:
                try:
                    # Parse timestamp (supports fractional seconds and Z/timezone offsets)
                    timestamp_str = timestamp_str.replace("Z", "+00:00")
                    doc_time = datetime.fromisoformat(timestamp_str)
                    delta_days = (now - doc_time).days
                    if delta_days < 0:
                        delta_days = 0
                    # Exponential decay: e^(-0.01 * days). Half life is ~70 days.
                    boost_recency = math.exp(-0.01 * delta_days) * self.recency_weight
                except Exception as e:
                    logger.warning(f"Failed to parse timestamp '{timestamp_str}' for ranking: {e}")

            # 2. Hierarchy Match Boost
            # Check if the document path/hierarchy matches the query hierarchy scope
            boost_hierarchy = 0.0
            if hierarchy_scope:
                doc_path = payload.get("metadata", {}).get("path") or ""
                doc_hierarchy = payload.get("hierarchy", [])
                
                # Standardize hierarchy scope to list of parts
                scope_parts = [p for p in hierarchy_scope.split("/") if p]
                
                # Check for prefix match in list
                if len(doc_hierarchy) >= len(scope_parts) and doc_hierarchy[:len(scope_parts)] == scope_parts:
                    # Exact folder subtree prefix match gets full boost
                    boost_hierarchy = self.hierarchy_weight
                elif any(part in doc_hierarchy for part in scope_parts):
                    # Partial overlap in path gets partial boost
                    boost_hierarchy = self.hierarchy_weight * 0.4

            # 3. Entity Overlap Boost
            boost_entities = 0.0
            doc_entities = set(payload.get("entities", []))
            if query_entities and doc_entities:
                overlap = query_entities.intersection(doc_entities)
                if overlap:
                    # Match up to 3 overlapping entities for max boost
                    boost_entities = min(len(overlap) / 3.0, 1.0) * self.entity_weight

            # 4. Source Weight Boost
            source = payload.get("source", "unknown")
            boost_source = self.source_weights.get(source, 0.0)

            # Calculate final combined score
            score_final = score_cosine + boost_recency + boost_hierarchy + boost_entities + boost_source
            
            # Format and enrich document result structure
            # Ensure safe extraction of metadata fields
            metadata = payload.get("metadata", {})
            result_item = {
                "content": payload.get("text", ""),
                "score": round(score_final, 4),
                "source": source,
                "source_type": payload.get("source_type", "document"),
                "author": payload.get("author", "unknown"),
                "timestamp": payload.get("timestamp", ""),
                "url": payload.get("url", ""),
                "hierarchy": payload.get("hierarchy", []),
                "entities": payload.get("entities", []),
                "relationships": payload.get("relationships", []),
                "metadata": metadata,
                "diagnostics": {
                    "cosine_similarity": round(score_cosine, 4),
                    "recency_boost": round(boost_recency, 4),
                    "hierarchy_boost": round(boost_hierarchy, 4),
                    "entity_boost": round(boost_entities, 4),
                    "source_boost": round(boost_source, 4)
                }
            }
            ranked_results.append(result_item)

        # Sort results by final score descending
        ranked_results.sort(key=lambda r: r["score"], reverse=True)
        return ranked_results
