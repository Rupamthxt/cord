import asyncio
import logging
from datetime import datetime, timezone, timedelta

from backend.models.store_memory import store_chunks
from backend.ingestion.chunker import chunk_text
from backend.services.db_manager import DBManager
from backend.models.memory_schema import MemoryDocument

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define related documents forming an operational flow of issues
MOCK_OPERATIONAL_PATTERN_DATA = [
    # 1. Deployment event at T - 65 minutes
    MemoryDocument(
        id="doc_deploy_service_a",
        source="notion",
        source_id="deploy_service_a_v10",
        path="/Notion/Engineering/Deployments/ServiceAPush",
        title="Deployment Release: Service A Version 1.0.0",
        content="""
        Deploying project ServiceA version 1.0.0 to production environment.
        Changes include connection timeout tuning for database.
        Triggered by Alice.
        """,
        author="Alice",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=65),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=65)
    ),
    # 2. Incident event 15 minutes after deployment (T - 50 minutes)
    MemoryDocument(
        id="doc_incident_service_a_outage",
        source="slack",
        source_id="slack_incident_ch_1",
        path="/Slack/alerts/ServiceAConnectionOutage",
        title="Incident Outage: Service A database timeout failures",
        content="""
        Project ServiceA is throwing database connection timeout failures in production environment.
        PagerDuty alert triggered. Sev-2 incident escalated to DevOps team.
        Bob is investigating.
        """,
        author="AlertManager",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=50),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=50)
    ),
    # 3. Second Incident event 2 days ago sharing the same entity (ServiceA)
    MemoryDocument(
        id="doc_past_incident_service_a",
        source="notion",
        source_id="notion_incident_service_a_retro",
        path="/Notion/Engineering/Incidents/ServiceARetro",
        title="Incident Postmortem: Service A memory leak outage",
        content="""
        RCA report for Sev-1 incident from 2 days ago.
        Project ServiceA suffered a memory leak causing database timeouts.
        Re-routing traffic recovered the production environment.
        """,
        author="Bob",
        created_time=datetime.now(timezone.utc) - timedelta(days=2),
        last_edited_time=datetime.now(timezone.utc) - timedelta(days=2)
    ),
]


async def run_pattern_verification():
    logger.info("Starting Operational Pattern Detection Verification...")

    # Step 1: Ingest mock documents
    logger.info("Ingesting pattern mock data...")
    for doc in MOCK_OPERATIONAL_PATTERN_DATA:
        chunks = chunk_text(doc.content)
        store_chunks(chunks, metadata=doc)

    # Let background threading tasks complete database writing
    logger.info("Waiting for background intelligence thread processing...")
    await asyncio.sleep(2.5)

    # Instantiate DB Manager
    db = DBManager()

    # Step 2: Verify Escalation Chain Pattern detection
    logger.info("\n--- TEST 1: Escalation Chain Detection ---")
    patterns = db.get_patterns(pattern_type="escalation_chain")
    
    assert len(patterns) >= 1
    found_chain = False
    for pat in patterns:
        logger.info(
            f"Detected Pattern: ID={pat['pattern_id']}, Type={pat['pattern_type']}, "
            f"Name='{pat['name']}', Description='{pat['description']}'"
        )
        if "Service A" in pat["description"] or "ServiceA" in pat["description"]:
            found_chain = True
            assert len(pat["related_events"]) == 2
            assert pat["severity"] == "high"

    assert found_chain
    logger.info("✓ Escalation chain successfully captured!")

    # Step 3: Verify Recurring Incident Pattern detection
    logger.info("\n--- TEST 2: Recurring Incident Sequence ---")
    recurring_patterns = db.get_patterns(pattern_type="recurring_incident")
    
    assert len(recurring_patterns) >= 1
    found_recurring = False
    for pat in recurring_patterns:
        logger.info(
            f"Detected Pattern: ID={pat['pattern_id']}, Type={pat['pattern_type']}, "
            f"Name='{pat['name']}', Description='{pat['description']}'"
        )
        if "ServiceA" in pat["pattern_id"] or "servicea" in pat["pattern_id"]:
            found_recurring = True
            # Should link at least 2 events (the recent outage and the past postmortem)
            assert len(pat["related_events"]) >= 2
            assert pat["confidence"] > 0.7

    assert found_recurring
    logger.info("✓ Recurring incident sequence successfully captured!")

    # Step 4: Test API Endpoint Simulation
    logger.info("\n--- TEST 3: Pattern Search Endpoint Simulation ---")
    from backend.api.app import search_patterns, PatternsSearchRequest
    req = PatternsSearchRequest(query="ServiceA", limit=5)
    api_res = await search_patterns(req)
    
    assert "patterns" in api_res
    assert len(api_res["patterns"]) >= 1
    logger.info(f"API Search returned {len(api_res['patterns'])} patterns for query 'ServiceA'.")
    for pat in api_res["patterns"]:
        logger.info(f"  API Pattern Result: '{pat['name']}' (Confidence: {pat['confidence']})")

    logger.info("✓ Patterns search API simulation passed!")
    logger.info("\nAll Operational Pattern Detection tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_pattern_verification())
