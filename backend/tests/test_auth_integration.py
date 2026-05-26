import os
import json
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.services.db_manager import DBManager
from backend.core.utils.security import vault

class TestAuthIntegration(unittest.TestCase):
    """
    Test suite for Authentication, Workspace management, and Integration settings endpoints.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.db = DBManager()
        self.test_email = "tester_auth_unit@company.com"
        self.test_password = "SecurePassword123"
        
        # Clean up existing test data
        with self.db.get_connection() as conn:
            # Delete user, workspaces, and credentials
            row = conn.execute("SELECT user_id FROM users WHERE email = ?", (self.test_email,)).fetchone()
            if row:
                uid = row["user_id"]
                conn.execute("DELETE FROM user_workspaces WHERE user_id = ?", (uid,))
                conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            
            # Clean up test workspace IDs
            conn.execute("DELETE FROM connector_credentials WHERE workspace_id IN ('tester_auth_unit_workspace', 'test_custom_ws')")
            conn.execute("DELETE FROM workspaces WHERE workspace_id IN ('tester_auth_unit_workspace', 'test_custom_ws')")
            conn.execute("DELETE FROM user_workspaces WHERE workspace_id IN ('tester_auth_unit_workspace', 'test_custom_ws')")
            conn.commit()

    def test_signup_and_login_flow(self):
        # 1. Test user signup
        signup_res = self.client.post(
            "/api/auth/signup",
            json={"email": self.test_email, "password": self.test_password}
        )
        self.assertEqual(signup_res.status_code, 200)
        signup_data = signup_res.json()
        self.assertEqual(signup_data["status"], "success")
        self.assertEqual(signup_data["user"]["email"], self.test_email)
        self.assertIn("default_workspace_id", signup_data["user"])
        
        # 2. Test duplicate user signup fails
        dup_res = self.client.post(
            "/api/auth/signup",
            json={"email": self.test_email, "password": self.test_password}
        )
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("exists", dup_res.json()["detail"].lower())

        # 3. Test user login
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.test_email, "password": self.test_password}
        )
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()
        self.assertEqual(login_data["status"], "success")
        self.assertIn("token", login_data)
        self.assertEqual(login_data["user"]["email"], self.test_email)
        self.assertGreater(len(login_data["workspaces"]), 0)
        
        # Capture token and workspace
        token = login_data["token"]
        ws_id = login_data["user"]["default_workspace_id"]

        # 4. Test listing workspaces with token
        headers = {"Authorization": f"Bearer {token}"}
        ws_list_res = self.client.get("/api/workspaces", headers=headers)
        self.assertEqual(ws_list_res.status_code, 200)
        self.assertEqual(ws_list_res.json()["workspaces"][0]["workspace_id"], ws_id)

        # 5. Test workspace creation
        new_ws_id = "test_custom_ws"
        new_ws_name = "Custom Testing Workspace"
        create_ws_res = self.client.post(
            "/api/workspaces",
            json={"workspace_id": new_ws_id, "name": new_ws_name},
            headers=headers
        )
        self.assertEqual(create_ws_res.status_code, 200)
        self.assertEqual(create_ws_res.json()["workspace"]["workspace_id"], new_ws_id)
        
        # Verify it lists in user workspaces now
        ws_list_res2 = self.client.get("/api/workspaces", headers=headers)
        self.assertEqual(len(ws_list_res2.json()["workspaces"]), 2)

    def test_workspace_connector_credentials(self):
        # Setup user
        signup_res = self.client.post(
            "/api/auth/signup",
            json={"email": self.test_email, "password": self.test_password}
        )
        token = signup_res.json()["user"]["user_id"]
        ws_id = signup_res.json()["user"]["default_workspace_id"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Fetch connectors list (should show disconnected)
        conn_res = self.client.get(f"/api/workspaces/{ws_id}/connectors", headers=headers)
        self.assertEqual(conn_res.status_code, 200)
        conns_list = conn_res.json()["connectors"]
        notion_conn = next(c for c in conns_list if c["connector_type"] == "notion")
        self.assertFalse(notion_conn["connected"])
        self.assertEqual(notion_conn["status"], "not_configured")

        # 2. Save Notion credentials
        cred_payload = {"api_key": "prod_notion_key_value_999", "start_page_id": "test_page"}
        save_res = self.client.post(
            f"/api/workspaces/{ws_id}/connectors",
            json={"connector_type": "notion", "credentials_json": json.dumps(cred_payload)},
            headers=headers
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertEqual(save_res.json()["status"], "success")

        # 3. Check connectors list again (should show connected & masked)
        conn_res2 = self.client.get(f"/api/workspaces/{ws_id}/connectors", headers=headers)
        conns_list2 = conn_res2.json()["connectors"]
        notion_conn2 = next(c for c in conns_list2 if c["connector_type"] == "notion")
        self.assertTrue(notion_conn2["connected"])
        self.assertEqual(notion_conn2["status"], "active")
        self.assertEqual(notion_conn2["config_preview"]["api_key"], "********")

        # 4. Assert that the vault dynamically resolves saved credentials
        resolved_token = vault.get_credential(ws_id, "notion")
        self.assertEqual(resolved_token, "prod_notion_key_value_999")

    def test_connector_connection_testing(self):
        # 1. Mock connection test check
        mock_res = self.client.post(
            "/api/connectors/test",
            json={"connector_type": "slack", "credentials_json": json.dumps({"token": "mock-token-abc"})}
        )
        self.assertEqual(mock_res.status_code, 200)
        self.assertTrue(mock_res.json()["success"])
        self.assertIn("Mock Mode", mock_res.json()["message"])

        # 2. Invalid json credentials check
        invalid_res = self.client.post(
            "/api/connectors/test",
            json={"connector_type": "slack", "credentials_json": "not-valid-json"}
        )
        self.assertEqual(invalid_res.status_code, 400)

    def test_workspace_synchronization_endpoint(self):
        # 1. Signup user and get token and workspace_id
        signup_res = self.client.post(
            "/api/auth/signup",
            json={"email": self.test_email, "password": self.test_password}
        )
        self.assertEqual(signup_res.status_code, 200)
        data = signup_res.json()
        token = data["user"]["user_id"]
        ws_id = data["user"]["default_workspace_id"]
        
        # Configure mock credentials so the connectors are processed
        from backend.core.services.db_manager import DBManager
        db = DBManager()
        db.save_connector_credentials(ws_id, "notion", '{"api_key": "test_token"}')
        db.save_connector_credentials(ws_id, "slack", '{"token": "test_token"}')
        db.save_connector_credentials(ws_id, "jira", '{"url": "test"}')
        db.save_connector_credentials(ws_id, "gdrive", '{"type": "service_account"}')

        # 2. Trigger synchronization under patched connector clients
        from unittest.mock import patch, AsyncMock
        from backend.core.models.memory_schema import MemoryDocument
        from datetime import datetime, timezone
        
        mock_docs = [
            MemoryDocument(
                id="doc_1",
                source="notion",
                source_id="page_1",
                workspace_id=ws_id,
                path="/test",
                title="Test Title",
                content="This is database and postgres scaling test content.",
                author="Alice",
                created_time=datetime.now(timezone.utc),
                last_edited_time=datetime.now(timezone.utc)
            )
        ]
        
        headers = {"Authorization": f"Bearer {token}"}
        with patch("backend.connectors.notion.notion_connector.NotionConnector.fetch_workspace", new_callable=AsyncMock) as mock_notion, \
             patch("backend.connectors.slack.slack_connector.SlackConnector.fetch_workspace", new_callable=AsyncMock) as mock_slack, \
             patch("backend.connectors.jira.jira_connector.JiraConnector.fetch") as mock_jira, \
             patch("backend.connectors.gdrive.gdrive_connector.GoogleDriveConnector.fetch") as mock_gdrive:
            
            mock_notion.return_value = mock_docs
            mock_slack.return_value = mock_docs
            mock_jira.return_value = mock_docs
            mock_gdrive.return_value = mock_docs

            sync_res = self.client.post(
                f"/api/workspaces/{ws_id}/sync",
                headers=headers
            )
            self.assertEqual(sync_res.status_code, 200)
            sync_data = sync_res.json()
            self.assertEqual(sync_data["status"], "success")
            self.assertEqual(sync_data["workspace_id"], ws_id)
            self.assertGreater(sync_data["documents_synced"], 0)
            self.assertGreater(sync_data["chunks_created"], 0)
            self.assertIn("notion", sync_data["details"])
            self.assertIn("slack", sync_data["details"])


if __name__ == "__main__":
    unittest.main()

