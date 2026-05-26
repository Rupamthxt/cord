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
        self.assertEqual(len(docs), 4)

        for doc in docs:
            self.assertIsInstance(doc, MemoryDocument)
            self.assertEqual(doc.source, "gdrive")
            self.assertEqual(doc.workspace_id, self.workspace_id)
            self.assertIsNotNone(doc.id)
            self.assertIsNotNone(doc.title)
            self.assertIsNotNone(doc.content)
            self.assertIsNotNone(doc.url)
            self.assertIsNotNone(doc.author)
            self.assertIsInstance(doc.created_time, datetime)
            self.assertIsInstance(doc.last_edited_time, datetime)
            self.assertTrue("gdrive" in doc.tags)
            self.assertEqual(doc.metadata["workspace_id"], self.workspace_id)
            self.assertEqual(doc.metadata["source"], "gdrive")
            self.assertEqual(doc.metadata["file_id"], doc.source_id)

        # Check specific mock files are present
        titles = [doc.title for doc in docs]
        self.assertIn("ServiceA Stripe Validation Design Specs", titles)
        self.assertIn("Infrastructure Escalation Matrix", titles)
        self.assertIn("PostgreSQL Replica Migration Plan Q3", titles)
        self.assertIn("Incident Report: Webhook Outage", titles)


if __name__ == "__main__":
    unittest.main()
