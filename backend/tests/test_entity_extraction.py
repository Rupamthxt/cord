"""
Tests for the organizational entity extraction layer.
Tests cover: LLM response parsing, Pydantic validation, fallback extraction,
and the ExtractionPipeline orchestration logic.

Run with: python -m unittest backend/tests/test_entity_extraction.py
"""
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ─────────────────────────────────────────────
# Validator Tests
# ─────────────────────────────────────────────

class TestExtractionValidator(unittest.TestCase):
    """Tests for parse_llm_response and Pydantic extraction schemas."""

    def test_parse_clean_json_response(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({
            "entities": [
                {"name": "Alice", "type": "person", "description": "Engineer"},
                {"name": "Project Phoenix", "type": "project", "description": None},
            ],
            "relationships": [
                {
                    "source": "Alice",
                    "target": "Project Phoenix",
                    "type": "assigned_to",
                    "evidence": "Alice is leading Project Phoenix",
                    "confidence": 0.92,
                }
            ]
        })
        result = parse_llm_response(raw)
        self.assertEqual(len(result.entities), 2)
        self.assertEqual(result.entities[0].name, "Alice")
        self.assertEqual(result.entities[0].type, "person")
        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0].type, "assigned_to")
        self.assertAlmostEqual(result.relationships[0].confidence, 0.92, places=4)

    def test_parse_json_wrapped_in_markdown(self):
        from backend.extraction.validator import parse_llm_response

        raw = """Here's the extracted data:
```json
{
  "entities": [{"name": "Qdrant", "type": "system", "description": "Vector DB"}],
  "relationships": []
}
```
Hope that helps!"""
        result = parse_llm_response(raw)
        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].name, "Qdrant")
        self.assertEqual(result.entities[0].type, "system")

    def test_parse_json_embedded_in_prose(self):
        from backend.extraction.validator import parse_llm_response

        raw = 'Some prose before {"entities": [{"name": "DevOps", "type": "team", "description": null}], "relationships": []} some prose after'
        result = parse_llm_response(raw)
        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].type, "team")

    def test_parse_malformed_json_returns_empty(self):
        from backend.extraction.validator import parse_llm_response

        result = parse_llm_response("This is not JSON at all!!!")
        self.assertEqual(result.entities, [])
        self.assertEqual(result.relationships, [])

    def test_unknown_entity_type_defaults_to_document(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({
            "entities": [{"name": "Mystery Thing", "type": "galaxy", "description": None}],
            "relationships": []
        })
        result = parse_llm_response(raw)
        self.assertEqual(result.entities[0].type, "document")

    def test_confidence_clamping(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({
            "entities": [
                {"name": "Incident 42", "type": "incident", "description": None},
                {"name": "API Gateway", "type": "system", "description": None},
            ],
            "relationships": [
                {
                    "source": "Incident 42",
                    "target": "API Gateway",
                    "type": "caused",
                    "evidence": "The incident was caused by the API Gateway",
                    "confidence": 99.9,   # way out of range
                }
            ]
        })
        result = parse_llm_response(raw)
        self.assertTrue(result.relationships[0].confidence <= 1.0)
        self.assertTrue(result.relationships[0].confidence >= 0.0)

    def test_relationship_filtered_if_entity_missing(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({
            "entities": [{"name": "Alice", "type": "person", "description": None}],
            "relationships": [
                {
                    "source": "Alice",
                    "target": "Ghost Entity",   # not in entities list
                    "type": "related_to",
                    "confidence": 0.7,
                }
            ]
        })
        result = parse_llm_response(raw)
        # Relationship should be filtered out since "Ghost Entity" is not in entities
        self.assertEqual(len(result.relationships), 0)

    def test_entity_name_too_short_excluded(self):
        from backend.extraction.validator import ExtractedEntity
        from pydantic import ValidationError

        # Bob is valid and passes validation
        entity = ExtractedEntity(name="Bob", type="person", description=None)
        self.assertEqual(entity.name, "Bob")

        # "A" should raise a validation error
        with self.assertRaises(ValidationError):
            ExtractedEntity(name="A", type="person", description=None)

    def test_relationship_type_normalization(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({
            "entities": [
                {"name": "Team Alpha", "type": "team", "description": None},
                {"name": "Service X", "type": "system", "description": None},
            ],
            "relationships": [
                {
                    "source": "Team Alpha",
                    "target": "Service X",
                    "type": "Depends On",   # needs normalization
                    "confidence": 0.8,
                }
            ]
        })
        result = parse_llm_response(raw)
        self.assertEqual(result.relationships[0].type, "depends_on")

    def test_empty_response(self):
        from backend.extraction.validator import parse_llm_response

        raw = json.dumps({"entities": [], "relationships": []})
        result = parse_llm_response(raw)
        self.assertEqual(result.entities, [])
        self.assertEqual(result.relationships, [])


# ─────────────────────────────────────────────
# Prompts Tests
# ─────────────────────────────────────────────

class TestExtractionPrompts(unittest.TestCase):
    """Tests for prompt template formatting."""

    def test_format_prompt_inserts_chunk_text(self):
        from backend.extraction.prompts import ExtractionPrompts

        chunk = "Alice deployed Project Phoenix to production on Friday."
        prompt = ExtractionPrompts.format_prompt(chunk)
        self.assertIn(chunk, prompt)

    def test_prompt_contains_entity_types(self):
        from backend.extraction.prompts import ExtractionPrompts

        prompt = ExtractionPrompts.ENTITY_EXTRACTION_PROMPT
        for entity_type in ["person", "team", "project", "system", "incident", "deployment"]:
            self.assertIn(entity_type, prompt)

    def test_prompt_contains_relationship_types(self):
        from backend.extraction.prompts import ExtractionPrompts

        prompt = ExtractionPrompts.ENTITY_EXTRACTION_PROMPT
        for rel_type in ["owns", "depends_on", "caused", "manages"]:
            self.assertIn(rel_type, prompt)

    def test_prompt_instructs_json_only(self):
        from backend.extraction.prompts import ExtractionPrompts

        prompt = ExtractionPrompts.ENTITY_EXTRACTION_PROMPT
        self.assertTrue("json" in prompt.lower() or "JSON" in prompt)


# ─────────────────────────────────────────────
# OllamaClient Tests
# ─────────────────────────────────────────────

class TestOllamaClient(unittest.IsolatedAsyncioTestCase):
    """Tests for the async Ollama HTTP client."""

    async def test_is_available_returns_true_on_200(self):
        from backend.extraction.ollama_client import OllamaClient

        client = OllamaClient()
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = mock_resp
            result = await client.is_available()
            self.assertIsInstance(result, bool)

    async def test_is_available_returns_false_on_connection_error(self):
        import aiohttp
        from backend.extraction.ollama_client import OllamaClient

        client = OllamaClient()
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.get.side_effect = aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("Connection refused")
            )
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session
            result = await client.is_available()
            self.assertFalse(result)


# ─────────────────────────────────────────────
# OllamaEntityExtractor Tests
# ─────────────────────────────────────────────

class TestOllamaEntityExtractor(unittest.IsolatedAsyncioTestCase):
    """Tests for the main extractor — mocking Ollama responses."""

    async def test_extract_with_ollama_available(self):
        from backend.extraction.extractor import OllamaEntityExtractor
        from backend.extraction.validator import ExtractionResponse

        extractor = OllamaEntityExtractor()

        mock_response_json = json.dumps({
            "entities": [
                {"name": "Alice", "type": "person", "description": "Lead engineer"},
                {"name": "Search Service", "type": "system", "description": "Internal search API"},
            ],
            "relationships": [
                {
                    "source": "Alice",
                    "target": "Search Service",
                    "type": "manages",
                    "evidence": "Alice manages the search service",
                    "confidence": 0.91,
                }
            ]
        })

        extractor._ollama_available = True
        extractor._last_availability_check = float("inf")

        with patch.object(extractor.ollama, "generate", new=AsyncMock(return_value=mock_response_json)):
            result = await extractor.extract("Alice manages the search service component.")

        self.assertIsInstance(result, ExtractionResponse)
        self.assertEqual(len(result.entities), 2)
        self.assertEqual(len(result.relationships), 1)

    async def test_fallback_when_ollama_unavailable(self):
        from backend.extraction.extractor import OllamaEntityExtractor
        from backend.extraction.validator import ExtractionResponse

        extractor = OllamaEntityExtractor()
        extractor._ollama_available = False
        extractor._last_availability_check = float("inf")

        result = await extractor.extract("The engineering team deployed Project Apollo to production.")
        self.assertIsInstance(result, ExtractionResponse)
        self.assertIsInstance(result.entities, list)


# ─────────────────────────────────────────────
# ExtractionPipeline Tests
# ─────────────────────────────────────────────

class TestExtractionPipeline(unittest.IsolatedAsyncioTestCase):
    """Tests for pipeline orchestration."""

    async def test_process_chunk_returns_summary_dict(self):
        from backend.extraction.pipeline import ExtractionPipeline
        from backend.extraction.validator import ExtractionResponse, ExtractedEntity

        pipeline = ExtractionPipeline()

        mock_extraction = ExtractionResponse(
            entities=[ExtractedEntity(name="Bob", type="person", description=None)],
            relationships=[]
        )

        mock_entity = MagicMock()
        mock_entity.id = uuid4()
        mock_entity.name = "Bob"
        mock_entity.type = "person"

        with patch.object(pipeline.extractor, "extract", new=AsyncMock(return_value=mock_extraction)):
            with patch.object(pipeline.deduplicator, "resolve", new=AsyncMock(return_value=None)):
                with patch.object(pipeline.entity_store, "get_or_create", new=AsyncMock(return_value=(mock_entity, True))):
                    with patch.object(pipeline.entity_store, "upsert_chunk_entity_ref", new=AsyncMock(return_value=None)):
                        with patch("backend.extraction.pipeline.get_db_session") as mock_ctx:
                            mock_session = AsyncMock()
                            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                            result = await pipeline.process_chunk(
                                chunk_text="Bob is on the team.",
                                chunk_id="test-chunk-123",
                                workspace_id="test_workspace"
                            )

        self.assertIn("entities_found", result)
        self.assertIn("entities_new", result)
        self.assertIn("relationships_stored", result)
        self.assertEqual(result["chunk_id"], "test-chunk-123")
        self.assertIsNone(result["error"])

    def test_process_chunk_sync_does_not_raise(self):
        """Synchronous wrapper must not raise even if async fails."""
        from backend.extraction.pipeline import ExtractionPipeline
        from backend.extraction.validator import ExtractionResponse

        pipeline = ExtractionPipeline()

        with patch.object(pipeline.extractor, "extract", new=AsyncMock(return_value=ExtractionResponse())):
            with patch("backend.extraction.pipeline.get_db_session") as mock_ctx:
                mock_session = AsyncMock()
                mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                result = pipeline.process_chunk_sync(
                    chunk_text="",
                    chunk_id="test-sync-001",
                    workspace_id="default_workspace"
                )

        self.assertIsInstance(result, dict)
        self.assertIn("chunk_id", result)
