"""
Tests for the new temporal pattern detection engine.
Covers: proximity clustering, incident frequency calculations, deployment-incident correlations.

Run with: python -m unittest backend/tests/test_pattern_detection_new.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from backend.intelligence.analytics.patterns import pattern_detector


class TestPatternDetectionNew(unittest.IsolatedAsyncioTestCase):
    """Tests for PatternDetector using mock SQLAlchemy execution."""

    def setUp(self):
        # Setup mock events
        self.now = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
        
        self.ev_deploy = MagicMock()
        self.ev_deploy.id = "ev-1"
        self.ev_deploy.event_type = "deployment"
        self.ev_deploy.title = "Release v1.0"
        self.ev_deploy.timestamp = self.now - timedelta(minutes=45)
        self.ev_deploy.source_chunk_id = "chunk-1"
        self.ev_deploy.workspace_id = "ws"
        self.ev_deploy.severity = "low"

        self.ev_incident = MagicMock()
        self.ev_incident.id = "ev-2"
        self.ev_incident.event_type = "incident"
        self.ev_incident.title = "PostgreSQL saturating"
        self.ev_incident.timestamp = self.now - timedelta(minutes=30)
        self.ev_incident.source_chunk_id = "chunk-2"
        self.ev_incident.workspace_id = "ws"
        self.ev_incident.severity = "high"

        self.ev_outage = MagicMock()
        self.ev_outage.id = "ev-3"
        self.ev_outage.event_type = "outage"
        self.ev_outage.title = "Outage on prod"
        self.ev_outage.timestamp = self.now - timedelta(minutes=25)
        self.ev_outage.source_chunk_id = "chunk-2"
        self.ev_outage.workspace_id = "ws"
        self.ev_outage.severity = "critical"

    async def test_detect_temporal_clusters(self):
        # Setup mock session
        session = AsyncMock()
        # Mock session execution returning events sorted by timestamp
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self.ev_deploy,
            self.ev_incident,
            self.ev_outage
        ]
        session.execute.return_value = mock_result

        clusters = await pattern_detector.detect_temporal_clusters(session, "ws", window_hours=1.0)
        
        # Verify 1 cluster containing 3 events was detected (since they are within 1 hour of each other)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["event_count"], 3)
        self.assertEqual(clusters[0]["events"][0]["title"], "Release v1.0")

    async def test_detect_deployment_incidents(self):
        session = AsyncMock()
        mock_result_dep = MagicMock()
        mock_result_dep.scalars.return_value.all.return_value = [self.ev_deploy]
        
        mock_result_inc = MagicMock()
        mock_result_inc.scalars.return_value.all.return_value = [self.ev_incident, self.ev_outage]
        
        # Return deployment results first, then issue results
        session.execute.side_effect = [mock_result_dep, mock_result_inc]

        correlations = await pattern_detector.detect_deployment_incidents(session, "ws", threshold_minutes=60.0)
        
        # Deploy is at -45m, incident at -30m, outage at -25m.
        # Both are within 60 minutes of the deployment.
        self.assertEqual(len(correlations), 2)
        self.assertEqual(correlations[0]["deployment"]["title"], "Release v1.0")
        self.assertEqual(correlations[0]["incident"]["title"], "PostgreSQL saturating")


if __name__ == "__main__":
    unittest.main()
