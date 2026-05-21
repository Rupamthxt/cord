from models.setup_client import client
from embeddings.model import get_embedding

COLLECTION_NAME = "workspace_memory"

def search(query: str):

    query_embedding = get_embedding(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=5
    )

    return results