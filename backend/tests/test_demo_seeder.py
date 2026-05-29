import unittest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.services.db_manager import DBManager
from backend.core.models.setup_client import client as qdrant_client

class TestDemoSeeder(unittest.TestCase):
    """Test suite for the Demo Seeding endpoint and utilities."""

    def setUp(self):
        self.client = TestClient(app)
        self.db = DBManager()

    def test_demo_seed_endpoint(self):
        """Verifies that POST /api/demo/seed seeds database records successfully."""
        response = self.client.post("/api/demo/seed")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["workspace_id"], "demo_workspace")

        # Verify SQLite Events
        with self.db.get_connection() as conn:
            events = conn.execute(
                "SELECT * FROM events WHERE workspace_id = 'demo_workspace'"
            ).fetchall()
            self.assertGreater(len(events), 0)

            # Verify credentials status
            notion_cred = conn.execute(
                "SELECT * FROM connector_credentials WHERE workspace_id = 'demo_workspace' AND connector_type = 'notion'"
            ).fetchone()
            self.assertIsNotNone(notion_cred)
            self.assertEqual(notion_cred["status"], "configured")

        # Verify Qdrant collections contain seeded points
        mem_collection = qdrant_client.get_collection("workspace_memory")
        self.assertGreater(mem_collection.points_count, 0)

        ev_collection = qdrant_client.get_collection("workspace_events")
        self.assertGreater(ev_collection.points_count, 0)

if __name__ == "__main__":
    unittest.main()
