import uuid
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Header, HTTPException, Request

from qdrant_client.models import PointStruct
from backend.core.embeddings.model import get_embedding
from backend.core.models.setup_client import client
from backend.core.services.db_manager import DBManager
from backend.graph.db import get_db_session
from backend.graph.events.store import EventStore
from backend.graph.events.schema import EventCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks Ingestion"])

db_manager = DBManager()
event_store = EventStore()
EVENTS_COLLECTION = "workspace_events"

# Helper function to register webhook event in SQLite, PostgreSQL and Qdrant
async def register_webhook_event(
    source: str,
    event_type: str,
    title: str,
    summary: str,
    entities: list[str],
    workspace_id: str,
    metadata: dict
):
    event_id = f"event_{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # 1. Insert into SQLite Events
    db_manager.add_event(
        event_id=event_id,
        title=title,
        timestamp=timestamp,
        summary=summary,
        event_type=event_type,
        entities=entities,
        source_refs=[event_id],
        related_teams=[metadata.get("team", "unknown")],
        workspace_id=workspace_id
    )
    
    # 2. Insert into PostgreSQL (using SQLAlchemy event store)
    try:
        async with get_db_session() as session:
            payload = EventCreate(
                event_type=event_type,
                title=title,
                description=summary,
                timestamp=datetime.now(timezone.utc),
                source_chunk_id=event_id,
                workspace_id=workspace_id,
                severity=metadata.get("severity", "medium"),
                confidence=1.0,
                metadata=metadata
            )
            await event_store.create_event(session, payload)
    except Exception as e:
        logger.error(f"Failed to save webhook event to PostgreSQL: {e}", exc_info=True)
        
    # 3. Index in Qdrant workspace_events
    try:
        ts_unix = datetime.now(timezone.utc).timestamp()
        event_embedding = get_embedding(summary)
        client.upsert(
            collection_name=EVENTS_COLLECTION,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=event_embedding,
                    payload={
                        "event_id": event_id,
                        "title": title,
                        "timestamp": timestamp,
                        "timestamp_unix": ts_unix,
                        "summary": summary,
                        "event_type": event_type,
                        "entities": entities,
                        "source_refs": [event_id],
                        "related_teams": [metadata.get("team", "unknown")],
                        "workspace_id": workspace_id
                    }
                )
            ]
        )
    except Exception as e:
        logger.error(f"Failed to upsert webhook event to Qdrant: {e}", exc_info=True)


# Webhook requests schemas
class SlackEventVerification(BaseModel):
    token: str
    challenge: str
    type: str

