import logging
from typing import List, Optional, Dict, Any
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range

from backend.models.setup_client import client
from backend.embeddings.model import get_embedding
from backend.retrieval.ranker import Ranker

logger = logging.getLogger(__name__)
COLLECTION_NAME = "workspace_memory"
ranker = Ranker()


def search(
    query: str,
    limit: int = 5,
    sources: Optional[List[str]] = None,
    author: Optional[str] = None,
    team: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    hierarchy_scope: Optional[str] = None,
    entities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Performs vector similarity search combined with metadata-aware filters
    and multi-dimensional ranking boosts. delegates to ReasoningPipeline.
    """
    from backend.retrieval.reasoning_pipeline import ReasoningPipeline
    pipeline = ReasoningPipeline(ranker=ranker)
    return pipeline.execute(
        query=query,
        limit=limit,
        sources=sources,
        author=author,
        team=team,
        start_time=start_time,
        end_time=end_time,
        hierarchy_scope=hierarchy_scope,
        entities=entities
    )