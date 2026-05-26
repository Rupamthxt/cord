"""
Tests for the GraphAwareRetriever — validates that semantic search results
are correctly enriched with entity and relationship context from PostgreSQL.

Run with: python -m unittest backend/tests/test_graph_retriever.py
"""
import unittest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────
# GraphAwareRetriever Tests
# ─────────────────────────────────────────────

class TestGraphAwareRetriever(unittest.IsolatedAsyncioTestCase):
    """Tests for result enrichment with graph context."""

    def _make_search_results(self, chunk_ids: list[str]) -> dict:
        """Helper: build a fake ReasoningPipeline output dict."""
        return {
            "query": "test query",
            "results": [
                {
                    "id": cid,
                    "content": f"Content for chunk {cid}",
                    "score": 0.85,
                    "source": "notion",
                    "source_type": "wiki_page",
                    "workspace_id": "default_workspace",
                    "author": "test_user",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "url": None,
                    "hierarchy": ["Engineering", "Docs"],
                    "entities": [],
                    "relationships": [],
                    "metadata": {},
                    "diagnostics": {"cosine_similarity": 0.85},
                }
                for cid in chunk_ids
            ]
        }

    async def test_enrich_results_adds_graph_fields(self):
        from backend.graph.retriever import GraphAwareRetriever

        retriever = GraphAwareRetriever()
        chunk_id = str(uuid4())
        entity_id = uuid4()

        # Mock chunk entity ref
        mock_ref = MagicMock()
        mock_ref.entity_id = entity_id
        mock_ref.mention_text = "Alice"

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Alice"
        mock_entity.type = "person"
        mock_entity.description = "Lead engineer"
        mock_entity.workspace_id = "default_workspace"
        mock_entity.created_at = datetime.utcnow()
        mock_entity.aliases_str = ""
        mock_entity.source_chunk_id = chunk_id
        mock_entity.metadata_ = {}
        mock_entity.metadata = {}

        search_results = self._make_search_results([chunk_id])

        with patch("backend.graph.retriever.get_db_session") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock DB execution for select(ChunkEntityRef)
            mock_execute_res = MagicMock()
            mock_execute_res.scalars.return_value.all.return_value = [mock_ref]
            mock_session.execute = AsyncMock(return_value=mock_execute_res)

            with patch("backend.graph.retriever.entity_store") as mock_entity_store:
                with patch("backend.graph.retriever.relationship_store") as mock_rel_store:
                    mock_entity_store.get_by_id = AsyncMock(return_value=mock_entity)
                    mock_rel_store.get_neighborhood = AsyncMock(return_value={"outgoing": [], "incoming": []})

                    enriched = await retriever.enrich_results(
                        search_results=search_results,
                        workspace_id="default_workspace",
                        include_relationships=True,
                    )

        self.assertIn("results", enriched)
        self.assertEqual(len(enriched["results"]), 1)
        result = enriched["results"][0]
        self.assertIn("graph_entities", result)
        self.assertIn("graph_relationships", result)

    async def test_enrich_results_graceful_degradation_on_db_error(self):
        """If PostgreSQL is unavailable, return original results unchanged."""
        from backend.graph.retriever import GraphAwareRetriever

        retriever = GraphAwareRetriever()
        chunk_id = str(uuid4())
        search_results = self._make_search_results([chunk_id])

        with patch("backend.graph.retriever.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("PostgreSQL connection refused")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            enriched = await retriever.enrich_results(
                search_results=search_results,
                workspace_id="default_workspace",
            )

        # Should return original results unchanged
        self.assertEqual(enriched["query"], "test query")
        self.assertEqual(len(enriched["results"]), 1)
        result = enriched["results"][0]
        # graph fields should NOT be present (since it returned early on error)
        self.assertNotIn("graph_entities", result)

    async def test_enrich_empty_results_list(self):
        """Enriching an empty results list should not raise."""
        from backend.graph.retriever import GraphAwareRetriever

        retriever = GraphAwareRetriever()
        empty_results = {"query": "no results query", "results": []}

        enriched = await retriever.enrich_results(empty_results)
        self.assertEqual(enriched["results"], [])

    async def test_get_entity_neighborhood_structure(self):
        from backend.graph.retriever import GraphAwareRetriever

        retriever = GraphAwareRetriever()
        entity_id = uuid4()

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Infrastructure Team"
        mock_entity.type = "team"
        mock_entity.workspace_id = "default_workspace"
        mock_entity.aliases_str = "Infra,InfraTeam"
        mock_entity.description = "Manages all infra"
        mock_entity.source_chunk_id = None
        mock_entity.metadata_ = {}
        mock_entity.metadata = {}
        mock_entity.created_at = datetime.utcnow()

        with patch("backend.graph.retriever.get_db_session") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("backend.graph.retriever.entity_store") as mock_entity_store:
                with patch("backend.graph.retriever.relationship_store") as mock_rel_store:
                    mock_entity_store.get_by_id = AsyncMock(return_value=mock_entity)
                    mock_entity_store.get_chunks_for_entity = AsyncMock(return_value=["chunk-1"])
                    mock_rel_store.get_neighborhood = AsyncMock(return_value={"outgoing": [], "incoming": []})

                    neighborhood = await retriever.get_entity_neighborhood(
                        entity_id=entity_id,
                        depth=1,
                        workspace_id="default_workspace",
                    )

        self.assertIn("entity", neighborhood)
        self.assertIn("outgoing", neighborhood)
        self.assertIn("incoming", neighborhood)
        self.assertEqual(neighborhood["linked_chunk_ids"], ["chunk-1"])

    async def test_get_entity_neighborhood_not_found(self):
        """If entity not found, return empty."""
        from backend.graph.retriever import GraphAwareRetriever

        retriever = GraphAwareRetriever()

        with patch("backend.graph.retriever.get_db_session") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("backend.graph.retriever.entity_store") as mock_entity_store:
                mock_entity_store.get_by_id = AsyncMock(return_value=None)

                result = await retriever.get_entity_neighborhood(
                    entity_id=uuid4(),
                    depth=1,
                )
                self.assertEqual(result, {})


