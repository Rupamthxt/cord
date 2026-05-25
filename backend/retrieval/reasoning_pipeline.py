import re
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from backend.ingestion.entity_extractor import EntityExtractor
from backend.services.db_manager import DBManager
from backend.retrieval.ranker import Ranker

logger = logging.getLogger(__name__)
extractor = EntityExtractor()
db_manager = DBManager()


class ReasoningPipeline:
    """
    Production-grade multi-stage hybrid retrieval and reasoning pipeline:
    query -> entity analysis -> temporal analysis -> correlation analysis -> Qdrant filters -> ranker -> synthesis
    """

    def __init__(self, ranker: Optional[Ranker] = None):
        self.ranker = ranker or Ranker()

    def parse_temporal_query(self, query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parses time expressions from query string.
        Returns:
            Tuple[start_time_iso, end_time_iso, cleaned_query]
        """
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None
        cleaned_query = query

        # Time mapping patterns
        time_patterns = [
            (r"\blast\s+([0-9]+)\s+days?\b", lambda m: now - timedelta(days=int(m.group(1)))),
            (r"\blast\s+([0-9]+)\s+weeks?\b", lambda m: now - timedelta(days=7 * int(m.group(1)))),
            (r"\blast\s+([0-9]+)\s+hours?\b", lambda m: now - timedelta(hours=int(m.group(1)))),
            (r"\bpast\s+week\b", lambda m: now - timedelta(days=7)),
            (r"\byesterday\b", lambda m: now - timedelta(days=1)),
            (r"\btoday\b", lambda m: now - timedelta(days=0.5)),  # rough limit
            (r"\brecent\b", lambda m: now - timedelta(days=14)),
        ]

        for pattern, delta_fn in time_patterns:
            match = re.search(pattern, cleaned_query, re.IGNORECASE)
            if match:
                try:
                    target_time = delta_fn(match)
                    # If it's 'yesterday', we can set a specific window, else just a lookback start_time
                    if "yesterday" in match.group(0).lower():
                        # From 2 days ago to 1 day ago
                        start_time = (now - timedelta(days=2)).isoformat()
                        end_time = (now - timedelta(days=1)).isoformat()
                    else:
                        start_time = target_time.isoformat()
                        end_time = now.isoformat()
                    
                    # Remove the time phrase from the query to improve semantic vector search
                    cleaned_query = re.sub(pattern, "", cleaned_query, flags=re.IGNORECASE).strip()
                    logger.info(f"Temporal parsing detected lookback: start={start_time}, end={end_time}")
                    break
                except Exception as e:
                    logger.error(f"Error parsing temporal query: {e}")

        return start_time, end_time, cleaned_query

    def execute(
        self,
        query: str,
        limit: int = 5,
        sources: Optional[List[str]] = None,
        author: Optional[str] = None,
        team: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        hierarchy_scope: Optional[str] = None,
        entities: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the reasoning stages to retrieve semantically matching,
        chronologically verified, and correlated workspace documents.
        """
        # Stage 1 & 2: Entity & Temporal Analysis
        query_extraction = extractor.extract(query)
        extracted_entities = query_extraction["entities"]
        
        # Parse temporal constraints from query string if not explicitly passed
        t_start, t_end, search_query = self.parse_temporal_query(query)
        if not start_time and t_start:
            start_time = t_start
        if not end_time and t_end:
            end_time = t_end

        # Stage 3: Correlation Analysis
        # Fetch correlations mapping from DB to see if any query entities match
        logger.info(f"Reasoning Pipeline: search_query='{search_query}' (original='{query}')")

        # Standard retrieve candidates from search
        from backend.retrieval.search import search as base_search
        
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range
        from backend.models.setup_client import client
        from backend.embeddings.model import get_embedding
        
        query_embedding = get_embedding(search_query)
        filter_conditions = []

        # Enforce workspace security isolation
        ws_filter = workspace_id or "default_workspace"
        filter_conditions.append(FieldCondition(key="workspace_id", match=MatchValue(value=ws_filter)))

        if sources:
            filter_conditions.append(FieldCondition(key="source", match=MatchAny(any=sources)))
        if author:
            filter_conditions.append(FieldCondition(key="author", match=MatchValue(value=author)))
        if team:
            filter_conditions.append(FieldCondition(key="team", match=MatchValue(value=team)))
        if start_time or end_time:
            start_unix = datetime.fromisoformat(start_time.replace("Z", "+00:00")).timestamp() if start_time else None
            end_unix = datetime.fromisoformat(end_time.replace("Z", "+00:00")).timestamp() if end_time else None
            filter_conditions.append(
                FieldCondition(
                    key="timestamp_unix",
                    range=Range(gte=start_unix, lte=end_unix)
                )
            )
        if hierarchy_scope:
            scope_parts = [p for p in hierarchy_scope.split("/") if p]
            if scope_parts:
                filter_conditions.append(FieldCondition(key="hierarchy", match=MatchValue(value=scope_parts[-1])))
        if entities:
            for entity in entities:
                filter_conditions.append(FieldCondition(key="entities", match=MatchValue(value=entity)))
        # Also match query entities as optional filters if needed, but keeping it broad is better for recall.

        qdrant_filter = Filter(must=filter_conditions) if filter_conditions else None
        candidates_limit = max(limit * 3, 20)
        
        try:
            results = client.query_points(
                collection_name="workspace_memory",
                query=query_embedding,
                query_filter=qdrant_filter,
                limit=candidates_limit
            )
            scored_points = results.points or []
        except Exception as e:
            if "not found" in str(e).lower():
                logger.warning("Qdrant collection 'workspace_memory' not found. Returning empty results.")
                scored_points = []
                class MockResults:
                    points = []
                results = MockResults()
            else:
                raise e

        # Stage 4 & 5: Hybrid Scoring with Correlation Boosts
        candidate_ids = {str(p.id) for p in scored_points}
        ranked_results = []
        
        # Warm up user query entities
        target_entities = set(extracted_entities)
        if entities:
            target_entities.update(entities)

        # Access standard ranker scores as base
        base_ranked = self.ranker.rank_results(
            query=search_query,
            results=results.points or [],
            hierarchy_scope=hierarchy_scope,
            entity_filters=entities
        )
        
        # Match back to original ScoredPoints or payload to inject correlation boosts
        # Correlation boost: if a point has registered correlations with other items in the candidate set,
        # it is considered high-value (highly cross-referenced in the current context)!
        for item in base_ranked:
            content = item["content"]
            score = item["score"]
            # Find the original point ID by matching content or lookup
            # Since rank_results outputs a clean dict, let's look up its point ID.
            # We can find it by finding the candidate that matches payload text.
            point_id = None
            for p in scored_points:
                if p.payload.get("text") == content:
                    point_id = str(p.id)
                    break
            
            boost_correlation = 0.0
            correlation_reasons = []
            
            if point_id:
                # Fetch correlations for this point from SQLite
                correlations = db_manager.get_correlations_for_source(point_id)
                for corr in correlations:
                    # If the correlated source is also in our current retrieved candidate set,
                    # we boost it (cross-source verification within the search context)!
                    if corr["related_source"] in candidate_ids:
                        # Boost is proportional to correlation score (max boost +0.1)
                        boost_val = corr["score"] * 0.1
                        boost_correlation += boost_val
                        correlation_reasons.append(
                            f"correlated with {corr['related_source'][:8]} ({corr['reason']})"
                        )

            # Adjust score
            final_score = score + boost_correlation
            
            # Retrieve diagnostics and update
            # rank_results added 'diagnostics' inside item, we pulled it out in search.py.
            # But here in ReasoningPipeline we want to expose it to API!
            diagnostics = item.get("diagnostics", {}).copy()
            # If diagnostics is not populated (e.g. empty), make sure we populate it
            diagnostics["correlation_boost"] = round(boost_correlation, 4)
            
            item_copy = item.copy()
            item_copy["score"] = round(final_score, 4)
            item_copy["diagnostics"] = diagnostics
            item_copy["metadata"] = item["metadata"].copy()
            
            if correlation_reasons:
                item_copy["metadata"]["correlation_traces"] = correlation_reasons
                
            ranked_results.append(item_copy)

        # Sort by final score
        ranked_results.sort(key=lambda r: r["score"], reverse=True)
        final_results = ranked_results[:limit]

        # Log diagnostics trace for observability
        for item in final_results:
            logger.info(
                f"Reasoning Trace for '{item['metadata'].get('title', 'Unknown')[:30]}': "
                f"FinalScore={item['score']}, Cosine={item['diagnostics'].get('cosine_similarity')}, "
                f"RecencyBoost={item['diagnostics'].get('recency_boost')}, "
                f"HierarchyBoost={item['diagnostics'].get('hierarchy_boost')}, "
                f"EntityBoost={item['diagnostics'].get('entity_boost')}, "
                f"CorrelationBoost={item['diagnostics'].get('correlation_boost')}"
            )

        return {
            "query": query,
            "results": final_results
        }
