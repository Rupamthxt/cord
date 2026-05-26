"""
Tests for the operational event extraction layer.
Tests cover: LLM event response parsing, Pydantic event validation, fallback extraction,
and the EventExtractionPipeline orchestration logic.

Run with: python -m unittest backend/tests/test_event_extraction.py
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.graph.events.extractor import EventExtractionResponse, event_extractor, ExtractedEvent
from backend.graph.events.schema import EventCreate, EventRelationshipCreate
from backend.graph.events.store import event_store


class TestEventExtractionValidator(unittest.TestCase):
    """Tests for parse_llm_response and Pydantic event extraction schemas."""

    def test_parse_clean_json_response(self):
        raw = json.dumps({
            "events": [
                {
                    "event_type": "deployment",
                    "title": "Deploy Service X",
                    "description": "Deploying v1.2",
                    "timestamp": "2026-05-25T10:00:00Z",
                    "severity": "low",
                    "confidence": 0.95,
                    "metadata": {"env": "prod"}
                },
                {
                    "event_type": "incident",
                    "title": "Incident INC-123",
                    "description": "Database outage",
                    "timestamp": "2026-05-25T10:15:00Z",
                    "severity": "critical",
                    "confidence": 0.9,
                    "metadata": {}
                }
            ],
            "relationships": [
                {
                    "source_title": "Incident INC-123",
                    "target_title": "Deploy Service X",
                    "relationship_type": "caused_by",
                    "confidence": 0.85
                }
            ]
        })
        result = event_extractor._parse_llm_response(raw)
        self.assertEqual(len(result.events), 2)
        self.assertEqual(result.events[0].title, "Deploy Service X")
        self.assertEqual(result.events[0].event_type, "deployment")
        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0].relationship_type, "caused_by")
        self.assertAlmostEqual(result.relationships[0].confidence, 0.85, places=4)

    def test_parse_invalid_json_returns_empty(self):
        result = event_extractor._parse_llm_response("invalid json")
        self.assertEqual(len(result.events), 0)
        self.assertEqual(len(result.relationships), 0)

    def test_event_type_fallback(self):
        raw = json.dumps({
            "events": [
                {
                    "event_type": "mystery_unsupported_type",
                    "title": "Random Event",
                    "description": None,
                    "timestamp": None,
                    "severity": None,
                    "confidence": 0.8,
                    "metadata": {}
                }
            ],
            "relationships": []
        })
        result = event_extractor._parse_llm_response(raw)
        # Should fall back to "decision" as default or another valid type
        self.assertIn(result.events[0].event_type, ["decision", "incident"])


class TestEventExtractorFallback(unittest.TestCase):
    """Tests for regex-based fallback extraction of events."""

    def test_fallback_extract_deployment_and_incident(self):
        text = "Bob deployed ServiceA to production.\nThen INC-456 occurred and DB crashed."
        result = event_extractor._fallback_extract(text)
        self.assertEqual(len(result.events), 2)
        
        # Verify first event is deployment
        self.assertEqual(result.events[0].event_type, "deployment")
        # Verify second event is incident/outage
        self.assertIn(result.events[1].event_type, ["incident", "outage"])
        
        # Verify relationship exists since multiple events were found
        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0].relationship_type, "occurred_after")


class TestEventExtractionPipeline(unittest.IsolatedAsyncioTestCase):
    """Tests for EventExtractionPipeline orchestrator."""

    async def test_process_chunk_flow(self):
        from backend.graph.events.pipeline import event_extraction_pipeline
        
        mock_response = EventExtractionResponse(
            events=[
                ExtractedEvent(event_type="deployment", title="Deploy", description="Desc", timestamp=None, severity="low", confidence=0.9, metadata={})
            ],
            relationships=[]
        )

        mock_db_event = MagicMock()
        mock_db_event.id = uuid4()
        mock_db_event.title = "Deploy"

        with patch.object(event_extractor, "extract", new=AsyncMock(return_value=mock_response)):
            with patch.object(event_store, "upsert_event", new=AsyncMock(return_value=(mock_db_event, True))):
                with patch("backend.graph.events.pipeline.get_db_session") as mock_ctx:
                    mock_session = AsyncMock()
                    mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                    summary = await event_extraction_pipeline.process_chunk(
                        chunk_text="Deploying service",
                        chunk_id="test-chunk-999",
                        workspace_id="test_workspace"
                    )

        self.assertEqual(summary["events_found"], 1)
        self.assertEqual(summary["events_new"], 1)
        self.assertEqual(summary["chunk_id"], "test-chunk-999")
        self.assertIsNone(summary["error"])


if __name__ == "__main__":
    unittest.main()
