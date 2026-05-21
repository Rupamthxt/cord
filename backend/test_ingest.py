from ingestion.chunker import chunk_text
from models.store_memory import store_chunks

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
    metadata={
        "source": "test"
    }
)