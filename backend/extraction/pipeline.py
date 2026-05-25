"""
backend/extraction/pipeline.py
------------------------------
Main ExtractionPipeline coordinating Ollama extraction, entity deduplication,
and PostgreSQL graph storage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.entities.schema import EntityCreate
from backend.entities.store import entity_store, EntityStore
from backend.relationships.schema import RelationshipCreate
from backend.relationships.store import relationship_store, RelationshipStore
from backend.entities.deduplicator import entity_deduplicator, EntityDeduplicator
from backend.extraction.extractor import extractor, OllamaEntityExtractor
from backend.graph.db import get_db_session

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """Orchestrates the end-to-end extraction and resolution flow."""

    def __init__(self) -> None:
        self.extractor: OllamaEntityExtractor = extractor
        self.entity_store: EntityStore = entity_store
        self.relationship_store: RelationshipStore = relationship_store
        self.deduplicator: EntityDeduplicator = entity_deduplicator

    async def process_chunk(
        self,
        chunk_text: str,
        chunk_id: str,
        workspace_id: str = "default_workspace",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runs the extraction pipeline for a single chunk."""
        t_start = time.perf_counter()
        summary = {
            "entities_found": 0,
            "entities_new": 0,
            "relationships_stored": 0,
            "chunk_id": chunk_id,
            "workspace_id": workspace_id,
            "error": None,
        }

        try:
            # 1. Extract entities and relationships from the text
            response = await self.extractor.extract(chunk_text)
            summary["entities_found"] = len(response.entities)

            # 2. Process and resolve entities within a single DB transaction
            async with get_db_session() as session:
                name_to_id = {}
                for e in response.entities:
                    canonical = await self.deduplicator.resolve(
                        session, e.name, e.type, workspace_id
                    )
                    
                    if canonical is not None:
                        entity_id = canonical.id
                        # Update description if the canonical one is empty
                        if not canonical.description and e.description:
                            canonical.description = e.description
                        # Add alias to aliases_str if not present
                        existing_aliases = [
                            a.strip().lower()
                            for a in (canonical.aliases_str or "").split(",")
                            if a.strip()
                        ]
                        if (
                            e.name.lower() != canonical.name.lower()
                            and e.name.lower() not in existing_aliases
                        ):
                            if canonical.aliases_str:
                                canonical.aliases_str += f",{e.name}"
                            else:
                                canonical.aliases_str = e.name
                    else:
                        # Create new canonical entity
                        entity, created = await self.entity_store.get_or_create(
                            session,
                            name=e.name,
                            entity_type=e.type,
                            workspace_id=workspace_id,
                            source_chunk_id=chunk_id,
                            description=e.description,
                            aliases=[e.name],
                        )
                        entity_id = entity.id
                        if created:
                            summary["entities_new"] += 1

                    name_to_id[e.name.lower()] = entity_id

                    # 3. Add ChunkEntityRef
                    await self.entity_store.upsert_chunk_entity_ref(
                        session,
                        chunk_id=chunk_id,
                        entity_id=entity_id,
                        workspace_id=workspace_id,
                        mention_text=e.name,
                    )

                # 4. Resolve and save relationships
                for r in response.relationships:
                    source_id = name_to_id.get(r.source.lower())
                    target_id = name_to_id.get(r.target.lower())
                    
                    if source_id and target_id:
                        rel_create = RelationshipCreate(
                            source_entity_id=source_id,
                            target_entity_id=target_id,
                            relationship_type=r.type,  # type: ignore[arg-type]
                            confidence=r.confidence,
                            evidence=r.evidence,
                            source_chunk_id=chunk_id,
                            workspace_id=workspace_id,
                        )
                        await self.relationship_store.upsert_relationship(
                            session, rel_create
                        )
                        summary["relationships_stored"] += 1

            elapsed = time.perf_counter() - t_start
            logger.info(
                "Pipeline process_chunk success | chunk=%s entities_new=%d rels=%d elapsed=%.3fs",
                chunk_id,
                summary["entities_new"],
                summary["relationships_stored"],
                elapsed,
            )

        except Exception as exc:
            logger.error("Pipeline process_chunk failed for chunk %s: %s", chunk_id, exc, exc_info=True)
            summary["error"] = str(exc)

        return summary

    async def process_chunks_batch(
        self,
        chunks: List[Tuple[str, str, str]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Process multiple chunks sequentially to prevent DB lock/write conflicts."""
        results = []
        for text, chunk_id, ws_id in chunks:
            res = await self.process_chunk(text, chunk_id, ws_id, metadata)
            results.append(res)
        return results

    def process_chunk_sync(
        self,
        chunk_text: str,
        chunk_id: str,
        workspace_id: str = "default_workspace",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for existing background execution contexts."""
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


extraction_pipeline = ExtractionPipeline()
