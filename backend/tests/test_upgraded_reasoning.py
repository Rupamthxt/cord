"""
Tests for the upgraded multi-hop reasoning pipeline.
Verifies the execution of the upgraded pipeline flow.

Run with: python -m unittest backend/tests/test_upgraded_reasoning.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.reasoning.pipeline import MultiHopReasoningPipeline
from backend.intelligence.timelines.builder import TimelineEvent, TimelineSequenceItem, TimelineResponse


class TestUpgradedReasoning(unittest.IsolatedAsyncioTestCase):
    """Tests for the upgraded MultiHopReasoningPipeline."""

    async def test_upgraded_pipeline_execution(self):
        pipeline = MultiHopReasoningPipeline()
        workspace_id = "default_workspace"
        query = "database latency issues past 24 hours"

        # Mock search results
        mock_search_results = {
            "query": "database latency issues",
            "results": [
                {
                    "id": "chunk-101",
                    "content": "PostgreSQL database connection pool latency is high.",
                    "score": 0.9,
                    "source": "slack",
                    "timestamp": "2026-05-25T09:00:00Z",
                    "entities": ["PostgreSQL"],
                }
            ]
        }

        # Mock ORM objects
        entity_id = uuid4()
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "PostgreSQL"
        mock_entity.type = "system"

        # Mock timeline Pydantic objects
        mock_timeline_event = TimelineEvent(
            id=uuid4(),
            event_type="incident",
            title="High Database Latency",
            description="Queries taking longer than 5 seconds",
            timestamp=datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc),
            confidence=0.88,
            source_chunk_id="chunk-101",
            workspace_id=workspace_id,
            entities=[{"id": str(entity_id), "name": "PostgreSQL", "type": "system"}]
        )
        
        mock_sequence_item = TimelineSequenceItem(event=mock_timeline_event)
        mock_timeline_response = TimelineResponse(
            workspace_id=workspace_id,
            events=[mock_sequence_item],
            total_count=1
        )

        # Mock database session
        session = AsyncMock()
        mock_ent_res = MagicMock()
        mock_ent_res.all.return_value = [(entity_id,)]
        mock_ref_res = MagicMock()
        mock_ref_res.all.return_value = [("chunk-101",)]
        mock_event_res = MagicMock()
        mock_event_res.scalars.return_value.all.return_value = []
        session.execute.side_effect = [mock_ent_res, mock_ref_res, mock_event_res]

        # Create a mock active insight to return
        mock_insight = MagicMock()
        mock_insight.id = uuid4()
        mock_insight.title = "Mock Insight"
        mock_insight.summary = "A mock insight summary"
        mock_insight.insight_type = "recurring_bottleneck"
        mock_insight.confidence = 0.85
        mock_insight.evidence = ["A text citation snippet"]
        mock_insight.supporting_events = []
        mock_insight.supporting_entities = []

        # Patch dependency pipelines
        with patch("backend.intelligence.reasoning.pipeline.search", return_value=mock_search_results):
            with patch("backend.intelligence.reasoning.pipeline.get_db_session") as mock_db_ctx:
                mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
                mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
                
                with patch("backend.intelligence.reasoning.pipeline.timeline_builder.build_timeline", new_callable=AsyncMock) as mock_build_timeline:
                    mock_build_timeline.return_value = mock_timeline_response
                    
                    with patch("backend.intelligence.reasoning.pipeline.pattern_detector.analyze_patterns", new_callable=AsyncMock) as mock_analyze_patterns:
                        mock_analyze_patterns.return_value = {
                            "temporal_clusters": [],
                            "incident_frequencies": [],
                            "deployment_incidents": [],
                        }
                        
                        with patch("backend.intelligence.insights.store.insight_store.list_insights", new_callable=AsyncMock) as mock_list:
                            mock_list.return_value = [mock_insight]

                            # Patch LLM summarization call
                            with patch("backend.intelligence.summarization.engine.ollama_client.is_available", new=AsyncMock(return_value=True)):
                                with patch("backend.intelligence.summarization.engine.ollama_client.generate", new=AsyncMock(return_value="Upgraded LLM Summary text report.")):
                                    result = await pipeline.execute_reasoning(
                                        query=query,
                                        workspace_id=workspace_id,
                                        limit=5
                                    )

        # Assert results contain the new structural elements
        self.assertEqual(result["query"], query)
        self.assertIn("evidence_backed_summary", result)
        self.assertIn("active_insights", result)
        
        evidence_summary = result["evidence_backed_summary"]
        self.assertEqual(evidence_summary["summary"], "Upgraded LLM Summary text report.")
        self.assertGreater(len(evidence_summary["key_findings"]), 0)
        self.assertGreater(len(evidence_summary["supporting_evidence"]), 0)
        self.assertGreater(len(evidence_summary["related_entities"]), 0)
        self.assertEqual(evidence_summary["confidence"], 0.86)


if __name__ == "__main__":
    unittest.main()
