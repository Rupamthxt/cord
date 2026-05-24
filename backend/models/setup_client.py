import os
from qdrant_client import QdrantClient

qdrant_url = os.getenv("QDRANT_URL")
if qdrant_url:
    client = QdrantClient(url=qdrant_url)
else:
    try:
        # Try local docker first with short timeout
        client = QdrantClient(host="localhost", port=6333, timeout=1.0)
        client.get_collections()
    except Exception:
        # Fall back to in-memory Qdrant instance
        client = QdrantClient(":memory:")