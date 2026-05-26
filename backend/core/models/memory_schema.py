from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class MemoryDocument(BaseModel):
    """
    Normalized document representation ready for chunking and embedding.
    This is the canonical form used downstream.
    """
    id: str
    source: str = "notion"
    source_id: str  # Notion page/database ID
    workspace_id: Optional[str] = None
    parent_id: Optional[str] = None
    path: Optional[str] = None  # e.g., "/Engineering/Incidents/May/Issue"
    title: str
    content: str
    url: Optional[str] = None
    author: Optional[str] = None
    created_time: datetime
    last_edited_time: datetime
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MemoryChunk(BaseModel):
    """
    Representation of a single chunk of memory, used for metadata in test_ingest and base connector.
    """
    source: str
    source_id: str
    author: Optional[str] = None
    team: Optional[str] = None
    timestamp: Optional[str] = None
    document_title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)