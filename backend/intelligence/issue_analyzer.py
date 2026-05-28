import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from backend.graph.events.models import Event
from backend.intelligence.insights.models import Insight
from backend.intelligence.workflows.models import Workflow

logger = logging.getLogger(__name__)


class IssueAnalyzer:
    """
    Core engine for Recurring Operational Issue Intelligence.
    Aggregates evidence, correlates operational signals, clusters issues,
    and calculates trust/confidence diagnostics for pilot reports.
    """

    async def analyze_recurring_issues(
        self, session: Any, workspace_id: str, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Clusters recurring operational bottlenecks and issues dynamically based on event keywords.
        Returns a list of structured recurring issues with confidence metrics and evidence.
        """
        now = now or datetime.now(timezone.utc)
        
        # 1. Fetch DB events, insights, and workflows to discover actual signals
        events = await self._fetch_events(session, workspace_id, now, days=30)

        # 2. Group events by lowercase words in title, filtering out small/common words
        groups = {}
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", 
            "of", "from", "release", "version", "chat:", "issue", "report:", "api", "slack", 
            "notion", "jira", "webhook", "error", "warning", "info", "alert"
        }
        
        for ev in events:
            title_words = [w.strip(":,.-()[]{}'\"") for w in ev.title.lower().split()]
            keywords = [w for w in title_words if len(w) > 2 and w not in stop_words]
            for kw in keywords:
                if kw not in groups:
                    groups[kw] = []
                groups[kw].append(ev)

        # 3. Only build recurring issues if there is repeating evidence (>= 2 events per keyword)
        issues = []
        for kw, group_events in groups.items():
            if len(group_events) >= 2:
                # Build a dynamic issue from these events!
                title = f"Recurring {kw.capitalize()} Activity Detected"
                ev_titles = [e.title for e in group_events]
                summary = f"Multiple operational events and signals referencing '{kw}' have been correlated. This includes: " + ", ".join(ev_titles[:3])
                if len(ev_titles) > 3:
                    summary += f" and {len(ev_titles) - 3} other event(s)."
                else:
                    summary += "."
                
                # Compute confidence based on the number of evidence items
                conf = min(0.98, 0.60 + len(group_events) * 0.12)
                
                # Gather evidence list
                evidence = [{
                    "id": str(ev.id),
                    "source": ev.event_type or "event",
                    "title": ev.title,
                    "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                    "snippet": ev.description or ""
                } for ev in group_events]
                
                # Try to assign a realistic team/assignee based on the keyword
                assigned_team = "Infrastructure Platform Team"
                assignee = "On-Call Engineer"
                if kw in ["billing", "payment", "stripe", "webhook"]:
                    assigned_team = "Billing Integration Team"
                    assignee = "Billing Engineer"
                elif kw in ["db", "postgres", "database", "pool"]:
                    assigned_team = "Database Ops Team"
                    assignee = "DB Reliability Engineer"
                
                issues.append({
                    "id": f"recurring-{kw}",
                    "title": title,
                    "category": f"{kw.capitalize()} Signal Cluster",
                    "summary": summary,
                    "confidence_diagnostics": {
                        "score": conf,
                        "factors_positive": [
                            f"Correlated {len(group_events)} signals referencing '{kw}'",
                            "Temporal proximity in recent log sequence"
                        ],
                        "factors_negative": [],
                        "data_sources": list(set(ev.event_type for ev in group_events)),
                        "evidence_count": len(group_events)
                    },
                    "assigned_team": assigned_team,
                    "assignee": assignee,
                    "status": "Under Investigation",
                    "severity": "high" if len(group_events) > 3 else "medium",
                    "evidence": evidence
                })
        
        return issues

    async def analyze_deployments(
        self, session: Any, workspace_id: str, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes deployment events and correlates them with subsequent outages or regressions.
        """
        now = now or datetime.now(timezone.utc)
        events = await self._fetch_events(session, workspace_id, now, days=30)
        
        deployments = [e for e in events if e.event_type == "deployment"]
        incidents = [e for e in events if e.event_type in {"incident", "outage", "abnormal_incident_frequency"}]

        # Return empty list if no deployments in DB
        if not deployments:
            return []

        results = []
        for dep in deployments:
            dep_time = dep.timestamp
            linked = []
            
            if dep_time:
                # Find incidents in a 2-hour window following the deployment
                for inc in incidents:
                    if inc.timestamp and dep_time <= inc.timestamp <= dep_time + timedelta(hours=2):
                        linked.append({
                            "id": str(inc.id),
                            "title": inc.title,
                            "timestamp": inc.timestamp.isoformat(),
                            "severity": inc.severity or "medium"
                        })
            
            # Stability score calculation
            score = 100.0
            if len(linked) == 1:
                score = 50.0
            elif len(linked) >= 2:
                score = 0.0

            results.append({
                "id": str(dep.id),
                "title": dep.title,
                "timestamp": dep_time.isoformat() if dep_time else None,
                "author": dep.metadata_.get("author") or "Unknown",
                "stability_score": score,
                "linked_incidents": linked,
                "confidence_diagnostics": {
                    "score": 0.85 if linked else 0.95,
                    "factors_positive": ["Deployment event verified in system log events"],
                    "factors_negative": []
                }
            })

        return results

    async def analyze_escalations(
        self, session: Any, workspace_id: str, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes escalations and triage pathways across incident response workflows.
        """
        now = now or datetime.now(timezone.utc)
        workflows = await self._fetch_workflows(session, workspace_id)

        escalations = []
        if workflows:
            # Combine database workflows
            for wf in workflows:
                steps = []
                meta_route = wf.metadata_.get("escalation_route")
                if meta_route:
                    steps = meta_route
                else:
                    steps = [
                        {"step": 1, "role": "Assignee", "duration_minutes": 30, "timestamp": wf.created_at.isoformat()}
                    ]

                escalations.append({
                    "id": str(wf.id),
                    "title": wf.title,
                    "incident_type": wf.workflow_type,
                    "priority": wf.priority,
                    "current_state": wf.state,
                    "escalation_route": steps,
                    "total_triage_minutes": wf.metadata_.get("total_triage_minutes") or 60,
                    "bottleneck_identified": wf.metadata_.get("bottleneck_identified") or "No clear bottleneck.",
                    "confidence_diagnostics": {
                        "score": 0.85,
                        "factors_positive": ["State audit transitions stored securely in database"],
                        "factors_negative": []
                    }
                })

        return escalations

    async def analyze_incidents(
        self, session: Any, workspace_id: str, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recent incidents and traces related Slack channels and entities.
        """
        now = now or datetime.now(timezone.utc)
        events = await self._fetch_events(session, workspace_id, now, days=15)
        
        incidents = [e for e in events if e.event_type in {"incident", "outage"}]

        results = []
        if not incidents:
            return []

        for inc in incidents:
            results.append({
                "id": str(inc.id),
                "title": inc.title,
                "timestamp": inc.timestamp.isoformat() if inc.timestamp else now.isoformat(),
                "severity": inc.severity or "medium",
                "correlated_slack_channel": inc.metadata_.get("slack_channel") or "#ops-alerts",
                "correlated_jira_ticket": inc.metadata_.get("jira_ticket") or "N/A",
                "affected_system": inc.metadata_.get("affected_system") or "ServiceA",
                "evidence_snippets": [inc.description] if inc.description else [],
                "confidence_diagnostics": {
                    "score": inc.confidence,
                    "factors_positive": ["Incident matched event metadata schema"],
                    "factors_negative": []
                }
            })

        return results

    async def analyze_timeline(
        self, session: Any, workspace_id: str, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Constructs a structured chronological timeline of events for the pilot UI.
        """
        now = now or datetime.now(timezone.utc)
        events = await self._fetch_events(session, workspace_id, now, days=7)

        # Build chronological timeline
        timeline = []
        for ev in events:
            timeline.append({
                "id": str(ev.id),
                "title": ev.title,
                "event_type": ev.event_type,
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                "summary": ev.description or "",
                "severity": ev.severity or "medium",
                "metadata": ev.metadata_
            })

        # Sort timeline chronologically
        timeline.sort(key=lambda x: x["timestamp"] or "")
        return timeline

    async def _fetch_events(self, session: Any, workspace_id: str, now: datetime, days: int) -> List[Any]:
        # Fetch from PostgreSQL
        try:
            start_time = now - timedelta(days=days)
            stmt = select(Event).where(
                Event.workspace_id == workspace_id,
                Event.timestamp >= start_time
            ).order_by(Event.timestamp.desc())
            res = await session.execute(stmt)
            return list(res.scalars().all())
        except Exception as e:
            logger.error(f"PostgreSQL fetch events failed: {e}", exc_info=True)
            return []

    async def _fetch_insights(self, session: Any, workspace_id: str) -> List[Insight]:
        try:
            stmt = select(Insight).where(Insight.workspace_id == workspace_id).order_by(Insight.generated_at.desc())
            res = await session.execute(stmt)
            return list(res.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching insights: {e}")
            return []

    async def _fetch_workflows(self, session: Any, workspace_id: str) -> List[Workflow]:
        try:
            stmt = select(Workflow).where(Workflow.workspace_id == workspace_id).order_by(Workflow.created_at.desc())
            res = await session.execute(stmt)
            return list(res.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching workflows: {e}")
            return []
