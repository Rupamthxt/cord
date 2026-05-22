from abc import ABC, abstractmethod
from typing import List

from backend.models.memory_schema import MemoryChunk

class BaseConnector(ABC):

    @abstractmethod
    def fetch(self) -> List[MemoryChunk]:
        pass