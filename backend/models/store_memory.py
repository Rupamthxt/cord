import uuid
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from qdrant_client.models import PointStruct

from backend.models.setup_client import client
from backend.embeddings.model import get_embedding
from backend.ingestion.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)
COLLECTION_NAME = "workspace_memory"
extractor = EntityExtractor()


def run_incremental_intelligence(points_data: List[Tuple[str, str, List[float], Dict[str, Any]]]):
    """
    Background worker function that processes new ingestion chunks
    incrementally to map co-occurrences, compute correlations, and abstract events.
    """
    try:
        from backend.services.correlation_engine import CrossSourceCorrelationEngine
        from backend.ingestion.event_extractor import EventExtractor
        
        correlation_engine = CrossSourceCorrelationEngine()
        event_extractor = EventExtractor()
        
        logger.info(f"Background incremental processing started for {len(points_data)} chunks...")
        for chunk_id, text, embedding, payload in points_data:
            # 1. Update correlations and co-occurrence scores
            correlation_engine.process_new_chunk(chunk_id, text, embedding, payload)
            # 2. Extract operational events
            event = event_extractor.detect_and_extract_event(text, chunk_id, payload)
            if event:
                try:
                    from backend.services.pattern_detector import PatternDetector
                    pattern_detector = PatternDetector()
                    pattern_detector.analyze_event(event["event_id"], event)
                except Exception as pe:
                    logger.error(f"Failed to analyze patterns for event {event.get('event_id')}: {pe}", exc_info=True)
            
            # 3. Run organizational entity extraction (Ollama → PostgreSQL graph)
            try:
                from backend.extraction.pipeline import extraction_pipeline
                workspace_id = payload.get("workspace_id", "default_workspace")
                extraction_pipeline.process_chunk_sync(
                    chunk_text=text,
                    chunk_id=chunk_id,
                    workspace_id=workspace_id,
                    metadata=payload
                )
            except Exception as ee:
                logger.warning(f"Entity extraction skipped for chunk {chunk_id}: {ee}")
        logger.info("Background incremental processing completed.")

    except Exception as e:
        logger.error(f"Error in background incremental processing: {e}", exc_info=True)



def standardize_metadata(metadata: Any) -> Dict[str, Any]:
    """
    Standardizes various connector metadata formats into a unified layout.
    """
    standardized = {
        "source": "unknown",
        "source_type": "document",
        "author": "unknown",
        "timestamp": None,
        "url": None,
        "hierarchy": [],
        "team": "unknown",
        "original_metadata": {}
    }

    if not metadata:
        standardized["timestamp"] = datetime.now(timezone.utc).isoformat()
        return standardized

    # Convert Pydantic object to dict
    if hasattr(metadata, "dict"):
        meta_dict = metadata.dict()
    elif isinstance(metadata, dict):
        meta_dict = metadata
    else:
        meta_dict = {}

    standardized["original_metadata"] = meta_dict

    # Extract source
    if "source" in meta_dict and meta_dict["source"]:
        standardized["source"] = str(meta_dict["source"])

    # Determine source type
    if standardized["source"] == "slack":
        standardized["source_type"] = "chat_thread"
    elif standardized["source"] == "notion":
        standardized["source_type"] = "wiki_page"
    elif standardized["source"] == "jira":
        standardized["source_type"] = "ticket"
    elif "source_type" in meta_dict and meta_dict["source_type"]:
        standardized["source_type"] = str(meta_dict["source_type"])

    # Extract author
    for author_key in ["author", "created_by", "creator"]:
        if author_key in meta_dict and meta_dict[author_key]:
            standardized["author"] = str(meta_dict[author_key])
            break

    # Extract timestamp
    for time_key in ["timestamp", "created_time", "last_edited_time", "date"]:
        if time_key in meta_dict and meta_dict[time_key]:
            val = meta_dict[time_key]
            if hasattr(val, "isoformat"):
                standardized["timestamp"] = val.isoformat()
            else:
                standardized["timestamp"] = str(val)
            break

    if not standardized["timestamp"]:
        standardized["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Extract URL
    if "url" in meta_dict and meta_dict["url"]:
        standardized["url"] = str(meta_dict["url"])

    # Extract hierarchy (from path or explicit)
    path = meta_dict.get("path")
    if path:
        parts = [p for p in path.split("/") if p]
        standardized["hierarchy"] = parts
    elif "hierarchy" in meta_dict and meta_dict["hierarchy"]:
        if isinstance(meta_dict["hierarchy"], list):
            standardized["hierarchy"] = meta_dict["hierarchy"]
        else:
            standardized["hierarchy"] = [p for p in str(meta_dict["hierarchy"]).split("/") if p]

    # Extract team
    if "team" in meta_dict and meta_dict["team"]:
        standardized["team"] = str(meta_dict["team"])
    elif standardized["source"] == "slack" and "channel_name" in meta_dict:
        standardized["team"] = str(meta_dict["channel_name"])

    return standardized


def store_chunks(chunks, metadata=None):
    # Ensure collection exists
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        from qdrant_client.models import Distance, VectorParams
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE
            )
        )

    # Standardize document-level metadata
    std_meta = standardize_metadata(metadata)
    points = []

    for chunk in chunks:
        # Extract entities from the chunk text
        extraction = extractor.extract(chunk)
        chunk_entities = extraction["entities"]
        chunk_entity_details = extraction["details"]

        # Merge with document tags if present
        doc_tags = std_meta["original_metadata"].get("tags", [])
        combined_entities_set = set(chunk_entities)
        for tag in doc_tags:
            combined_entities_set.add(tag)

        # Build relationships
        relationships = []
        
        # 1. Hierarchy link (child_of parent document)
        parent_id = std_meta["original_metadata"].get("parent_id")
        if parent_id:
            relationships.append({
                "type": "child_of",
                "target": str(parent_id),
                "target_type": "document"
            })
            
        # 2. Entity reference links (references person/project)
        for detail in chunk_entity_details:
            if detail["type"] in ["person", "project", "system"]:
                relationships.append({
                    "type": f"references_{detail['type']}",
                    "target": detail["name"],
                    "target_type": detail["type"]
                })

        embedding = get_embedding(chunk)

        # Build structured payload matching intelligence expectations
        ts_iso = std_meta["timestamp"]
        try:
            ts_unix = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts_unix = datetime.now(timezone.utc).timestamp()

        payload = {
            "text": chunk,
            "source": std_meta["source"],
            "source_type": std_meta["source_type"],
            "workspace_id": std_meta["original_metadata"].get("workspace_id") or "default_workspace",
            "author": std_meta["author"],
            "timestamp": ts_iso,
            "timestamp_unix": ts_unix,
            "url": std_meta["url"],
            "hierarchy": std_meta["hierarchy"],
            "team": std_meta["team"],
            "entities": list(combined_entities_set),
            "entity_details": chunk_entity_details,
            "relationships": relationships,
            "metadata": std_meta["original_metadata"]  # preserving original structure
        }

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload
            )
        )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    # Launch background intelligence processing asynchronously
    try:
        points_data = [
            (p.id, p.payload["text"], p.vector, p.payload)
            for p in points
        ]
        bg_thread = threading.Thread(
            target=run_incremental_intelligence,
            args=(points_data,),
            daemon=True
        )
        bg_thread.start()
    except Exception as e:
        logger.error(f"Failed to start background intelligence thread: {e}")

    logger.info(f"Stored {len(points)} chunks with standardized metadata and entity extraction.")
    print(f"Stored {len(points)} chunks")