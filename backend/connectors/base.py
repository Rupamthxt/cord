from abc import ABC, abstractmethod
from typing import List

from backend.models.memory_schema import MemoryDocument

class BaseConnector(ABC):

    @abstractmethod
    def fetch(self) -> List[MemoryDocument]:
        pass