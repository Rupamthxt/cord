"""
backend/insights/generator.py
-----------------------------
Proactive insight generation engine for operational intelligence.
Synthesizes entity co-occurrences, incident groups, and workflow escalations into
traceable insights.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from backend.graph.entities.models import ChunkEntityRef, Entity
from backend.graph.events.models import Event, EventRelationship
from backend.extraction.ollama_client import ollama_client
from backend.intelligence.insights.schema import InsightCreate
from backend.intelligence.insights.store import insight_store

logger = logging.getLogger(__name__)

INSIGHT_PROMPT_TEMPLATE = """\
You are an expert SRE and operational intelligence analyst.
Analyze the following operational patterns and event logs to write a narrative operational summary.

────────────────────────────────────────────────────────────────────────────
ANALYSIS CATEGORY: {category}
────────────────────────────────────────────────────────────────────────────
AFFECTED ENTITY: {entity_name} ({entity_type})
────────────────────────────────────────────────────────────────────────────
OPERATIONAL LOGS:
{logs_text}
────────────────────────────────────────────────────────────────────────────

Provide a professional, concise response containing:
1. **Title**: A single action-oriented summary sentence (e.g. "Frequent database connection failures bottlenecking Service A").
2. **Narrative Summary**: A 2-3 sentence explanation of the pattern, potential causes, and direct evidence from the logs.
3. **Evidence Citations**: Mention dates and titles of specific events.

Output ONLY a JSON block matching this structure. Do NOT include markdown fences, comments, or extra text:
{{
  "title": "Action-oriented title",
  "summary": "Narrative explanation of the bottleneck or blocker with citations."
}}
"""


class InsightGenerator:
    """Proactively synthesizes timelines and entity graphs to generate traceable insights."""

    async def generate_proactive_insights(
        self,
        session: Any,
        workspace_id: str,
    ) -> List[Any]:
        """Scans the event store and entity graph to generate recurring bottlenecks and blockers."""
        generated_insights = []
        try:
            now = datetime.now(timezone.utc)
            lookback = now - timedelta(days=14)

            # 1. Fetch recent events and map them to entities
            stmt = select(Event).where(
                Event.workspace_id == workspace_id,
                Event.timestamp >= lookback,
            )
            res = await session.execute(stmt)
            events = list(res.scalars().all())

            if len(events) < 2:
                return []

            # Map event IDs/chunk IDs to events
            chunk_to_events: Dict[str, List[Event]] = {}
            for e in events:
                if e.source_chunk_id:
                    chunk_to_events.setdefault(e.source_chunk_id, []).append(e)

            # 2. Get entities linked to these events
            chunk_ids = list(chunk_to_events.keys())
            entity_to_events: Dict[Tuple[str, str, str], List[Event]] = {}

            if chunk_ids:
                ref_stmt = (
                    select(Entity.id, Entity.name, Entity.type, ChunkEntityRef.chunk_id)
                    .join(ChunkEntityRef, ChunkEntityRef.entity_id == Entity.id)
                    .where(ChunkEntityRef.chunk_id.in_(chunk_ids))
                )
                ref_res = await session.execute(ref_stmt)
                for ent_id, name, ent_type, chunk_id in ref_res.all():
                    key = (str(ent_id), name, ent_type)
                    entity_to_events.setdefault(key, [])
                    entity_to_events[key].extend(chunk_to_events[chunk_id])

            # 3. Analyze each entity for bottlenecks (e.g. associated with >= 2 incidents/outages)
            for (ent_id, name, ent_type), linked in entity_to_events.items():
                issues = [e for e in linked if e.event_type in {"incident", "outage", "performance_issue"}]
                
                if len(issues) >= 2:
                    # Synthesize insight for this entity
                    logs_lines = []
                    supporting_events = []
                    for idx, issue in enumerate(issues):
                        logs_lines.append(
                            f"[{idx+1}] {issue.timestamp.strftime('%Y-%m-%d') if issue.timestamp else 'N/A'} - {issue.event_type.upper()} - {issue.title}"
                        )
                        supporting_events.append({
                            "id": str(issue.id),
                            "title": issue.title,
                            "timestamp": issue.timestamp.isoformat() if issue.timestamp else None,
                        })

                    logs_text = "\n".join(logs_lines)
                    category = "recurring_bottleneck"
                    
                    title = f"Recurring operational bottleneck detected on {name}"
                    summary = f"Entity '{name}' ({ent_type}) was associated with {len(issues)} operational issue events in the last 14 days, including: " + ", ".join([f"'{i.title}'" for i in issues[:3]]) + "."
                    evidence = [f"Linked issue events count: {len(issues)}"]

                    # Attempt LLM synthesis
                    if await ollama_client.is_available():
                        try:
                            prompt = INSIGHT_PROMPT_TEMPLATE.format(
                                category=category,
                                entity_name=name,
                                entity_type=ent_type,
                                logs_text=logs_text,
                            )
                            response = await ollama_client.generate(prompt, temperature=0.0)
                            import json
                            import re
                            # Clean response and parse json
                            match = re.search(r"(\{.*\})", response.strip(), re.DOTALL)
                            if match:
                                parsed = json.loads(match.group(1))
                                if "title" in parsed and "summary" in parsed:
                                    title = parsed["title"]
                                    summary = parsed["summary"]
                        except Exception as exc:
                            logger.warning("LLM insight synthesis failed for %s: %s. Falling back to programmatic.", name, exc)

                    payload = InsightCreate(
                        title=title,
                        summary=summary,
                        insight_type=category,
                        confidence=0.8,
                        severity="high" if any(i.event_type == "outage" for i in issues) else "medium",
                        supporting_entities=[{"id": ent_id, "name": name, "type": ent_type}],
                        supporting_events=supporting_events,
                        evidence=evidence,
                        workspace_id=workspace_id,
                        metadata={"recurring_issues_count": len(issues)},
                    )

                    insight, _ = await insight_store.upsert_insight(session, payload)
                    generated_insights.append(insight)

            logger.info("Proactive insight generation complete. Synthesized %d insights.", len(generated_insights))
            return generated_insights

        except Exception as exc:
            logger.error("InsightGenerator.generate_proactive_insights failed: %s", exc, exc_info=True)
            return []


# Module singleton
insight_generator = InsightGenerator()