@router.post("/slack/events")
async def handle_slack_webhook(request: Request):
    """
    Handles Slack Event Subscriptions.
    Supports challenge URL verification and logs message history dynamically.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    try:
        data = json.loads(body_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # URL Verification Challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    event_id = data.get("event_id") or f"slack_{uuid.uuid4()}"
    workspace_id = data.get("workspace_id", "default_workspace")
    db_manager.add_webhook_event(
        webhook_event_id=event_id,
        source="slack",
        payload=body_str,
        received_at=datetime.now(timezone.utc).isoformat(),
        workspace_id=workspace_id
    )

    event = data.get("event", {})
    # Map message to discussion event if in incident channel or mentions alert
    if event.get("type") == "message" and not event.get("subtype"):
        channel = event.get("channel", "")
        text = event.get("text", "")
        
        # Check channel keywords or message keywords
        if "incident" in channel or "alert" in text.lower() or "fail" in text.lower():
            await register_webhook_event(
                source="slack",
                event_type="incident",
                title=f"Slack Incident Chat: #{channel}",
                summary=text,
                entities=["slack", channel],
                workspace_id=workspace_id,
                metadata={
                    "channel": channel,
                    "user": event.get("user"),
                    "team": "Operations",
                    "severity": "medium"
                }
            )

    return {"status": "ok"}


@router.post("/github/events")
async def handle_github_webhook(request: Request, x_github_event: Optional[str] = Header(None)):
    """
    Handles GitHub deployment and release webhooks.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    try:
        data = json.loads(body_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = f"github_{uuid.uuid4()}"
    workspace_id = data.get("workspace_id", "default_workspace")
    db_manager.add_webhook_event(
        webhook_event_id=event_id,
        source="github",
        payload=body_str,
        received_at=datetime.now(timezone.utc).isoformat(),
        workspace_id=workspace_id
    )

    # Register release or deployment event
    repo = data.get("repository", {}).get("name", "unknown_repo")
    ref = data.get("ref", "main")
    
    # Check if deployment payload
    if data.get("deployment") or x_github_event == "deployment":
        deploy = data.get("deployment", {})
        environment = deploy.get("environment", "production")
        creator = deploy.get("creator", {}).get("login", "unknown_author")
        
        await register_webhook_event(
            source="github",
            event_type="deployment",
            title=f"GitHub Deployment: {repo} to {environment}",
            summary=f"Deployment of {repo} ({ref}) to {environment} triggered by {creator}.",
            entities=[repo, environment, "github"],
            workspace_id=workspace_id,
            metadata={
                "repository": repo,
                "ref": ref,
                "environment": environment,
                "author": creator,
                "team": "Engineering",
                "severity": "low"
            }
        )
    elif data.get("release") or x_github_event == "release":
        release = data.get("release", {})
        tag = release.get("tag_name", "v1.0.0")
        author = release.get("author", {}).get("login", "unknown")
        
        await register_webhook_event(
            source="github",
            event_type="release",
            title=f"GitHub Release: {repo} {tag}",
            summary=f"GitHub release {tag} published in repository {repo} by {author}.",
            entities=[repo, tag, "github"],
            workspace_id=workspace_id,
            metadata={
                "repository": repo,
                "tag": tag,
                "author": author,
                "team": "Engineering",
                "severity": "low"
            }
        )

    return {"status": "ok"}


@router.post("/sentry/alerts")
async def handle_sentry_webhook(request: Request):
    """
    Handles Sentry Exception/Alert webhooks.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    try:
        data = json.loads(body_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = f"sentry_{uuid.uuid4()}"
    workspace_id = data.get("workspace_id", "default_workspace")
    db_manager.add_webhook_event(
        webhook_event_id=event_id,
        source="sentry",
        payload=body_str,
        received_at=datetime.now(timezone.utc).isoformat(),
        workspace_id=workspace_id
    )

    # Register sentry incident
    project = data.get("project_name") or data.get("project") or "unknown_project"
    message = data.get("message") or data.get("error_message") or "Unknown error alert"
    level = data.get("level") or "error"
    
    severity_map = {
        "fatal": "critical",
        "error": "high",
        "warning": "medium",
        "info": "low",
        "debug": "low"
    }
    severity = severity_map.get(level.lower(), "high")

    await register_webhook_event(
        source="sentry",
        event_type="incident",
        title=f"Sentry Alert: {project} Exception",
        summary=message,
        entities=[project, "sentry", level],
        workspace_id=workspace_id,
        metadata={
            "project": project,
            "level": level,
            "team": "Platform",
            "severity": severity
        }
    )

    # Trigger proactive diagnostics and post to Slack in the background
    from backend.api.slack_bot import dispatch_proactive_alert_context
    import asyncio
    asyncio.create_task(
        dispatch_proactive_alert_context(
            workspace_id=workspace_id,
            alert_title=f"Sentry Alert: {project} Exception",
            alert_summary=message,
            severity=severity
        )
    )

    return {"status": "ok"}


@router.post("/stripe")
async def handle_stripe_webhook(request: Request):
    """
    Handles Stripe subscription and invoice events.
    Supports mock/local bypass for signature verification if secret key is mock or dummy.
    """
    import os
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    
    is_mock = not stripe_key or "dummy" in stripe_key or "mock" in stripe_key
    
    event = None
    if is_mock or not sig_header or not webhook_secret:
        try:
            event = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
    else:
        try:
            import stripe
            stripe.api_key = stripe_key
            event = stripe.Webhook.construct_event(
                payload_bytes, sig_header, webhook_secret
            )
        except Exception as e:
            logger.error(f"Stripe signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
            
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})
    
    logger.info(f"Received Stripe webhook event: {event_type}")
    
    if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
        metadata = data_object.get("metadata", {})
        workspace_id = metadata.get("workspace_id")
        
        if not workspace_id:
            workspace_id = data_object.get("client_reference_id")
            
        status = data_object.get("status")
        sub_id = data_object.get("id")
        customer_id = data_object.get("customer")
        
        if workspace_id:
            plan_level = "pro" if status in ["active", "trialing"] else "free"
            db_manager.update_workspace_subscription(
                workspace_id=workspace_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                subscription_status=status,
                plan_level=plan_level
            )
            logger.info(f"Updated workspace {workspace_id} subscription status to {status}, plan to {plan_level}")
            
    elif event_type == "customer.subscription.deleted":
        sub_id = data_object.get("id")
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT workspace_id FROM workspaces WHERE stripe_subscription_id = ?", (sub_id,)).fetchone()
        if row:
            workspace_id = row["workspace_id"]
            db_manager.update_workspace_subscription(
                workspace_id=workspace_id,
                subscription_status="canceled",
                plan_level="free"
            )
            logger.info(f"Canceled subscription for workspace {workspace_id}")
            
    return {"status": "ok"}
