# 🚀 START HERE - Production-Grade Notion Crawler

## What You Have

A **complete, production-ready Notion workspace crawler system** that:
- Recursively extracts ALL content from Notion
- Normalizes everything to production-grade schemas
- Preserves hierarchy and metadata
- Handles pagination, retries, and rate limits
- Outputs normalized documents ready for embedding

**Status**: ✅ Ready to use immediately

---

## 5-Minute Start

### Step 1: Install (1 minute)
```bash
pip install -r /Users/rupamthxt/Projects/cord/backend/requirements_notion.txt
```

### Step 2: Get API Key (2 minutes)
1. Go to https://www.notion.com/my-integrations
2. Create integration → copy token
3. Set environment: `export NOTION_API_KEY="your_token"`

### Step 3: Run (1 minute)
```bash
cd /Users/rupamthxt/Projects/cord
python -m backend.connectors.notion_connector
```

**That's it!** You'll see:
```
✓ Extracted 47 documents
✓ Pages: 12
✓ Blocks: 234
✓ Databases: 3
✓ Duration: 15.3s
```

---

## What You Get

### Output: List of `MemoryDocument`

```python
{
    'id': 'notion_page_uuid',
    'title': 'Page Title',
    'content': 'Full text content here...',
    'path': '/Organization/Department/Project/Document',
    'url': 'https://notion.so/...',
    'created_time': datetime(...),
    'last_edited_time': datetime(...),
    'tags': ['engineering', 'incident'],
    'metadata': {
        'archived': False,
        'block_count': 12,
        'properties': {...}
    }
}
```

Ready for:
- ✅ Embedding
- ✅ Vector storage
- ✅ Semantic search
- ✅ RAG pipelines

---

## Files to Read (in order)

### 1. **This File** (📍 You are here)
   - Quick overview
   - Getting started

### 2. **QUICK_START_NOTION.md** (15 minutes)
   - Installation details
   - Configuration options
   - Common patterns
   - Troubleshooting

### 3. **ARCHITECTURE_DIAGRAM.md** (10 minutes)
   - Visual architecture
   - Data flow examples
   - System components
   - Type hierarchy

### 4. **README_NOTION_CRAWLER.md** (20 minutes)
   - Complete feature reference
   - All available options
   - Advanced configuration
   - Performance notes

### 5. **ARCHITECTURE_NOTION_SYSTEM.md** (30 minutes)
   - Deep technical details
   - Design principles
   - Component explanations
   - Production deployment

### 6. **Code Examples**
   - `backend/examples_notion_usage.py` - 8 real examples
   - `backend/test_notion_integration.py` - Tests
   - Docstrings in code

---

## Code Structure

```
🎯 Start here:
  backend/connectors/notion_connector.py
  ├─ Main orchestrator
  └─ Simple async API

Main components:
  notion_extraction/
  ├─ async_client.py          ← API wrapper
  ├─ crawler.py               ← Recursive engine
  ├─ block_extractor.py       ← 20+ block handlers
  └─ database_extractor.py    ← DB extraction

Utilities:
  notion_utils/
  ├─ logging_config.py        ← Structured logs
  ├─ pagination.py            ← Pagination
  └─ retry.py                 ← Retries + backoff

Pipeline:
  notion_normalization/
  └─ pipeline.py              ← Filtering, chunking

Schemas:
  notion_models/
  └─ schemas.py               ← Pydantic models
```

---

## Cheat Sheet

### Basic Crawl
```python
import asyncio
from backend.connectors.notion_connector import NotionConnector

connector = NotionConnector()
docs = await connector.fetch_workspace()
print(f"✓ {len(docs)} documents")
```

### With Configuration
```python
connector = NotionConnector(
    max_concurrent_requests=5,  # API rate limit
    max_depth=20,               # Max recursion
)

docs = await connector.fetch_workspace(
    start_page_id="optional_page_id"
)
```

### Get Statistics
```python
stats = connector.get_stats()
print(f"Pages: {stats.total_pages}")
print(f"Blocks: {stats.total_blocks}")
print(f"Duration: {stats.duration_seconds}s")
```

### Chunk for Embedding
```python
from backend.notion_normalization.pipeline import DocumentChunker

chunker = DocumentChunker()
chunks = chunker.chunk_documents(docs)

for chunk in chunks:
    embedding = model.encode(chunk['text'])
```

### Filter Documents
```python
# Recent documents
recent = [d for d in docs if d.last_edited_time > week_ago]

# By path
eng_docs = [d for d in docs if 'Engineering' in (d.path or '')]

# By size
substantial = [d for d in docs if len(d.content or '') > 500]
```

