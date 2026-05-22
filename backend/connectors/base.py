from abc import ABC, abstractmethod

class BaseConnector(ABC):

    @abstractmethod
    def fetch(self):
        pass