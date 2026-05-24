# Cord: Organizational Memory & Reasoning Intelligence Backend

Cord is a production-grade, metadata-aware organizational memory and operational reasoning intelligence backend. It crawls, ingests, and indexes communication channels (Slack) and structured documentation (Notion) into semantic vector databases (Qdrant) and a local relational network (SQLite). 

Cord uses a **multi-stage hybrid reasoning pipeline** to dynamically resolve temporal constraints, auto-correlate related events, map entity co-occurrences, and perform context-boosted document rankings.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% Ingestion Sources
    subgraph Ingestion Layer
        Slack[Slack Connector]
        Notion[Notion Connector]
    end

    %% Ingestion Pipeline
    subgraph Core Processing Pipeline
        Normalize[Normalization Pipeline]
        Chunker[Chunking & Standarization]
        Embeddings[Embedding Generation - BGE-Micro]
        EntityExt[Pattern Entity Extractor]
    end

    %% Storage
    subgraph Storage Layer
        Qdrant[(Qdrant Vector DB)]
        SQLite[(SQLite Relational DB)]
    end

    %% Background Processing
    subgraph Background Processing [Background Worker Thread]
        CorrEngine[Correlation Engine]
        EvExtractor[Event Extractor]
    end

    %% Retrieval Pipeline
    subgraph Reasoning Retrieval Pipeline
        QTemporal[Query Temporal Parser]
        QEntities[Query Entity Parser]
        Ranker[Multi-Dimensional Ranker]
        Pipeline[Reasoning Pipeline Executor]
    end

    %% APIs
    subgraph FastAPI Endpoints
        API_Search[POST /search]
        API_Events[POST /events/search]
        API_Timeline[POST /timeline/search]
        API_Corr[POST /correlations/search]
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
    Chunker -. Trigger Background .-> Background Processing
    CorrEngine --> SQLite
    EvExtractor --> SQLite
    EvExtractor --> Qdrant

    %% Search Flow
    API_Search --> Pipeline
    API_Events --> API_Events_Query{Query?}
    API_Events_Query -- Semantics --> Qdrant
    API_Events_Query -- Database --> SQLite
    API_Timeline --> Pipeline
    API_Timeline --> SQLite
    API_Corr --> Pipeline
    API_Corr --> SQLite

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

### 5. Graph Foundations & Relational Memory (SQLite)
- **`entity_cooccurrences`**: Lexicographically ordered entity pairs mapped with occurrence frequency and last seen timestamps.
- **`correlations`**: Tracks calculated similarities between chunks for diagnostic reference.
- **`events`**: Extracted operational events connected to their source chunks.

---

## 📂 Project Structure

```
backend/
├── api/
│   ├── __init__.py
│   └── app.py                      # FastAPI routes & middlewares
├── connectors/
│   ├── notion/                     # Notion API ingestion connector
│   └── slack/                      # Slack workspace crawler
├── embeddings/
│   ├── __init__.py
│   └── model.py                    # Embedding model wrapper (BGE-Micro-v2)
├── ingestion/
│   ├── chunker.py                  # Chunking algorithms
│   ├── entity_extractor.py         # Pattern-matching entity parsing
│   └── event_extractor.py          # Operational event classifier
├── main.py                         # FastAPI Uvicorn entrypoint
├── memory/
│   └── memory_store.db             # Local SQLite database [Gitignored]
├── models/
│   ├── memory_schema.py            # Pydantic schemas for data structures
│   ├── setup_client.py             # Qdrant client connection initializer
│   └── store_memory.py             # standardized metadata & ingestion trigger
├── retrieval/
│   ├── ranker.py                   # Multi-dimensional ranking boosts
│   ├── reasoning_pipeline.py       # Temporal query parser & search engine
│   └── search.py                   # Standard search route delegator
├── services/
│   ├── correlation_engine.py       # Cross-source correlation logic
│   └── db_manager.py               # SQLite schema & database transactions
├── tests/
│   ├── test_extended_search.py     # Base multi-dimensional boost tests
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

### 1. Standard Search
`POST /search`
Advanced semantic search with metadata-aware filtering, source attribution, and multi-dimensional ranking boosts.
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Postgres latency", "limit": 5}' \
  http://localhost:8000/search
```

### 2. Events Search
`POST /events/search`
Query abstracted operational events semantically or via time range / type filters.
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "database rollback", "event_type": "deployment", "limit": 5}' \
  http://localhost:8000/events/search
```

### 3. Chronological Timeline Search
`POST /timeline/search`
Groups matched chunks and events day-by-day.
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Postgres latency last 24 hours", "limit": 5}' \
  http://localhost:8000/timeline/search
```

### 4. Correlation Search
`POST /correlations/search`
Finds chunks matching a query and lists details of their cross-source/intra-source correlations.
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Postgres latency", "limit": 5}' \
  http://localhost:8000/correlations/search
```

---

## 🧪 Verification & Testing

Verify that all systems (ingestion, vector indexes, relation SQLite mappings, and query reasoners) are functioning correctly:

```bash
# Run Multi-Dimensional Search Tests
python -m backend.tests.test_extended_search

# Run Mock Slack Ingestion Tests
python -m backend.tests.test_slack_ingest

# Run Reasoning & Operational Intelligence Tests (Co-occurrences, Timelines, Correlations)
python -m backend.tests.test_reasoning_pipeline
```
