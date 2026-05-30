import unittest
import logging
import time
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.services.db_manager import DBManager
from backend.core.models.setup_client import client as qdrant_client
from backend.core.models.store_memory import store_chunks, COLLECTION_NAME
from backend.core.models.memory_schema import MemoryDocument
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestBillingLimits(unittest.TestCase):
    """
    Test suite for Stripe billing APIs, mock webhooks, and quota enforcements.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.db = DBManager()
        
        # Create a test user and a workspace
        self.test_user_id = "test_user_billing_123"
        self.test_email = "billing_tester@cord.com"
        
        # Add test user to database directly
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO users (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                         (self.test_user_id, self.test_email, "hash", "2026-05-30T00:00:00Z"))
        
        self.workspace_id = "test_workspace_billing"
        self.db.create_workspace(self.workspace_id, "Billing Test WS", self.test_user_id)
        
        # Ensure workspace is free first
        self.db.update_workspace_subscription(
            self.workspace_id,
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_status="active",
            plan_level="free"
        )
        
        # Clear any Qdrant points for this workspace to start clean
        try:
            qdrant_client.get_collection(COLLECTION_NAME)
            # Delete points for this workspace
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant_client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="workspace_id", match=MatchValue(value=self.workspace_id))]
                )
            )
        except Exception:
            pass

    def tearDown(self):
        # Cleanup test workspace and user
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM user_workspaces WHERE workspace_id = ?", (self.workspace_id,))
            conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (self.workspace_id,))
            conn.execute("DELETE FROM users WHERE user_id = ?", (self.test_user_id,))
            
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant_client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="workspace_id", match=MatchValue(value=self.workspace_id))]
                )
            )
        except Exception:
            pass

    def test_checkout_and_portal_session_mock(self):
        """Verifies creating checkout and portal sessions in mock mode."""
        headers = {"Authorization": f"Bearer {self.test_user_id}"}
        
        # 1. Checkout Session Creation
        response = self.client.post(
            "/billing/checkout-session",
            json={
                "workspace_id": self.workspace_id,
                "success_url": "http://localhost:8000/dashboard?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": "http://localhost:8000/dashboard"
            },
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("url", data)
        self.assertIn("session_id", data)
        self.assertTrue(data["session_id"].startswith("cs_test_"))
        
        # Allow background simulation task to run
        time.sleep(0.6)
        
        # Verify workspace upgraded to Pro
        workspace = self.db.get_workspace(self.workspace_id)
        self.assertEqual(workspace["plan_level"], "pro")
        
        # 2. Portal Session Creation (should return return_url since it's mock)
        response_portal = self.client.post(
            "/billing/portal-session",
            json={
                "workspace_id": self.workspace_id,
                "return_url": "http://localhost:8000/dashboard"
            },
            headers=headers
        )
        self.assertEqual(response_portal.status_code, 200)
        portal_data = response_portal.json()
        self.assertEqual(portal_data["url"], "http://localhost:8000/dashboard")

    def test_stripe_webhook_updates(self):
        """Verifies the Stripe Webhook endpoint correctly maps updates and deletions to SQLite workspaces."""
        # 1. Create a subscription created event payload
        sub_id = "sub_test_webhook_123"
        cus_id = "cus_test_webhook_123"
        payload = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": sub_id,
                    "customer": cus_id,
                    "status": "active",
                    "client_reference_id": self.workspace_id,
                    "metadata": {
                        "workspace_id": self.workspace_id
                    }
                }
            }
        }
        
        response = self.client.post(
            "/webhooks/stripe",
            json=payload
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify db updated
        workspace = self.db.get_workspace(self.workspace_id)
        self.assertEqual(workspace["plan_level"], "pro")
        self.assertEqual(workspace["stripe_subscription_id"], sub_id)
        self.assertEqual(workspace["stripe_customer_id"], cus_id)
        self.assertEqual(workspace["subscription_status"], "active")
        
        # 2. Test deletion (cancellation)
        payload_delete = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": sub_id
                }
            }
        }
        response_delete = self.client.post(
            "/webhooks/stripe",
            json=payload_delete
        )
        self.assertEqual(response_delete.status_code, 200)
        
        # Verify downgraded to Free
        workspace_deleted = self.db.get_workspace(self.workspace_id)
        self.assertEqual(workspace_deleted["plan_level"], "free")
        self.assertEqual(workspace_deleted["subscription_status"], "canceled")

    def test_quota_limits_free_vs_pro(self):
        """Verifies that the 50 document quota is blocked for Free plan and enabled for Pro plan."""
        headers = {"Authorization": f"Bearer {self.test_user_id}"}
        
        # 1. Workspace is Free by default. Let's ingest 50 documents into Qdrant.
        # Standardize and save mock documents
        for i in range(50):
            doc = MemoryDocument(
                id=f"doc_{self.workspace_id}_{i}",
                source="jira",
                source_id=f"limit_issue_{i}",
                workspace_id=self.workspace_id,
                parent_id=None,
                path=f"/Jira/limit_issue_{i}",
                title=f"Mock Issue {i}",
                content=f"This is a mock issue body for index {i}.",
                url=f"https://jira.company.com/browse/limit_issue_{i}",
                author="Tester",
                created_time=datetime.now(timezone.utc),
                last_edited_time=datetime.now(timezone.utc),
                tags=["jira", "ticket"],
                metadata={"ticket_key": f"limit_issue_{i}", "workspace_id": self.workspace_id, "source": "jira"}
            )
            store_chunks([f"This is a mock issue body for index {i}."], metadata=doc)
            
        # Assert that document count in workspace is 50
        count = self.db.get_workspace_document_count(self.workspace_id)
        self.assertEqual(count, 50)
        
        # 2. Try to sync Jira tickets while on the Free plan (should fail with 403 WORKSPACE_QUOTA_EXCEEDED)
        sync_response = self.client.post(
            "/connectors/jira/sync",
            json={"workspace_id": self.workspace_id}
        )
        self.assertEqual(sync_response.status_code, 403)
        self.assertEqual(sync_response.json()["detail"], "WORKSPACE_QUOTA_EXCEEDED")
        
        # 3. Try to sync Notion/Slack workspace sync while on the Free plan (should fail with 403 WORKSPACE_QUOTA_EXCEEDED)
        ws_sync_response = self.client.post(
            f"/api/workspaces/{self.workspace_id}/sync",
            headers=headers
        )
        self.assertEqual(ws_sync_response.status_code, 403)
        self.assertEqual(ws_sync_response.json()["detail"], "WORKSPACE_QUOTA_EXCEEDED")
        
        # 4. Now upgrade workspace to Pro
        self.db.update_workspace_subscription(self.workspace_id, plan_level="pro")
        
        # 5. Try syncing Jira tickets again (should proceed and return 200)
        with patch("backend.connectors.jira.jira_connector.JiraConnector.fetch", return_value=[]):
            sync_response_pro = self.client.post(
                "/connectors/jira/sync",
                json={"workspace_id": self.workspace_id}
            )
            self.assertEqual(sync_response_pro.status_code, 200)
            
        # 6. Try Notion/Slack workspace sync again (should proceed and return 200)
        ws_sync_response_pro = self.client.post(
            f"/api/workspaces/{self.workspace_id}/sync",
            headers=headers
        )
        self.assertEqual(ws_sync_response_pro.status_code, 200)


if __name__ == "__main__":
    unittest.main()
