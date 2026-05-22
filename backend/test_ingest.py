from ingestion.chunker import chunk_text
from models.store_memory import store_chunks
from models.memory_schema import MemoryChunk

text = """
Customer onboarding delays are increasing.

The engineering team identified
deployment instability as a major cause.

Support tickets also increased
after the latest release.
"""

chunks = chunk_text(text)

store_chunks(
    chunks,
    metadata=MemoryChunk(
        source="customer_support",
        source_id="ticket_12345",
        author="John Doe",
        team="Support",
        timestamp="2024-06-01T12:00:00Z",
        document_title="Customer Support Ticket #12345",
        tags=["onboarding", "deployment", "support"]
    )
)