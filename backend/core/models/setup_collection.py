from qdrant_client.models import Distance, VectorParams

from backend.core.models.setup_client import client

COLLECTION_NAME = "workspace_memory"

client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(
        size=384,
        distance=Distance.COSINE
    )
)

print("Collection created successfully.")