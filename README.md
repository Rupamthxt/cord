# Cord: Organizational Memory & Reasoning Intelligence Backend

Cord is a production-grade, metadata-aware organizational memory and operational reasoning intelligence backend. It crawls, ingests, and indexes communication channels (Slack) and structured documentation (Notion) into semantic vector databases (Qdrant) and a local relational network (SQLite). 

Cord uses a **multi-stage hybrid reasoning pipeline** to dynamically resolve temporal constraints, auto-correlate related events, map entity co-occurrences, and perform context-boosted document rankings.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% Ingestion Sources
    subgraph IngestionLayer ["Ingestion Layer"]
        Slack["Slack Connector"]
        Notion["Notion Connector"]
    end

    %% Ingestion Pipeline
    subgraph CoreProcessing ["Core Processing Pipeline"]
        Normalize["Normalization Pipeline"]
        Chunker["Chunking & Standardization"]
        Embeddings["Embedding Generation - BGE-Micro"]
        EntityExt["Pattern Entity Extractor"]
    end

    %% Storage
    subgraph StorageLayer ["Storage Layer"]
        Qdrant[("Qdrant Vector DB")]
        SQLite[("SQLite Relational DB")]
    end

    %% Background Processing
    subgraph BackgroundProcessing ["Background Worker Thread"]
        CorrEngine["Correlation Engine"]
        EvExtractor["Event Extractor"]
        PatDetector["Pattern Detector"]
    end

    %% Retrieval & Reasoning Pipeline
    subgraph ReasoningPipelines ["Reasoning & Intelligence Pipelines"]
        QTemporal["Query Temporal Parser"]
        QEntities["Query Entity Parser"]
        Ranker["Multi-Dimensional Ranker"]
        Pipeline["Reasoning Pipeline Executor"]
        
        QClassifier["Query Classifier"]
        EvAggregator["Evidence Aggregator"]
        RCAnalyzer["Root Cause Analyzer"]
        InsightSynth["Insight Synthesizer"]
        IntelPipeline["Intel Pipeline Orchestrator"]
    end

    %% APIs
    subgraph FastApiEndpoints ["FastAPI Endpoints"]
        API_Search["POST /search"]
        API_Events["POST /events/search"]
        API_Timeline["POST /timeline/search"]
        API_Corr["POST /correlations/search"]
        API_Patterns["POST /patterns/search"]
        
        API_Intel_Issues["POST /insights/issues"]
        API_Intel_Trends["POST /insights/trends"]
        API_Intel_Root["POST /insights/root-causes"]
        API_Intel_Esc["POST /insights/escalations"]
        API_Intel_Bot["POST /insights/bottlenecks"]
    end

    %% Ingestion Flow
    Slack --> Normalize
    Notion --> Normalize
    Normalize --> Chunker
    Chunker --> EntityExt
    Chunker --> Embeddings
    Embeddings --> Qdrant
    EntityExt --> Qdrant

    %% Background Hooks
    Chunker -. "Trigger Background" .-> BackgroundProcessing
    CorrEngine --> SQLite
    EvExtractor --> SQLite
    EvExtractor --> Qdrant
    PatDetector --> SQLite

    %% Search Flow
    API_Search --> Pipeline
    API_Events --> API_Events_Query{"Query?"}
    API_Events_Query -- "Semantics" --> Qdrant
    API_Events_Query -- "Database" --> SQLite
    API_Timeline --> Pipeline
    API_Timeline --> SQLite
    API_Corr --> Pipeline
    API_Corr --> SQLite
    API_Patterns --> SQLite

    %% Intel Flow
    API_Intel_Issues --> IntelPipeline
    API_Intel_Trends --> IntelPipeline
    API_Intel_Root --> IntelPipeline
    API_Intel_Esc --> IntelPipeline
    API_Intel_Bot --> IntelPipeline
    
    IntelPipeline --> QClassifier
    IntelPipeline --> EvAggregator
    IntelPipeline --> RCAnalyzer
    IntelPipeline --> InsightSynth
    
    Pipeline --> QTemporal
    Pipeline --> QEntities
    Pipeline --> Qdrant
    Pipeline --> Ranker
    Ranker --> SQLite
