```
╔══════════════════════════════════════════════════════════════════════════════╗
║         Production-Grade Notion Crawler - System Architecture               ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Your Application Code                             │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      NotionConnector (Orchestrator)                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ await connector.fetch_workspace(start_page_id=None)                  │  │
│  │ • Initializes async client                                          │  │
│  │ • Starts recursive crawler                                          │  │
│  │ • Applies normalization                                             │  │
│  │ • Returns List[MemoryDocument]                                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────┬──────────────────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌──────────────────┐  ┌──────────────────────────┐
│ NotionClientAsync│  │NotionWorkspaceCrawler    │
│                  │  │                          │
│ • Async wrapper  │  │ • Recursively traverses │
│ • Retry logic    │  │   ├─ Pages              │
│ • Rate limiting  │  │   ├─ Databases          │
│ • Pagination     │  │   ├─ Blocks             │
│ • Semaphore      │  │   └─ Hierarchy          │
│                  │  │                          │
│ Methods:         │  │ Features:                │
│ • get_page()     │  │ • Visited tracking      │
│ • get_blocks()   │  │ • Max depth limit       │
│ • search()       │  │ • Concurrent processing │
│ • query_db()     │  │ • Error recovery        │
│ • get_database() │  │ • Stats collection      │
└────────┬─────────┘  └────────┬─────────────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
     ┌──────────────────────────────────┐
     │   Extraction Layer (Normalizers)  │
     ├──────────────────────────────────┤
     │                                  │
     │  BlockExtractor                  │
     │  ├─ Paragraph handler            │
     │  ├─ Heading (1/2/3)              │
     │  ├─ List handlers                │
     │  ├─ Toggle handler               │
     │  ├─ Code handler                 │
     │  ├─ Table handler                │
     │  ├─ Database handler             │
     │  ├─ Rich text processor          │
     │  └─ 20+ block types              │
     │                                  │
     │  DatabaseExtractor               │
     │  ├─ Schema extraction            │
     │  ├─ Property type handlers       │
     │  ├─ Row value extraction         │
     │  └─ Relationship tracking        │
     │                                  │
     └──────────────────────────────────┘
                    │
                    ▼
     ┌──────────────────────────────────┐
     │  Data Models (Pydantic Schemas)  │
     ├──────────────────────────────────┤
     │                                  │
     │ • Block                          │
     │ • BlockHierarchy                 │
     │ • RichText                       │
     │ • RichTextAnnotation             │
     │ • DatabaseSchema                 │
     │ • DatabaseProperty               │
     │ • DatabaseRow                    │
     │ • MemoryDocument ⭐ (main output)│
     │ • WorkspaceNode                  │
     │ • ExtractionStats                │
     │                                  │
     └──────────────────────────────────┘
                    │
                    ▼
     ┌──────────────────────────────────┐
     │  Utility Modules                 │
     ├──────────────────────────────────┤
     │                                  │
     │ Pagination                       │
     │ ├─ paginate_list_items()         │
     │ └─ paginate_with_callback()      │
     │                                  │
     │ Retry                            │
     │ ├─ RetryConfig                   │
     │ └─ async_retry()                 │
     │                                  │
     │ Logging                          │
     │ ├─ StructuredLogger              │
     │ └─ JSON format output            │
     │                                  │
     └──────────────────────────────────┘
                    │
                    ▼
     ┌──────────────────────────────────┐
     │  Normalization Pipeline          │
     ├──────────────────────────────────┤
     │                                  │
     │ NormalizationPipeline            │
     │ ├─ Filter (min content length)   │
     │ ├─ Deduplicate (content hash)    │
     │ ├─ Validate (required fields)    │
     │ └─ Enrich (custom function)      │
     │                                  │
     │ DocumentChunker                  │
     │ ├─ Split by size                 │
     │ ├─ Preserve metadata             │
     │ └─ Overlap support               │
     │                                  │
     └──────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Normalized Output: List[MemoryDocument]                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ id: "page_uuid"                                                    │   │
│  │ title: "Page Title"                                                │   │
│  │ content: "Full text content..."                                    │   │
│  │ path: "/Org/Department/Project/Document"  ← Hierarchy preserved   │   │
│  │ url: "https://notion.so/..."                                      │   │
│  │ created_time: 2024-01-15T10:30:00                                 │   │
│  │ last_edited_time: 2024-05-22T14:20:00                             │   │
│  │ tags: ["engineering", "incident"]                                 │   │
│  │ metadata: {                                                        │   │
│  │   "archived": false,                                              │   │
│  │   "block_count": 12,                                              │   │
│  │   "database_id": "...",                                           │   │
│  │   ...                                                             │   │
│  │ }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼ (Never expose raw API responses downstream)
     ┌──────────────────────────────────┐
     │  Your Downstream Pipeline        │
     ├──────────────────────────────────┤
     │                                  │
     │ ❶ Embedding                     │
     │    └─ model.encode(doc.content) │
     │                                  │
     │ ❷ Vector Storage                │
     │    └─ vector_db.insert(...)      │
     │                                  │
     │ ❸ Indexing                      │
     │    └─ index.upsert(...)          │
     │                                  │
     └──────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════════╗
║                            Data Flow Example                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. Workspace Root (Notion)
   └─ Page "Engineering" (archived: false)
      ├─ Page "Incidents" (has_children: true)
      │  └─ Page "May Outage" (has_children: true)
      │     ├─ Block: Heading "Root Cause Analysis"
      │     ├─ Block: Paragraph "The issue started at..."
      │     ├─ Block: Code "Error trace..."
      │     └─ Block: Table (database rows)
      │
      ├─ Database "Projects"
      │  ├─ Row "Project A" (with properties)
      │  │  └─ Blocks: description, tasks, etc.
      │  ├─ Row "Project B"
      │  │  └─ Blocks: description, tasks, etc.
      │  └─ ...
      │
      └─ Page "Runbooks"
         └─ Page "Deployment"
            └─ Blocks: steps, code, etc.

↓ (Recursive crawl with block extraction)

2. Extracted MemoryDocuments
   ├─ MemoryDocument(
   │    id: "page_xyz_engineering",
   │    title: "Engineering",
   │    path: "/Engineering",
   │    content: "...",
   │    metadata: {...}
   │  )
   ├─ MemoryDocument(
   │    id: "page_abc_incidents",
   │    title: "Incidents",
   │    path: "/Engineering/Incidents",
   │    content: "...",
   │    metadata: {...}
   │  )
   ├─ MemoryDocument(
   │    id: "page_def_may_outage",
   │    title: "May Outage",
   │    path: "/Engineering/Incidents/May Outage",
   │    content: "Root Cause Analysis\nThe issue started at...\nError trace...",
   │    metadata: {...}
   │  )
   ├─ MemoryDocument(
   │    id: "db_row_project_a",
   │    title: "Project A",
   │    path: "/Engineering/Projects/Project A",
   │    content: "Project Name: A\nStatus: Active\nOwner: Team X\n...",
   │    metadata: {"database_id": "db_xyz"}
   │  )
   └─ ... (more documents)

↓ (Normalization: filter, deduplicate, validate)

3. Normalized Documents ready for embedding

╔══════════════════════════════════════════════════════════════════════════════╗
║                         Configuration Options                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

connector = NotionConnector(
    api_key="...",                      # or env: NOTION_API_KEY
    max_concurrent_requests=5,           # Rate limiting (requests/parallel)
    max_depth=20,                        # Max recursion depth
    retry_config=RetryConfig(
        max_retries=3,                   # Number of retries
        initial_delay=1.0,               # Initial delay (seconds)
        max_delay=32.0,                  # Max delay (seconds)
        exponential_base=2.0,            # Backoff multiplier
        jitter=True                      # Add randomness
    )
)

╔══════════════════════════════════════════════════════════════════════════════╗
║                        Performance Characteristics                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Concurrency:      Configurable (5 concurrent by default)
Pagination:       Transparent (handles all API pagination)
Memory Usage:     Streaming where possible
Recursion:        Configurable depth (20 by default)
Rate Limiting:    Respects Notion API limits (3-4 req/sec)
Error Recovery:   Retries + graceful degradation
Timeout Handling: Exponential backoff (max 32s)

Typical Performance:
- 100-page workspace:    10-30 seconds
- 1000-page workspace:   2-5 minutes
- Large workspace (10k+): Scales linearly with concurrency

╔══════════════════════════════════════════════════════════════════════════════╗
║                            Error Recovery Flow                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

API Call
   │
   ├─ Success ──────────────────┐
   │                            │
   ├─ Rate Limited (429) ───────┤ Retry after delay
   │                            │
   ├─ Timeout ──────────────────┤ Exponential backoff
   │                            │
   ├─ Network Error ────────────┤ Retry with jitter
   │                            │
   └─ Fatal Error ──────────────┤ Log and continue
                                │
                                ▼
                        Continue with next item
                        Log error with context
                        Update stats (error count)
                        Return partial results

╔══════════════════════════════════════════════════════════════════════════════╗
║                           Type Safety Pyramid                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

                          Type-Checked Output
                    List[MemoryDocument] ← Pydantic
                            /
                           /
                          /
              Normalized Internal Schemas
              (Block, DatabaseSchema, etc.)
                      /
                     /
                    /
            Extracted Raw Data
            (from API responses)
                  /
                 /
                /
        Raw Notion API
        (No longer trusted after extraction)
```

---

## Legend

- ⭐ = Main output
- ← = Direction of data flow
- └─ = Hierarchy/nesting
- ├─ = Item in list
- │ = Continuation line

---

## Key Takeaways

1. **Modular**: Each component has single responsibility
2. **Type-Safe**: Pydantic models for all data
3. **Async-First**: Non-blocking throughout
4. **Resilient**: Retries, error recovery, partial success
5. **Observable**: Structured logging + statistics
6. **Normalized**: Never expose raw API responses
7. **Hierarchical**: Preserves Notion's organizational structure
8. **Production-Ready**: Enterprise quality + reliability
