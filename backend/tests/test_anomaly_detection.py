"""
Tests for the statistical anomaly and release instability detection engine.
Covers: volume spikes and deployment instability regressions.

Run with: python -m unittest backend/tests/test_anomaly_detection.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.anomalies.detector import AnomalyDetector
from backend.intelligence.insights.schema import InsightCreate


class TestAnomalyDetection(unittest.IsolatedAsyncioTestCase):
    """Tests for the AnomalyDetector class."""

    def setUp(self):
        self.detector = AnomalyDetector()
        self.workspace_id = "default_workspace"
        self.now = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)

    async def test_detect_volume_spikes(self):
        # 1. Create a set of historical events representing a baseline and a target spike
        session = AsyncMock()

        # Let's mock 10 events spread over the past 30 days
        events = []
        # Baseline events (low frequency: e.g. 1 per day on some days)
        for i in range(10, 30):
            ev = MagicMock()
            ev.id = uuid4()
            ev.workspace_id = self.workspace_id
            ev.event_type = "incident"
            ev.title = f"Baseline incident {i}"
            ev.timestamp = self.now - timedelta(days=i)
            ev.source_chunk_id = f"chunk-baseline-{i}"
            events.append(ev)

        # Target window events (high frequency spike: 12 events in the last 2 days)
        for i in range(12):
            ev = MagicMock()
            ev.id = uuid4()
            ev.workspace_id = self.workspace_id
            ev.event_type = "incident"
            ev.title = f"Spike incident {i}"
            ev.timestamp = self.now - timedelta(hours=i * 2)
            ev.source_chunk_id = f"chunk-spike-{i}"
            events.append(ev)

        # Mock query return
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = events
        
        # When entity query runs inside volume spikes detection (ChunkEntityRefs join)
        mock_ent_res = MagicMock()
        mock_ent_res.all.return_value = [(uuid4(), "PostgreSQL", "system")]
        
        session.execute.side_effect = [mock_res, mock_ent_res]

        insights = await self.detector.detect_volume_spikes(session, self.workspace_id, now=self.now)
        
        self.assertGreaterEqual(len(insights), 1)
        spike_insight = insights[0]
        self.assertEqual(spike_insight.insight_type, "anomaly")
        self.assertIn("Abnormal volume spike", spike_insight.title)
        self.assertEqual(spike_insight.severity, "high")

    async def test_detect_instability_patterns(self):
        # Mock a deployment followed by 2 incidents in the last 7 days
        session = AsyncMock()

        dep_ev = MagicMock()
        dep_ev.id = uuid4()
        dep_ev.workspace_id = self.workspace_id
        dep_ev.event_type = "deployment"
        dep_ev.title = "Release v2.5"
        dep_ev.timestamp = self.now - timedelta(hours=4)
        dep_ev.source_chunk_id = "chunk-dep-1"

        inc1 = MagicMock()
        inc1.id = uuid4()
        inc1.workspace_id = self.workspace_id
        inc1.event_type = "incident"
        inc1.title = "API Latency spike"
        inc1.timestamp = self.now - timedelta(hours=3, minutes=30)
        inc1.source_chunk_id = "chunk-inc-1"

        inc2 = MagicMock()
        inc2.id = uuid4()
        inc2.workspace_id = self.workspace_id
        inc2.event_type = "incident"
        inc2.title = "Outage on auth service"
        inc2.timestamp = self.now - timedelta(hours=3, minutes=10)
        inc2.source_chunk_id = "chunk-inc-2"

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [dep_ev, inc1, inc2]

        mock_ent_res = MagicMock()
        mock_ent_res.all.return_value = [
            (uuid4(), "AuthService", "system"),
            (uuid4(), "API Gateway", "system"),
        ]

        session.execute.side_effect = [mock_res, mock_ent_res]

        insights = await self.detector.detect_instability_patterns(session, self.workspace_id, now=self.now)

        self.assertEqual(len(insights), 1)
        inst_insight = insights[0]
        self.assertEqual(inst_insight.insight_type, "deployment_instability")
        self.assertIn("Release v2.5", inst_insight.title)
        self.assertEqual(inst_insight.severity, "high")

    async def test_run_detection(self):
        # Verify run_detection aggregates and upserts correctly
        session = AsyncMock()
        
        # Mock empty returns for simplicity
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_res

        with patch("backend.intelligence.anomalies.detector.insight_store.upsert_insight") as mock_upsert:
            mock_upsert.return_value = (MagicMock(), True)
            persisted = await self.detector.run_detection(session, self.workspace_id, now=self.now)
            self.assertEqual(len(persisted), 0)


if __name__ == "__main__":
    unittest.main()
