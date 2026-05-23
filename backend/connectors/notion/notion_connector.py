"""
Production-grade Notion connector implementing recursive workspace crawling,
content extraction, normalization, and preparation for downstream pipelines.
"""

import os
import asyncio
from typing import List, Optional
from backend.connectors.notion.notion_extraction.async_client import NotionClientAsync
from backend.connectors.notion.notion_extraction.crawler import NotionWorkspaceCrawler
from backend.connectors.notion.notion_utils.retry import RetryConfig
from backend.connectors.notion.notion_models.schemas import ExtractionStats
from backend.models.memory_schema import MemoryDocument
from backend.utils.pipeline import NormalizationPipeline
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)


class NotionConnector():
    """
    Production-grade connector for Notion workspaces.
    
    Implements:
    - Async-first architecture
    - Recursive workspace traversal
    - Pagination handling
    - Retry with exponential backoff
    - Rate limit handling
    - Structured error recovery
    - Normalized output schemas
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_concurrent_requests: int = 5,
        max_depth: int = 20,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize Notion connector.
        
        Args:
            api_key: Notion API token (defaults to NOTION_API_KEY env var)
            max_concurrent_requests: Max concurrent API calls
            max_depth: Max recursion depth for workspace traversal
            retry_config: Retry configuration for resilience
        """
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY environment variable or api_key parameter required")
        
        self.max_concurrent_requests = max_concurrent_requests
        self.max_depth = max_depth
        self.retry_config = retry_config or RetryConfig()
        
        self.client: Optional[NotionClientAsync] = None
        self.crawler: Optional[NotionWorkspaceCrawler] = None
        self.documents: List[MemoryDocument] = []
        self.extraction_stats: Optional[ExtractionStats] = None
        
        logger.info("Notion connector initialized")
    
    async def fetch_workspace(
        self,
        start_page_id: Optional[str] = None,
        normalize: bool = True
    ) -> List[MemoryDocument]:
        """
        Crawl and extract complete Notion workspace.
        
        Args:
            start_page_id: Optional starting page ID
            normalize: Apply normalization pipeline
        
        Returns:
            List of normalized MemoryDocument objects
        """
        try:
            # Initialize async client
            self.client = NotionClientAsync(
                auth_token=self.api_key,
                retry_config=self.retry_config,
                max_concurrent_requests=self.max_concurrent_requests
            )
            
            # Initialize crawler
            self.crawler = NotionWorkspaceCrawler(
                client=self.client,
                max_depth=self.max_depth,
                max_concurrent_tasks=self.max_concurrent_requests
            )
            
            # Crawl workspace
            logger.info("Beginning workspace crawl")
            self.documents = await self.crawler.crawl_workspace(start_page_id)
            self.extraction_stats = self.crawler.stats
            
            logger.info(
                "Workspace crawl complete",
                documents_extracted=len(self.documents),
                stats=self.extraction_stats.dict() if self.extraction_stats else {}
            )
            
            # Normalize if requested
            if normalize:
                self.documents = self._normalize_documents(self.documents)
            
            return self.documents
        
        except Exception as e:
            logger.error("Workspace fetch failed", error=str(e))
            raise
    
    def _normalize_documents(
        self,
        documents: List[MemoryDocument]
    ) -> List[MemoryDocument]:
        """
        Apply normalization pipeline to extracted documents.
        
        Args:
            documents: Extracted documents
        
        Returns:
            Normalized documents
        """
        pipeline = NormalizationPipeline()
        
        # Process through pipeline
        normalized = pipeline.process(
            documents,
            min_content_length=20,
            remove_duplicates=True
        )
        
        logger.info(
            "Normalization complete",
            input_count=len(documents),
            output_count=len(normalized)
        )
        
        return normalized
    
    def get_documents(self) -> List[MemoryDocument]:
        """
        Get extracted documents.
        
        Returns:
            List of MemoryDocument objects
        """
        return self.documents
    
    def get_stats(self) -> Optional[ExtractionStats]:
        """
        Get extraction statistics.
        
        Returns:
            ExtractionStats object or None if not extracted
        """
        return self.extraction_stats
    
    def sync_fetch(self, start_page_id: Optional[str] = None) -> List[MemoryDocument]:
        """
        Synchronous wrapper for async fetch (for compatibility).
        
        Args:
            start_page_id: Optional starting page ID
        
        Returns:
            List of MemoryDocument objects
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.fetch_workspace(start_page_id)
            )
        finally:
            loop.close()


async def main():
    """Example usage of production Notion connector."""
    # Initialize connector
    connector = NotionConnector(
        max_concurrent_requests=5,
        max_depth=10
    )
    
    # Crawl workspace
    documents = await connector.fetch_workspace()
    
    # Print summary
    print(f"\n✓ Extracted {len(documents)} documents")
    
    if connector.extraction_stats:
        stats = connector.extraction_stats
        print(f"\nExtraction Statistics:")
        print(f"  Pages: {stats.total_pages}")
        print(f"  Blocks: {stats.total_blocks}")
        print(f"  Databases: {stats.total_databases}")
        print(f"  Database Rows: {stats.total_database_rows}")
        print(f"  Errors: {stats.errors}")
        print(f"  Duration: {stats.duration_seconds:.1f}s")
    
    # Show sample documents
    if documents:
        print(f"\nSample Documents:")
        print(documents[0])


if __name__ == "__main__":
    asyncio.run(main())