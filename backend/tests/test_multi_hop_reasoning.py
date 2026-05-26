"""
Tests for the multi-hop reasoning pipeline.
Mocks semantic Qdrant search, PostgreSQL graph retrieval, and local LLM summarization.

Run with: python -m unittest backend/tests/test_multi_hop_reasoning.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.reasoning.pipeline import multi_hop_reasoning_pipeline


class TestMultiHopReasoning(unittest.IsolatedAsyncioTestCase):
    """Tests for the MultiHopReasoningPipeline orchestrator."""

    async def test_execute_reasoning_flow(self):
        # 1. Mock semantic Qdrant search results
        mock_search_results = {
            "query": "PostgreSQL saturated last 2 hours",
            "results": [
                {
                    "id": "chunk-id-123",
                    "content": "PostgreSQL database CPU usage spiked. Connection pool saturated.",
                    "score": 0.88,
                    "source": "slack",
                    "timestamp": "2026-05-25T09:30:00Z",
                    "entities": ["PostgreSQL", "Platform Team"],
                    "metadata": {"title": "Slack Alert"}
                }
            ]
        }

        # 2. Mock database objects
        mock_entity = MagicMock()
        mock_entity.id = uuid4()
        mock_entity.name = "PostgreSQL"
        mock_entity.type = "system"

        mock_event = MagicMock()
        mock_event.id = uuid4()
        mock_event.event_type = "incident"
        mock_event.title = "DB Saturated"
        mock_event.description = "Connection timeout"
        mock_event.timestamp = datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc)
        mock_event.source_chunk_id = "chunk-id-123"
        mock_event.workspace_id = "default_workspace"
        mock_event.severity = "high"
        mock_event.confidence = 0.85
        mock_event.metadata_ = {}

        # Mock database session execution
        mock_session = AsyncMock()
        mock_res_entities = MagicMock()
        mock_res_entities.all.return_value = [(mock_entity.id,)]
        
        mock_res_chunk_refs = MagicMock()
        mock_res_chunk_refs.all.return_value = [("chunk-id-123",)]

        mock_res_events = MagicMock()
        mock_res_events.scalars.return_value.all.return_value = [mock_event]

        # side effects for session.execute
        # 1st execute: Resolve entities (ent_stmt)
        # 2nd execute: Resolve chunk refs (ref_stmt)
        # 3rd execute: Fetch events (event_stmt)
        # 4th execute: Fetch events for timeline (within timeline_builder)
        # 5th execute: Fetch chunk entities for timeline
        # 6th execute: PatternDetector - detect_temporal_clusters (events)
        # 7th execute: PatternDetector - detect_temporal_clusters (entities)
        # 8th execute: PatternDetector - detect_incident_frequencies (issues)
        # 9th execute: PatternDetector - detect_incident_frequencies (entities)
        # 10th execute: PatternDetector - detect_deployment_incidents (deployments)
        # 11th execute: PatternDetector - detect_deployment_incidents (incidents)
        mock_session.execute.side_effect = [
            mock_res_entities,
            mock_res_chunk_refs,
            mock_res_events,
            # timeline builder events
            mock_res_events,
            # timeline builder entity fetch
            MagicMock(all=MagicMock(return_value=[("chunk-id-123", mock_entity.id, "PostgreSQL", "system")])),
            # pattern clustering (events query)
            MagicMock(scalars=MagicMock(all=MagicMock(return_value=[mock_event]))),
            # pattern clustering (entities query)
            MagicMock(all=MagicMock(return_value=[(mock_entity.id, "PostgreSQL", "system")])),
            # pattern incident frequency (issues query)
            MagicMock(all=MagicMock(return_value=[("chunk-id-123", "incident")])),
            # pattern incident frequency (entities query)
            MagicMock(all=MagicMock(return_value=[(mock_entity.id, "PostgreSQL", "system", "chunk-id-123")])),
            # pattern deployments incidents: deployments
            MagicMock(scalars=MagicMock(all=MagicMock(return_value=[]))),
            # pattern deployments incidents: incidents
            MagicMock(scalars=MagicMock(all=MagicMock(return_value=[mock_event]))),
        ]

        # 3. Patch dependency systems
        with patch("backend.intelligence.reasoning.pipeline.search", return_value=mock_search_results):
            with patch("backend.intelligence.reasoning.pipeline.get_db_session") as mock_db_ctx:
                mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                # Patch LLM summarization call
                with patch("backend.intelligence.summarization.engine.ollama_client.is_available", new=AsyncMock(return_value=True)):
                    with patch("backend.intelligence.summarization.engine.ollama_client.generate", new=AsyncMock(return_value="Mocked LLM Summary text report.")):
                        result = await multi_hop_reasoning_pipeline.execute_reasoning(
                            query="PostgreSQL saturated last 2 hours",
                            workspace_id="default_workspace",
                            limit=5
                        )

        # 4. Assert response payload matches specs
        self.assertEqual(result["query"], "PostgreSQL saturated last 2 hours")
        self.assertIn("parsed_time_range", result)
        self.assertIn("search_results", result)
        self.assertIn("timeline", result)
        self.assertIn("detected_patterns", result)
        self.assertEqual(result["summary"], "Mocked LLM Summary text report.")


if __name__ == "__main__":
    unittest.main()
