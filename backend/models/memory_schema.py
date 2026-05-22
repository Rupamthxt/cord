from pydantic import BaseModel
from typing import List, Optional

class MemoryChunk(BaseModel):

    source: str
    source_id: Optional[str]

    author: Optional[str]
    team: Optional[str]

    timestamp: Optional[str]

    document_title: Optional[str]

    tags: Optional[List[str]]