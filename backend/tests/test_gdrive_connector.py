import unittest
from datetime import datetime
from backend.connectors.gdrive.gdrive_connector import GoogleDriveConnector
from backend.core.models.memory_schema import MemoryDocument


class TestGoogleDriveConnector(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "test_workspace"
        self.connector = GoogleDriveConnector(workspace_id=self.workspace_id)

    def test_gdrive_connector_initialization(self):
        self.assertEqual(self.connector.workspace_id, self.workspace_id)

    def test_gdrive_connector_fetch(self):
        docs = self.connector.fetch()
        self.assertEqual(len(docs), 0)


if __name__ == "__main__":
    unittest.main()