---

## Common Tasks

### Export to JSON
```python
import json

data = [{
    'title': d.title,
    'content': d.content[:500],
    'path': d.path,
    'url': d.url
} for d in docs]

with open('export.json', 'w') as f:
    json.dump(data, f, indent=2)
```

### Incremental Sync
```python
from datetime import datetime, timedelta

week_ago = datetime.now() - timedelta(days=7)
updated = [d for d in docs if d.last_edited_time > week_ago]
print(f"Updated: {len(updated)} documents")
```

### Preserve Hierarchy
```python
for doc in docs:
    # Full path (e.g., "/Org/Dept/Project/Doc")
    print(doc.path)
    
    # Parent ID
    print(doc.parent_id)
    
    # Metadata
    print(doc.metadata)
```

---

## What Gets Extracted

✅ **Pages**: Title, metadata, timestamps, properties
✅ **Blocks**: 20+ types (paragraphs, code, tables, etc.)
✅ **Rich Text**: Formatting, links, colors, annotations
✅ **Databases**: Schema, properties, all rows
✅ **Hierarchy**: Full paths, parent-child relationships
✅ **Metadata**: Created by, timestamps, archived status
✅ **Content**: Tables, lists, code blocks, embeds

❌ Not included (by design):
- Raw Notion API responses (normalized instead)
- Real-time webhooks (batch sync only)
- Comments (if API unavailable)

---

## Production Features

| Feature | Details |
|---------|---------|
| **Async** | Non-blocking throughout |
| **Pagination** | Transparent, complete |
| **Retries** | Exponential backoff |
| **Rate Limit** | Configurable concurrency |
| **Hierarchy** | Full paths preserved |
| **Type Safe** | Pydantic models |
| **Logging** | Structured JSON |
| **Stats** | Metrics tracking |
| **Error Recovery** | Graceful degradation |

---

## Example Output

```python
MemoryDocument(
    id='page_12345',
    source='notion',
    title='Engineering Incidents',
    path='/Engineering/Incidents',
    content='Root Cause Analysis\n\nThe system experienced an outage...',
    url='https://notion.so/...',
    created_time=datetime(2024, 5, 1, 10, 30),
    last_edited_time=datetime(2024, 5, 22, 14, 20),
    tags=['engineering', 'incident', 'postmortem'],
    metadata={
        'archived': False,
        'block_count': 24,
        'database_id': 'db_xyz',
        'properties': {...}
    }
)
```

---

## Troubleshooting

### "No API key found"
```bash
export NOTION_API_KEY="your_token_here"
```

### "No module named 'notion_client'"
```bash
pip install -r backend/requirements_notion.txt
```

### "Rate limited"
```python
# Reduce concurrency
connector = NotionConnector(max_concurrent_requests=2)
```

### "Taking too long"
```python
# Reduce recursion depth
connector = NotionConnector(max_depth=10)
```

---

## Next Steps

1. ✅ **Install dependencies** (1 min)
   ```bash
   pip install -r backend/requirements_notion.txt
   ```

2. ✅ **Set API key** (2 min)
   ```bash
   export NOTION_API_KEY="your_token"
   ```

3. ✅ **Run extraction** (1 min)
   ```bash
   python -m backend.connectors.notion_connector
   ```

4. 📖 **Read QUICK_START_NOTION.md** (15 min)
   - More options and examples

5. 🏗️ **Study ARCHITECTURE_DIAGRAM.md** (10 min)
   - Understand the architecture

6. 📚 **Check examples_notion_usage.py** (20 min)
   - See 8 production patterns

7. 🔧 **Configure for your needs** (varies)
   - Adjust concurrency, depth, retry
   - Add custom filters/enrichment
   - Integrate with embedding

---

## Support

- 📖 **Documentation**: See QUICK_START_NOTION.md
- 🏗️ **Architecture**: See ARCHITECTURE_DIAGRAM.md  
- 💡 **Examples**: See backend/examples_notion_usage.py
- 🧪 **Tests**: See backend/test_notion_integration.py
- 📝 **Code**: Fully documented docstrings

---

## Summary

You have a **production-ready Notion crawler** that:

- ✅ Works immediately with 3 commands
- ✅ Handles all content types automatically
- ✅ Preserves hierarchy and metadata
- ✅ Normalizes for downstream pipelines
- ✅ Includes error recovery & logging
- ✅ Comes with examples & tests
- ✅ Fully documented
- ✅ Enterprise-grade quality

**Start with**: `python -m backend.connectors.notion_connector`

**Questions?** Check the docs or examine the well-commented code.

Good luck! 🚀
