"""
Tests for the evidence-backed operational summarizer.
Covers: formatting, findings extraction, citations, and confidence calculations.

Run with: python -m unittest backend/tests/test_evidence_summary.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.summarization.engine import SummarizationEngine
from backend.intelligence.timelines.builder import TimelineEvent, TimelineSequenceItem, TimelineResponse


class TestEvidenceSummary(unittest.IsolatedAsyncioTestCase):
    """Tests for the SummarizationEngine."""

    def setUp(self):
        self.engine = SummarizationEngine()

    async def test_generate_evidence_backed_summary_fallback(self):
        # 1. Create actual Pydantic models to satisfy schema validation
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()

        ev1 = TimelineEvent(
            id=uuid4(),
            event_type="deployment",
            title="PostgreSQL Rollback",
            description="Rollback triggered due to pool exhaustion.",
            timestamp=datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc),
            confidence=0.9,
            source_chunk_id="chunk-1",
            workspace_id="default_workspace",
            entities=[{"id": str(entity_id_1), "name": "PostgreSQL", "type": "system"}]
        )

        ev2 = TimelineEvent(
            id=uuid4(),
            event_type="incident",
            title="Service Latency Spike",
            description="API requests timing out.",
            timestamp=datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc),
            confidence=0.8,
            source_chunk_id="chunk-2",
            workspace_id="default_workspace",
            entities=[{"id": str(entity_id_2), "name": "API Gateway", "type": "system"}]
        )

        item1 = TimelineSequenceItem(event=ev1, time_since_previous_str=None)
        item2 = TimelineSequenceItem(event=ev2, time_since_previous_str="30m")

        timeline = TimelineResponse(workspace_id="default_workspace", events=[item1, item2], total_count=2)

        # 2. Create mock active insights
        mock_insight = MagicMock()
        mock_insight.id = uuid4()
        mock_insight.title = "Recurring Database Saturation"
        mock_insight.summary = "PostgreSQL is frequently running out of connections."
        mock_insight.insight_type = "recurring_bottleneck"
        mock_insight.confidence = 0.85
        mock_insight.evidence = ["Query count spiked 4x", "Connection pool timeout alerts"]
        mock_insight.supporting_events = [{"id": str(ev1.id), "title": ev1.title}]
        mock_insight.supporting_entities = [{"id": str(entity_id_1), "name": "PostgreSQL", "type": "system"}]

        # 3. Call generate_evidence_backed_summary
        with patch("backend.intelligence.summarization.engine.ollama_client.is_available", new=AsyncMock(return_value=False)):
            res = await self.engine.generate_evidence_backed_summary(
                query="Why is PostgreSQL failing?",
                timeline_data=timeline,
                related_insights=[mock_insight],
            )

        # 4. Verify structural format and content
        self.assertIn("summary", res)
        self.assertTrue(res["summary"].startswith("# Operational Health Summary"))
        
        # Verify findings
        self.assertEqual(len(res["key_findings"]), 1)
        self.assertEqual(res["key_findings"][0]["finding"], "[RECURRING_BOTTLENECK] Recurring Database Saturation")
        self.assertEqual(res["key_findings"][0]["source_id"], str(mock_insight.id))

        # Verify evidence citations
        self.assertIn("Event: PostgreSQL Rollback - Rollback triggered due to pool exhaustion.", res["supporting_evidence"])
        self.assertIn("Query count spiked 4x", res["supporting_evidence"])

        # Verify entities and events lists
        self.assertEqual(len(res["related_entities"]), 2)
        self.assertEqual(len(res["related_events"]), 2)
        self.assertEqual(res["confidence"], 0.85)  # Avg of [0.9, 0.8, 0.85]


if __name__ == "__main__":
    unittest.main()
