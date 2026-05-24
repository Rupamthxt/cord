import asyncio
import logging
from datetime import datetime, timezone, timedelta

from backend.models.store_memory import store_chunks
from backend.ingestion.chunker import chunk_text
from backend.models.memory_schema import MemoryDocument
from backend.reasoning.query_classifier import QueryClassifier
from backend.intelligence.evidence_aggregator import EvidenceAggregator
from backend.reasoning.root_cause_analyzer import RootCauseAnalyzer
from backend.intelligence.pipeline import OperationalIntelligencePipeline

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MOCK_INTEL_DATA = [
    # 1. Deployment
    MemoryDocument(
        id="doc_intel_deploy",
        source="notion",
        source_id="deploy_intel_service_a",
        path="/Notion/Engineering/Deployments/ServiceAPushIntel",
        title="Deployment Release: Service A version 2.3",
        content="""
        Deploying project ServiceA version 2.3 to production environment.
        Updated database pool config and connection timeouts.
        Triggered by Alice.
        """,
        author="Alice",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=45),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=45)
    ),
    # 2. Incident
    MemoryDocument(
        id="doc_intel_incident",
        source="slack",
        source_id="slack_incident_service_a_intel",
        path="/Slack/alerts/ServiceAConnectionOutageIntel",
        title="Incident Outage: Service A query latency surge",
        content="""
        Project ServiceA query latency surged in production environment.
        PostgreSQL connection pool exhausted. Triggered rollback deployment.
        Sev-1 escalated to DevOps.
        """,
        author="AlertSystem",
        created_time=datetime.now(timezone.utc) - timedelta(minutes=30),
        last_edited_time=datetime.now(timezone.utc) - timedelta(minutes=30)
    ),
]


async def run_intel_verification():
    logger.info("Starting Operational Intelligence Verification...")

    # Step 1: Ingest mock data
    logger.info("Ingesting mock dataset...")
    for doc in MOCK_INTEL_DATA:
        chunks = chunk_text(doc.content)
        store_chunks(chunks, metadata=doc)

    logger.info("Waiting for background intelligence processing...")
    await asyncio.sleep(2.5)

    # Step 2: Verify Query Classification
    logger.info("\n--- TEST 1: Query Classification Parsing ---")
    classifier = QueryClassifier()
    
    res_root = classifier.classify("Why did ServiceA fail after deployment?")
    logger.info(f"Classification: {res_root}")
    assert res_root["query_type"] == "root_cause_analysis"
    assert "why" in res_root["keywords_matched"]

    res_rec = classifier.classify("What recurring incident patterns occurred this week?")
    logger.info(f"Classification: {res_rec}")
    assert res_rec["query_type"] == "recurring_issue"

    logger.info("✓ Query classification passed!")

    # Step 3: Verify Evidence Aggregation
    logger.info("\n--- TEST 2: Evidence Aggregation ---")
    aggregator = EvidenceAggregator()
    evidence = aggregator.aggregate("ServiceA failure", limit=5)
    
    assert len(evidence["chunks"]) > 0
    assert len(evidence["events"]) > 0
    logger.info(f"Aggregated {len(evidence['chunks'])} chunks and {len(evidence['events'])} events.")
    logger.info("✓ Evidence aggregation passed!")

    # Step 4: Verify Root Cause Tracing
    logger.info("\n--- TEST 3: Root Cause Analysis Tracing ---")
    analyzer = RootCauseAnalyzer()
    analysis = analyzer.analyze("ServiceA why", evidence["events"], evidence["correlations"])
    
    assert len(analysis["chain"]) >= 2
    logger.info(f"Traced Chain: {[e['title'] for e in analysis['chain']]}")
    logger.info(f"Explanation Steps: {analysis['explanation_steps']}")
    logger.info("✓ Root cause analysis tracing passed!")

    # Step 5: Verify Pipeline Execution and API Simulation
    logger.info("\n--- TEST 4: API Endpoint Simulation ---")
    from backend.api.app import get_root_causes_insights, InsightsQueryRequest
    
    req = InsightsQueryRequest(query="Why did ServiceA fail after release v2.3?", limit=5)
    api_res = await get_root_causes_insights(req)
    
    assert "query" in api_res
    assert "insight" in api_res
    assert "evidence" in api_res
    assert "diagnostics" in api_res
    
    insight = api_res["insight"]
    logger.info(f"Summary: {insight['summary']}")
    logger.info(f"Key Findings: {insight['key_findings']}")
    logger.info(f"Confidence Score: {insight['confidence_score']}")
    
    assert insight["confidence_score"] > 0.5
    logger.info("✓ Operational intelligence pipeline execution passed!")
    logger.info("\nAll Operational Intelligence workflows completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_intel_verification())