```

---

## 🌟 Key Features

### 1. Multi-Connector Ingestion
- **Slack Connector**: Crawls workspace message threads, resolves participants, and maps discussions.
- **Notion Connector**: Crawls page subtrees, preserves document layouts, page hierarchies, and metadata.

### 2. Multi-Dimensional Ranking
Scores retrieved chunks by combining semantic vector cosine similarity with metadata-based relevance boosts:
- **Recency Decay**: Exponential time-decay ($e^{-0.01 \cdot \text{days\_diff}}$) favoring newer operational documents.
- **Hierarchy Scope Scoping**: Boosts documents under a requested subtree prefix (e.g. `/Notion/Engineering/Incidents`).
- **Entity Matching**: Boosts matches containing overlapping entities extracted from the query.
- **Source Weighting**: Gives official wiki documentation a slight priority boost over informal chats.

### 3. Operational Event Abstraction
- Identifies and classifies operational event categories (incidents, deployments, meetings, escalations, discussions) from ingested text.
- Indexes events in **SQLite** and stores event vectors in a dedicated Qdrant `"workspace_events"` collection.

### 4. Cross-Source Correlation Engine
- Executed incrementally in an asynchronous background thread on new chunk ingestion.
- Matches documents across platforms using **temporal proximity** (< 1 hour, < 24 hours), **shared entity overlaps**, and **semantic similarity**.
- Resolves context-boosted signals (e.g., matching a production hotfix deployment document with a live Slack latency discussion).

### 5. Operational Pattern Detection Foundations
- **Recurring Incident Detector**: Detects when incidents or escalations sharing entities occur repeatedly (>= 2 times) within the last 7 days.
- **Escalation Chain Detector**: Scans for sequences of events where an incident, escalation, or general outage discussion occurs within 60 minutes of a deployment event.
- **Frequency Spike Detector**: Compares event volumes over the last 24 hours against the daily baseline of the preceding 7 days, flagging spikes.

### 6. Operational Intelligence Workflows (Decision Reasoning)
- **Query Classification Layer**: Tokenizes and profiles user query categories (e.g. root causes, trend analysis, bottlenecks).
- **Evidence Aggregator**: Gathers relevant semantic chunks, deduplicates content, scores evidence, and groups items chronologically.
- **Root Cause Analyzer**: Identifies chronological sequences and escalation pathways using database correlations.
- **Insight Synthesizer**: Compiles findings, maps chronological progression paths, and outputs combined confidence indicator scores.

---

## 📂 Project Structure

```
backend/
├── api/
│   ├── __init__.py
│   └── app.py                      # FastAPI routes, schemas & endpoints
├── connectors/
│   ├── notion/                     # Notion API crawl connector
│   └── slack/                      # Slack crawl connector
├── embeddings/
│   ├── __init__.py
│   └── model.py                    # Embedding model wrapper (BGE-Micro-v2)
├── ingestion/
│   ├── chunker.py                  # Chunking algorithms
│   ├── entity_extractor.py         # Pattern-matching entity parsing
│   └── event_extractor.py          # Operational event classifier
├── intelligence/
│   ├── __init__.py
│   ├── evidence_aggregator.py      # Evidence gathering and scoring engine [NEW]
│   ├── insight_synthesizer.py      # Structured insights compiler [NEW]
│   └── pipeline.py                 # Intel pipeline orchestrator [NEW]
├── main.py                         # FastAPI Uvicorn entrypoint
├── memory/
│   └── memory_store.db             # Local SQLite database [Gitignored]
├── models/
│   ├── memory_schema.py            # Pydantic schemas for data structures
│   ├── setup_client.py             # Qdrant client connection initializer
│   └── store_memory.py             # standardized metadata & ingestion trigger
├── reasoning/
│   ├── __init__.py
│   ├── query_classifier.py         # Operational query profiler [NEW]
│   └── root_cause_analyzer.py      # Correlation-based chain mapper [NEW]
├── retrieval/
│   ├── ranker.py                   # Multi-dimensional ranking boosts
│   ├── reasoning_pipeline.py       # Temporal query parser & search engine
│   └── search.py                   # Standard search route delegator
├── services/
│   ├── correlation_engine.py       # Cross-source correlation logic
│   ├── db_manager.py               # SQLite schema & database transactions
│   └── pattern_detector.py         # Incremental operational pattern detector
├── tests/
│   ├── test_extended_search.py     # Base multi-dimensional boost tests
│   ├── test_operational_intelligence.py # Intel pipeline verification tests [NEW]
│   ├── test_pattern_detection.py   # Pattern detection verification tests
│   ├── test_reasoning_pipeline.py  # Advanced reasoning, timeline & event tests
│   └── test_slack_ingest.py        # Slack mock ingestion tests
└── requirements.txt                # Project dependencies
```

---

## 🚀 Setup & Execution

### Prerequisites
- Python 3.10+
- Port 8000 free for the FastAPI server.

### Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### Launch the Live FastAPI Server
```bash
python -m backend.main
```
The server will start at `http://0.0.0.0:8000`.

---

## 📡 API Reference

### 1. Web UI Dashboard
`GET /`
Serves the premium, dark-themed, glassmorphic Single Page App (SPA) dashboard. Contains query execution console, interactive chronological timeline checklist, SQLite correlation link graphs, semantic evidence cards, and one-click demo controls.

### 2. Standard Search
`POST /search`
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Postgres latency", "limit": 5}' \
  http://localhost:8000/search
```

### 3. Chronological Timeline Search
`POST /timeline/search`
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Postgres latency last 24 hours", "limit": 5}' \
  http://localhost:8000/timeline/search
```

