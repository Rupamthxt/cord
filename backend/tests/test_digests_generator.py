"""
Tests for daily and weekly Slack/Email digests.
Covers: Slack Block Kit structures, HTML email styling, and metric compilation.

Run with: python -m unittest backend/tests/test_digests_generator.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.digests.generator import DigestGenerator


class TestDigestsGenerator(unittest.IsolatedAsyncioTestCase):
    """Tests for the DigestGenerator class."""

    def setUp(self):
        self.generator = DigestGenerator()
        self.workspace_id = "default_workspace"

    async def test_generate_slack_digest(self):
        session = AsyncMock()

        # Mock database items fetched for digest
        mock_event = MagicMock()
        mock_event.event_type = "incident"
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_event.title = "PostgreSQL saturating"
        mock_event.description = "Connection pool exhausted"
        mock_event.workspace_id = self.workspace_id

        mock_insight = MagicMock()
        mock_insight.insight_type = "anomaly"
        mock_insight.generated_at = datetime.now(timezone.utc)
        mock_insight.title = "Volume spike detected"
        mock_insight.summary = "A lot of incidents lately"
        mock_insight.severity = "high"
        mock_insight.confidence = 0.88
        mock_insight.workspace_id = self.workspace_id

        mock_wf = MagicMock()
        mock_wf.state = "blocked"
        mock_wf.priority = "critical"
        mock_wf.title = "Incident DB Triage"
        mock_wf.workspace_id = self.workspace_id

        mock_res_ev = MagicMock()
        mock_res_ev.scalars.return_value.all.return_value = [mock_event]
        
        mock_res_ins = MagicMock()
        mock_res_ins.scalars.return_value.all.return_value = [mock_insight]
        
        mock_res_wf = MagicMock()
        mock_res_wf.scalars.return_value.all.return_value = [mock_wf]

        session.execute.side_effect = [mock_res_ev, mock_res_ins, mock_res_wf]

        digest = await self.generator.generate_slack_digest(
            session=session,
            workspace_id=self.workspace_id,
            digest_type="daily_digest",
            hours_lookback=24,
        )

        self.assertIn("text", digest)
        self.assertIn("blocks", digest)
        self.assertGreaterEqual(len(digest["blocks"]), 4)
        
        # Verify headers/metrics in Block Kit
        header_text = digest["blocks"][0]["text"]["text"]
        self.assertEqual(header_text, "Cord Operational Digest 🤖")

        fields = digest["blocks"][3]["fields"]
        self.assertEqual(fields[0]["text"], "*Incidents/Outages:* 1")
        self.assertEqual(fields[1]["text"], "*Deployments:* 0")
        self.assertEqual(fields[2]["text"], "*Active Blockers:* 1")

    async def test_generate_email_digest(self):
        session = AsyncMock()

        # Mock database items
        mock_event = MagicMock()
        mock_event.event_type = "incident"
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_event.title = "PostgreSQL saturating"
        mock_event.description = "Connection pool exhausted"
        mock_event.workspace_id = self.workspace_id

        mock_insight = MagicMock()
        mock_insight.insight_type = "anomaly"
        mock_insight.generated_at = datetime.now(timezone.utc)
        mock_insight.title = "Volume spike detected"
        mock_insight.summary = "A lot of incidents lately"
        mock_insight.severity = "high"
        mock_insight.confidence = 0.88
        mock_insight.workspace_id = self.workspace_id

        mock_wf = MagicMock()
        mock_wf.state = "blocked"
        mock_wf.priority = "critical"
        mock_wf.title = "Incident DB Triage"
        mock_wf.assigned_entities = [{"name": "Platform DevOps Team", "type": "team"}]
        mock_wf.workspace_id = self.workspace_id

        mock_res_ev = MagicMock()
        mock_res_ev.scalars.return_value.all.return_value = [mock_event]
        
        mock_res_ins = MagicMock()
        mock_res_ins.scalars.return_value.all.return_value = [mock_insight]
        
        mock_res_wf = MagicMock()
        mock_res_wf.scalars.return_value.all.return_value = [mock_wf]

        session.execute.side_effect = [mock_res_ev, mock_res_ins, mock_res_wf]

        digest = await self.generator.generate_email_digest(
            session=session,
            workspace_id=self.workspace_id,
            digest_type="weekly_engineering",
            hours_lookback=168,
        )

        self.assertIn("subject", digest)
        self.assertIn("html", digest)
        self.assertIn("text", digest)
        
        # Verify structured html components and inline CSS classes
        html_str = digest["html"]
        self.assertIn("weekly engineering", html_str.lower())
        self.assertIn("PostgreSQL saturating", html_str)
        self.assertIn("Volume spike detected", html_str)
        self.assertIn("Incident DB Triage", html_str)
        self.assertIn("metric-card", html_str)
        self.assertIn("timeline-item", html_str)


if __name__ == "__main__":
    unittest.main()