# ─────────────────────────────────────────────
# EntityStore Tests (unit)
# ─────────────────────────────────────────────

class TestEntityStore(unittest.IsolatedAsyncioTestCase):
    """Unit tests for EntityStore CRUD operations."""

    async def test_get_or_create_creates_when_not_exists(self):
        from backend.graph.entities.store import EntityStore
        from backend.graph.entities.models import Entity

        store = EntityStore()
        mock_session = AsyncMock()
        new_entity = Entity(id=uuid4(), name="Bob", type="person")

        with patch.object(store, "get_by_name", new=AsyncMock(return_value=None)):
            with patch.object(store, "create", new=AsyncMock(return_value=new_entity)):
                entity, is_new = await store.get_or_create(
                    mock_session,
                    name="Bob",
                    entity_type="person",
                    workspace_id="test_ws"
                )

        self.assertTrue(is_new)
        self.assertEqual(entity.name, "Bob")

    async def test_get_or_create_returns_existing_when_found(self):
        from backend.graph.entities.store import EntityStore
        from backend.graph.entities.models import Entity

        store = EntityStore()
        mock_session = AsyncMock()
        existing = Entity(id=uuid4(), name="Bob", type="person")

        with patch.object(store, "get_by_name", new=AsyncMock(return_value=existing)):
            entity, is_new = await store.get_or_create(
                mock_session,
                name="Bob",
                entity_type="person",
                workspace_id="test_ws"
            )

        self.assertFalse(is_new)
        self.assertEqual(entity.id, existing.id)


# ─────────────────────────────────────────────
# EntityDeduplicator Tests
# ─────────────────────────────────────────────

class TestEntityDeduplicator(unittest.TestCase):
    """Tests for cosine similarity based deduplication."""

    def test_cosine_identical_vectors(self):
        from backend.graph.entities.deduplicator import _cosine

        v = [0.1, 0.5, -0.3, 0.8]
        sim = _cosine(v, v)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_cosine_orthogonal_vectors(self):
        from backend.graph.entities.deduplicator import _cosine

        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        sim = _cosine(a, b)
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_cosine_zero_vector_returns_zero(self):
        from backend.graph.entities.deduplicator import _cosine

        a = [0.0, 0.0, 0.0]
        b = [0.5, 0.3, 0.1]
        sim = _cosine(a, b)
        self.assertEqual(sim, 0.0)


class TestEntityDeduplicatorAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for EntityDeduplicator."""

    async def test_resolve_returns_exact_match(self):
        from backend.graph.entities.deduplicator import EntityDeduplicator

        dedup = EntityDeduplicator()
        mock_session = AsyncMock()

        existing = MagicMock()
        existing.id = uuid4()
        existing.name = "Alice"
        existing.type = "person"

        dedup.store = AsyncMock()
        dedup.store.get_by_name = AsyncMock(return_value=existing)

        result = await dedup.resolve(
            session=mock_session,
            name="Alice",
            entity_type="person",
            workspace_id="default_workspace",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.id, existing.id)
