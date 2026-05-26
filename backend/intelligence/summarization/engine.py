"""
backend/summarization/engine.py
------------------------------
Synthesizes structured operational summaries and root-cause hypotheses
from chronological timelines using the local Ollama LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.extraction.ollama_client import ollama_client
from backend.intelligence.timelines.builder import TimelineResponse

logger = logging.getLogger(__name__)

SUMMARIZATION_PROMPT = """\
You are an expert site reliability engineer (SRE) and operational intelligence analyst.
Analyze the following query and chronological timeline of operational events to synthesize a comprehensive, evidence-backed Markdown summary of the system's operational health.

────────────────────────────────────────────────────────────────────────────
USER QUERY: {query}
────────────────────────────────────────────────────────────────────────────
CHRONOLOGICAL TIMELINE:
{timeline_text}
────────────────────────────────────────────────────────────────────────────

Provide a professional, direct Markdown summary containing:
1. **Executive Summary**: 2-3 sentence overview of the health status during this window.
2. **Chronological Breakdown**: Highlight key events (deployments, incidents, escalations) and the exact time elapsed between them.
3. **Correlations & Root Cause Analysis**: Call out potential root causes (e.g., deployments followed by outages or spikes in latencies).
4. **Impacted Systems/Entities**: Identify which systems, databases, teams, or customers were affected.
5. **Recommended Actions**: Actionable next steps for remediation or investigation.

