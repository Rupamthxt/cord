"""
Production-grade Slack connector implementing workspace crawling,
conversation extraction, normalization, and preparation for downstream pipelines.
"""

import os
import asyncio
import logging
from typing import List, Optional
from backend.models.memory_schema import MemoryDocument
from backend.utils.pipeline import NormalizationPipeline
from backend.connectors.slack.slack_extraction.client import SlackClientAsync
from backend.connectors.slack.slack_extraction.crawler import SlackWorkspaceCrawler
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)



class SlackConnector:
    """
    Production-grade connector for Slack workspaces.
    
    Implements:
    - Async-first architecture
    - Channel filtering and time-based lookback windows
    - User cache and username resolution (replacing user IDs in text)
    - Rate limit backoff (exponential retry on 429)
    - Reusable normalization pipeline
    """

    def __init__(
        self,
        slack_token: Optional[str] = None,
        lookback_days: Optional[int] = 30,
        max_concurrent_requests: int = 5,
    ):
        """
        Initialize Slack connector.
        
        Args:
            slack_token: Slack Bot User OAuth Token (defaults to SLACK_BOT_TOKEN env var)
            lookback_days: Restrict history crawl to last N days (None for all history)
            max_concurrent_requests: Max concurrent API requests to Slack
        """
        self.slack_token = slack_token or os.getenv("SLACK_BOT_TOKEN")
        if not self.slack_token:
            raise ValueError("SLACK_BOT_TOKEN environment variable or slack_token parameter required")

        self.lookback_days = lookback_days
        self.max_concurrent_requests = max_concurrent_requests
        
        self.client: Optional[SlackClientAsync] = None
        self.crawler: Optional[SlackWorkspaceCrawler] = None
        self.documents: List[MemoryDocument] = []

        logger.info("Slack connector initialized")

    async def fetch_workspace(
        self,
        channel_filters: Optional[List[str]] = None,
        normalize: bool = True,
    ) -> List[MemoryDocument]:
        """
        Crawl and extract channels, messages, and threads from Slack.
        
        Args:
            channel_filters: List of channel names/IDs to crawl (e.g. ['general', 'C12345']). Crawls all if None.
            normalize: Apply normalization pipeline (deduplicate, validation)
            
        Returns:
            List of normalized MemoryDocument objects.
        """
        try:
            # Initialize async client wrapper
            self.client = SlackClientAsync(
                token=self.slack_token,
                max_retries=5,
            )

            # Initialize crawler
            self.crawler = SlackWorkspaceCrawler(
                client=self.client,
                lookback_days=self.lookback_days,
                max_concurrent_tasks=self.max_concurrent_requests,
            )

            logger.info("Beginning Slack workspace crawl...")
            self.documents = await self.crawler.crawl_workspace(
                channel_filters=channel_filters
            )
            
            logger.info(
                "Slack workspace crawl complete",
                documents_extracted=len(self.documents),
            )

            # Apply normalization
            if normalize:
                self.documents = self._normalize_documents(self.documents)

            return self.documents

        except Exception as e:
            logger.error("Slack workspace fetch failed", error=str(e))
            raise

    def _normalize_documents(
        self,
        documents: List[MemoryDocument]
    ) -> List[MemoryDocument]:
        """Apply normalization pipeline to extracted Slack documents."""
        pipeline = NormalizationPipeline()
        
        # Process through pipeline
        normalized = pipeline.process(
            documents,
            min_content_length=20,
            remove_duplicates=True,
        )
        
        logger.info(
            "Slack normalization complete",
            input_count=len(documents),
            output_count=len(normalized),
        )
        
        return normalized

    def get_documents(self) -> List[MemoryDocument]:
        """Get extracted documents."""
        return self.documents

    def sync_fetch(
        self,
        channel_filters: Optional[List[str]] = None,
        normalize: bool = True,
    ) -> List[MemoryDocument]:
        """Synchronous wrapper for fetch_workspace."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.fetch_workspace(channel_filters, normalize)
            )
        finally:
            loop.close()
