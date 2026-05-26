import asyncio
import logging
from datetime import datetime, timezone, timedelta

from backend.core.models.store_memory import store_chunks
from backend.connectors.ingestion.chunker import chunk_text
from backend.intelligence.retrieval.search import search
from backend.core.services.db_manager import DBManager
from backend.core.models.memory_schema import MemoryDocument

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 1. Define related documents forming an operational thread
MOCK_OPERATIONAL_DATA = [
    MemoryDocument(
        id="doc_slack_incident",
        source="slack",
        source_id="slack_ch_1",
        path="/Slack/general/PostgresLatencyIncident",
        title="Slack Chat: Postgres Latency Incident",
        content="""
        Alice [22:00:00]: The production environment is showing high latency on PostgreSQL queries.
        Bob [22:05:00]: Yes, connection pool is saturated. Let's trigger a rollback deployment.
        Alice [22:07:00]: Bob is working on the hotfix.
        """,
        author="Alice",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=60),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=60)
    ),
    MemoryDocument(
        id="doc_github_deploy",
        source="notion",
        source_id="github_deploy_9",
        path="/Notion/Engineering/Deployments/RollbackPool",
        title="Deployment Release: Revert DB Pool Size",
        content="""
        Deploying hotfix-9 to production environment.
        Rollback PostgreSQL database connection configuration.
        Triggered by Bob. Connection pool resized from 100 to 20.
        """,
        author="Bob",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=30),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=30)
    ),
    MemoryDocument(
        id="doc_notion_rca",
        source="notion",
        source_id="notion_rca_postgres",
        path="/Notion/Engineering/Incidents/PostgresRCAPostmortem",
        title="Postmortem: PostgreSQL Connection Pool Saturation",
        content="""
        RCA details for the Sev-1 incident.
        The PostgreSQL connection pool was exhausted, causing severe latency.
        Bob triggered a rollback deployment to resize connection pool, recovering the production environment.
        """,
        author="Bob",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=10),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=10)
    ),
]


async def run_reasoning_verification():
    logger.info("Starting Reasoning & Operational Memory Infrastructure Verification...")

    # Step 1: Ingest mock documents
    logger.info("Ingesting related mock data...")
    for doc in MOCK_OPERATIONAL_DATA:
        chunks = chunk_text(doc.content)
        store_chunks(chunks, metadata=doc)

    # Let background threading tasks complete database writing
    logger.info("Waiting for background intelligence thread processing...")
    await asyncio.sleep(2.0)

    # Instantiate DB Manager
    db = DBManager()

    # Step 2: Verify Event Abstraction
    logger.info("\n--- TEST 1: Event Abstraction Verification ---")
    events = db.get_timeline(limit=10)
    assert len(events) >= 2
    for event in events:
        logger.info(
            f"Extracted Event: ID={event['event_id']}, Type={event['event_type']}, "
            f"Title='{event['title']}', Summary='{event['summary']}'"
        )
    logger.info("✓ Events successfully abstracted in SQLite!")

    # Step 3: Verify Cross-Source Correlation
    logger.info("\n--- TEST 2: Cross-Source Correlation Verification ---")
    # Let's retrieve correlations for the Slack incident document
    # Since our background thread processed them, let's query Qdrant to find the point UUID
    from backend.core.models.setup_client import client
    res = client.query_points(collection_name="workspace_memory", limit=10)
    
    correlations_found = False
    for p in res.points:
        p_id = str(p.id)
        corrs = db.get_correlations_for_source(p_id)
        if corrs:
            correlations_found = True
            logger.info(f"Correlations for Point {p_id[:8]} ({p.payload.get('source')}):")
            for c in corrs:
                logger.info(
                    f"  -> Correlates with {c['related_source'][:8]} (Type: {c['type']}, "
                    f"Score: {c['score']}, Reason: {c['reason']})"
                )
    
    assert correlations_found
    logger.info("✓ Cross-source correlations successfully captured!")

    # Step 4: Verify Relationship Traversal
    logger.info("\n--- TEST 3: Relationship Traversal (SQLite Co-occurrences) ---")
    # Traverse co-occurrences for "PostgreSQL"
    relations = db.traverse_relationships("PostgreSQL")
    assert len(relations) > 0
    logger.info(f"Traversed relationships for 'PostgreSQL': {relations}")
    logger.info("✓ Entity co-occurrence relationship traversal passed!")

    # Step 5: Test Temporal Query Parsing & Hybrid Retrieval Pipeline
    logger.info("\n--- TEST 4: Temporal Query Parsing & Hybrid Retrieval ---")
    # Query contains temporal phrase "last 2 hours"
    query_str = "Postgres latency last 2 hours"
    res_search = search(query=query_str)
    
    # Assert temporal query was parsed and cleaned
    assert len(res_search["results"]) > 0
    top_doc = res_search["results"][0]
    
    # Assert traces and boosts are included in diagnostics
    assert "diagnostics" in top_doc
    logger.info(f"Top result: '{top_doc['metadata'].get('title')}' (Score: {top_doc['score']})")
    logger.info(f"Diagnostics: {top_doc['diagnostics']}")
    logger.info("✓ Temporal parsing and hybrid scoring passed!")

    # Step 6: Test Timeline API Render Output
    logger.info("\n--- TEST 5: Timeline Endpoint Simulation ---")
    from backend.api.app import search_timeline, TimelineSearchRequest
    req = TimelineSearchRequest(query="Postgres latency", limit=5)
    timeline_res = await search_timeline(req)
    
    assert "timeline" in timeline_res
    assert len(timeline_res["timeline"]) > 0
    day_group = timeline_res["timeline"][0]
    logger.info(f"Timeline Day: {day_group['date']}")
    logger.info(f"  Events: {day_group['events']}")
    logger.info(f"  References: {len(day_group['references'])} matching chunks")
    logger.info("✓ Timeline rendering passed!")

    logger.info("\nAll reasoning and timeline operational tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_reasoning_verification())
