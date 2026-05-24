import time
import logging
from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.retrieval.search import search

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Organizational Memory & Operational Intelligence API",
    description="Backend service providing metadata-aware semantic retrieval, entity alignment, and hierarchy search.",
    version="1.1.0"
)


# Request schemas
class SearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query text.")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum number of results to return.")
    sources: Optional[List[str]] = Field(default=None, description="Filter results by source (e.g. ['slack', 'notion']).")
    author: Optional[str] = Field(default=None, description="Filter results by document author.")
    team: Optional[str] = Field(default=None, description="Filter results by team or channel name.")
    start_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range start.")
    end_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range end.")
    hierarchy_scope: Optional[str] = Field(default=None, description="Scope query within specific hierarchy branch prefix.")
    entities: Optional[List[str]] = Field(default=None, description="Filter by extracted entity names (e.g., ['Apollo', 'JohnDoe']).")


# Observability middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"API Request: method={request.method} path={request.url.path} "
        f"status={response.status_code} duration={duration:.4f}s"
    )
    return response


@app.get("/health", tags=["Diagnostic"])
async def health_check():
    """Returns the operational status of the service."""
    return {"status": "healthy", "timestamp": time.time()}


@app.post("/search", tags=["Retrieval"])
async def post_search(body: SearchRequest):
    """
    Advanced semantic search with metadata-aware filtering, source attribution,
    and multi-dimensional ranking boosts.
    """
    try:
        results = search(
            query=body.query,
            limit=body.limit,
            sources=body.sources,
            author=body.author,
            team=body.team,
            start_time=body.start_time,
            end_time=body.end_time,
            hierarchy_scope=body.hierarchy_scope,
            entities=body.entities
        )
        return results
    except Exception as e:
        logger.error(f"Search endpoint execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Search Error: {str(e)}")


@app.get("/search", tags=["Retrieval"])
async def get_search(
    query: str = Query(..., description="Semantic query text"),
    limit: int = Query(default=5, ge=1, le=50),
    source: Optional[str] = Query(default=None, description="Comma-separated list of sources to filter (e.g. 'slack,notion')"),
    author: Optional[str] = Query(default=None),
    team: Optional[str] = Query(default=None),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    hierarchy_scope: Optional[str] = Query(default=None),
    entity: Optional[str] = Query(default=None, description="Comma-separated list of entities to filter")
):
    """
    HTTP GET endpoint for search. Maintained for simple integrations, backwards compatibility,
    and quick query execution.
    """
    sources_list = [s.strip() for s in source.split(",")] if source else None
    entities_list = [e.strip() for e in entity.split(",")] if entity else None

    try:
        results = search(
            query=query,
            limit=limit,
            sources=sources_list,
            author=author,
            team=team,
            start_time=start_time,
            end_time=end_time,
            hierarchy_scope=hierarchy_scope,
            entities=entities_list
        )
        return results
    except Exception as e:
        logger.error(f"GET search endpoint execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Search Error: {str(e)}")
