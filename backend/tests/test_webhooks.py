import unittest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.services.db_manager import DBManager


class TestWebhooksIngestion(unittest.TestCase):
    """
    Test suite verifying webhook events are correctly ingested, parsed, 
    stored in SQLite/PostgreSQL databases, and indexed in Qdrant.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.db = DBManager()
        self.workspace_id = "webhook_test_ws"

    @patch("backend.api.webhooks.get_embedding")
    @patch("backend.api.webhooks.client")
    @patch("backend.api.webhooks.get_db_session")
    def test_slack_url_verification(self, mock_db_session, mock_qdrant_client, mock_get_embedding):
        """Verifies Slack URL verification request challenge."""
        payload = {
            "token": "verification_token_123",
            "challenge": "challenge_response_456",
            "type": "url_verification"
        }
        response = self.client.post("/webhooks/slack/events", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"challenge": "challenge_response_456"})

    @patch("backend.api.webhooks.get_embedding")
    @patch("backend.api.webhooks.client")
    @patch("backend.api.webhooks.get_db_session")
    def test_slack_incident_message_webhook(self, mock_db_session, mock_qdrant_client, mock_get_embedding):
        """Verifies Slack message from incident channel triggers incident registration."""
        mock_get_embedding.return_value = [0.1] * 384
        
        # Mock database session with AsyncMock
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        payload = {
            "workspace_id": self.workspace_id,
            "event_id": "slack_msg_999",
            "event": {
                "type": "message",
                "channel": "incident-billing-timeouts",
                "text": "Stripe payments are timeout failing under heavy traffic.",
                "user": "U12345"
            }
        }

        response = self.client.post("/webhooks/slack/events", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

        # Assert raw webhook event is stored in SQLite
        events = self.db.get_webhook_events(self.workspace_id, "slack")
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0]["webhook_event_id"], "slack_msg_999")

        # Assert structured operational event is created in SQLite
        sqlite_events = self.db.get_timeline(workspace_id=self.workspace_id)
        slack_events = [e for e in sqlite_events if e["event_type"] == "incident" and "Slack Incident Chat" in e["title"]]
        self.assertTrue(len(slack_events) > 0)
        self.assertIn("Stripe payments are timeout", slack_events[0]["summary"])

        # Assert Postgres session was called to persist the event
        mock_session.add.assert_called()
        # Assert Qdrant client upserted the event
        mock_qdrant_client.upsert.assert_called()

    @patch("backend.api.webhooks.get_embedding")
    @patch("backend.api.webhooks.client")
    @patch("backend.api.webhooks.get_db_session")
    def test_github_deployment_webhook(self, mock_db_session, mock_qdrant_client, mock_get_embedding):
        """Verifies GitHub deployment webhook triggers deployment registration."""
        mock_get_embedding.return_value = [0.1] * 384
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        payload = {
            "workspace_id": self.workspace_id,
            "repository": {"name": "cord-gateway"},
            "ref": "release-v2.3.4",
            "deployment": {
                "environment": "production",
                "creator": {"login": "rupamthxt"}
            }
        }

        headers = {"X-GitHub-Event": "deployment"}
        response = self.client.post("/webhooks/github/events", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        # Assert structured event stored in SQLite
        sqlite_events = self.db.get_timeline(workspace_id=self.workspace_id)
        deploy_events = [e for e in sqlite_events if e["event_type"] == "deployment"]
        self.assertTrue(len(deploy_events) > 0)
        self.assertEqual(deploy_events[0]["title"], "GitHub Deployment: cord-gateway to production")

        # Assert storage invocations
        mock_session.add.assert_called()
        mock_qdrant_client.upsert.assert_called()

    @patch("backend.api.webhooks.get_embedding")
    @patch("backend.api.webhooks.client")
    @patch("backend.api.webhooks.get_db_session")
    def test_sentry_alert_webhook(self, mock_db_session, mock_qdrant_client, mock_get_embedding):
        """Verifies Sentry alert webhook triggers incident registration."""
        mock_get_embedding.return_value = [0.1] * 384
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        payload = {
            "workspace_id": self.workspace_id,
            "project_name": "gateway-api",
            "error_message": "Redis connection pool exhaustion: limit reached",
            "level": "error"
        }

        response = self.client.post("/webhooks/sentry/alerts", json=payload)
        self.assertEqual(response.status_code, 200)

        # Assert structured event stored in SQLite
        sqlite_events = self.db.get_timeline(workspace_id=self.workspace_id)
        incident_events = [e for e in sqlite_events if e["event_type"] == "incident" and "Sentry Alert" in e["title"]]
        self.assertTrue(len(incident_events) > 0)
        self.assertEqual(incident_events[0]["title"], "Sentry Alert: gateway-api Exception")
        self.assertEqual(incident_events[0]["summary"], "Redis connection pool exhaustion: limit reached")

        # Assert storage invocations
        mock_session.add.assert_called()
        mock_qdrant_client.upsert.assert_called()

    @patch("backend.api.chat.search")
    @patch("backend.api.chat.ollama_client")
    def test_chat_diagnostics_offline_fallback(self, mock_ollama, mock_search):
        """Verifies that the /insights/chat endpoint falls back to programmatic context display when Ollama is offline."""
        # Setup async mocks
        mock_ollama.is_available = AsyncMock(return_value=False)
        
        mock_search.return_value = {
            "results": [
                {
                    "content": "Redis connection pool size set to 10.",
                    "source": "notion",
                    "metadata": {"title": "Redis Configurations"}
                }
            ]
        }

        payload = {
            "query": "What is the Redis pool size?",
            "workspace_id": self.workspace_id,
            "history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "How can I help you?"}
            ]
        }

        response = self.client.post("/insights/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("response", data)
        self.assertIn("Ollama offline fallback", data["response"])
        self.assertIn("Redis Configurations", data["response"])
        self.assertEqual(len(data["evidence"]["chunks"]), 1)

    def test_rollback_playbook(self):
        """Verifies that the /insights/actions/rollback endpoint triggers simulated rollback successfully."""
        payload = {
            "workspace_id": self.workspace_id,
            "repository": "cord-gateway",
            "environment": "production",
            "target_ref": "v2.3.3"
        }
        response = self.client.post("/insights/actions/rollback", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["repository"], "cord-gateway")
        self.assertEqual(data["target_ref"], "v2.3.3")

    def test_postmortem_playbook(self):
        """Verifies that the /insights/actions/postmortem endpoint compiles and drafts a postmortem report."""
        payload = {
            "workspace_id": self.workspace_id,
            "incident_title": "Database connection pool exhaustion",
            "incident_summary": "Sentry reported 500s because connection pool hit limit 10",
            "timeline": [
                {"timestamp": "2026-05-28T12:00:00Z", "title": "Sentry Alert", "summary": "DB error"}
            ],
            "evidence": [
                {"content": "Redis configurations", "source": "notion"}
            ]
        }
        response = self.client.post("/insights/actions/postmortem", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("Incident Postmortem", data["markdown"])
        self.assertIn("DB error", data["markdown"])
        self.assertFalse(data["pushed_to_notion"])

    def test_oauth_callback(self):
        """Verifies that the OAuth connection callback saves credentials successfully."""
        response = self.client.get(f"/auth/slack/callback?code=mock_code_123&state={self.workspace_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Slack Connection Successful!", response.text)
        
        # Verify credential record was stored
        creds = self.db.get_connector_credentials(self.workspace_id, "slack")
        self.assertIsNotNone(creds)
        self.assertIn("xoxb-mock-token", creds["credentials_json"])

    @patch("backend.intelligence.evidence_aggregator.client")
    def test_workspace_autodiscovery(self, mock_qdrant_client):
        """Verifies that the evidence aggregator automatically infers workspace ID based on vector payload."""
        # Setup Qdrant points return payload
        mock_point = MagicMock()
        mock_point.payload = {"workspace_id": "discovered_test_ws"}
        mock_qdrant_client.query_points.return_value.points = [mock_point]

        from backend.intelligence.evidence_aggregator import EvidenceAggregator
        aggregator = EvidenceAggregator()
        
        # Call aggregate with workspace_id=None to trigger autodiscovery
        with patch("backend.intelligence.evidence_aggregator.search") as mock_search:
            mock_search.return_value = {"results": []}
            aggregator.aggregate(query="Stripe validation failure", workspace_id=None)
            
            # Assert search was called with the discovered workspace_id
            mock_search.assert_called_once_with(
                query="Stripe validation failure",
                limit=20,
                workspace_id="discovered_test_ws"
            )


if __name__ == "__main__":
    unittest.main()
