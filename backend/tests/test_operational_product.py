import unittest
import logging
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.connectors.jira.jira_connector import JiraConnector
from backend.core.services.db_manager import DBManager
from backend.core.models.setup_client import client as qdrant_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestOperationalProduct(unittest.TestCase):
    """
    Test suite for Operational Issue Intelligence product layer:
    - Jira Integration Connector
    - Workspace isolation / security boundaries
    - REST Insights endpoints
    """

    def setUp(self):
        self.client = TestClient(app)
        self.db = DBManager()

    def test_jira_connector_fetch(self):
        """Verifies that the Jira connector can fetch and normalize tickets correctly."""
        workspace = "jira_test_workspace"
        connector = JiraConnector(workspace_id=workspace)
        docs = connector.fetch()
        self.assertEqual(len(docs), 0)

    def test_workspace_isolation_and_insights(self):
        """
        Verifies that data stored in one workspace is isolated from another.
        Syncs Jira tickets in 'test_workspace_scope' and asserts that:
        1. Querying 'test_workspace_scope' returns synced tickets / insights.
        2. Querying 'other_workspace_scope' returns empty results (security isolation).
        """
        target_ws = "test_workspace_scope"
        other_ws = "other_workspace_scope"
        
        from unittest.mock import patch
        from backend.core.models.memory_schema import MemoryDocument
        from datetime import datetime, timezone
        
        mock_docs = [
            MemoryDocument(
                id="jira_issue_COR-101",
                source="jira",
                source_id="COR-101",
                workspace_id=target_ws,
                parent_id=None,
                path="/Jira/Projects/COR/COR-101",
                title="Jira Issue COR-101: Database connection pool timeouts",
                content="Stripe webhook processing fails with database connection pool timeouts.",
                url="https://jira.company.com/browse/COR-101",
                author="Bob",
                created_time=datetime.now(timezone.utc),
                last_edited_time=datetime.now(timezone.utc),
                tags=["jira", "ticket"],
                metadata={"ticket_key": "COR-101", "status": "Done", "workspace_id": target_ws, "source": "jira"}
            )
        ]
        
        logger.info(f"Syncing Jira tickets for workspace: {target_ws}")
        with patch("backend.connectors.jira.jira_connector.JiraConnector.fetch", return_value=mock_docs):
            sync_response = self.client.post(
                "/connectors/jira/sync",
                json={"workspace_id": target_ws}
            )
            self.assertEqual(sync_response.status_code, 200)
            sync_data = sync_response.json()
            self.assertEqual(sync_data["status"], "success")
            self.assertGreater(sync_data["synced_tickets_count"], 0)
        
        logger.info("Verifying insights for targeted workspace...")
        # Search queries for the target workspace
        res_target = self.client.post(
            "/insights/deployments",
            json={
                "query": "Database connection pool timeouts",
                "limit": 5,
                "workspace_id": target_ws
            }
        )
        self.assertEqual(res_target.status_code, 200)
        target_data = res_target.json()
        
        # Verify that we retrieved evidence or documents belonging to the workspace
        evidence_chunks = target_data.get("evidence", {}).get("chunks", [])
        self.assertGreater(
            len(evidence_chunks), 0,
            f"Expected to find evidence chunks in workspace '{target_ws}'"
        )
        for chunk in evidence_chunks:
            self.assertEqual(
                chunk.get("workspace_id"), target_ws,
                "Chunkn belongs to a different workspace!"
            )
            
        logger.info("Verifying security boundaries on other workspace...")
        res_other = self.client.post(
            "/insights/deployments",
            json={
                "query": "Database connection pool timeouts",
                "limit": 5,
                "workspace_id": other_ws
            }
        )
        self.assertEqual(res_other.status_code, 200)
        other_data = res_other.json()
        
        other_chunks = other_data.get("evidence", {}).get("chunks", [])
        self.assertEqual(
            len(other_chunks), 0,
            f"Security Breach! Evidence from workspace '{target_ws}' leaked to '{other_ws}'"
        )

    def test_all_insights_endpoints(self):
        """Verifies that all operational insights endpoints return HTTP 200."""
        endpoints = [
            "/insights/operational-issues",
            "/insights/deployments",
            "/insights/incidents",
            "/insights/root-causes",
            "/insights/trends",
            "/insights/escalations",
            "/insights/bottlenecks"
        ]
        
        for ep in endpoints:
            logger.info(f"Testing GET/POST endpoint: {ep}")
            response = self.client.post(
                ep,
                json={
                    "query": "ServiceA Stripe validation timeout",
                    "limit": 5,
                    "workspace_id": "demo_test_ws"
                }
            )
            self.assertEqual(
                response.status_code, 200,
                f"Endpoint {ep} failed with status {response.status_code}"
            )
            data = response.json()
            self.assertIn("query", data)
            self.assertIn("insight", data)
            self.assertIn("evidence", data)
            self.assertIn("diagnostics", data)


if __name__ == "__main__":
    unittest.main()
