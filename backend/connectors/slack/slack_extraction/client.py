import asyncio
from typing import Any, Dict, List, Optional
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)



class SlackClientAsync:
    """
    Production-grade async client for Slack API with built-in rate-limit
    handling (exponential backoff) and pagination traversal.
    """

    def __init__(
        self,
        token: str,
        max_retries: int = 5,
        backoff_factor: float = 1.5,
        initial_delay: float = 1.0,
    ):
        self.client = AsyncWebClient(token=token)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.initial_delay = initial_delay

    async def _call_with_retry(self, api_method: str, **kwargs) -> Dict[str, Any]:
        """
        Executes a Slack API call with exponential backoff on rate limits (HTTP 429).
        """
        delay = self.initial_delay
        for attempt in range(self.max_retries):
            try:
                # Resolve the method dynamically from the client
                parts = api_method.split(".")
                method = self.client
                for part in parts:
                    method = getattr(method, part)

                response = await method(**kwargs)
                if response.get("ok"):
                    return response
                else:
                    raise SlackApiError(f"Slack API error: {response.get('error')}", response)

            except SlackApiError as e:
                # Check for rate limiting
                is_rate_limited = False
                if e.response.status_code == 429:
                    is_rate_limited = True
                    # Respect Retry-After header if present
                    retry_after = float(e.response.headers.get("Retry-After", delay))
                    logger.warning(
                        f"Rate limited (429) calling {api_method}. Waiting {retry_after}s. "
                        f"Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(retry_after)
                
                # Also retry for common network/server errors
                elif e.response.status_code in [500, 502, 503, 504]:
                    logger.warning(
                        f"Server error ({e.response.status_code}) calling {api_method}. "
                        f"Waiting {delay}s. Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(delay)
                else:
                    # Non-retryable API error (e.g. invalid token, invalid arguments)
                    logger.error(f"Slack API error on {api_method}: {e}")
                    raise e
            except Exception as e:
                logger.error(f"Unexpected error calling {api_method}: {e}")
                if attempt == self.max_retries - 1:
                    raise e
                await asyncio.sleep(delay)

            delay *= self.backoff_factor

        raise RuntimeError(f"Failed to call Slack API {api_method} after {self.max_retries} attempts.")

    async def get_public_channels(self) -> List[Dict[str, Any]]:
        """
        Retrieve all public channels in the workspace.
        """
        channels = []
        cursor = None

        while True:
            response = await self._call_with_retry(
                "conversations.list",
                types="public_channel",
                exclude_archived=True,
                cursor=cursor,
                limit=100,
            )
            channels.extend(response.get("channels", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    async def get_channel_history(
        self,
        channel_id: str,
        oldest: Optional[float] = None,
        latest: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve message history for a channel within a timeframe.
        """
        messages = []
        cursor = None

        kwargs = {
            "channel": channel_id,
            "limit": limit,
        }
        if oldest is not None:
            kwargs["oldest"] = str(oldest)
        if latest is not None:
            kwargs["latest"] = str(latest)

        while True:
            if cursor:
                kwargs["cursor"] = cursor

            response = await self._call_with_retry("conversations.history", **kwargs)
            messages.extend(response.get("messages", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return messages

    async def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all replies in a thread.
        """
        replies = []
        cursor = None

        kwargs = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": limit,
        }

        while True:
            if cursor:
                kwargs["cursor"] = cursor

            response = await self._call_with_retry("conversations.replies", **kwargs)
            replies.extend(response.get("messages", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return replies

    async def get_users_list(self) -> List[Dict[str, Any]]:
        """
        Retrieve all users in the workspace.
        """
        users = []
        cursor = None

        while True:
            response = await self._call_with_retry(
                "users.list",
                cursor=cursor,
                limit=150,
            )
            users.extend(response.get("members", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return users

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch details for a single user.
        """
        response = await self._call_with_retry("users.info", user=user_id)
        return response.get("user", {})
