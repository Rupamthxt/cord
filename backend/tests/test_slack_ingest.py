import asyncio
import logging
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from backend.connectors.slack.slack_connector import SlackConnector
from backend.connectors.ingestion.chunker import chunk_text
from backend.core.models.store_memory import store_chunks

# Set up logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define Mock Responses
MOCK_MEMBERS = [
    {
        "id": "U1",
        "name": "john.doe",
        "real_name": "John Doe",
        "profile": {"display_name": "JohnDoe"},
    },
    {
        "id": "U2",
        "name": "jane.smith",
        "real_name": "Jane Smith",
        "profile": {"display_name": "JaneS"},
    },
]

MOCK_CHANNELS = [
    {"id": "C1", "name": "general", "is_channel": True},
    {"id": "C2", "name": "engineering", "is_channel": True},
]

MOCK_GENERAL_HISTORY = [
    {
        "type": "message",
        "ts": "1716550000.000000",
        "user": "U1",
        "text": "Hey <@U2>, did you see the database error?",
        "reply_count": 2,
    },
    {
        "type": "message",
        "ts": "1716570000.000000",
        "user": "U1",
        "text": "This is a standalone message from John on another topic.",
    },
]

MOCK_GENERAL_THREAD_REPLIES = [
    {
        "type": "message",
        "ts": "1716550000.000000",
        "user": "U1",
        "text": "Hey <@U2>, did you see the database error?",
        "thread_ts": "1716550000.000000",
    },
    {
        "type": "message",
        "ts": "1716550100.000000",
        "user": "U2",
        "text": "Yes John, I am looking into it now.",
        "thread_ts": "1716550000.000000",
    },
    {
        "type": "message",
        "ts": "1716550200.000000",
        "user": "U1",
        "text": "Awesome, thank you <@U2>!",
        "thread_ts": "1716550000.000000",
    },
]


async def run_mock_verification():
    """Runs a complete Slack ingestion simulation with mocked Slack API calls."""
    logger.info("Starting Slack Ingestion Verification (Mocked API)...")

    # Instantiate the connector with a fake token
    connector = SlackConnector(slack_token="xoxb-mock-token", lookback_days=10)

    # Initialize a mock AsyncWebClient using Patch
    mock_client_instance = AsyncMock()

    # Define mock behaviors
    async def mock_conversations_list(*args, **kwargs):
        return {"ok": True, "channels": MOCK_CHANNELS}

    async def mock_users_list(*args, **kwargs):
        return {"ok": True, "members": MOCK_MEMBERS}

    async def mock_conversations_history(*args, **kwargs):
        channel = kwargs.get("channel")
        if channel == "C1":
            return {"ok": True, "messages": MOCK_GENERAL_HISTORY}
        return {"ok": True, "messages": []}

    async def mock_conversations_replies(*args, **kwargs):
        channel = kwargs.get("channel")
        ts = kwargs.get("ts")
        if channel == "C1" and ts == "1716550000.000000":
            return {"ok": True, "messages": MOCK_GENERAL_THREAD_REPLIES}
        return {"ok": True, "messages": []}

    # Assign mocks to client wrapper calls
    mock_client_instance.client.conversations.list = mock_conversations_list
    mock_client_instance.client.users.list = mock_users_list
    mock_client_instance.client.conversations.history = mock_conversations_history
    mock_client_instance.client.conversations.replies = mock_conversations_replies

    # Patch the AsyncWebClient instantiation inside SlackClientAsync
    with patch(
        "backend.connectors.slack.slack_extraction.client.AsyncWebClient",
        return_value=mock_client_instance.client,
    ):
        # Trigger the fetch workspace pipeline
        documents = await connector.fetch_workspace()

        # Output summary of documents
        print(f"\n✓ Mock Ingestion generated {len(documents)} documents.")
        
        for doc in documents:
            print(f"\n--- Document Info ---")
            print(f"ID: {doc.id}")
            print(f"Path: {doc.path}")
            print(f"Title: {doc.title}")
            print(f"Content Preview:\n{doc.content}")
            print(f"Tags: {doc.tags}")
            print(f"Metadata: {doc.metadata}")

            # Verify chunking
            chunks = chunk_text(doc.content)
            print(f"Generated {len(chunks)} chunks.")

            # Store in Qdrant (will use the in-memory fallback client)
            store_chunks(chunks, metadata=doc.dict())

    print("\n✓ Ingestion verification completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_mock_verification())
