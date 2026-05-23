"""
Quick start guide for the production-grade Notion crawler system.
"""

# Quick Start: Production-Grade Notion Crawler

## 1. Installation

```bash
pip install -r backend/requirements_notion.txt
```

## 2. Get Notion API Key

1. Go to https://www.notion.com/my-integrations
2. Create a new integration
3. Copy the "Internal Integration Token"
4. Set environment variable:
   ```bash
   export NOTION_API_KEY="your_token_here"
   ```

## 3. Basic Usage (3 lines)

```python
import asyncio
from backend.connectors.notion_connector import NotionConnector

async def main():
    connector = NotionConnector()
    documents = await connector.fetch_workspace()
    print(f"✓ Extracted {len(documents)} documents")

asyncio.run(main())
```

## 4. Run as Module

```bash
cd /Users/rupamthxt/Projects/cord
python -m backend.connectors.notion_connector
```

## 5. Key Features at a Glance

| Feature | How to Use |
|---------|-----------|
| **Recursive crawling** | Automatically traverses pages, databases, nested blocks |
| **Pagination** | Handled transparently - never truncates data |
| **Retry logic** | Automatic with exponential backoff (3 retries default) |
| **Rate limiting** | Configurable concurrency (5 requests default) |
| **Normalized output** | All documents returned as `MemoryDocument` objects |
| **Hierarchy preservation** | `doc.path` shows full organizational path |
| **Statistics** | `connector.get_stats()` returns extraction metrics |

## 6. Common Patterns

### Pattern 1: Extract and Chunk for Embedding

```python
connector = NotionConnector()
documents = await connector.fetch_workspace()

from backend.notion_normalization.pipeline import DocumentChunker
chunker = DocumentChunker()
chunks = chunker.chunk_documents(documents)
# Now ready for embedding: for chunk in chunks: embedding(chunk['text'])
```

### Pattern 2: Incremental Sync

```python
from datetime import datetime, timedelta

documents = await connector.fetch_workspace()

# Get only recently changed
week_ago = datetime.now() - timedelta(days=7)
recent = [d for d in documents if d.last_edited_time > week_ago]
```

### Pattern 3: Filter by Path

```python
documents = await connector.fetch_workspace()

# Get only engineering docs
eng_docs = [d for d in documents if 'Engineering' in (d.path or '')]

# Get top-level pages
top_level = [d for d in documents if d.path and d.path.count('/') == 0]
```

### Pattern 4: Export to JSON

```python
import json

documents = await connector.fetch_workspace()
data = [
    {
        'title': d.title,
        'content': d.content[:500],
        'path': d.path,
        'url': d.url,
    }
    for d in documents
]

with open('export.json', 'w') as f:
    json.dump(data, f, indent=2)
```

## 7. Configuration Options

```python
connector = NotionConnector(
    api_key="...",                    # Default: env var NOTION_API_KEY
    max_concurrent_requests=5,         # API call parallelism
    max_depth=20,                      # Max recursion depth
    retry_config=RetryConfig(...)      # Custom retry behavior
)
```

## 8. Understanding Output

Each `MemoryDocument` contains:

```python
{
    'id': 'page_uuid',                 # Notion ID
    'title': 'Page Title',             # Page/block name
    'content': '...',                  # Full text content
    'path': '/Parent/Child/Title',     # Hierarchical path
    'url': 'https://notion.so/...',   # Notion URL
    'created_time': datetime(...),     # Created timestamp
    'last_edited_time': datetime(...), # Last edit timestamp
    'metadata': {                      # Rich metadata dict
        'archived': False,
        'block_count': 12,
        'database_id': '...',
        ...
    }
}
```

## 9. What Gets Extracted

✅ All of this:
- Pages (with properties, metadata)
- Nested child pages (recursive)
- Databases (schema + all rows)
- Blocks: paragraphs, headings, lists, toggles, tables, code, quotes, callouts, images, files, bookmarks
- Rich text with formatting
- Database properties and values
- Hierarchy and relationships
- Timestamps and authors

❌ NOT extracted:
- Raw Notion API responses (normalized instead)
- Embedded blocks (metadata only)
- Comments (if not in API)

## 10. Troubleshooting

### "ModuleNotFoundError: No module named 'notion_client'"
```bash
pip install -r backend/requirements_notion.txt
```

### "No API key found"
```bash
export NOTION_API_KEY="your_token_here"
```

### "Rate limited (429)"
- System auto-retries with exponential backoff
- Reduce `max_concurrent_requests` if persistent:
  ```python
  connector = NotionConnector(max_concurrent_requests=2)
  ```

### "Extraction taking too long"
- Workspace is large
- Reduce `max_depth` to skip deep recursion
- Or increase concurrency if rate limit allows

## 11. Running Tests

```bash
# Test without API (schema, pagination, async)
python -m backend.test_notion_integration

# Full integration test (requires NOTION_API_KEY)
NOTION_API_KEY="..." python -m backend.test_notion_integration
```

## 12. Example Scripts

```bash
# Basic extraction
python -m backend.examples_notion_usage

# Run specific example
python -c "
import asyncio
from backend.examples_notion_usage import example_basic_crawl
asyncio.run(example_basic_crawl())
"
```

## 13. Architecture Overview

```
User Code
    ↓
NotionConnector (orchestrator)
    ├─→ NotionClientAsync (API wrapper + retry)
    ├─→ NotionWorkspaceCrawler (recursive traversal)
    │   ├─→ BlockExtractor (normalize blocks)
    │   └─→ DatabaseExtractor (normalize databases)
    └─→ NormalizationPipeline (filter + deduplicate)
    ↓
MemoryDocument[] (normalized output)
    ↓
Downstream (chunking, embedding, storage)
```

## 14. Production Readiness

✅ This system is production-ready:
- Type-safe (Pydantic models)
- Error recovery (retries + graceful degradation)
- Structured logging (JSON format)
- Rate limit handling
- Pagination transparency
- Circular reference prevention
- Comprehensive error messages

## 15. Next Steps

1. **Extract workspace**: `await connector.fetch_workspace()`
2. **Normalize docs**: `NormalizationPipeline().process(documents)`
3. **Chunk for embedding**: `DocumentChunker().chunk_documents(documents)`
4. **Embed chunks**: `model.encode(chunk['text'])`
5. **Store vectors**: Your vector DB of choice

---

For complete documentation, see:
- `README_NOTION_CRAWLER.md` - Full feature reference
- `backend/examples_notion_usage.py` - Usage examples
- `backend/test_notion_integration.py` - Test suite
