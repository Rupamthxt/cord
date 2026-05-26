import asyncio
import logging
from datetime import datetime, timezone, timedelta

from backend.core.models.store_memory import store_chunks
from backend.connectors.ingestion.chunker import chunk_text
from backend.intelligence.retrieval.search import search
from backend.core.models.memory_schema import MemoryDocument

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 1. Define Mock Dataset with diverse features
MOCK_DOCUMENTS = [
    MemoryDocument(
        id="notion_apollo_spec",
        source="notion",
        source_id="page_apollo_spec",
        path="/Notion/Engineering/Projects/Apollo",
        title="Project Apollo Specification",
        content="""
        This document defines the specification for Project Apollo.
        Our goal is to migrate the legacy database system to PostgreSQL.
        The engineering team led by @Alice will spearhead this effort.
        We expect the deployment to happen in production environment by Q3.
        """,
        author="Alice",
        created_time=datetime.now(timezone.utc) - timedelta(days=90),  # Old document
        last_edited_time=datetime.now(timezone.utc) - timedelta(days=90),
        tags=["engineering", "database"]
    ),
    MemoryDocument(
        id="notion_apollo_incident",
        source="notion",
        source_id="page_apollo_incident",
        path="/Notion/Engineering/Incidents/ApolloOutage",
        title="Postmortem: Project Apollo Outage",
        content="""
        Incident report for the Project Apollo migration.
        We experienced a Sev-1 incident during the deployment to production.
        The PostgreSQL database became overloaded, causing a 20-minute outage.
        @Bob resolved the connection issues by tuning the FastAPI server.
        """,
        author="Bob",
        created_time=datetime.now(timezone.utc) - timedelta(days=2),  # Very recent document
        last_edited_time=datetime.now(timezone.utc) - timedelta(days=2),
        tags=["incident", "database", "postmortem"]
    ),
    MemoryDocument(
        id="slack_chat_discussion",
        source="slack",
        source_id="chat_thread_discussion",
        path="/Slack/general/2026-05-24",
        title="Slack General Chat (2026-05-24)",
        content="""
        Alice [10:00:00]: Has anyone looked at the database performance metrics?
        Bob [10:02:00]: Yes, I noticed some slow queries on PostgreSQL during the migration tests.
        Alice [10:03:00]: Let's make sure we document this in the Project Apollo specification.
        """,
        author="Alice",
        created_time=datetime.now(timezone.utc) - timedelta(days=1),  # Recent chat
        last_edited_time=datetime.now(timezone.utc) - timedelta(days=1),
        tags=["slack", "chat"]
    ),
]


async def run_extended_search_verification():
    logger.info("Starting Advanced Organizational Memory Retrieval Verification...")

    # Step 1: Ingest mock documents
    logger.info("Ingesting mock dataset into in-memory Qdrant...")
    for doc in MOCK_DOCUMENTS:
        chunks = chunk_text(doc.content)
        store_chunks(chunks, metadata=doc)

    # Allow sentence-transformers/qdrant a moment
    await asyncio.sleep(0.5)

    # Step 2: Test Metadata Filtering
    logger.info("\n--- TEST 1: Source Filtering (Slack only) ---")
    res1 = search(query="database", sources=["slack"])
    assert all(r["source"] == "slack" for r in res1["results"])
    logger.info("✓ Source filtering passed!")

    logger.info("\n--- TEST 2: Author Filtering (Bob only) ---")
    res2 = search(query="PostgreSQL", author="Bob")
    assert all(r["author"] == "Bob" for r in res2["results"])
    logger.info("✓ Author filtering passed!")

    logger.info("\n--- TEST 3: Hierarchy-Scoped Retrieval ---")
    # Search for "database" under /Notion/Engineering/Incidents
    res3 = search(query="database", hierarchy_scope="/Notion/Engineering/Incidents")
    assert len(res3["results"]) > 0
    assert any("Incidents" in r["hierarchy"] for r in res3["results"])
    logger.info("✓ Hierarchy-scoped retrieval passed!")

    # Step 3: Test Entity Alignment & Relationships
    logger.info("\n--- TEST 4: Entity & Relationship Ingestion Verification ---")
    # Search query specifically containing a project entity
    res4 = search(query="Project Apollo specification PostgreSQL")
    first_result = res4["results"][0]
    
    # Assert entities got extracted and standardized
    assert "Apollo" in first_result["entities"]
    assert "PostgreSQL" in first_result["entities"]
    logger.info("✓ Entity extraction during ingestion verified!")
    
    # Check relationships
    relationships = first_result.get("relationships", [])
    # Verify child_of and references got populated
    assert len(relationships) > 0
    assert any(rel["type"] == "references_project" and rel["target"] == "Apollo" for rel in relationships)
    logger.info(f"✓ Relationships verified: {relationships}")

    # Step 4: Test Multi-Dimensional Ranking Boosts
    logger.info("\n--- TEST 5: Ranking Boosts (Recency & Entity overlap) ---")
    # Query: "Apollo outage production"
    # Document 'notion_apollo_incident' matches:
    #   - Semantic content ("outage", "production", "Apollo")
    #   - Recent time stamp (2 days ago)
    #   - Overlapping entities ("Apollo", "production", "incident")
    # Document 'notion_apollo_spec' matches:
    #   - Semantic content ("Apollo", "production")
    #   - Older timestamp (90 days ago)
    # The incident report should rank HIGHER because of recency boost + entity overlap boost.
    res5 = search(query="Apollo outage production")
    top_result = res5["results"][0]
    assert "Outage" in top_result["metadata"]["title"]
    logger.info(f"Top ranked document title: '{top_result['metadata']['title']}' (Score: {top_result['score']})")
    logger.info("✓ Ranking boosts verified!")

    # Step 5: Test Structured Output response format
    logger.info("\n--- TEST 6: Structured Response Schema Compliance ---")
    required_keys = {"content", "score", "source", "source_type", "author", "timestamp", "url", "hierarchy", "entities", "metadata"}
    for key in required_keys:
        assert key in top_result
    logger.info("✓ Response schema compliance passed!")

    logger.info("\nAll Retrieval & Operational Intelligence tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(run_extended_search_verification())
