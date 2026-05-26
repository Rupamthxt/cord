import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.core.services.db_manager import DBManager
from backend.connectors.ingestion.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)
extractor = EntityExtractor()


class RootCauseAnalyzer:
    """
    Analyzes historical events and cross-source correlations in SQLite
    to construct chronological root-cause chains and progression traces.
    """

    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db = db_manager or DBManager()

    def analyze(self, query: str, related_events: List[Dict[str, Any]], correlations: List[Dict[str, Any]], workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Traces relationships between events based on temporal sequencing and correlations.
        """
        logger.info("Analyzing root causes and escalation pathways...")
        
        # 1. Sort events chronologically ascending to build trigger sequence
        sorted_events = sorted(
            related_events, 
            key=lambda x: x.get("timestamp") or ""
        )
        
        chain = []
        links = []
        confidence_accum = 0.0
        
        # 2. Check for correlation links between subsequent events
        for i in range(len(sorted_events)):
            ev_current = sorted_events[i]
            chain.append({
                "event_id": ev_current["event_id"],
                "title": ev_current["title"],
                "timestamp": ev_current["timestamp"],
                "event_type": ev_current["event_type"],
                "entities": ev_current.get("entities", [])
            })
            
            # Look for correlations to subsequent events
            for j in range(i + 1, len(sorted_events)):
                ev_next = sorted_events[j]
                
                # Check if there's a correlation row linking them
                # Since chunk IDs are stored, let's map event source references (which are chunk IDs)
                refs_current = ev_current.get("source_refs", [])
                refs_next = ev_next.get("source_refs", [])
                
                matching_corr = None
                for ref_c in refs_current:
                    for ref_n in refs_next:
                        # Find if this correlation exists in our aggregated list
                        for corr in correlations:
                            if (corr["source_a"] == ref_c and corr["source_b"] == ref_n) or \
                               (corr["source_b"] == ref_c and corr["source_a"] == ref_n):
                                matching_corr = corr
                                break
                        if matching_corr:
                            break
                    if matching_corr:
                        break
                
                if matching_corr:
                    links.append({
                        "from_event": ev_current["event_id"],
                        "to_event": ev_next["event_id"],
                        "type": matching_corr["type"],
                        "score": matching_corr["score"],
                        "reason": matching_corr["reason"]
                    })
                    confidence_accum += matching_corr["score"]

        # 3. Fetch matched pattern logs from SQLite with workspace filtering
        # Extract query entities to find matching patterns
        query_extraction = extractor.extract(query)
        query_entities = query_extraction["entities"]
        
        matching_patterns = []
        ws_filter = workspace_id or "default_workspace"
        for ent in query_entities:
            # Let's query SQLite patterns table directly for this entity and workspace
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM patterns WHERE entities LIKE ? AND workspace_id = ? ORDER BY last_detected DESC",
                    (f"%{ent}%", ws_filter)
                ).fetchall()
                for r in rows:
                    pat = {
                        "pattern_id": r["pattern_id"],
                        "pattern_type": r["pattern_type"],
                        "name": r["name"],
                        "description": r["description"],
                        "severity": r["severity"],
                        "confidence": r["confidence"],
                        "last_detected": r["last_detected"]
                    }
                    if pat not in matching_patterns:
                        matching_patterns.append(pat)

        # 4. Calculate overall root-cause confidence
        base_confidence = 0.5
        if links:
            # Avg correlation score boosts confidence
            avg_link_score = sum(l["score"] for l in links) / len(links)
            base_confidence = min(base_confidence + (avg_link_score * 0.4), 0.99)
        if matching_patterns:
            base_confidence = min(base_confidence + 0.1, 0.99)

        # 5. Explanatory chain builder
        explanation_steps = []
        for link in links:
            from_title = next((e["title"] for e in sorted_events if e["event_id"] == link["from_event"]), "Event")
            to_title = next((e["title"] for e in sorted_events if e["event_id"] == link["to_event"]), "Event")
            explanation_steps.append(
                f"Step: '{from_title}' linked to '{to_title}' (Reason: {link['reason']}, Similarity: {link['score']})"
            )

        logger.info(f"Root cause analysis complete. Constructed chain of length {len(chain)} with {len(links)} links.")

        return {
            "chain": chain,
            "correlations": links,
            "matched_patterns": matching_patterns,
            "explanation_steps": explanation_steps,
            "confidence_score": round(base_confidence, 2)
        }
