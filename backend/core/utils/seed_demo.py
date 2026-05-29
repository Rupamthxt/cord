import uuid
import json
import logging
from datetime import datetime, timezone
from qdrant_client.models import PointStruct, Distance, VectorParams

from backend.core.models.setup_client import client
from backend.core.embeddings.model import get_embedding
from backend.core.services.db_manager import DBManager

logger = logging.getLogger(__name__)

def seed_demo_workspace_data(workspace_id: str = "demo_workspace"):
    print(f"Seeding demo workspace: {workspace_id}...")
    db = DBManager()
    
    # 1. Ensure Qdrant Collections exist
    for col in ["workspace_memory", "workspace_events"]:
        try:
            client.get_collection(col)
        except Exception:
            client.create_collection(
                collection_name=col,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                )
            )
            print(f"Created Qdrant collection: {col}")

    # 2. Get or create users & link to demo_workspace
    owner_id = "demo_user"
    with db.get_connection() as conn:
        # Create a default demo user if no users exist
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (owner_id, "demo@cord.ai", "pbkdf2:sha256:mock_hash", datetime.now(timezone.utc).isoformat())
        )
        
        # Link workspace to ALL existing users so whoever logs in can see it
        users = conn.execute("SELECT user_id FROM users").fetchall()
        user_ids = [u["user_id"] for u in users]
        if owner_id not in user_ids:
            user_ids.append(owner_id)
            
    db.create_workspace(workspace_id=workspace_id, name="Demo Corporate Workspace", owner_id=owner_id)
    
    with db.get_connection() as conn:
        for uid in user_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_workspaces (user_id, workspace_id) VALUES (?, ?)",
                (uid, workspace_id)
            )

    # 3. Seed active credentials status for Notion, Slack, Jira
    db.save_connector_credentials(
        workspace_id=workspace_id,
        connector_type="notion",
        credentials_json=json.dumps({"token": "mock_notion_token", "start_page_id": "mock_page_id"}),
        status="configured"
    )
    db.save_connector_credentials(
        workspace_id=workspace_id,
        connector_type="slack",
        credentials_json=json.dumps({"bot_token": "mock_slack_token", "channels": "general,incident-room"}),
        status="configured"
    )
    db.save_connector_credentials(
        workspace_id=workspace_id,
        connector_type="jira",
        credentials_json=json.dumps({"token": "mock_jira_token"}),
        status="configured"
    )

    # 4. Define rich documents (workspace_memory)
    docs_data = [
        {
            "chunk_id": "chunk_jira_cor101",
            "text": "Jira Issue COR-101: Stripe webhook processing fails with database connection pool timeouts. During high traffic events, Stripe webhook validation calls time out. Active connections spike to the pool limit (10) causing subsequent requests to block. System: API Gateway. Component: Redis & PostgreSQL.",
            "source": "jira",
            "source_type": "ticket",
            "author": "Alice",
            "timestamp": "2026-05-22T09:45:00Z",
            "url": "https://jira.company.com/browse/COR-101",
            "hierarchy": ["Jira", "COR", "COR-101"],
            "team": "Platform Engineering",
            "entities": ["Stripe", "Redis", "PostgreSQL", "API Gateway", "webhook"]
        },
        {
            "chunk_id": "chunk_notion_redis",
            "text": "Notion: Redis Configuration Guidelines. The default pool size for api-gateway is 10 connections. In high-concurrency environments, increase pool size to 50 using REDIS_POOL_SIZE environment variable. Ensure max client connections on Redis server is set to 500.",
            "source": "notion",
            "source_type": "wiki_page",
            "author": "Bob",
            "timestamp": "2026-05-22T09:30:00Z",
            "url": "https://notion.company.com/pages/redis-configs",
            "hierarchy": ["Notion", "Infrastructure", "Redis Guidelines"],
            "team": "Platform Engineering",
            "entities": ["Redis", "API Gateway", "REDIS_POOL_SIZE"]
        },
        {
            "chunk_id": "chunk_slack_incident",
            "text": "Slack Conversation: #incident-api-gateway-outage. Alice: Sentry is showing high connection pool exhaustion. Bob: The new gateway deployment v2.4.0 might have a leak or misconfigured pool limit. Alice: Reverting to v2.3.9 solves the issue. I've initiated the rollback. Charlie: Let's increase REDIS_POOL_SIZE to 50 after this.",
            "source": "slack",
            "source_type": "chat_thread",
            "author": "Alice",
            "timestamp": "2026-05-22T10:15:00Z",
            "url": "https://slack.company.com/archives/incident-gateway/p12345",
            "hierarchy": ["Slack", "Channels", "incident-api-gateway-outage"],
            "team": "Platform Engineering",
            "entities": ["Slack", "Alice", "Bob", "v2.4.0", "v2.3.9", "REDIS_POOL_SIZE", "rollback"]
        }
    ]

    # Embed and upsert documents
    points_mem = []
    for doc in docs_data:
        emb = get_embedding(doc["text"])
        ts_unix = datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00")).timestamp()
        payload = {
            "text": doc["text"],
            "source": doc["source"],
            "source_type": doc["source_type"],
            "workspace_id": workspace_id,
            "author": doc["author"],
            "timestamp": doc["timestamp"],
            "timestamp_unix": ts_unix,
            "url": doc["url"],
            "hierarchy": doc["hierarchy"],
            "team": doc["team"],
            "entities": doc["entities"],
            "entity_details": [{"name": e, "type": "system" if e in ["Redis", "PostgreSQL", "API Gateway"] else "generic"} for e in doc["entities"]],
            "relationships": [{"type": "references_system", "target": e, "target_type": "system"} for e in doc["entities"] if e in ["Redis", "PostgreSQL", "API Gateway"]],
            "metadata": {
                "source": doc["source"],
                "workspace_id": workspace_id,
                "title": doc["text"].split(".")[0],
                "path": "/".join(doc["hierarchy"])
            }
        }
        points_mem.append(PointStruct(id=str(uuid.uuid4()), vector=emb, payload=payload))

    client.upsert(collection_name="workspace_memory", points=points_mem)
    print(f"Upserted {len(points_mem)} documents to Qdrant 'workspace_memory'.")

    # 5. Define rich events
    events_data = [
        {
            "event_id": "event_dep_v240",
            "title": "v2.4.0 API Gateway Rollout",
            "timestamp": "2026-05-22T10:00:00Z",
            "summary": "Deploys new JWT verification middleware and updates Redis client connection pool settings.",
            "event_type": "deployment",
            "entities": ["v2.4.0", "API Gateway", "Redis"],
            "source_refs": ["chunk_notion_redis"],
            "related_teams": ["Platform Engineering"]
        },
        {
            "event_id": "event_sentry_alert",
            "title": "Sentry Alert: DBConnectionError in api-gateway",
            "timestamp": "2026-05-22T10:05:00Z",
            "summary": "Database connection pool exhaustion detected. Active connections: 50/50. Pool limit reached.",
            "event_type": "incident",
            "entities": ["API Gateway", "Redis", "DBConnectionError"],
            "source_refs": ["chunk_jira_cor101"],
            "related_teams": ["Platform Engineering"]
        },
        {
            "event_id": "event_stripe_timeout",
            "title": "Stripe Webhook Delivery Timeout",
            "timestamp": "2026-05-22T10:08:00Z",
            "summary": "Stripe endpoints reporting 504 Gateway Timeout for customer payment webhooks.",
            "event_type": "incident",
            "entities": ["Stripe", "webhook"],
            "source_refs": ["chunk_jira_cor101"],
            "related_teams": ["Platform Engineering"]
        },
        {
            "event_id": "event_slack_discussion",
            "title": "Incident Room: #incident-api-gateway-outage Discussion",
            "timestamp": "2026-05-22T10:15:00Z",
            "summary": "@alice: Sentry alerts spiked. @bob: Gateway is dropping requests, looks like Redis pool exhaustion. @alice: Rollback initiated.",
            "event_type": "meeting",
            "entities": ["Slack", "Alice", "Bob", "Redis", "rollback"],
            "source_refs": ["chunk_slack_incident"],
            "related_teams": ["Platform Engineering"]
        },
        {
            "event_id": "event_dep_v239",
            "title": "v2.3.9 API Gateway Rollback",
            "timestamp": "2026-05-22T10:20:00Z",
            "summary": "Rollback api-gateway to v2.3.9. Connections restored to normal state.",
            "event_type": "deployment",
            "entities": ["v2.3.9", "API Gateway"],
            "source_refs": ["chunk_slack_incident"],
            "related_teams": ["Platform Engineering"]
        }
    ]

    points_ev = []
    # Clear existing SQLite events for this workspace first
    with db.get_connection() as conn:
        conn.execute("DELETE FROM events WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM correlations WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM patterns WHERE workspace_id = ?", (workspace_id,))

    for ev in events_data:
        # SQLite
        db.add_event(
            event_id=ev["event_id"],
            title=ev["title"],
            timestamp=ev["timestamp"],
            summary=ev["summary"],
            event_type=ev["event_type"],
            entities=ev["entities"],
            source_refs=ev["source_refs"],
            related_teams=ev["related_teams"],
            workspace_id=workspace_id
        )

        # Qdrant events
        emb = get_embedding(ev["summary"])
        ts_unix = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")).timestamp()
        points_ev.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "event_id": ev["event_id"],
                    "title": ev["title"],
                    "timestamp": ev["timestamp"],
                    "timestamp_unix": ts_unix,
                    "summary": ev["summary"],
                    "event_type": ev["event_type"],
                    "entities": ev["entities"],
                    "source_refs": ev["source_refs"],
                    "related_teams": ev["related_teams"],
                    "workspace_id": workspace_id
                }
            )
        )
    client.upsert(collection_name="workspace_events", points=points_ev)
    print(f"Upserted {len(points_ev)} events to Qdrant 'workspace_events' and SQLite.")

    # 6. Seed SQLite Correlations
    db.add_correlation(
        source_a="chunk_slack_incident",
        source_b="chunk_jira_cor101",
        c_type="shared_entities",
        score=0.95,
        reason="Both reference Stripe webhooks, Redis connection pool limits, and API Gateway stability during outages.",
        timestamp="2026-05-22T10:15:00Z",
        workspace_id=workspace_id
    )
    db.add_correlation(
        source_a="chunk_slack_incident",
        source_b="chunk_notion_redis",
        c_type="temporal_proximity",
        score=0.85,
        reason="Discusses Redis connection pool sizing recommendations to resolve thread starvation during the gateway incident window.",
        timestamp="2026-05-22T10:15:00Z",
        workspace_id=workspace_id
    )
    print("Seeded SQLite Correlations.")

    # 7. Seed SQLite Patterns
    db.add_pattern(
        pattern_id="pat_conn_pool_exhaustion",
        pattern_type="recurring_incident",
        name="Connection Pool Exhaustion",
        description="Repeated database/Redis connection pool starvation leading to HTTP 504 and webhook timeouts.",
        severity="high",
        confidence=0.9,
        last_detected="2026-05-22T10:20:00Z",
        entities=["Redis", "API Gateway", "Stripe"],
        related_events=["event_sentry_alert", "event_stripe_timeout"],
        workspace_id=workspace_id
    )
    print("Seeded SQLite Patterns.")
    print("Demo workspace seeding completed successfully!")

if __name__ == "__main__":
    seed_demo_workspace_data()
