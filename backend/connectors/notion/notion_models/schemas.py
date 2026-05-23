"""
Production-grade Pydantic schemas for normalized Notion content.
These represent the internal canonical form, decoupled from Notion's API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field


class BlockType(str, Enum):
    """Supported Notion block types."""
    PARAGRAPH = "paragraph"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    BULLETED_LIST_ITEM = "bulleted_list_item"
    NUMBERED_LIST_ITEM = "numbered_list_item"
    TO_DO = "to_do"
    TOGGLE = "toggle"
    CHILD_PAGE = "child_page"
    CHILD_DATABASE = "child_database"
    QUOTE = "quote"
    CODE = "code"
    CALLOUT = "callout"
    TABLE = "table"
    TABLE_ROW = "table_row"
    SYNCED_BLOCK = "synced_block"
    BOOKMARK = "bookmark"
    EMBED = "embed"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"
    EQUATION = "equation"
    DIVIDER = "divider"
    BREADCRUMB = "breadcrumb"


class RichTextAnnotation(BaseModel):
    """Rich text formatting annotations."""
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False
    code: bool = False
    color: Optional[str] = None


class RichText(BaseModel):
    """Rich text segment with annotations and links."""
    text: str
    href: Optional[str] = None
    annotations: RichTextAnnotation = Field(default_factory=RichTextAnnotation)
    
    @property
    def plain_text(self) -> str:
        """Get plain text without annotations."""
        return self.text


class Block(BaseModel):
    """Normalized representation of a Notion block."""
    id: str
    block_type: BlockType
    parent_id: Optional[str] = None
    has_children: bool = False
    created_time: datetime
    last_edited_time: datetime
    content: Optional[str] = None
    rich_text_content: Optional[List[RichText]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = False


class BlockHierarchy(BaseModel):
    """Block with its recursively fetched children."""
    block: Block
    children: List['BlockHierarchy'] = Field(default_factory=list)


BlockHierarchy.update_forward_refs()


class DatabaseProperty(BaseModel):
    """Schema for a single Notion database property."""
    id: str
    name: str
    type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DatabaseSchema(BaseModel):
    """Complete schema of a Notion database."""
    database_id: str
    title: str
    properties: List[DatabaseProperty]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DatabaseRow(BaseModel):
    """A single row/page in a Notion database."""
    row_id: str
    database_id: str
    properties: Dict[str, Any]
    content_blocks: List[Block] = Field(default_factory=list)
    created_time: datetime
    last_edited_time: datetime
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# class MemoryDocument(BaseModel):
#     """
#     Normalized document representation ready for chunking and embedding.
#     This is the canonical form used downstream.
#     """
#     id: str
#     source: str = "notion"
#     source_id: str  # Notion page/database ID
#     workspace_id: Optional[str] = None
#     parent_id: Optional[str] = None
#     path: Optional[str] = None  # e.g., "/Engineering/Incidents/May/Issue"
#     title: str
#     content: str
#     url: Optional[str] = None
#     author: Optional[str] = None
#     created_time: datetime
#     last_edited_time: datetime
#     tags: List[str] = Field(default_factory=list)
#     metadata: Dict[str, Any] = Field(default_factory=dict)
    
#     class Config:
#         json_encoders = {
#             datetime: lambda v: v.isoformat()
#         }


class WorkspaceNode(BaseModel):
    """Represents a node in the workspace hierarchy."""
    node_id: str
    parent_node_id: Optional[str] = None
    node_type: str  # "page", "database", "block"
    title: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    children_ids: List[str] = Field(default_factory=list)


class ExtractionStats(BaseModel):
    """Statistics from an extraction run."""
    total_pages: int = 0
    total_blocks: int = 0
    total_databases: int = 0
    total_database_rows: int = 0
    total_documents: int = 0
    errors: int = 0
    warnings: int = 0
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
