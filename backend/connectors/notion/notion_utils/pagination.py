"""Pagination utilities for Notion API."""

from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic
import asyncio

T = TypeVar('T')


class PaginationCursor:
    """Manages pagination state across Notion API calls."""
    
    def __init__(self):
        self.cursor: Optional[str] = None
        self.has_more: bool = True
    
    def update(self, response: Dict[str, Any]):
        """Update cursor state from API response."""
        self.cursor = response.get('next_cursor')
        self.has_more = response.get('has_more', False)
    
    def reset(self):
        """Reset pagination to start."""
        self.cursor = None
        self.has_more = True


async def paginate_list_items(
    fetch_fn: Callable,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Paginate through all list results from Notion API.
    
    Args:
        fetch_fn: Async function that returns paginated results
        **kwargs: Arguments to pass to fetch_fn
    
    Returns:
        Complete list of all items across all pages
    """
    items = []
    cursor = None
    
    while True:
        params = {k: v for k, v in kwargs.items() if v is not None}
        if cursor:
            params['start_cursor'] = cursor
        
        response = await fetch_fn(**params)
        
        if 'results' in response:
            items.extend(response['results'])
        
        has_more = response.get('has_more', False)
        cursor = response.get('next_cursor')
        
        if not has_more or cursor is None:
            break
    
    return items


async def paginate_with_callback(
    fetch_fn: Callable,
    callback: Callable,
    **kwargs
) -> int:
    """
    Paginate through results, calling callback for each item.
    Useful for streaming processing of large result sets.
    
    Args:
        fetch_fn: Async function that returns paginated results
        callback: Async function called for each item
        **kwargs: Arguments to pass to fetch_fn
    
    Returns:
        Total number of items processed
    """
    count = 0
    cursor = None
    
    while True:
        params = {k: v for k, v in kwargs.items() if v is not None}
        if cursor:
            params['start_cursor'] = cursor
        
        response = await fetch_fn(**params)
        
        if 'results' in response:
            for item in response['results']:
                await callback(item)
                count += 1
        
        has_more = response.get('has_more', False)
        cursor = response.get('next_cursor')
        
        if not has_more or cursor is None:
            break
    
    return count
