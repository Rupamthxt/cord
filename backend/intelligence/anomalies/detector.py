"""
backend/anomalies/detector.py
----------------------------
Statistical anomaly and instability detection engine for operational events.
Calculates historical baseline metrics, rolling averages, and threshold spikes.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from backend.graph.entities.models import ChunkEntityRef, Entity
from backend.graph.events.models import Event
from backend.intelligence.insights.schema import InsightCreate
from backend.intelligence.insights.store import insight_store

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects volume spikes, deployment instabilities, and escalation anomalies."""

    async def detect_volume_spikes(
        self,
        session: Any,
        workspace_id: str,
        window_days: int = 7,
        now: Optional[datetime] = None,
    ) -> List[InsightCreate]:
        """Compares daily event frequency in the target window vs. historical baseline."""
        insights = []
        try:
            now = now or datetime.now(timezone.utc)
            history_start = now - timedelta(days=30)
            baseline_end = now - timedelta(days=window_days)

            # Query all events in the last 30 days
            stmt = select(Event).where(
                Event.workspace_id == workspace_id,
                Event.timestamp >= history_start,
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                return []

            # Group event timestamps by event_type and day
            # Format: { event_type: { date_str: count } }
            type_daily_counts: Dict[str, Dict[str, int]] = {}
            for ev in events:
                if not ev.timestamp:
                    continue
                ev_type = ev.event_type
                day_str = ev.timestamp.strftime("%Y-%m-%d")

                type_daily_counts.setdefault(ev_type, {})
                type_daily_counts[ev_type][day_str] = type_daily_counts[ev_type].get(day_str, 0) + 1

            # Analyse each event type for spikes
            for ev_type, daily_map in type_daily_counts.items():
                # Split days into baseline (days -30 to -7) and target (last 7 days)
                baseline_counts: List[int] = []
                target_counts: List[int] = []

                for day_offset in range(30):
                    day_dt = now - timedelta(days=day_offset)
                    day_str = day_dt.strftime("%Y-%m-%d")
                    count = daily_map.get(day_str, 0)

                    if day_dt < baseline_end:
                        baseline_counts.append(count)
                    else:
                        target_counts.append(count)

                if not baseline_counts:
                    continue

                # Calculate baseline mean and standard deviation
                n_baseline = len(baseline_counts)
                mean_baseline = sum(baseline_counts) / n_baseline
                
                # Standard deviation
                variance = sum((x - mean_baseline) ** 2 for x in baseline_counts) / n_baseline
                std_baseline = math.sqrt(variance)

                # Calculate target window mean (rolling average)
                mean_target = sum(target_counts) / len(target_counts)

                # Threshold: mean_target exceeds baseline by 2 standard deviations
                # If std dev is 0, check if target count is at least 3x baseline and >= 1.5 daily
                has_spike = False
                reason = ""
                if std_baseline > 0:
                    z_score = (mean_target - mean_baseline) / std_baseline
                    if z_score >= 2.0 and mean_target > 0.5:
                        has_spike = True
                        reason = f"rolling average is {z_score:.1f} standard deviations above historical baseline ({mean_target:.2f} vs. {mean_baseline:.2f} daily)"
                else:
                    if mean_target > mean_baseline * 3 and mean_target >= 1.5:
                        has_spike = True
                        reason = f"rolling average increased {mean_target/max(mean_baseline, 0.1):.1f}x over baseline ({mean_target:.2f} vs. {mean_baseline:.2f} daily)"

                if has_spike:
                    # Collect supporting events from target window
                    target_events = [
                        {
                            "id": str(e.id),
                            "title": e.title,
                            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                        }
                        for e in events
                        if e.event_type == ev_type and e.timestamp and e.timestamp >= baseline_end
                    ]

                    # Retrieve entities linked to these events' chunks
                    chunk_ids = [e.source_chunk_id for e in events if e.event_type == ev_type and e.timestamp and e.timestamp >= baseline_end]
                    supporting_entities = []
                    if chunk_ids:
                        ent_stmt = (
                            select(Entity.id, Entity.name, Entity.type)
                            .join(ChunkEntityRef, ChunkEntityRef.entity_id == Entity.id)
                            .where(ChunkEntityRef.chunk_id.in_(chunk_ids))
                            .distinct()
                        )
                        ent_res = await session.execute(ent_stmt)
                        supporting_entities = [
                            {"id": str(r[0]), "name": r[1], "type": r[2]}
                            for r in ent_res.all()
                        ]

                    insight_type = "support_spike" if ev_type in {"support_spike", "customer_complaint"} else "anomaly"
                    title = f"Abnormal volume spike in {ev_type} events"
                    summary = f"The system detected an abnormal increase in '{ev_type}' events. The current {reason}."
                    
                    insights.append(
                        InsightCreate(
                            title=title,
                            summary=summary,
                            insight_type=insight_type,
                            confidence=0.85,
                            severity="high" if ev_type in {"outage", "incident", "security_event"} else "medium",
                            supporting_entities=supporting_entities,
                            supporting_events=target_events,
                            evidence=[f"Baseline daily rate: {mean_baseline:.2f}", f"Target window daily rate: {mean_target:.2f}"],
                            workspace_id=workspace_id,
                            metadata={"baseline_days": 23, "target_days": window_days},
                        )
                    )

            return insights
        except Exception as exc:
            logger.error("AnomalyDetector.detect_volume_spikes failed: %s", exc, exc_info=True)
            return []

    async def detect_instability_patterns(
        self,
        session: Any,
        workspace_id: str,
        now: Optional[datetime] = None,
    ) -> List[InsightCreate]:
        """Detects sequence anomalies such as deployments followed by multiple outages."""
        insights = []
        try:
            now = now or datetime.now(timezone.utc)
            lookback = now - timedelta(days=7)

            # Query all deployment and incident/outage events in the last 7 days
            stmt = (
                select(Event)
                .where(
                    Event.workspace_id == workspace_id,
                    Event.timestamp >= lookback,
                )
                .order_by(Event.timestamp.asc())
            )
            result = await session.execute(stmt)
            events = list(result.scalars().all())

            deployments = [e for e in events if e.event_type == "deployment"]
            issues = [e for e in events if e.event_type in {"incident", "outage", "performance_issue", "infrastructure_failure"}]

            for dep in deployments:
                if not dep.timestamp:
                    continue
                # Look for issue events occurring within 2 hours after the deployment
                linked_issues = []
                for issue in issues:
                    if issue.timestamp and dep.timestamp <= issue.timestamp <= dep.timestamp + timedelta(hours=2):
                        linked_issues.append(issue)

                if len(linked_issues) >= 2:
                    # Flag deployment instability!
                    supporting_events = [
                        {
                            "id": str(dep.id),
                            "title": dep.title,
                            "timestamp": dep.timestamp.isoformat(),
                            "event_type": dep.event_type,
                        }
                    ] + [
                        {
                            "id": str(i.id),
                            "title": i.title,
                            "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                            "event_type": i.event_type,
                        }
                        for i in linked_issues
                    ]

                    # Retrieve associated entities
                    chunk_ids = [dep.source_chunk_id] + [i.source_chunk_id for i in linked_issues if i.source_chunk_id]
                    supporting_entities = []
                    if chunk_ids:
                        ent_stmt = (
                            select(Entity.id, Entity.name, Entity.type)
                            .join(ChunkEntityRef, ChunkEntityRef.entity_id == Entity.id)
                            .where(ChunkEntityRef.chunk_id.in_(chunk_ids))
                            .distinct()
                        )
                        ent_res = await session.execute(ent_stmt)
                        supporting_entities = [
                            {"id": str(r[0]), "name": r[1], "type": r[2]}
                            for r in ent_res.all()
                        ]

                    insights.append(
                        InsightCreate(
                            title=f"Deployment instability detected following release '{dep.title}'",
                            summary=f"Deployment '{dep.title}' was followed by {len(linked_issues)} incident events within a 2-hour window, indicating potential release regression or DB saturation.",
                            insight_type="deployment_instability",
                            confidence=0.9,
                            severity="critical" if any(i.event_type == "outage" or i.severity == "critical" for i in linked_issues) else "high",
                            supporting_entities=supporting_entities,
                            supporting_events=supporting_events,
                            evidence=[
                                f"Deployment timestamp: {dep.timestamp.isoformat()}",
                                f"Subsequent incidents count: {len(linked_issues)}",
                            ],
                            workspace_id=workspace_id,
                            metadata={"deployment_event_id": str(dep.id)},
                        )
                    )

            return insights
        except Exception as exc:
            logger.error("AnomalyDetector.detect_instability_patterns failed: %s", exc, exc_info=True)
            return []

    async def run_detection(
        self,
        session: Any,
        workspace_id: str,
        now: Optional[datetime] = None,
    ) -> List[Any]:
        """Runs all detectors, saves them to PostgreSQL, and returns the persisted insights."""
        logger.info("Running proactive operational anomaly detection...")
        spikes = await self.detect_volume_spikes(session, workspace_id, now=now)
        regressions = await self.detect_instability_patterns(session, workspace_id, now=now)

        persisted = []
        for p in (spikes + regressions):
            insight, _ = await insight_store.upsert_insight(session, p)
            persisted.append(insight)

        logger.info("Anomaly detection run complete. Generated %d insights.", len(persisted))
        return persisted


# Module-level singleton
anomaly_detector = AnomalyDetector()
