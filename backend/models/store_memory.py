import uuid

from qdrant_client.models import PointStruct

from backend.models.setup_client import client
from backend.embeddings.model import get_embedding

COLLECTION_NAME = "workspace_memory"

def store_chunks(chunks, metadata=None):

    points = []

    for chunk in chunks:

        embedding = get_embedding(chunk)

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "text": chunk,
                    "metadata": metadata or {}
                }
            )
        )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    print(f"Stored {len(points)} chunks")