Do not include any conversational preambles (e.g., "Here is the summary:") or post-conversational notes. Start directly with the Markdown headings.
"""


class SummarizationEngine:
    """Summarizes operational event timelines using Ollama with a programmatic fallback."""

    async def summarize_timeline(
        self,
        query: str,
        timeline: TimelineResponse,
    ) -> str:
        """Generate a markdown summary of a timeline relative to a query."""
        if not timeline.events:
            return "No events or timeline data found for the specified criteria."

        # 1. Format timeline text for LLM context
        timeline_lines = []
        for idx, item in enumerate(timeline.events):
            ev = item.event
            delta_str = f" (+{item.time_since_previous_str} since prev)" if item.time_since_previous_str else ""
            ents_str = ", ".join([f"{ent['type']}:{ent['name']}" for ent in ev.entities])
            ents_suffix = f" [Entities: {ents_str}]" if ents_str else ""

            line = (
                f"[{idx + 1}] Time: {ev.timestamp or 'N/A'} | Type: {ev.event_type.upper()} | "
                f"Title: {ev.title} | Severity: {ev.severity or 'N/A'}{delta_str}{ents_suffix}\n"
                f"    Desc: {ev.description or 'No description'}"
            )
            timeline_lines.append(line)

        timeline_text = "\n".join(timeline_lines)

        # 2. Try LLM generation
        if await ollama_client.is_available():
            try:
                prompt = SUMMARIZATION_PROMPT.format(
                    query=query,
                    timeline_text=timeline_text,
                )
                logger.info("Generating operational summary via Ollama...")
                summary = await ollama_client.generate(prompt, temperature=0.2)
                if summary and summary.strip():
                    return summary.strip()
            except Exception as exc:
                logger.warning("Ollama summarization failed: %s. Using fallback.", exc)

        # 3. Heuristic Fallback
        return self._generate_fallback_summary(query, timeline)

    def _generate_fallback_summary(
        self,
        query: str,
        timeline: TimelineResponse,
    ) -> str:
        """Programmatic fallback summary when LLM is unavailable."""
        logger.info("Generating fallback programmatic summary.")
        total_events = len(timeline.events)

        # Group by type and severity
        type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        affected_entities: Set[str] = set()

        for item in timeline.events:
            ev = item.event
            type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1
            if ev.severity:
                severity_counts[ev.severity] = severity_counts.get(ev.severity, 0) + 1
            for ent in ev.entities:
                affected_entities.add(f"{ent['name']} ({ent['type']})")

        # Detect deployment-incident correlations
        correlations = []
        prev_dep = None
        for item in timeline.events:
            ev = item.event
            if ev.event_type == "deployment":
                prev_dep = ev
            elif ev.event_type in {"incident", "outage"} and prev_dep:
                # If they both have timestamp
                if ev.timestamp and prev_dep.timestamp:
                    diff = (ev.timestamp - prev_dep.timestamp).total_seconds()
                    if 0 < diff <= 3600:
                        correlations.append(
                            f"- Outage/Incident *\"{ev.title}\"* occurred within {int(diff // 60)} minutes of Deployment *\"{prev_dep.title}\"*"
                        )

        # Build markdown report
        md = []
        md.append("# Operational Health Summary (Heuristic Fallback)")
        md.append(f"**Query**: {query}\n")

        md.append("## Executive Summary")
        md.append(
            f"The analyzed timeline contains **{total_events} operational events** within this scope. "
            f"The primary categories detected were: "
            + ", ".join([f"{k} ({v})" for k, v in type_counts.items()])
            + "."
        )

        if severity_counts.get("critical", 0) > 0 or severity_counts.get("high", 0) > 0:
            md.append(
                "⚠️ **Warning**: The timeline contains high-severity issues (critical: "
                f"{severity_counts.get('critical', 0)}, high: {severity_counts.get('high', 0)}). Immediate attention is required."
            )
        else:
            md.append("✅ **Status**: No critical or high-severity incidents detected in this window.")

        if correlations:
            md.append("\n## Correlation & Risk Observations")
            md.append("The system detected potential sequence relationships between events:")
            md.extend(correlations)

        if affected_entities:
            md.append("\n## Impacted System Entities")
            md.append("The following organizational entities are linked to these events:")
            for ent in sorted(affected_entities):
                md.append(f"- {ent}")

        md.append("\n## Chronological Log")
        for item in timeline.events:
            ev = item.event
            time_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S") if ev.timestamp else "N/A"
            sev_str = f" [{ev.severity.upper()}]" if ev.severity else ""
            md.append(f"- **{time_str}** | **{ev.event_type.upper()}**{sev_str} — *{ev.title}*")
            if ev.description:
                md.append(f"  * {ev.description}")

        return "\n".join(md)

    async def generate_evidence_backed_summary(
        self,
        query: str,
        timeline_data: Any,
        related_insights: List[Any],
    ) -> Dict[str, Any]:
        """Generates a traceable, evidence-backed operational report summary."""
        # 1. Convert timeline data to TimelineResponse if dict
        if isinstance(timeline_data, dict):
            from backend.intelligence.timelines.builder import TimelineResponse
            timeline = TimelineResponse.model_validate(timeline_data)
        else:
            timeline = timeline_data

        # 2. Generate narrative summary string
        summary_str = await self.summarize_timeline(query, timeline)

        # 3. Extract key findings and supporting evidence
        key_findings = []
        supporting_evidence = []
        related_entities = []
        related_events = []

        seen_entities = set()
        seen_events = set()

        # Extract from timeline events
        for item in timeline.events:
            ev = item.event
            event_ref = {"id": str(ev.id), "title": ev.title, "event_type": ev.event_type}
            if str(ev.id) not in seen_events:
                seen_events.add(str(ev.id))
                related_events.append(event_ref)

            # Add entities
            for ent in ev.entities:
                ent_id = ent.get("id")
                if ent_id and str(ent_id) not in seen_entities:
                    seen_entities.add(str(ent_id))
                    related_entities.append({"id": str(ent_id), "name": ent["name"], "type": ent["type"]})

            # Add to evidence citations
            if ev.description:
                supporting_evidence.append(f"Event: {ev.title} - {ev.description}")

        # Extract from insights
        for ins in related_insights:
            # support dict or read models
            ins_id = getattr(ins, "id", None) or ins.get("id")
            ins_title = getattr(ins, "title", None) or ins.get("title")
            ins_summary = getattr(ins, "summary", None) or ins.get("summary")
            ins_type = getattr(ins, "insight_type", None) or ins.get("insight_type")
            ins_evidence = getattr(ins, "evidence", None) or ins.get("evidence", [])

            key_findings.append({
                "finding": f"[{ins_type.upper()}] {ins_title}",
                "source_id": str(ins_id) if ins_id else None,
            })

            if ins_summary:
                supporting_evidence.append(f"Insight: {ins_title} - {ins_summary}")

            for ev in getattr(ins, "supporting_events", []) or ins.get("supporting_events", []):
                ev_id = ev.get("id")
                if ev_id and str(ev_id) not in seen_events:
                    seen_events.add(str(ev_id))
                    related_events.append(ev)

            for ent in getattr(ins, "supporting_entities", []) or ins.get("supporting_entities", []):
                ent_id = ent.get("id")
                if ent_id and str(ent_id) not in seen_entities:
                    seen_entities.add(str(ent_id))
                    related_entities.append(ent)

            if ins_evidence:
                supporting_evidence.extend(ins_evidence)

        # 4. Calculate confidence
        confidence_vals = [item.event.confidence for item in timeline.events]
        for ins in related_insights:
            confidence_vals.append(getattr(ins, "confidence", None) or ins.get("confidence", 0.8))

        avg_confidence = sum(confidence_vals) / len(confidence_vals) if confidence_vals else 0.8

        return {
            "summary": summary_str,
            "key_findings": key_findings,
            "supporting_evidence": list(set(supporting_evidence))[:15],  # cap at 15 items
            "related_entities": related_entities,
            "related_events": related_events,
            "confidence": round(avg_confidence, 2),
        }


# Module singleton
summarization_engine = SummarizationEngine()
