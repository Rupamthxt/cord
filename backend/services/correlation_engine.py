import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Set

from backend.models.setup_client import client
from backend.services.db_manager import DBManager

logger = logging.getLogger(__name__)
db_manager = DBManager()
MEM_COLLECTION = "workspace_memory"


class CrossSourceCorrelationEngine:
    """
    Correlates operational documents, Slack conversations, and incidents
    based on temporal proximity, shared entities, and semantic similarity.
    Updates entity networks and records correlations incrementally.
    """

    def __init__(self, correlation_threshold: float = 0.65):
        self.correlation_threshold = correlation_threshold

    def process_new_chunk(
        self,
        chunk_id: str,
        chunk_text: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ):
        """
        Processes a newly ingested chunk to:
        1. Log entity co-occurrences in the relational network.
        2. Scan and record cross-source correlations with historical chunks.
        """
        entities = metadata.get("entities", [])
        timestamp_str = metadata.get("timestamp")
        
        # 1. Update Entity Co-occurrence matrix
        if len(entities) > 1:
            logger.debug(f"Recording co-occurrences for entities: {entities}")
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    db_manager.record_cooccurrence(
                        entity_a=entities[i],
                        entity_b=entities[j],
                        weight=1.0,
                        timestamp=timestamp_str
                    )

        # 2. Query Qdrant for semantic matches to search for correlations
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Retrieve semantic candidates from workspace_memory
            candidates = client.query_points(
                collection_name=MEM_COLLECTION,
                query=embedding,
                limit=10
            )
            
            if not candidates or not candidates.points:
                return

            now_str = datetime.now(timezone.utc).isoformat()

            for match in candidates.points:
                match_id = match.id
                match_payload = match.payload or {}
                
                # Skip self-correlation
                if str(match_id) == str(chunk_id):
                    continue
                
                # Extract matching info
                match_entities = set(match_payload.get("entities", []))
                match_timestamp_str = match_payload.get("timestamp")
                match_source = match_payload.get("source", "unknown")
                match_text = match_payload.get("text", "")
                
                # Check Temporal Proximity
                temporal_score = 0.0
                time_diff_minutes = float("inf")
                if timestamp_str and match_timestamp_str:
                    try:
                        t1 = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        t2 = datetime.fromisoformat(match_timestamp_str.replace("Z", "+00:00"))
                        time_diff_seconds = abs((t1 - t2).total_seconds())
                        time_diff_minutes = time_diff_seconds / 60.0
                        
                        if time_diff_minutes <= 60:
                            temporal_score = 1.0
                        elif time_diff_minutes <= 1440:  # 24 hours
                            temporal_score = 0.5
                        elif time_diff_minutes <= 10080:  # 7 days
                            temporal_score = 0.2
                    except Exception as e:
                        logger.warning(f"Error parsing dates for correlation: {e}")

                # Check Entity Overlap
                shared_entities = set(entities).intersection(match_entities)
                overlap_score = 0.0
                if entities:
                    overlap_score = min(len(shared_entities) / max(len(entities), 1), 1.0)
                
                # Semantic Score
                semantic_score = match.score  # cosine similarity range is typically 0.0 to 1.0

                # Weighted Combined Score
                # Semantic (40%), Entity Overlap (30%), Temporal Proximity (30%)
                combined_score = (semantic_score * 0.40) + (overlap_score * 0.30) + (temporal_score * 0.30)

                # Cross-source boost (e.g. Slack correlating to Notion adds extra contextual interest)
                is_cross_source = metadata.get("source") != match_source
                if is_cross_source and combined_score > 0.5:
                    combined_score = min(combined_score + 0.05, 1.0)

                # Record correlation if above threshold
                if combined_score >= self.correlation_threshold:
                    reasons = []
                    if shared_entities:
                        reasons.append(f"shared entities: {list(shared_entities)}")
                    if time_diff_minutes <= 60:
                        reasons.append("temporal proximity (< 1 hr)")
                    elif time_diff_minutes <= 1440:
                        reasons.append("temporal proximity (< 24 hrs)")
                    if semantic_score > 0.8:
                        reasons.append("high semantic similarity")
                    
                    reason_str = ", ".join(reasons) if reasons else "semantic overlap"
                    correlation_type = "cross_source" if is_cross_source else "intra_source"
                    
                    # Store in database
                    db_manager.add_correlation(
                        source_a=chunk_id,
                        source_b=str(match_id),
                        c_type=correlation_type,
                        score=round(combined_score, 4),
                        reason=reason_str,
                        timestamp=now_str,
                        workspace_id=metadata.get("workspace_id", "default_workspace")
                    )
                    
                    logger.debug(
                        f"Correlated chunk {chunk_id} with match {match_id} "
                        f"(Score: {combined_score:.4f}, Reason: {reason_str})"
                    )

        except Exception as e:
            logger.error(f"Correlation scanning failed: {e}", exc_info=True)
