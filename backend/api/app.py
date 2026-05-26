import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field

from backend.intelligence.retrieval.search import search

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

from backend.graph.router import router as graph_router
app.include_router(graph_router)

from backend.intelligence.insights.router import router as insights_router
app.include_router(insights_router, prefix="/insights")

from backend.api.pilot_router import router as pilot_router
app.include_router(pilot_router)

from backend.api.auth_router import router as auth_router
app.include_router(auth_router)

# Mount static files from root-level frontend directory

from fastapi.staticfiles import StaticFiles
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(project_root, "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


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


# ----------------------------------------------------
# Reasoning API Request Models
# ----------------------------------------------------

class EventsSearchRequest(BaseModel):
    query: Optional[str] = Field(default=None, description="Semantic search query over events.")
    event_type: Optional[str] = Field(default=None, description="Filter by event type (incident, deployment, meeting, escalation, discussion).")
    start_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range start.")
    end_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range end.")
    limit: int = Field(default=10, ge=1, le=100)


class TimelineSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query.")
    limit: int = Field(default=5, ge=1, le=50)
    hierarchy_scope: Optional[str] = Field(default=None, description="Scope query to specific hierarchy prefix.")
    start_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range start.")
    end_time: Optional[str] = Field(default=None, description="ISO-8601 timestamp range end.")


class CorrelationsSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic query to look up correlations.")
    limit: int = Field(default=5, ge=1, le=50)


class PatternsSearchRequest(BaseModel):
    query: Optional[str] = Field(default=None, description="Semantic or keyword filter over patterns.")
    pattern_type: Optional[str] = Field(default=None, description="Filter by pattern type (recurring_incident, escalation_chain, frequency_spike).")
    min_confidence: float = Field(default=0.0, description="Minimum pattern detection confidence.")
    limit: int = Field(default=10, ge=1, le=100)



# ----------------------------------------------------
# Reasoning API Endpoints
# ----------------------------------------------------

@app.post("/events/search", tags=["Reasoning"])
async def search_events(body: EventsSearchRequest):
    """
    Search for derived organizational events semantically or by metadata filtering.
    """
    try:
        if body.query:
            from backend.core.embeddings.model import get_embedding
            from backend.core.models.setup_client import client
            from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
            
            query_embedding = get_embedding(body.query)
            filter_conds = []
            
            if body.event_type:
                filter_conds.append(
                    FieldCondition(key="event_type", match=MatchValue(value=body.event_type))
                )
            if body.start_time or body.end_time:
                from datetime import datetime
                start_unix = datetime.fromisoformat(body.start_time.replace("Z", "+00:00")).timestamp() if body.start_time else None
                end_unix = datetime.fromisoformat(body.end_time.replace("Z", "+00:00")).timestamp() if body.end_time else None
                filter_conds.append(
                    FieldCondition(
                        key="timestamp_unix",
                        range=Range(gte=start_unix, lte=end_unix)
                    )
                )
                
            q_filter = Filter(must=filter_conds) if filter_conds else None
            
            try:
                results = client.query_points(
                    collection_name="workspace_events",
                    query=query_embedding,
                    query_filter=q_filter,
                    limit=body.limit
                )
                points_list = results.points or []
            except Exception as e:
                if "not found" in str(e).lower():
                    logger.warning("Qdrant collection 'workspace_events' not found. Returning empty results.")
                    points_list = []
                else:
                    raise e
            
            events = []
            for point in points_list:
                payload = point.payload or {}
                events.append({
                    "event_id": payload.get("event_id"),
                    "title": payload.get("title"),
                    "timestamp": payload.get("timestamp"),
                    "entities": payload.get("entities", []),
                    "source_refs": payload.get("source_refs", []),
                    "summary": payload.get("summary"),
                    "event_type": payload.get("event_type"),
                    "related_teams": payload.get("related_teams", []),
                    "score": round(point.score, 4)
                })
            return {"query": body.query, "events": events}
        else:
            from backend.core.services.db_manager import DBManager
            db = DBManager()
            events = db.get_timeline(
                start_time=body.start_time,
                end_time=body.end_time,
                limit=body.limit
            )
            return {"events": events}
    except Exception as e:
        logger.error(f"Events search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Event Search Error: {str(e)}")


@app.post("/timeline/search", tags=["Reasoning"])
async def search_timeline(body: TimelineSearchRequest):
    """
    Groups semantically matched documents and events chronologically
    in a day-by-day structured timeline.
    """
    try:
        # 1. Fetch chunks using the ReasoningPipeline search
        results = search(
            query=body.query,
            limit=body.limit * 2,
            start_time=body.start_time,
            end_time=body.end_time,
            hierarchy_scope=body.hierarchy_scope
        )

        grouped = {}
        
        # Group search results by day
        for doc in results.get("results", []):
            ts = doc.get("timestamp")
            if ts:
                day = ts.split("T")[0]
                grouped.setdefault(day, {"date": day, "events": [], "references": []})
                grouped[day]["references"].append(doc)

        # 2. Query events semantically to mix chronologically
        try:
            from backend.core.embeddings.model import get_embedding
            from backend.core.models.setup_client import client
            query_embedding = get_embedding(body.query)
            
            results_events = client.query_points(
                collection_name="workspace_events",
                query=query_embedding,
                limit=body.limit
            )
            
            for point in (results_events.points or []):
                payload = point.payload or {}
                ts = payload.get("timestamp", "")
                if ts:
                    day = ts.split("T")[0]
                    grouped.setdefault(day, {"date": day, "events": [], "references": []})
                    if not any(e["event_id"] == payload.get("event_id") for e in grouped[day]["events"]):
                        grouped[day]["events"].append({
                            "event_id": payload.get("event_id"),
                            "title": payload.get("title"),
                            "timestamp": ts,
                            "summary": payload.get("summary"),
                            "event_type": payload.get("event_type"),
                            "entities": payload.get("entities", []),
                            "related_teams": payload.get("related_teams", [])
                        })
        except Exception as ee:
            logger.warning(f"Failed to query events for timeline: {ee}")

        # Sort daily groups chronologically descending
        timeline = list(grouped.values())
        timeline.sort(key=lambda x: x["date"], reverse=True)

        return {
            "query": body.query,
            "timeline": timeline[:body.limit]
        }
    except Exception as e:
        logger.error(f"Timeline search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Timeline Search Error: {str(e)}")


@app.post("/correlations/search", tags=["Reasoning"])
async def search_correlations(body: CorrelationsSearchRequest):
    """
    Finds semantically matched chunks and maps their cross-source
    correlation context and traces.
    """
    try:
        results = search(query=body.query, limit=body.limit)
        
        from backend.core.services.db_manager import DBManager
        db = DBManager()
        
        correlations_output = []
        for doc in results.get("results", []):
            point_id = doc.get("id")
            related_contexts = []
            
            if point_id:
                correlations = db.get_correlations_for_source(point_id)
                for corr in correlations:
                    related_contexts.append({
                        "related_source_id": corr["related_source"],
                        "type": corr["type"],
                        "score": corr["score"],
                        "reason": corr["reason"],
                        "timestamp": corr["timestamp"]
                    })
            
            correlations_output.append({
                "document": {
                    "id": point_id,
                    "title": doc.get("metadata", {}).get("title") or doc.get("title", "Unknown"),
                    "source": doc.get("source"),
                    "source_type": doc.get("source_type"),
                    "content": doc.get("content")
                },
                "related_contexts": related_contexts
            })
            
        return {
            "query": body.query,
            "correlations": correlations_output
        }
    except Exception as e:
        logger.error(f"Correlations search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Correlations Search Error: {str(e)}")


@app.post("/patterns/search", tags=["Reasoning"])
async def search_patterns(body: PatternsSearchRequest):
    """
    Search for detected operational patterns and recurring issue trends.
    """
    try:
        from backend.core.services.db_manager import DBManager
        db = DBManager()
        
        # Retrieve patterns matching criteria from SQLite
        patterns = db.get_patterns(
            pattern_type=body.pattern_type,
            min_confidence=body.min_confidence,
            limit=body.limit
        )
        
        # If a query is provided, perform a simple filter matching the query text in name/description/entities
        if body.query:
            query_lower = body.query.lower()
            filtered_patterns = []
            for pat in patterns:
                in_name = query_lower in pat["name"].lower()
                in_desc = query_lower in pat["description"].lower()
                in_entities = any(query_lower in ent.lower() for ent in pat["entities"])
                if in_name or in_desc or in_entities:
                    filtered_patterns.append(pat)
            patterns = filtered_patterns
            
        return {
            "query": body.query,
            "patterns": patterns,
            "diagnostics": {
                "total_patterns_found": len(patterns),
                "filter_type": body.pattern_type,
                "min_confidence": body.min_confidence
            }
        }
    except Exception as e:
        logger.error(f"Patterns search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Patterns Search Error: {str(e)}")


# ----------------------------------------------------
# Operational Intelligence Request Schemas
# ----------------------------------------------------

class InsightsQueryRequest(BaseModel):
    query: str = Field(..., description="Query string for operational intelligence analysis.")
    limit: int = Field(default=10, ge=1, le=100)
    workspace_id: Optional[str] = Field(default="default_workspace", description="Strict workspace isolation scope.")


class JiraSyncRequest(BaseModel):
    workspace_id: Optional[str] = Field(default="default_workspace", description="Workspace ID to sync tickets into.")


# ----------------------------------------------------
# Operational Intelligence Routes
# ----------------------------------------------------

@app.post("/insights/operational-issues", tags=["Intelligence"])
async def get_operational_issues_insights(body: InsightsQueryRequest):
    """
    Surfaces recurring tickets, outages, and system errors with supporting evidence.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Operational issues insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Operational Issues Insight Error: {str(e)}")


@app.post("/insights/deployments", tags=["Intelligence"])
async def get_deployments_insights(body: InsightsQueryRequest):
    """
    Analyzes deployment history, release-related incidents, stability trends, and rollback events.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Deployments insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Deployments Insight Error: {str(e)}")


@app.post("/insights/incidents", tags=["Intelligence"])
async def get_incidents_insights(body: InsightsQueryRequest):
    """
    Analyzes incident clusters, postmortem document summaries, and severity metrics.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Incidents insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Incidents Insight Error: {str(e)}")


@app.post("/insights/issues", tags=["Intelligence"])
async def get_issues_insights(body: InsightsQueryRequest):
    """
    Backward compatible route surfacing recurring issues and errors.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Issues insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Issues Insight Error: {str(e)}")


@app.post("/insights/trends", tags=["Intelligence"])
async def get_trends_insights(body: InsightsQueryRequest):
    """
    Surfaces worsening delays, performance progressions, and operational trends over time.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Trends insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Trends Insight Error: {str(e)}")


@app.post("/insights/root-causes", tags=["Intelligence"])
async def get_root_causes_insights(body: InsightsQueryRequest):
    """
    Traces correlation chains and sequence paths to identify potential initial triggers.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Root causes insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Root Causes Insight Error: {str(e)}")


@app.post("/insights/escalations", tags=["Intelligence"])
async def get_escalations_insights(body: InsightsQueryRequest):
    """
    Traces incident escalation timelines, alert states, and team handoffs.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Escalations insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Escalations Insight Error: {str(e)}")


@app.post("/insights/bottlenecks", tags=["Intelligence"])
async def get_bottlenecks_insights(body: InsightsQueryRequest):
    """
    Identifies slower processes, deployment delays, and blocked resources.
    """
    try:
        from backend.intelligence.pipeline import OperationalIntelligencePipeline
        pipeline = OperationalIntelligencePipeline()
        res = pipeline.execute(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        return res
    except Exception as e:
        logger.error(f"Bottlenecks insight search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Bottlenecks Insight Error: {str(e)}")


# ----------------------------------------------------
# Integration Connectors Routes
# ----------------------------------------------------

@app.post("/connectors/jira/sync", tags=["Connectors"])
async def sync_jira_tickets(body: JiraSyncRequest):
    """
    Synchronizes tickets from the production-grade Jira connector.
    """
    try:
        from backend.connectors.jira.jira_connector import JiraConnector
        from backend.connectors.ingestion.chunker import chunk_text
        from backend.core.models.store_memory import store_chunks
        
        connector = JiraConnector(workspace_id=body.workspace_id)
        docs = connector.fetch()
        
        for doc in docs:
            chunks = chunk_text(doc.content)
            store_chunks(chunks, metadata=doc)
            
        return {"status": "success", "synced_tickets_count": len(docs)}
    except Exception as e:
        logger.error(f"Jira sync API failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Jira Sync Error: {str(e)}")


# ----------------------------------------------------
# Demo Simulation Routes
# ----------------------------------------------------




# ----------------------------------------------------
# UI Dashboard Web Server Route
# ----------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def get_dashboard():
    """
    Delivers the single-page glassmorphic HTML/JS dashboard dashboard workspace.
    """
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    frontend_dir = os.path.join(project_root, "frontend")
    index_path = os.path.join(frontend_dir, "index.html")
    try:
        with open(index_path, "r") as f:
            html_content = f.read()
        return html_content
    except Exception as ex:
        logger.error(f"Dashboard index.html loading failed: {ex}")
        return HTMLResponse(
            content=f"<h1>Dashboard index.html not found</h1><p>Please verify it exists at {index_path}. Details: {ex}</p>",
            status_code=404
        )


