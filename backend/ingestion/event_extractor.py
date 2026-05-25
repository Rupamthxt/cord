import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from backend.embeddings.model import get_embedding
from backend.models.setup_client import client
from backend.services.db_manager import DBManager

logger = logging.getLogger(__name__)
db_manager = DBManager()
EVENTS_COLLECTION = "workspace_events"


class EventExtractor:
    """
    Analyzes content during ingestion to abstract organizational events
    (incidents, deployments, meetings, escalations) and indices them in both
    relational (SQLite) and semantic (Qdrant) layers.
    """

    # Keyword profiles for mapping event types
    CLASSIFIERS = {
        "incident": ["incident", "outage", "sev-", "severity", "downtime", "postmortem", "incident report", "rca", "incident-"],
        "deployment": ["deployment", "deploy", "release", "released", "shipped", "production push", "rollback", "migration"],
        "meeting": ["meeting", "sync", "standup", "retro", "retrospective", "weekly", "all-hands", "kickoff"],
        "escalation": ["escalation", "escalate", "escalated", "paged", "pagerduty", "alert", "pager"],
    }

    def __init__(self):
        self._ensure_events_collection()

    def _ensure_events_collection(self):
        """Verify that the Qdrant workspace_events collection is created."""
        try:
            client.get_collection(EVENTS_COLLECTION)
        except Exception:
            from qdrant_client.models import Distance, VectorParams
            client.create_collection(
                collection_name=EVENTS_COLLECTION,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Qdrant events collection '{EVENTS_COLLECTION}' created.")

    def detect_and_extract_event(
        self,
        chunk_text: str,
        chunk_id: str,
        metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyzes the chunk content. If it matches an event pattern,
        creates, stores, and indexes the event.
        """
        lower_text = chunk_text.lower()
        matched_type = None

        # Classify event based on keywords
        for event_type, keywords in self.CLASSIFIERS.items():
            if any(k in lower_text for k in keywords):
                matched_type = event_type
                break

        # If it doesn't match any operational event profile, skip event abstraction
        if not matched_type:
            # Fall back to general discussion if it's from slack or contains specific entities
            if metadata.get("source") == "slack" and len(chunk_text) > 40:
                matched_type = "discussion"
            else:
                return None

        # Derive a suitable Title
        doc_title = metadata.get("title") or metadata.get("document_title") or metadata.get("metadata", {}).get("title") or "discussion"
        if matched_type == "incident" and "incident" not in doc_title.lower() and "outage" not in doc_title.lower():
            title = f"Incident: {doc_title}"
        elif matched_type == "deployment" and "deploy" not in doc_title.lower() and "release" not in doc_title.lower():
            title = f"Deployment/Release: {doc_title}"
        else:
            title = doc_title

        # Timestamp parsing
        timestamp = metadata.get("timestamp") or metadata.get("created_time")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
        elif hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        else:
            timestamp = str(timestamp)

        # Generate event summary (e.g. first 2 sentences or first 180 chars)
        sentences = [s.strip() for s in chunk_text.replace("\n", " ").split(".") if s.strip()]
        summary = ". ".join(sentences[:2])
        if len(summary) > 200:
            summary = summary[:197] + "..."
        if not summary:
            summary = chunk_text[:200]

        # Extract entities from metadata
        entities = metadata.get("entities", [])
        team = metadata.get("team", "unknown")
        related_teams = [team] if team != "unknown" else []

        # Parse potential additional teams from entities
        for entity in entities:
            # If entity is formatted as 'TeamName (team)' or in a list
            if "team" in entity.lower() or entity in ["Engineering", "Product", "Support", "Devops"]:
                clean_team = entity.split(" ")[0]
                if clean_team not in related_teams:
                    related_teams.append(clean_team)

        event_id = f"event_{chunk_id}"

        workspace_id = metadata.get("workspace_id", "default_workspace")

        # 1. Store in SQLite Database
        db_manager.add_event(
            event_id=event_id,
            title=title,
            timestamp=timestamp,
            summary=summary,
            event_type=matched_type,
            entities=entities,
            source_refs=[chunk_id],
            related_teams=related_teams,
            workspace_id=workspace_id
        )

        # 2. Index in Qdrant events collection (semantic search enablement)
        try:
            # Index with a numeric unix timestamp for Qdrant Range compatibility
            try:
                ts_unix = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts_unix = datetime.now(timezone.utc).timestamp()

            from qdrant_client.models import PointStruct
            event_embedding = get_embedding(summary)
            client.upsert(
                collection_name=EVENTS_COLLECTION,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),  # Qdrant point UUID
                        vector=event_embedding,
                        payload={
                            "event_id": event_id,
                            "title": title,
                            "timestamp": timestamp,
                            "timestamp_unix": ts_unix,
                            "summary": summary,
                            "event_type": matched_type,
                            "entities": entities,
                            "source_refs": [chunk_id],
                            "related_teams": related_teams,
                            "workspace_id": workspace_id
                        }
                    )
                ]
            )
            logger.info(f"Operational Event '{title}' abstracted and indexed successfully.")
        except Exception as e:
            logger.error(f"Failed to upsert event to Qdrant: {e}", exc_info=True)

        return {
            "event_id": event_id,
            "title": title,
            "timestamp": timestamp,
            "entities": entities,
            "source_refs": [chunk_id],
            "summary": summary,
            "event_type": matched_type,
            "related_teams": related_teams
        }
