"""Recursive workspace crawler for full Notion content extraction."""

import asyncio
from typing import Dict, Any, Set, Optional, List
from datetime import datetime
from backend.connectors.notion.notion_extraction.async_client import NotionClientAsync
from backend.connectors.notion.notion_extraction.block_extractor import BlockExtractor
from backend.connectors.notion.notion_extraction.database_extractor import DatabaseExtractor
from backend.connectors.notion.notion_models.schemas import (
    Block, BlockType, WorkspaceNode, ExtractionStats
)
from backend.models.memory_schema import MemoryDocument
from backend.connectors.notion.notion_utils.logging_config import get_logger

logger = get_logger(__name__)


class NotionWorkspaceCrawler:
    """
    Recursively crawls and extracts all accessible content from a Notion workspace.
    Preserves hierarchy, handles pagination, and recovers from errors gracefully.
    """
    
    def __init__(
        self,
        client: NotionClientAsync,
        max_depth: int = 20,
        max_concurrent_tasks: int = 5
    ):
        self.client = client
        self.max_depth = max_depth
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        # Tracking for circular reference prevention
        self.visited_pages: Set[str] = set()
        self.visited_databases: Set[str] = set()
        self.visited_blocks: Set[str] = set()
        
        # Extraction results
        self.documents: List[MemoryDocument] = []
        self.workspace_nodes: Dict[str, WorkspaceNode] = {}
        self.stats = ExtractionStats()
    
    async def crawl_workspace(
        self,
        start_page_id: Optional[str] = None
    ) -> List[MemoryDocument]:
        """
        Crawl entire workspace starting from a page or workspace root.
        
        Args:
            start_page_id: Optional starting page ID. If None, searches workspace.
        
        Returns:
            List of normalized MemoryDocument objects ready for downstream processing
        """
        start_time = datetime.now()
        logger.info("Starting workspace crawl", start_page_id=start_page_id)
        
        try:
            if start_page_id:
                await self._crawl_page(start_page_id, parent_path="")
            else:
                # Search for accessible pages
                search_results = await self.client.search()
                for result in search_results:
                    if result['object'] == 'page' and result['id'] not in self.visited_pages:
                        await self._crawl_page(result['id'], parent_path="")
        
        except Exception as e:
            logger.error(
                "Workspace crawl failed",
                error=str(e),
                documents_extracted=len(self.documents)
            )
            self.stats.errors += 1
        
        # Calculate stats
        duration = (datetime.now() - start_time).total_seconds()
        self.stats.duration_seconds = duration
        self.stats.total_documents = len(self.documents)
        
        logger.info(
            "Workspace crawl complete",
            stats={
                'total_documents': self.stats.total_documents,
                'total_pages': self.stats.total_pages,
                'total_databases': self.stats.total_databases,
                'duration_seconds': self.stats.duration_seconds,
                'errors': self.stats.errors,
            }
        )
        
        return self.documents
    
    async def _crawl_page(
        self,
        page_id: str,
        parent_path: str,
        depth: int = 0
    ) -> None:
        """
        Recursively crawl a single page and all its content.
        
        Args:
            page_id: Notion page ID
            parent_path: Path to parent page
            depth: Current recursion depth
        """
        if page_id in self.visited_pages or depth > self.max_depth:
            return
        
        async with self.semaphore:
            self.visited_pages.add(page_id)
            self.stats.total_pages += 1
            
            try:
                # Fetch page metadata
                page = await self.client.get_page(page_id)
                page_title = self._extract_page_title(page)
                page_path = f"{parent_path}/{page_title}" if parent_path else page_title
                
                logger.debug(
                    "Crawling page",
                    page_id=page_id,
                    title=page_title,
                    depth=depth
                )
                
                # Create workspace node
                self.workspace_nodes[page_id] = WorkspaceNode(
                    node_id=page_id,
                    node_type="page",
                    title=page_title,
                    path=page_path,
                    url=page.get('url'),
                    metadata={
                        'archived': page.get('archived', False),
                        'created_time': page.get('created_time'),
                        'last_edited_time': page.get('last_edited_time'),
                    }
                )
                
                # Extract all blocks
                blocks = await self.client.get_page_blocks(page_id)
                
                # Process blocks recursively
                block_contents = []
                for block_data in blocks:
                    block_doc = await self._process_block(
                        block_data, page_id, page_path, depth
                    )
                    if block_doc:
                        block_contents.append(block_doc.content)
                
                # Create document for this page
                document = MemoryDocument(
                    id=page_id,
                    source_id=page_id,
                    title=page_title,
                    content='\n\n'.join(block_contents),
                    url=page.get('url'),
                    path=page_path,
                    created_time=datetime.fromisoformat(
                        page.get('created_time', '').replace('Z', '+00:00')
                    ),
                    last_edited_time=datetime.fromisoformat(
                        page.get('last_edited_time', '').replace('Z', '+00:00')
                    ),
                    metadata={
                        'archived': page.get('archived', False),
                        'block_count': len(blocks),
                    }
                )
                
                self.documents.append(document)
                
            except Exception as e:
                logger.error(
                    "Failed to crawl page",
                    page_id=page_id,
                    error=str(e)
                )
                self.stats.errors += 1
    
    async def _process_block(
        self,
        block_data: Dict[str, Any],
        parent_page_id: str,
        parent_path: str,
        depth: int
    ) -> Optional[Block]:
        """
        Process a single block, recursively handling child blocks.
        
        Args:
            block_data: Raw block from Notion API
            parent_page_id: ID of parent page
            parent_path: Path to parent
            depth: Current depth
        
        Returns:
            Processed Block or None if unsupported type
        """
        block_id = block_data['id']
        if block_id in self.visited_blocks:
            return None
        
        self.visited_blocks.add(block_id)
        self.stats.total_blocks += 1
        
        try:
            # Extract block
            block = BlockExtractor.extract_block(block_data)
            if not block:
                return None
            
            block.parent_id = parent_page_id
            
            # Handle special block types
            if block.block_type == BlockType.CHILD_PAGE:
                child_page_id = block_data['id']
                await self._crawl_page(
                    child_page_id,
                    parent_path,
                    depth + 1
                )
            
            elif block.block_type == BlockType.CHILD_DATABASE:
                await self._crawl_database(
                    block_data['id'],
                    parent_path,
                    depth + 1
                )
            
            elif block.block_type == BlockType.TABLE:
                # Fetch table rows
                try:
                    table_rows = await self.client.get_page_blocks(block_id)
                    row_contents = []
                    for row_data in table_rows:
                        row_block = BlockExtractor.extract_block(row_data)
                        if row_block:
                            row_contents.append(row_block.content or '')
                    block.content = '\n'.join(row_contents)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch table rows",
                        block_id=block_id,
                        error=str(e)
                    )
            
            # Recursively fetch child blocks
            if block.has_children and depth < self.max_depth:
                try:
                    children = await self.client.get_page_blocks(block_id)
                    child_contents = []
                    for child_data in children:
                        child_block = await self._process_block(
                            child_data, parent_page_id, parent_path, depth + 1
                        )
                        if child_block and child_block.content:
                            child_contents.append(child_block.content)
                    
                    if child_contents and block.content:
                        block.content += '\n' + '\n'.join(child_contents)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch child blocks",
                        block_id=block_id,
                        error=str(e)
                    )
            
            return block
        
        except Exception as e:
            logger.error(
                "Failed to process block",
                block_id=block_id,
                error=str(e)
            )
            self.stats.errors += 1
            return None
    
    async def _crawl_database(
        self,
        database_id: str,
        parent_path: str,
        depth: int
    ) -> None:
        """
        Recursively crawl a database and all its rows.
        
        Args:
            database_id: Notion database ID
            parent_path: Path to parent
            depth: Current depth
        """
        if database_id in self.visited_databases or depth > self.max_depth:
            return
        
        async with self.semaphore:
            self.visited_databases.add(database_id)
            self.stats.total_databases += 1
            
            try:
                logger.debug(
                    "Crawling database",
                    database_id=database_id,
                    depth=depth
                )
                
                # Fetch database schema
                database = await self.client.get_database(database_id)
                schema = DatabaseExtractor.extract_database_schema(database)
                
                db_title = schema.title
                db_path = f"{parent_path}/{db_title}" if parent_path else db_title
                
                # Create workspace node
                self.workspace_nodes[database_id] = WorkspaceNode(
                    node_id=database_id,
                    node_type="database",
                    title=db_title,
                    path=db_path,
                    metadata={
                        'properties': [
                            {'name': p.name, 'type': p.type}
                            for p in schema.properties
                        ]
                    }
                )
                
                # Fetch all database rows
                rows = await self.client.get_database_rows(database_id)
                self.stats.total_database_rows += len(rows)
                
                # Process each row
                for row_data in rows:
                    await self._process_database_row(
                        row_data, database_id, db_path, depth
                    )
            
            except Exception as e:
                logger.error(
                    "Failed to crawl database",
                    database_id=database_id,
                    error=str(e)
                )
                self.stats.errors += 1
    
    async def _process_database_row(
        self,
        row_data: Dict[str, Any],
        database_id: str,
        parent_path: str,
        depth: int
    ) -> None:
        """
        Process a database row and recursively crawl its content.
        
        Args:
            row_data: Raw row from Notion API
            database_id: Parent database ID
            parent_path: Path to parent
            depth: Current depth
        """
        row_id = row_data['id']
        
        try:
            # Extract row data
            db_row = DatabaseExtractor.extract_database_row(row_data, database_id)
            
            # Extract title from row properties
            row_title = self._extract_row_title(row_data)
            row_path = f"{parent_path}/{row_title}" if row_title else parent_path
            
            # Fetch row content blocks
            row_blocks = await self.client.get_page_blocks(row_id)
            
            block_contents = []
            for block_data in row_blocks:
                block = await self._process_block(
                    block_data, row_id, row_path, depth
                )
                if block and block.content:
                    block_contents.append(block.content)
            
            # Create document for row
            properties_text = '\n'.join([
                f"{k}: {v}" for k, v in db_row.properties.items() if v
            ])
            
            document = MemoryDocument(
                id=row_id,
                source_id=row_id,
                title=row_title or 'Untitled',
                content='\n\n'.join([properties_text] + block_contents),
                url=row_data.get('url'),
                path=row_path,
                parent_id=database_id,
                created_time=db_row.created_time,
                last_edited_time=db_row.last_edited_time,
                metadata={
                    'database_id': database_id,
                    'properties': db_row.properties,
                }
            )
            
            self.documents.append(document)
        
        except Exception as e:
            logger.error(
                "Failed to process database row",
                row_id=row_id,
                database_id=database_id,
                error=str(e)
            )
            self.stats.errors += 1
    
    def _extract_page_title(self, page: Dict[str, Any]) -> str:
        """Extract page title from properties."""
        properties = page.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                rich_text = prop_data.get('title', [])
                return ''.join(rt.get('plain_text', '') for rt in rich_text) or 'Untitled'
        return 'Untitled'
    
    def _extract_row_title(self, row: Dict[str, Any]) -> str:
        """Extract row title from first title property."""
        properties = row.get('properties', {})
        for prop_name, prop_data in properties.items():
            if prop_data.get('type') == 'title':
                rich_text = prop_data.get('title', [])
                return ''.join(rt.get('plain_text', '') for rt in rich_text)
        return ''
