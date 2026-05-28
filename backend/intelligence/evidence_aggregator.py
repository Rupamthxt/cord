import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

from backend.intelligence.retrieval.search import search
from backend.core.services.db_manager import DBManager
from backend.connectors.ingestion.entity_extractor import EntityExtractor
from backend.core.models.setup_client import client

logger = logging.getLogger(__name__)
extractor = EntityExtractor()


class EvidenceAggregator:
    """
    Assembles evidence for operational intelligence:
    - Fetches semantic chunks from Qdrant 'workspace_memory'
    - Fetches events from Qdrant 'workspace_events' & SQLite 'events'
    - Identifies relevant correlations from SQLite 'correlations'
    - Scores and deduplicates evidence
    - Groups evidence chronologically
    """

    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db = db_manager or DBManager()

    def aggregate(self, query: str, limit: int = 10, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Assembles all related chunks, events, and correlations for a query.
        """
        logger.info(f"Aggregating evidence for query: '{query}' in workspace '{workspace_id}'...")
        
        # 1. Extract query entities
        query_extraction = extractor.extract(query)
        query_entities = query_extraction["entities"]
        
        # 2. Autodiscover workspace scope if not explicitly passed
        if not workspace_id:
            try:
                from backend.core.embeddings.model import get_embedding
                query_emb = get_embedding(query)
                q_res = client.query_points(
                    collection_name="workspace_memory",
                    query=query_emb,
                    limit=5
                )
                ws_counts = {}
                for p in (q_res.points or []):
                    ws = (p.payload or {}).get("workspace_id")
                    if ws:
                        ws_counts[ws] = ws_counts.get(ws, 0) + 1
                if ws_counts:
                    workspace_id = max(ws_counts, key=ws_counts.get)
                    logger.info(f"Auto-discovered workspace scope: '{workspace_id}' based on entity payload correlation")
            except Exception as e:
                logger.debug(f"Auto-discovery workspace lookup failed: {e}")

        # 3. Retrieve chunks from standard reasoning search with workspace isolation
        search_res = search(query=query, limit=limit * 2, workspace_id=workspace_id)
        raw_chunks = search_res.get("results", [])

        # 3. Retrieve events
        # A. Semantically from Qdrant with workspace filter
        semantic_events = []
        try:
            from backend.core.embeddings.model import get_embedding
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_emb = get_embedding(query)
            
            ws_filter = workspace_id or "default_workspace"
            q_filter = Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=ws_filter))])
            
            q_res = client.query_points(
                collection_name="workspace_events",
                query=query_emb,
                query_filter=q_filter,
                limit=limit
            )
            for p in (q_res.points or []):
                payload = p.payload or {}
                semantic_events.append({
                    "event_id": payload.get("event_id"),
                    "title": payload.get("title"),
                    "timestamp": payload.get("timestamp"),
                    "summary": payload.get("summary"),
                    "event_type": payload.get("event_type"),
                    "entities": payload.get("entities", []),
                    "related_teams": payload.get("related_teams", []),
                    "score": round(p.score, 4)
                })
        except Exception as e:
            if "not found" not in str(e).lower():
                logger.warning(f"Failed to query events from Qdrant: {e}")

        # B. Relational from SQLite based on entities and workspace isolation
        relational_events = []
        ws_filter = workspace_id or "default_workspace"
        for ent in query_entities:
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT e.* FROM events e
                    JOIN event_entities ee ON e.event_id = ee.event_id
                    WHERE ee.entity_name = ? AND e.workspace_id = ?
                    ORDER BY e.timestamp DESC LIMIT 10
                    """,
                    (ent, ws_filter)
                ).fetchall()
                for r in rows:
                    ev = self.db.get_event(r["event_id"])
                    if ev and ev not in relational_events:
                        relational_events.append(ev)

        # Merge and deduplicate events
        merged_events = []
        seen_event_ids = set()
        for ev in (semantic_events + relational_events):
            ev_id = ev.get("event_id")
            if ev_id and ev_id not in seen_event_ids:
                seen_event_ids.add(ev_id)
                merged_events.append(ev)

        # 4. Gather Correlations from SQLite
        # For each chunk retrieved, lookup correlations in the DB
        correlations = []
        seen_corr_ids = set()
        chunk_ids = {c["id"] for c in raw_chunks}
        
        for chunk_id in chunk_ids:
            chunk_corrs = self.db.get_correlations_for_source(chunk_id)
            for corr in chunk_corrs:
                # Format a correlation item
                related = corr["related_source"]
                c_type = corr["type"]
                # Create a stable identifier
                s1, s2 = sorted([chunk_id, related])
                corr_key = f"{s1}_{s2}_{c_type}"
                
                if corr_key not in seen_corr_ids:
                    seen_corr_ids.add(corr_key)
                    correlations.append({
                        "source_a": chunk_id,
                        "source_b": related,
                        "type": c_type,
                        "score": corr["score"],
                        "reason": corr["reason"],
                        "timestamp": corr["timestamp"]
                    })

        # 5. Deduplicate and score chunks
        processed_chunks = []
        seen_chunk_texts = set()
        
        for c in raw_chunks:
            text = c["content"]
            # Basic normalization for deduplication
            normalized_text = " ".join(text.lower().split())
            if normalized_text in seen_chunk_texts:
                continue
            seen_chunk_texts.add(normalized_text)
            
            # Boost score if chunk has registered correlations with other retrieved chunks
            boost = 0.0
            has_corr = False
            for corr in correlations:
                if (corr["source_a"] == c["id"] and corr["source_b"] in chunk_ids) or \
                   (corr["source_b"] == c["id"] and corr["source_a"] in chunk_ids):
                    boost += 0.05
                    has_corr = True
            
            c_score = c["score"] + min(boost, 0.15)
            c["score"] = round(c_score, 4)
            c["diagnostics"]["aggregation_boost"] = round(boost, 4)
            processed_chunks.append(c)

        # Sort processed chunks
        processed_chunks.sort(key=lambda x: x["score"], reverse=True)
        final_chunks = processed_chunks[:limit]

        # 6. Group evidence chronologically
        all_evidence = []
        for c in final_chunks:
            all_evidence.append({
                "type": "chunk",
                "id": c["id"],
                "title": c["metadata"].get("title") or "discussion",
                "source": c["source"],
                "timestamp": c["timestamp"],
                "score": c["score"],
                "content": c["content"],
                "entities": c["entities"]
            })
            
        for ev in merged_events:
            all_evidence.append({
                "type": "event",
                "id": ev["event_id"],
                "title": ev["title"],
                "source": ev.get("source_refs", [None])[0] or "system",
                "timestamp": ev["timestamp"],
                # Events score defaults to its vector match or 0.8 base
                "score": ev.get("score", 0.8),
                "content": ev["summary"],
                "entities": ev.get("entities", [])
            })

        # Sort chronological descending
        all_evidence.sort(key=lambda x: x["timestamp"] or "", reverse=True)

        logger.info(
            f"Evidence aggregation complete. Collected {len(final_chunks)} chunks, "
            f"{len(merged_events)} events, and {len(correlations)} correlations."
        )

        return {
            "chunks": final_chunks,
            "events": merged_events,
            "correlations": correlations,
            "chronological_timeline": all_evidence
        }
