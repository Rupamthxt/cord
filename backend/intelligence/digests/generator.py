"""
backend/digests/generator.py
----------------------------
Generates daily/weekly operational and engineering digests.
Formats Slack Block Kit payloads and HTML email templates with citations and evidence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from sqlalchemy import select

from backend.graph.events.models import Event
from backend.intelligence.insights.models import Insight
from backend.intelligence.workflows.models import Workflow

logger = logging.getLogger(__name__)


class DigestGenerator:
    """Compiles operational events, insights, and workflows into Slack and HTML Email formats."""

    async def _fetch_digest_data(
        self,
        session: Any,
        workspace_id: str,
        hours_lookback: int,
    ) -> Dict[str, List[Any]]:
        """Utility to fetch recent events, insights, and workflows for digest generation."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)

        # 1. Fetch events
        ev_stmt = select(Event).where(
            Event.workspace_id == workspace_id,
            Event.timestamp >= since,
        ).order_by(Event.timestamp.desc())
        ev_res = await session.execute(ev_stmt)
        events = list(ev_res.scalars().all())

        # 2. Fetch insights
        ins_stmt = select(Insight).where(
            Insight.workspace_id == workspace_id,
            Insight.generated_at >= since,
        ).order_by(Insight.generated_at.desc())
        ins_res = await session.execute(ins_stmt)
        insights = list(ins_res.scalars().all())

        # 3. Fetch active workflows (states: pending_review, blocked, in_progress, escalated)
        wf_stmt = select(Workflow).where(
            Workflow.workspace_id == workspace_id,
            Workflow.state.in_(["pending_review", "blocked", "in_progress", "escalated"]),
        ).order_by(Workflow.updated_at.desc())
        wf_res = await session.execute(wf_stmt)
        workflows = list(wf_res.scalars().all())

        return {"events": events, "insights": insights, "workflows": workflows}

    async def generate_slack_digest(
        self,
        session: Any,
        workspace_id: str,
        digest_type: str,
        hours_lookback: int = 24,
    ) -> Dict[str, Any]:
        """Generates a Slack Block Kit JSON payload representing the operational digest."""
        data = await self._fetch_digest_data(session, workspace_id, hours_lookback)
        events = data["events"]
        insights = data["insights"]
        workflows = data["workflows"]

        # Group count stats
        incidents_count = sum(1 for e in events if e.event_type in {"incident", "outage"})
        deploys_count = sum(1 for e in events if e.event_type == "deployment")
        anomalies_count = sum(1 for i in insights if i.insight_type == "anomaly")

        title_str = f"*{digest_type.replace('_', ' ').title()}* — Workspace: `{workspace_id}`"
        fallback_text = f"{digest_type.replace('_', ' ').title()} Digest: {incidents_count} incidents, {deploys_count} deploys, {anomalies_count} anomalies."

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Cord Operational Digest 🤖",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{title_str}\nPeriod: Past {hours_lookback} hours."
                }
            },
            {"type": "divider"}
        ]

        # Add Metrics Summary Block
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Incidents/Outages:* {incidents_count}"},
                {"type": "mrkdwn", "text": f"*Deployments:* {deploys_count}"},
                {"type": "mrkdwn", "text": f"*Active Blockers:* {len([w for w in workflows if w.state == 'blocked'])}"},
                {"type": "mrkdwn", "text": f"*Proactive Insights:* {len(insights)}"}
            ]
        })
        blocks.append({"type": "divider"})

        # Add Anomalies/Insights Block
        if insights:
            ins_text = "*🚨 Important Proactive Insights & Anomalies:*\n"
            for ins in insights[:3]:
                ins_text += f"• *[{ins.severity.upper()}]* {ins.title} — _(Confidence: {ins.confidence:.2f})_\n"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ins_text
                }
            })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• *No critical anomalies or volume spikes detected* during this window. ✅"
                }
            })

        # Add Active Workflows Block
        if workflows:
            wf_text = "*📋 Workflows Pending Attention:*\n"
            for wf in workflows[:3]:
                wf_text += f"• *[{wf.state.replace('_', ' ').upper()}]* _{wf.priority.upper()}_: {wf.title}\n"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": wf_text
                }
            })

        # Footer / Context Block
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} • Cord Supervised Operational Intelligence Engine."
                }
            ]
        })

        return {
            "text": fallback_text,
            "blocks": blocks
        }

    async def generate_email_digest(
        self,
        session: Any,
        workspace_id: str,
        digest_type: str,
        hours_lookback: int = 24,
    ) -> Dict[str, Any]:
        """Generates a fully styled HTML email digest with tables, timelines, and citations."""
        data = await self._fetch_digest_data(session, workspace_id, hours_lookback)
        events = data["events"]
        insights = data["insights"]
        workflows = data["workflows"]

        incidents = [e for e in events if e.event_type in {"incident", "outage"}]
        deployments = [e for e in events if e.event_type == "deployment"]

        subject = f"Cord Operational Report: {digest_type.replace('_', ' ').title()} - {workspace_id}"

        # Build HTML payload
        html = []
        html.append("<!DOCTYPE html><html><head>")
        html.append("<style>")
        html.append("body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333333; line-height: 1.6; margin: 0; padding: 20px; background-color: #f9f9f9; }")
        html.append(".container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }")
        html.append(".header { text-align: center; border-bottom: 2px solid #6366f1; padding-bottom: 15px; margin-bottom: 20px; }")
        html.append(".header h2 { color: #4f46e5; margin: 0; }")
        html.append(".metric-grid { display: flex; justify-content: space-between; margin-bottom: 25px; gap: 10px; }")
        html.append(".metric-card { flex: 1; text-align: center; background-color: #f3f4f6; border-radius: 6px; padding: 12px; border: 1px solid #e5e7eb; }")
        html.append(".metric-card h3 { margin: 0 0 5px 0; font-size: 24px; color: #4f46e5; }")
        html.append(".metric-card p { margin: 0; font-size: 12px; color: #6b7280; text-transform: uppercase; font-weight: bold; }")
        html.append(".section-title { font-size: 16px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; color: #111827; margin-top: 25px; margin-bottom: 12px; font-weight: bold; }")
        html.append("table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }")
        html.append("th, td { border-bottom: 1px solid #e5e7eb; padding: 10px; text-align: left; font-size: 13px; }")
        html.append("th { background-color: #f9fafb; font-weight: bold; color: #4b5563; }")
        html.append(".badge { display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: bold; border-radius: 4px; text-transform: uppercase; }")
        html.append(".badge-critical { background-color: #fee2e2; color: #991b1b; }")
        html.append(".badge-high { background-color: #ffedd5; color: #9a3412; }")
        html.append(".badge-medium { background-color: #f3f4f6; color: #374151; }")
        html.append(".timeline-item { border-left: 2px solid #e5e7eb; padding-left: 15px; margin-bottom: 15px; position: relative; }")
        html.append(".timeline-item::before { content: ''; position: absolute; left: -6px; top: 6px; width: 10px; height: 10px; background-color: #cbd5e1; border-radius: 50%; }")
        html.append(".footer { margin-top: 30px; font-size: 11px; text-align: center; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 15px; }")
        html.append("</style></head><body>")

        html.append("<div class='container'>")
        # Header
        html.append("<div class='header'>")
        html.append(f"<h2>Cord Operational Report</h2>")
        html.append(f"<p style='margin:5px 0 0 0; color:#6b7280; font-size:14px;'>{digest_type.replace('_', ' ').title()} Digest — {workspace_id}</p>")
        html.append("</div>")

        # Metric grid
        html.append("<div class='metric-grid'>")
        html.append(f"<div class='metric-card'><h3>{len(incidents)}</h3><p>Incidents</p></div>")
        html.append(f"<div class='metric-card'><h3>{len(deployments)}</h3><p>Deployments</p></div>")
        html.append(f"<div class='metric-card'><h3>{len(insights)}</h3><p>Insights</p></div>")
        html.append(f"<div class='metric-card'><h3>{len(workflows)}</h3><p>Workflows</p></div>")
        html.append("</div>")

        # Proactive Insights Table
        html.append("<div class='section-title'>Proactive Anomalies & Insights</div>")
        if insights:
            html.append("<table><thead><tr><th>Severity</th><th>Category</th><th>Title / Finding</th></tr></thead><tbody>")
            for ins in insights:
                sev_badge = f"<span class='badge badge-{ins.severity}'>{ins.severity}</span>"
                html.append(f"<tr><td>{sev_badge}</td><td>{ins.insight_type.replace('_', ' ')}</td><td><b>{ins.title}</b><br/><span style='font-size:12px; color:#6b7280;'>{ins.summary}</span></td></tr>")
            html.append("</tbody></table>")
        else:
            html.append("<p style='font-size:13px; color:#4b5563;'>No anomalies or bottlenecks identified in this lookback period.</p>")

        # Workflow state table
        html.append("<div class='section-title'>Supervised Coordination Workflows</div>")
        if workflows:
            html.append("<table><thead><tr><th>Priority</th><th>State</th><th>Workflow Title / Assignee</th></tr></thead><tbody>")
            for wf in workflows:
                priority_badge = f"<span class='badge badge-{wf.priority}'>{wf.priority}</span>"
                assignees = ", ".join([e.get("name", "unknown") for e in wf.assigned_entities])
                html.append(f"<tr><td>{priority_badge}</td><td><span class='badge badge-medium'>{wf.state}</span></td><td><b>{wf.title}</b><br/><span style='font-size:12px; color:#6b7280;'>Assignee: {assignees}</span></td></tr>")
            html.append("</tbody></table>")
        else:
            html.append("<p style='font-size:13px; color:#4b5563;'>All active workflows have been triaged or resolved.</p>")

        # Chronological timeline
        html.append("<div class='section-title'>Recent Operational Events Log</div>")
        if events:
            for ev in events[:5]:
                time_str = ev.timestamp.strftime("%Y-%m-%d %H:%M UTC") if ev.timestamp else "N/A"
                html.append(f"<div class='timeline-item'>")
                html.append(f"<span style='font-size:11px; color:#6b7280; font-weight:bold;'>{time_str} | {ev.event_type.upper()}</span><br/>")
                html.append(f"<span style='font-size:13px; font-weight:bold; color:#1f2937;'>{ev.title}</span>")
                if ev.description:
                    html.append(f"<br/><span style='font-size:12px; color:#4b5563;'>{ev.description}</span>")
                html.append("</div>")
        else:
            html.append("<p style='font-size:13px; color:#4b5563;'>No operational events logged during this window.</p>")

        # Footer
        html.append("<div class='footer'>")
        html.append(f"Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>")
        html.append("You are receiving this operational summary from Cord SRE Engine.")
        html.append("</div>")

        html.append("</div></body></html>")

        plain_text = f"Cord {digest_type.replace('_', ' ').title()} Digest for {workspace_id}. Incidents: {len(incidents)}. Deployments: {len(deployments)}. Active workflows: {len(workflows)}."

        return {
            "subject": subject,
            "html": "".join(html),
            "text": plain_text
        }


# Module singleton
digest_generator = DigestGenerator()
