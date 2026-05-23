# Production-Grade Notion Crawler

A comprehensive, production-ready system for recursively crawling and extracting ALL content from a Notion workspace.

## Features

### Core Capabilities
- **Recursive Workspace Traversal**: Crawls pages, databases, nested blocks with full hierarchy preservation
- **Complete Content Extraction**: Pages, blocks, databases, tables, lists, code, images, and more
- **Async-First Architecture**: Concurrent crawling with configurable rate limits and semaphore protection
- **Pagination Handling**: Fully transparent handling of all paginated APIs
- **Retry & Resilience**: Exponential backoff, graceful error recovery, partial failure tolerance

### Extracted Content Types
- ✅ Pages (with rich metadata)
- ✅ Nested child pages (recursive)
- ✅ Databases (schema + rows)
- ✅ All block types (paragraphs, headings, lists, toggles, code, tables, callouts, etc.)
- ✅ Rich text with annotations
- ✅ Embedded content (images, files, bookmarks)
- ✅ Database relationships
- ✅ Page hierarchy and paths
- ✅ Timestamps and authors
- ✅ Full metadata preservation

### Production Features
- **Structured Logging**: JSON-formatted logs for monitoring and debugging
- **Statistics Tracking**: Extraction stats (pages, blocks, databases, duration, errors)
- **Normalization Pipeline**: Document filtering, deduplication, enrichment
- **Type Safety**: Full Pydantic models with validation
- **Circular Reference Prevention**: Visited node tracking
- **Configurable Concurrency**: Control API call parallelism
- **Incremental Sync Support**: Track changes via last_edited_time

## Architecture

```
notion_models/
  schemas.py          # Pydantic models (Block, MemoryDocument, etc.)

notion_extraction/
  async_client.py     # Async Notion API wrapper
  crawler.py          # Recursive workspace crawler
  block_extractor.py  # Block type handlers
  database_extractor.py  # Database/row extraction

notion_utils/
  logging_config.py   # Structured logging
  pagination.py       # Pagination utilities
  retry.py            # Retry with exponential backoff

notion_normalization/
  pipeline.py         # Normalization + chunking

connectors/
  notion_connector.py  # Main orchestrator
```

## Usage

### Basic Setup

```python
import asyncio
from backend.connectors.notion_connector import NotionConnector

async def main():
    connector = NotionConnector(api_key="your-notion-api-key")
    documents = await connector.fetch_workspace()
    
    for doc in documents:
        print(f"📄 {doc.title}")
        print(f"   Path: {doc.path}")
        print(f"   Content: {doc.content[:200]}...")

asyncio.run(main())
```

### With Options

```python
connector = NotionConnector(
    max_concurrent_requests=5,  # API rate limiting
    max_depth=15,               # Recursion depth limit
    api_key="your-token"        # Or use NOTION_API_KEY env var
)

# Crawl from specific page instead of workspace root
documents = await connector.fetch_workspace(
    start_page_id="page_id_here",
    normalize=True  # Apply normalization
)
```

### Extraction Statistics

```python
stats = connector.get_stats()
print(f"Pages: {stats.total_pages}")
print(f"Blocks: {stats.total_blocks}")
print(f"Databases: {stats.total_databases}")
print(f"Duration: {stats.duration_seconds}s")
print(f"Errors: {stats.errors}")
```

### Document Chunking for Embedding

```python
from backend.notion_normalization.pipeline import DocumentChunker

chunker = DocumentChunker(chunk_size=1000, chunk_overlap=100)
chunks = chunker.chunk_documents(documents)

for chunk in chunks:
    # Ready for embeddings
    embedding = model.encode(chunk['text'])
```

### Hierarchy Preservation

```python
for doc in documents:
    print(doc.path)  # e.g., "/Engineering/Incidents/May/Outage"
    print(doc.parent_id)  # Parent page/database ID
    print(doc.metadata)  # Rich metadata dict
```

## Output Schema

All extracted content is normalized to `MemoryDocument`:

```python
class MemoryDocument(BaseModel):
    id: str                          # Notion ID
    source: str = "notion"
    source_id: str                   # Notion ID
    workspace_id: Optional[str]
    parent_id: Optional[str]         # Parent page/database
    path: Optional[str]              # Hierarchical path
    title: str                       # Page/block title
    content: str                     # Full text content
    url: Optional[str]               # Notion URL
    author: Optional[str]            # Created by
    created_time: datetime
    last_edited_time: datetime
    tags: List[str]
    metadata: Dict[str, Any]         # Block type, properties, etc.
```

### NOT Raw Notion Responses

The system deliberately avoids returning raw Notion API responses downstream. Everything is normalized to internal schemas for:
- Decoupling from API changes
- Semantic consistency
- Type safety
- Downstream compatibility

## Advanced Configuration

### Retry Behavior

```python
from backend.notion_utils.retry import RetryConfig

retry_config = RetryConfig(
    max_retries=5,
    initial_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True  # Add randomness to prevent thundering herd
)

connector = NotionConnector(retry_config=retry_config)
```

### Normalization Pipeline

```python
from backend.notion_normalization.pipeline import NormalizationPipeline

pipeline = NormalizationPipeline()
normalized = pipeline.process(
    documents,
    min_content_length=50,      # Filter short documents
    remove_duplicates=True,      # Content deduplication
    enrichment_fn=my_enrich_fn  # Optional custom enrichment
)
```

## Logging

Structured JSON logging for production monitoring:

```python
from backend.notion_utils.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Crawl started", workspace_id="ws_123")
logger.error("API failed", error="rate_limited", retry_count=3)
```

## Error Recovery

- Gracefully handles API failures
- Continues crawling on partial errors
- Tracks and reports error statistics
- Supports retry with exponential backoff
- Rate limit detection and handling

## Performance

- Async-first architecture for I/O efficiency
- Configurable concurrency control
- Pagination handles large datasets transparently
- Memory efficient: streams results where possible
- Circular reference prevention

## Limitations

- Respects Notion API rate limits (3-4 req/sec)
- Max depth configurable (default 20)
- Archive/trash handling via metadata
- Comments support (if API available)

## Environment Variables

```bash
export NOTION_API_KEY="your_notion_integration_token"
```

## Examples

See `examples_notion_usage.py` for:
- Basic workspace crawl
- Crawl from specific page
- Chunking for embedding
- Incremental sync patterns
- Hierarchy preservation
- Metadata extraction
- Document filtering
- JSON export

## Dependencies

```
notion-client>=2.0
pydantic>=2.0
```

## Future Enhancements

- Comment thread extraction
- OCR for embedded images
- Vector indexing integration
- Change stream subscriptions
- Batch operations
- Webhook support for real-time sync

---

**Status**: Production-ready for enterprise organizational memory platforms.