### 4. Patterns Search
`POST /patterns/search`
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "ServiceA", "limit": 5}' \
  http://localhost:8000/patterns/search
```

### 5. Workspace-Scoped Operational Insights
Retrieve structured query analytics, chronological triggers, and confidence diagnostics isolated by `workspace_id` (default: `"default_workspace"`).

- **Root Cause Insight**: `POST /insights/root-causes`
- **Deployments Insight**: `POST /insights/deployments`
- **Incidents Insight**: `POST /insights/incidents`
- **Trends Insight**: `POST /insights/trends`
- **Escalations Insight**: `POST /insights/escalations`
- **Bottlenecks Insight**: `POST /insights/bottlenecks`
- **Issues Insight**: `POST /insights/operational-issues`

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Why did ServiceA fail after release v2.3?", "limit": 5, "workspace_id": "production_workspace"}' \
  http://localhost:8000/insights/root-causes
```


### 6. Connector Integrations
- **Sync Jira Tickets**: `POST /connectors/jira/sync`
  Synchronizes tickets from the production-grade Jira connector mock client into the scoped workspace.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"workspace_id": "custom_workspace"}' \
    http://localhost:8000/connectors/jira/sync
  ```

### 7. Demo Simulations & Diagnostics
- **Run Live Incident Simulation**: `POST /demo/simulate`
  Ingests a cohesive sequence of events (Notion deployment doc, Slack database alarm thread, Jira bug ticket) into the pipeline to trigger and test live correlation scanners.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"workspace_id": "simulation_workspace"}' \
    http://localhost:8000/demo/simulate
  ```

---

## 🕸️ Entity Memory Graph Layer

Cord features a structured organizational entity and relationship graph layer built on PostgreSQL. It automatically parses text chunks using LLMs (local Ollama instance) or regex fallback logic to extract nodes (`person`, `team`, `project`, `incident`, `system`, etc.) and directed typed edges (`owns`, `depends_on`, `caused`, etc.), and links them to the underlying semantic document chunks.

### 🛢️ Database Configuration & Migrations
Specify the PostgreSQL connection string via the `GRAPH_DATABASE_URL` environment variable:
```bash
export GRAPH_DATABASE_URL="postgresql+asyncpg://cord:cord@localhost:5432/cord_graph"
```

Initialize the database schema (creates tables `cord_entities`, `cord_entity_aliases`, `cord_relationships`, and `cord_chunk_entity_refs`):
```bash
python -m backend.graph.migrations
```

### 🔗 Graph & Entity API Endpoints

- **Search Entities**: `POST /entities/search`
  Searches for entities within a workspace using a prefix or substring matcher.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"query": "apollo", "workspace_id": "default_workspace"}' \
    http://localhost:8000/entities/search
  ```

- **Graph Neighborhood (Ego-Graph)**: `GET /graph/neighborhood/{entity_id}`
  Retrieves incoming/outgoing edges up to 2 hops from the starting entity.
  ```bash
  curl http://localhost:8000/graph/neighborhood/550e8400-e29b-41d4-a716-446655440000?depth=1
  ```

- **Enriched Graph Search**: `POST /graph/search`
  Performs hybrid semantic search over Qdrant memory chunks, then enriches the results with related entity nodes and localized neighborhood relationships from PostgreSQL.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"query": "Why is the database slow?", "workspace_id": "default_workspace"}' \
    http://localhost:8000/graph/search
  ```

- **Direct Trigger Extraction**: `POST /extract/chunk`
  Manually triggers entity extraction and deduplication on a text chunk.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"text": "John Doe deployed Service A to production.", "chunk_id": "chunk_uuid_123"}' \
    http://localhost:8000/extract/chunk
  ```

- **Merge Entities**: `POST /entities/merge`
  Manually merges a duplicate entity into a canonical canonical record, updating all existing chunk references and relationships.
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"canonical_id": "uuid-1", "duplicate_id": "uuid-2"}' \
    http://localhost:8000/entities/merge
  ```

---


## 🧪 Verification & Testing

Verify that all systems (ingestion, vector indexes, relation SQLite mappings, query reasoners, intelligence synthesis pipelines, and security boundaries) are functioning correctly:

```bash
# Run Product Verification Tests (Jira Connector, API schemas, and Workspace Isolation Security boundaries)
python -m backend.tests.test_operational_product

# Run Multi-Dimensional Search Tests
python -m backend.tests.test_extended_search

# Run Mock Slack Ingestion Tests
python -m backend.tests.test_slack_ingest

# Run Reasoning & Operational Memory Tests
python -m backend.tests.test_reasoning_pipeline

# Run Pattern Detection Tests
python -m backend.tests.test_pattern_detection

# Run Operational Intelligence Pipeline Tests
python -m backend.tests.test_operational_intelligence
```
