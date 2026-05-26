"""
backend/events/pipeline.py
--------------------------
Orchestrates event extraction, deduplication, and PostgreSQL storage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.graph.events.extractor import event_extractor, OllamaEventExtractor
from backend.graph.events.schema import EventCreate, EventRelationshipCreate
from backend.graph.events.store import event_store, EventStore
from backend.graph.db import get_db_session

logger = logging.getLogger(__name__)


class EventExtractionPipeline:
    """Orchestrates event extraction, deduplication, title resolution, and database storage."""

    def __init__(self) -> None:
        self.extractor: OllamaEventExtractor = event_extractor
        self.event_store: EventStore = event_store

    async def process_chunk(
        self,
        chunk_text: str,
        chunk_id: str,
        workspace_id: str = "default_workspace",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runs the event extraction pipeline for a single chunk."""
        t_start = time.perf_counter()
        summary = {
            "events_found": 0,
            "events_new": 0,
            "relationships_stored": 0,
            "chunk_id": chunk_id,
            "workspace_id": workspace_id,
            "error": None,
        }

        try:
            # 1. Extract events and relationships from the text
            response = await self.extractor.extract(chunk_text)
            summary["events_found"] = len(response.events)

            if not response.events:
                return summary

            # 2. Process and save events within a database transaction
            async with get_db_session() as session:
                title_to_id = {}
                for ev in response.events:
                    payload = EventCreate(
                        event_type=ev.event_type,  # type: ignore[arg-type]
                        title=ev.title,
                        description=ev.description,
                        timestamp=ev.timestamp,
                        source_chunk_id=chunk_id,
                        workspace_id=workspace_id,
                        severity=ev.severity,      # type: ignore[arg-type]
                        confidence=ev.confidence,
                        metadata=ev.metadata,
                    )
                    db_event, created = await self.event_store.upsert_event(session, payload)
                    if created:
                        summary["events_new"] += 1
                    
                    title_to_id[ev.title.lower().strip()] = db_event.id

                # 3. Process and save event relationships
                for rel in response.relationships:
                    src_id = title_to_id.get(rel.source_title.lower().strip())
                    tgt_id = title_to_id.get(rel.target_title.lower().strip())

                    if src_id and tgt_id:
                        rel_payload = EventRelationshipCreate(
                            source_event_id=src_id,
                            target_event_id=tgt_id,
                            relationship_type=rel.relationship_type,  # type: ignore[arg-type]
                            confidence=rel.confidence,
                            workspace_id=workspace_id,
                        )
                        await self.event_store.upsert_relationship(session, rel_payload)
                        summary["relationships_stored"] += 1

            elapsed = time.perf_counter() - t_start
            logger.info(
                "EventPipeline process_chunk success | chunk=%s events_new=%d rels=%d elapsed=%.3fs",
                chunk_id,
                summary["events_new"],
                summary["relationships_stored"],
                elapsed,
            )

        except Exception as exc:
            logger.error("EventPipeline process_chunk failed for chunk %s: %s", chunk_id, exc, exc_info=True)
            summary["error"] = str(exc)

        return summary

    def process_chunk_sync(
        self,
        chunk_text: str,
        chunk_id: str,
        workspace_id: str = "default_workspace",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for background execution contexts."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(
                        self.process_chunk(chunk_text, chunk_id, workspace_id, metadata)
                    )
                )
                return future.result()
        else:
            return loop.run_until_complete(
                self.process_chunk(chunk_text, chunk_id, workspace_id, metadata)
            )


# Module-level singleton
event_extraction_pipeline = EventExtractionPipeline()
