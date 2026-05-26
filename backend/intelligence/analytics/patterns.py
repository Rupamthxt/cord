"""
backend/analytics/patterns.py
-----------------------------
Detects anomalies, temporal clusters, and recurring operational patterns
(like deployments followed by incidents) across events.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from backend.graph.entities.models import ChunkEntityRef, Entity
from backend.graph.events.models import Event, EventRelationship

logger = logging.getLogger(__name__)


class PatternDetector:
    """Analyzes PostgreSQL event store to detect temporal clusters, correlations, and bottlenecks."""

    async def detect_temporal_clusters(
        self,
        session: Any,
        workspace_id: str,
        window_hours: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """Cluster events that occurred close to each other in time."""
        try:
            # Get all events with timestamps, sorted chronologically
            stmt = (
                select(Event)
                .where(Event.workspace_id == workspace_id, Event.timestamp.isnot(None))
                .order_by(Event.timestamp.asc())
            )
            result = await session.execute(stmt)
            events = list(result.scalars().all())

            if not events:
                return []

            clusters: List[List[Event]] = []
            current_cluster: List[Event] = [events[0]]
            max_delta = timedelta(hours=window_hours)

            for ev in events[1:]:
                # If current event timestamp is within window of previous event
                prev_ev = current_cluster[-1]
                if ev.timestamp and prev_ev.timestamp:
                    if ev.timestamp - prev_ev.timestamp <= max_delta:
                        current_cluster.append(ev)
                    else:
                        clusters.append(current_cluster)
                        current_cluster = [ev]
                else:
                    current_cluster.append(ev)

            if current_cluster:
                clusters.append(current_cluster)

            # Enrich clusters with metadata and entities
            enriched_clusters: List[Dict[str, Any]] = []
            for idx, cluster in enumerate(clusters):
                if len(cluster) < 2:
                    continue  # Skip single-event clusters as they aren't patterns

                # Gather chunk ids
                chunk_ids = [e.source_chunk_id for e in cluster if e.source_chunk_id]
                entities: List[Dict[str, Any]] = []
                if chunk_ids:
                    ref_stmt = (
                        select(Entity.id, Entity.name, Entity.type)
                        .join(ChunkEntityRef, ChunkEntityRef.entity_id == Entity.id)
                        .where(ChunkEntityRef.chunk_id.in_(chunk_ids))
                        .distinct()
                    )
                    ref_result = await session.execute(ref_stmt)
                    entities = [
                        {"id": r[0], "name": r[1], "type": r[2]}
                        for r in ref_result.all()
                    ]

                start_t = cluster[0].timestamp
                end_t = cluster[-1].timestamp
                span_seconds = (end_t - start_t).total_seconds() if start_t and end_t else 0

                enriched_clusters.append({
                    "cluster_id": idx + 1,
                    "event_count": len(cluster),
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_seconds": span_seconds,
                    "events": [
                        {
                            "id": e.id,
                            "title": e.title,
                            "event_type": e.event_type,
                            "timestamp": e.timestamp,
                            "severity": e.severity,
                        }
                        for e in cluster
                    ],
                    "related_entities": entities,
                })

            # Sort clusters by size descending
            enriched_clusters.sort(key=lambda x: x["event_count"], reverse=True)
            return enriched_clusters

        except Exception as exc:
            logger.error("PatternDetector.detect_temporal_clusters failed: %s", exc, exc_info=True)
            raise

    async def detect_incident_frequencies(
        self,
        session: Any,
        workspace_id: str,
    ) -> List[Dict[str, Any]]:
        """Count how many incidents, outages, or performance issues are associated with entities."""
        try:
            # Query events that represent issues
            issue_types = {"incident", "outage", "performance_issue", "infrastructure_failure"}
            stmt = (
                select(Event.source_chunk_id, Event.event_type)
                .where(Event.workspace_id == workspace_id, Event.event_type.in_(issue_types))
            )
            result = await session.execute(stmt)
            issues = result.all()

            if not issues:
                return []

            chunk_to_issue_types: Dict[str, List[str]] = {}
            for chunk_id, ev_type in issues:
                if chunk_id not in chunk_to_issue_types:
                    chunk_to_issue_types[chunk_id] = []
                chunk_to_issue_types[chunk_id].append(ev_type)

            # Query entities linked to those chunks
            ref_stmt = (
                select(Entity.id, Entity.name, Entity.type, ChunkEntityRef.chunk_id)
                .join(ChunkEntityRef, ChunkEntityRef.entity_id == Entity.id)
                .where(ChunkEntityRef.chunk_id.in_(list(chunk_to_issue_types.keys())))
            )
            ref_result = await session.execute(ref_stmt)

            entity_stats: Dict[uuid.UUID, Dict[str, Any]] = {}
            for ent_id, ent_name, ent_type, chunk_id in ref_result.all():
                if ent_id not in entity_stats:
                    entity_stats[ent_id] = {
                        "id": ent_id,
                        "name": ent_name,
                        "type": ent_type,
                        "incident_count": 0,
                        "breakdown": {},
                    }

                # Add count for each issue type in this chunk
                for issue_type in chunk_to_issue_types.get(chunk_id, []):
                    entity_stats[ent_id]["incident_count"] += 1
                    entity_stats[ent_id]["breakdown"][issue_type] = (
                        entity_stats[ent_id]["breakdown"].get(issue_type, 0) + 1
                    )

            # Sort by frequency descending
            sorted_stats = list(entity_stats.values())
            sorted_stats.sort(key=lambda x: x["incident_count"], reverse=True)
            return sorted_stats

        except Exception as exc:
            logger.error("PatternDetector.detect_incident_frequencies failed: %s", exc, exc_info=True)
            raise

    async def detect_deployment_incidents(
        self,
        session: Any,
        workspace_id: str,
        threshold_minutes: float = 60.0,
    ) -> List[Dict[str, Any]]:
        """Correlate deployments with subsequent incidents or outages."""
        try:
            # Fetch deployments
            deploy_stmt = (
                select(Event)
                .where(Event.workspace_id == workspace_id, Event.event_type == "deployment", Event.timestamp.isnot(None))
                .order_by(Event.timestamp.asc())
            )
            deploy_res = await session.execute(deploy_stmt)
            deployments = list(deploy_res.scalars().all())

            # Fetch issues
            issue_types = {"incident", "outage", "performance_issue", "infrastructure_failure"}
            issue_stmt = (
                select(Event)
                .where(Event.workspace_id == workspace_id, Event.event_type.in_(issue_types), Event.timestamp.isnot(None))
                .order_by(Event.timestamp.asc())
            )
            issue_res = await session.execute(issue_stmt)
            issues = list(issue_res.scalars().all())

            correlations: List[Dict[str, Any]] = []
            delta_threshold = timedelta(minutes=threshold_minutes)

            for dep in deployments:
                for issue in issues:
                    if dep.timestamp and issue.timestamp:
                        # If issue occurred after deployment, but within the threshold
                        if dep.timestamp <= issue.timestamp <= dep.timestamp + delta_threshold:
                            delta_sec = (issue.timestamp - dep.timestamp).total_seconds()
                            correlations.append({
                                "deployment": {
                                    "id": dep.id,
                                    "title": dep.title,
                                    "timestamp": dep.timestamp,
                                },
                                "incident": {
                                    "id": issue.id,
                                    "title": issue.title,
                                    "event_type": issue.event_type,
                                    "timestamp": issue.timestamp,
                                    "severity": issue.severity,
                                },
                                "delay_seconds": delta_sec,
                                "delay_str": f"{int(delta_sec // 60)}m {int(delta_sec % 60)}s",
                            })

            return correlations

        except Exception as exc:
            logger.error("PatternDetector.detect_deployment_incidents failed: %s", exc, exc_info=True)
            raise

    async def analyze_patterns(
        self,
        session: Any,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Run all pattern analysis heuristics for the workspace."""
        temporal_clusters = await self.detect_temporal_clusters(session, workspace_id)
        incident_frequencies = await self.detect_incident_frequencies(session, workspace_id)
        deployment_incidents = await self.detect_deployment_incidents(session, workspace_id)

        return {
            "workspace_id": workspace_id,
            "temporal_clusters": temporal_clusters,
            "incident_frequencies": incident_frequencies,
            "deployment_incidents": deployment_incidents,
            "generated_at": datetime.now(timezone.utc),
        }


# Module singleton
pattern_detector = PatternDetector()
