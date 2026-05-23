"""Retry utilities with exponential backoff for resilience."""

import asyncio
import random
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 32.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = self.initial_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            delay *= (0.5 + random.random())
        
        return delay


async def async_retry(
    fn: Callable,
    config: Optional[RetryConfig] = None,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """
    Retry an async function with exponential backoff.
    
    Args:
        fn: Async function to retry
        config: Retry configuration
        retryable_exceptions: Tuple of exceptions to retry on
    
    Returns:
        Result of function call
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < config.max_retries:
                delay = config.get_delay(attempt)
                await asyncio.sleep(delay)
            continue
    
    raise last_exception or RuntimeError("Retry failed")


def retry_decorator(config: Optional[RetryConfig] = None):
    """Decorator for retrying async functions."""
    if config is None:
        config = RetryConfig()
    
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            async def call_fn():
                return await fn(*args, **kwargs)
            
            return await async_retry(call_fn, config=config)
        
        return wrapper
    
    return decorator
