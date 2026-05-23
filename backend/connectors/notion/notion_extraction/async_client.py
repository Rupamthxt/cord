"""Async wrapper around Notion client with retry and pagination support."""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from notion_client import Client
from backend.connectors.notion.notion_utils.retry import RetryConfig, async_retry
from backend.connectors.notion.notion_utils.pagination import paginate_list_items
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)


class NotionClientAsync:
    """
    Async wrapper around synchronous Notion client.
    Handles retries, pagination, and structured error handling.
    """
    
    def __init__(
        self,
        auth_token: str,
        retry_config: Optional[RetryConfig] = None,
        max_concurrent_requests: int = 5
    ):
        self.client = Client(auth=auth_token)
        self.retry_config = retry_config or RetryConfig()
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
    
    async def _call_with_retry(
        self,
        fn: Callable,
        operation: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call a Notion API method with retry and rate limit handling.
        
        Args:
            fn: Notion client method to call
            operation: Human-readable operation name for logging
            **kwargs: Arguments to pass to fn
        
        Returns:
            API response dict
        """
        async def make_call():
            async with self.semaphore:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, lambda: fn(**kwargs)
                )
        
        try:
            result = await async_retry(make_call, config=self.retry_config)
            logger.debug(
                f"API call succeeded: {operation}",
                operation=operation,
                kwargs=str(kwargs)[:100]
            )
            return result
        except Exception as e:
            logger.error(
                f"API call failed: {operation}",
                operation=operation,
                error=str(e)
            )
            raise
    
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Retrieve a single page."""
        return await self._call_with_retry(
            self.client.pages.retrieve,
            "pages.retrieve",
            page_id=page_id
        )
    
    async def search(
        self,
        query: str = "",
        filter_: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search pages with pagination.
        
        Args:
            query: Search query
            filter_: Search filter
            sort: Sort configuration
        
        Returns:
            List of all matching pages
        """
        async def fetch_fn(**kwargs):
            result = await self._call_with_retry(
                self.client.search,
                "search",
                **kwargs
            )
            return result
        
        return await paginate_list_items(
            fetch_fn,
            query=query,
            filter=filter_,
            sort=sort
        )
    
    async def get_page_blocks(
        self,
        page_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all blocks from a page with pagination.
        
        Args:
            page_id: ID of page to fetch blocks from
        
        Returns:
            List of all blocks
        """
        async def fetch_fn(**kwargs):
            result = await self._call_with_retry(
                self.client.blocks.children.list,
                "blocks.children.list",
                **kwargs
            )
            return result
        
        return await paginate_list_items(fetch_fn, block_id=page_id)
    
    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Retrieve database schema."""
        return await self._call_with_retry(
            self.client.databases.retrieve,
            "databases.retrieve",
            database_id=database_id
        )
    
    async def query_database(
        self,
        database_id: str,
        filter_: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query database with pagination.
        
        Args:
            database_id: ID of database to query
            filter_: Query filter
            sorts: Sort configuration
        
        Returns:
            List of all matching pages
        """
        async def fetch_fn(**kwargs):
            result = await self._call_with_retry(
                self.client.databases.query,
                "databases.query",
                **kwargs
            )
            return result
        
        return await paginate_list_items(
            fetch_fn,
            database_id=database_id,
            filter=filter_,
            sorts=sorts
        )
    
    async def get_database_rows(
        self,
        database_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all rows from database with pagination.
        
        Args:
            database_id: ID of database
        
        Returns:
            List of all rows
        """
        return await self.query_database(database_id)
    
    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user information."""
        return await self._call_with_retry(
            self.client.users.retrieve,
            "users.retrieve",
            user_id=user_id
        )
    
    async def get_comment_threads(
        self,
        page_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all comments on a page.
        
        Args:
            page_id: ID of page
        
        Returns:
            List of all comments
        """
        async def fetch_fn(**kwargs):
            result = await self._call_with_retry(
                self.client.comments.list,
                "comments.list",
                **kwargs
            )
            return result
        
        return await paginate_list_items(fetch_fn, block_id=page_id)
