import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class InsightSynthesizer:
    """
    Synthesizes aggregated operational evidence, query profiles,
    and root-cause analyses into highly structured, evidence-linked summaries.
    """

    def synthesize(
        self,
        query: str,
        query_classification: Dict[str, Any],
        aggregated_evidence: Dict[str, Any],
        root_cause_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Builds a traceable operational insight payload.
        """
        logger.info("Synthesizing evidence and reasoning results...")
        
        chunks = aggregated_evidence.get("chunks", [])
        events = aggregated_evidence.get("events", [])
        patterns = root_cause_analysis.get("matched_patterns", [])
        query_type = query_classification["query_type"]
        
        # 1. Synthesize concise Summary statement
        if query_type == "root_cause_analysis":
            primary_trigger = "unknown"
            if root_cause_analysis.get("correlations"):
                first_link = root_cause_analysis["correlations"][0]
                from_id = first_link["from_event"]
                # Find event title
                for ev in events:
                    if ev["event_id"] == from_id:
                        primary_trigger = ev["title"]
                        break
            
            summary = (
                f"Analysis of query '{query}' indicates a possible sequence chain. "
                f"The primary initial trigger appears related to '{primary_trigger}'."
            )
        elif query_type == "recurring_issue":
            problem_entity = "unknown"
            if patterns:
                # Find recurring incident patterns
                recurring = [p for p in patterns if p["pattern_type"] == "recurring_incident"]
                if recurring:
                    problem_entity = recurring[0]["name"]
            
            summary = (
                f"Recurring issue profile detected. "
                f"Primary active bottleneck matches '{problem_entity}'."
            )
        elif query_type == "trend_analysis":
            summary = (
                f"Trend analysis highlights frequency changes and progression. "
                f"Detected {len(events)} operational events over the timeline."
            )
        else:
            summary = (
                f"Operational report compiled. "
                f"Synthesized evidence from {len(chunks)} chunks and {len(events)} events."
            )

        # 2. Extract key findings (traceable bullet points mapping back to sources)
        key_findings = []
        for i, c in enumerate(chunks[:3]):
            source_info = f"{c['source']}:{c['metadata'].get('path') or 'doc'}"
            key_findings.append({
                "finding": f"Semantic overlap found in {c['source_type']}: '{c['content'][:150].strip()}...'",
                "source": source_info,
                "evidence_chunk_id": c["id"]
            })
            
        for pat in patterns[:2]:
            key_findings.append({
                "finding": f"Registered alert pattern: '{pat['name']}' ({pat['description']})",
                "source": "SQLite:patterns",
                "pattern_id": pat["pattern_id"]
            })

        # 3. Escalation path chronological mapping
        escalation_path = []
        for step in root_cause_analysis.get("chain", []):
            escalation_path.append({
                "event_id": step["event_id"],
                "title": step["title"],
                "timestamp": step["timestamp"],
                "type": step["event_type"]
            })

        # 4. Recurring issues mapping
        recurring_issues = []
        for pat in patterns:
            if pat["pattern_type"] == "recurring_incident":
                recurring_issues.append({
                    "issue_name": pat["name"],
                    "description": pat["description"],
                    "severity": pat["severity"],
                    "confidence": pat["confidence"]
                })

        # 5. Combined confidence score calculation
        confidence_score = (
            (query_classification["confidence"] * 0.3) + 
            (root_cause_analysis["confidence_score"] * 0.7)
        )
        
        confidence_explanation = (
            f"Confidence score {confidence_score:.2f} derived from query parsing match "
            f"({query_classification['confidence']:.2f}) and relational database correlation traces "
            f"({root_cause_analysis['confidence_score']:.2f})."
        )

        return {
            "summary": summary,
            "key_findings": key_findings,
            "escalation_path": escalation_path,
            "recurring_issues": recurring_issues,
            "confidence_score": round(confidence_score, 2),
            "confidence_explanation": confidence_explanation
        }
