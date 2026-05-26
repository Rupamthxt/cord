import re
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from backend.core.models.memory_schema import MemoryDocument
from backend.connectors.slack.slack_extraction.client import SlackClientAsync
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)



class SlackWorkspaceCrawler:
    """
    Crawls Slack channels, messages, and threads, resolves user mentions,
    and groups them into normalized MemoryDocuments.
    """

    def __init__(
        self,
        client: SlackClientAsync,
        lookback_days: Optional[int] = 30,
        max_concurrent_tasks: int = 5,
    ):
        self.client = client
        self.lookback_days = lookback_days
        self.max_concurrent_tasks = max_concurrent_tasks
        self.user_cache: Dict[str, str] = {}  # user_id -> display_name
        self.channel_name_cache: Dict[str, str] = {}  # channel_id -> channel_name

    async def _fetch_and_cache_users(self):
        """Pre-fetch all users in the workspace to populate user_cache."""
        try:
            logger.info("Pre-fetching workspace users...")
            users = await self.client.get_users_list()
            for user in users:
                user_id = user.get("id")
                # Prefer real name or display name over username
                profile = user.get("profile", {})
                display_name = (
                    profile.get("display_name")
                    or user.get("real_name")
                    or user.get("name")
                    or user_id
                )
                if user_id and display_name:
                    self.user_cache[user_id] = display_name
            logger.info(f"Cached {len(self.user_cache)} users.")
        except Exception as e:
            logger.warning(f"Failed to pre-fetch users: {e}. Fallback to lazy-loading.")

    async def _resolve_user_name(self, user_id: str) -> str:
        """Resolve a User ID to a human-readable display name, using cache or API."""
        if not user_id:
            return "System"
        
        # Check cache
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        # Lazy load if not in cache
        try:
            logger.debug(f"Lazy loading user profile for {user_id}...")
            user_info = await self.client.get_user_info(user_id)
            profile = user_info.get("profile", {})
            name = (
                profile.get("display_name")
                or user_info.get("real_name")
                or user_info.get("name")
                or user_id
            )
            self.user_cache[user_id] = name
            return name
        except Exception as e:
            logger.warning(f"Failed to resolve user name for {user_id}: {e}")
            return user_id

    async def _replace_user_mentions(self, text: str) -> str:
        """Parse Slack's raw user mention syntax <@U12345> and replace it with @Display Name."""
        if not text:
            return ""
        
        user_mentions = re.findall(r"<@(U[A-Z0-9]+)>", text)
        if not user_mentions:
            return text

        # Deduplicate and resolve names
        resolved_names = {}
        for uid in set(user_mentions):
            name = await self._resolve_user_name(uid)
            resolved_names[uid] = name

        # Replace in text
        for uid, name in resolved_names.items():
            text = text.replace(f"<@{uid}>", f"@{name}")

        return text

    def _get_timestamp_seconds(self, ts_str: str) -> float:
        """Parse Slack's string timestamp (e.g., '1622548800.000200') into a float."""
        try:
            return float(ts_str)
        except ValueError:
            return datetime.now(timezone.utc).timestamp()

    def _format_datetime(self, ts_str: str) -> datetime:
        """Convert Slack's string timestamp to a timezone-aware UTC datetime."""
        seconds = self._get_timestamp_seconds(ts_str)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    async def crawl_workspace(
        self,
        channel_filters: Optional[List[str]] = None,
    ) -> List[MemoryDocument]:
        """
        Crawl the workspace public channels, messages, and threads,
        and generate normalized documents.
        """
        # 1. Fetch and cache users first
        await self._fetch_and_cache_users()

        # 2. Get list of channels
        all_channels = await self.client.get_public_channels()
        
        # Populate channel name cache
        for ch in all_channels:
            self.channel_name_cache[ch["id"]] = ch["name"]

        # Filter channels if specified
        target_channels = []
        if channel_filters:
            # Filters can be channel names (e.g., "general") or IDs (e.g., "C12345")
            filters_set = set(channel_filters)
            for ch in all_channels:
                if ch["id"] in filters_set or ch["name"] in filters_set:
                    target_channels.append(ch)
        else:
            target_channels = all_channels

        logger.info(f"Targeting {len(target_channels)} Slack channels for crawl.")

        # Calculate time constraint
        oldest_ts = None
        if self.lookback_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
            oldest_ts = cutoff_date.timestamp()

        # 3. Fetch channel content concurrently
        semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        documents = []

        async def process_channel(ch_info: Dict[str, Any]):
            async with semaphore:
                ch_id = ch_info["id"]
                ch_name = ch_info["name"]
                try:
                    logger.info(f"Crawling history for #{ch_name} (ID: {ch_id})...")
                    messages = await self.client.get_channel_history(
                        channel_id=ch_id,
                        oldest=oldest_ts,
                    )
                    logger.info(f"Fetched {len(messages)} messages from #{ch_name}.")
                    
                    if messages:
                        ch_docs = await self._process_messages(messages, ch_id, ch_name)
                        documents.extend(ch_docs)
                except Exception as e:
                    logger.error(f"Error crawling channel #{ch_name}: {e}")

        tasks = [process_channel(ch) for ch in target_channels]
        await asyncio.gather(*tasks)

        logger.info(f"Slack crawl complete. Generated {len(documents)} MemoryDocuments.")
        return documents

    async def _process_messages(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: str,
    ) -> List[MemoryDocument]:
        """
        Processes a list of raw Slack messages from a channel.
        - Fetches thread replies.
        - Resolves usernames and user mentions.
        - Groups threaded messages.
        - Groups non-threaded messages by channel + day.
        """
        # Sort messages oldest first
        messages = sorted(messages, key=lambda m: self._get_timestamp_seconds(m["ts"]))

        # Identify thread parent messages and fetch replies
        threaded_messages: Dict[str, List[Dict[str, Any]]] = {}  # thread_ts -> list of messages
        non_threaded_messages: List[Dict[str, Any]] = []

        # Process parent messages and check for threads
        for msg in messages:
            # Check if this message is part of a thread
            # A message is a thread parent if it has 'reply_count' > 0 (or 'thread_ts' == its own 'ts')
            thread_ts = msg.get("thread_ts")
            
            # Parent of a thread
            if msg.get("reply_count", 0) > 0:
                parent_ts = msg["ts"]
                try:
                    # Fetch all replies for this thread
                    logger.info(f"Fetching {msg['reply_count']} thread replies for message {parent_ts} in #{channel_name}")
                    replies = await self.client.get_thread_replies(channel_id, parent_ts)
                    # Sort replies chronologically
                    replies = sorted(replies, key=lambda r: self._get_timestamp_seconds(r["ts"]))
                    threaded_messages[parent_ts] = replies
                except Exception as e:
                    logger.error(f"Failed to fetch thread replies for {parent_ts}: {e}")
                    # Fallback: treat parent as non-threaded if replies can't be fetched
                    non_threaded_messages.append(msg)
            
            # Reply message (if we already processed parent, replies are in threaded_messages)
            elif thread_ts and thread_ts != msg["ts"]:
                # We skip individual replies here since they will be retrieved as a group
                # when fetching replies for the parent message
                continue
            else:
                non_threaded_messages.append(msg)

        documents: List[MemoryDocument] = []

        # 4. Generate documents for threads
        for thread_ts, thread_msgs in threaded_messages.items():
            doc = await self._build_thread_document(thread_msgs, channel_id, channel_name, thread_ts)
            if doc:
                documents.append(doc)

        # 5. Group non-threaded messages by day
        day_groups: Dict[str, List[Dict[str, Any]]] = {}  # YYYY-MM-DD -> messages
        for msg in non_threaded_messages:
            dt = self._format_datetime(msg["ts"])
            day_str = dt.strftime("%Y-%m-%d")
            day_groups.setdefault(day_str, []).append(msg)

        for day_str, day_msgs in day_groups.items():
            doc = await self._build_day_document(day_msgs, channel_id, channel_name, day_str)
            if doc:
                documents.append(doc)

        return documents

    async def _build_thread_document(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: str,
        thread_ts: str,
    ) -> Optional[MemoryDocument]:
        """Format a list of thread messages into a single MemoryDocument."""
        if not messages:
            return None

        # Thread metadata
        first_msg = messages[0]
        created_time = self._format_datetime(first_msg["ts"])
        last_edited_time = self._format_datetime(messages[-1]["ts"])
        
        # Build document text representation
        lines = []
        participants: Set[str] = set()

        for msg in messages:
            user_id = msg.get("user") or msg.get("bot_id", "System")
            user_name = await self._resolve_user_name(user_id)
            participants.add(user_name)
            
            # Format message timestamp
            msg_time = self._format_datetime(msg["ts"]).strftime("%H:%M:%S")
            
            # Clean text (replace mentions)
            cleaned_text = await self._replace_user_mentions(msg.get("text", ""))
            
            lines.append(f"{user_name} [{msg_time}]: {cleaned_text}")

        content_body = "\n".join(lines)
        thread_starter_name = await self._resolve_user_name(first_msg.get("user"))
        title = f"Slack Thread: {thread_starter_name} in #{channel_name}"
        
        # Generate stable document ID
        doc_id = f"slack_thread_{channel_id}_{thread_ts}"

        return MemoryDocument(
            id=doc_id,
            source="slack",
            source_id=f"{channel_id}:{thread_ts}",
            parent_id=channel_id,
            path=f"/Slack/{channel_name}/Thread_{thread_ts}",
            title=title,
            content=content_body,
            created_time=created_time,
            last_edited_time=last_edited_time,
            tags=["slack", "thread", channel_name],
            metadata={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "thread_ts": thread_ts,
                "participants": list(participants),
                "reply_count": len(messages) - 1,
            }
        )

    async def _build_day_document(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: str,
        day_str: str,
    ) -> Optional[MemoryDocument]:
        """Format a list of daily channel messages into a single MemoryDocument."""
        if not messages:
            return None

        # Time range
        created_time = self._format_datetime(messages[0]["ts"])
        last_edited_time = self._format_datetime(messages[-1]["ts"])

        lines = []
        participants: Set[str] = set()

        for msg in messages:
            user_id = msg.get("user") or msg.get("bot_id", "System")
            user_name = await self._resolve_user_name(user_id)
            participants.add(user_name)

            msg_time = self._format_datetime(msg["ts"]).strftime("%H:%M:%S")
            cleaned_text = await self._replace_user_mentions(msg.get("text", ""))
            
            lines.append(f"{user_name} [{msg_time}]: {cleaned_text}")

        content_body = f"Slack messages in #{channel_name} on {day_str}:\n\n" + "\n".join(lines)
        title = f"Slack Chat: #{channel_name} ({day_str})"
        
        # Generate stable document ID
        doc_id = f"slack_chat_{channel_id}_{day_str}"

        return MemoryDocument(
            id=doc_id,
            source="slack",
            source_id=f"{channel_id}:{day_str}",
            parent_id=channel_id,
            path=f"/Slack/{channel_name}/{day_str}",
            title=title,
            content=content_body,
            created_time=created_time,
            last_edited_time=last_edited_time,
            tags=["slack", "chat", channel_name],
            metadata={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "date": day_str,
                "participants": list(participants),
                "message_count": len(messages),
            }
        )
