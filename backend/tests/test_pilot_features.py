"""
Unit tests for Cord's Pilot Operational Intelligence endpoints and Security utilities.
Covers:
- WorkspaceIsolationManager scope checks
- CredentialVault register/fetch boundaries
- AuditLogger log formatting
- VisibilityFilter source filter logic
- All /pilot/* endpoints via FastAPI TestClient
"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.utils.security import (
    workspace_isolation,
    vault,
    audit_logger,
    visibility_filter,
)

class TestSecurityUtils(unittest.TestCase):
    """Tests for core security, isolation, and access controls."""

    def test_workspace_isolation_enforcement(self):
        # Empty inputs should fall back to default_workspace
        self.assertEqual(workspace_isolation.enforce_workspace_scope(""), "default_workspace")
        self.assertEqual(workspace_isolation.enforce_workspace_scope("  "), "default_workspace")
        
        # Valid workspace ids should be stripped and returned
        self.assertEqual(workspace_isolation.enforce_workspace_scope("my_workspace  "), "my_workspace")
        self.assertEqual(workspace_isolation.enforce_workspace_scope(None, "override_ws"), "override_ws")

    def test_credential_vault(self):
        # Check standard credentials after registering
        vault.register_credential("default_workspace", "notion", "secret_notion_default_token_123")
        default_notion = vault.get_credential("default_workspace", "notion")
        self.assertEqual(default_notion, "secret_notion_default_token_123")

        # Register new credentials and query them
        vault.register_credential("temp_test_workspace", "slack", "xoxb-temp-secret-999")
        self.assertEqual(vault.get_credential("temp_test_workspace", "slack"), "xoxb-temp-secret-999")

        # Check environment variable fallback
        with patch.dict(os.environ, {"GDRIVE_BOT_TOKEN": "gdrive-env-token-777"}):
            env_token = vault.get_credential("non_existent_workspace", "gdrive")
            self.assertEqual(env_token, "gdrive-env-token-777")

    def test_audit_logger(self):
        with patch("backend.core.utils.security.logger.info") as mock_log:
            audit_logger.log_access("SELECT * FROM documents", "demo_test_ws", "QueryDocs")
            mock_log.assert_called_once()
            log_msg = mock_log.call_args[0][0]
            self.assertIn("[AUDIT]", log_msg)
            self.assertIn("demo_test_ws", log_msg)
            self.assertIn("QueryDocs", log_msg)

    def test_visibility_filter(self):
        # Sample document class
        class MockDoc:
            def __init__(self, source):
                self.source = source

        docs = [
            MockDoc("slack"),
            MockDoc("notion"),
            {"source": "slack"},
            {"source": "jira"},
            {"source": "gdrive"},
        ]

        # Allowed sources list
        filtered = visibility_filter.filter_sources(docs, ["slack", "jira"])
        self.assertEqual(len(filtered), 3)
        for doc in filtered:
            source = getattr(doc, "source", None) or doc.get("source")
            self.assertIn(source, ["slack", "jira"])

        # No filter should return everything
        self.assertEqual(len(visibility_filter.filter_sources(docs, None)), len(docs))
        self.assertEqual(len(visibility_filter.filter_sources(docs, [])), len(docs))


class TestPilotEndpoints(unittest.TestCase):
    """Tests for all pilot operational reasoning and evaluation REST routes."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.api.pilot_router.analyzer")
    def test_operational_issues_endpoint(self, mock_analyzer):
        mock_analyzer.analyze_recurring_issues = AsyncMock(return_value=[{
            "id": "recurring-stripe",
            "title": "Recurring Stripe Activity Detected",
            "category": "Stripe Signal Cluster",
            "summary": "Multiple events found...",
            "confidence_diagnostics": {
                "score": 0.85,
                "factors_positive": [],
                "factors_negative": [],
                "data_sources": ["slack"],
                "evidence_count": 2
            },
            "assigned_team": "Billing Integration Team",
            "assignee": "Billing Engineer",
            "status": "Under Investigation",
            "severity": "medium",
            "evidence": []
        }])
        response = self.client.post(
            "/pilot/operational-issues",
            json={"workspace_id": "demo_test_ws", "limit": 10}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_id"], "demo_test_ws")
        self.assertIn("recurring_issues_count", data)
        self.assertIn("issues", data)
        self.assertGreater(len(data["issues"]), 0)
        for issue in data["issues"]:
            self.assertIn("confidence_diagnostics", issue)
            self.assertIn("score", issue["confidence_diagnostics"])
            self.assertIn("evidence", issue)

    @patch("backend.api.pilot_router.analyzer")
    def test_deployment_analysis_endpoint(self, mock_analyzer):
        mock_analyzer.analyze_deployments = AsyncMock(return_value=[{
            "id": "dep-1",
            "title": "Deploy BillingService v2.5.0",
            "timestamp": "2026-05-26T07:00:00Z",
            "author": "Alice",
            "stability_score": 100.0,
            "linked_incidents": [],
            "confidence_diagnostics": {
                "score": 0.95,
                "factors_positive": [],
                "factors_negative": []
            }
        }])
        response = self.client.post(
            "/pilot/deployment-analysis",
            json={"workspace_id": "demo_test_ws", "limit": 5}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_id"], "demo_test_ws")
        self.assertIn("deployments_analyzed", data)
        self.assertIn("deployments", data)
        self.assertGreater(len(data["deployments"]), 0)
        for dep in data["deployments"]:
            self.assertIn("stability_score", dep)
            self.assertIn("linked_incidents", dep)

    @patch("backend.api.pilot_router.analyzer")
    def test_escalation_analysis_endpoint(self, mock_analyzer):
        mock_analyzer.analyze_escalations = AsyncMock(return_value=[{
            "id": "wf-123",
            "title": "Escalation to Billing Team",
            "incident_type": "incident",
            "priority": "high",
            "current_state": "open",
            "escalation_route": [{"step": 1, "role": "Assignee", "duration_minutes": 30}],
            "total_triage_minutes": 30,
            "bottleneck_identified": "None",
            "confidence_diagnostics": {"score": 0.85}
        }])
        response = self.client.post(
            "/pilot/escalation-analysis",
            json={"workspace_id": "demo_test_ws", "limit": 10}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_id"], "demo_test_ws")
        self.assertIn("escalations_tracked", data)
        self.assertIn("escalations", data)
        self.assertGreater(len(data["escalations"]), 0)
        for esc in data["escalations"]:
            self.assertIn("escalation_route", esc)
            self.assertIn("total_triage_minutes", esc)

    @patch("backend.api.pilot_router.analyzer")
    def test_incident_explorer_endpoint(self, mock_analyzer):
        mock_analyzer.analyze_incidents = AsyncMock(return_value=[{
            "id": "inc-456",
            "title": "Stripe Webhook Signature Verification Failures",
            "timestamp": "2026-05-26T07:10:00Z",
            "severity": "critical",
            "correlated_slack_channel": "#billing-alerts",
            "correlated_jira_ticket": "COR-101",
            "affected_system": "BillingService",
            "evidence_snippets": ["Stripe signature verification fails"],
            "confidence": 0.95
        }])
        response = self.client.post(
            "/pilot/incident-explorer",
            json={
                "workspace_id": "demo_test_ws",
                "query": "stripe webhook signature validation",
                "limit": 10
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_id"], "demo_test_ws")
        self.assertEqual(data["query"], "stripe webhook signature validation")
        self.assertIn("incidents_matched", data)
        self.assertIn("incidents", data)
        self.assertGreater(len(data["incidents"]), 0)

    @patch("backend.api.pilot_router.analyzer")
    def test_timeline_analysis_endpoint(self, mock_analyzer):
        mock_analyzer.analyze_timeline = AsyncMock(return_value=[{
            "id": "ev-789",
            "title": "Event Title",
            "event_type": "incident",
            "timestamp": "2026-05-26T07:05:00Z",
            "summary": "Event summary",
            "severity": "medium",
            "metadata": {}
        }])
        response = self.client.post(
            "/pilot/timeline-analysis",
            json={"workspace_id": "demo_test_ws", "limit": 10}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_id"], "demo_test_ws")
        self.assertIn("timeline_events_count", data)
        self.assertIn("timeline", data)
        self.assertGreater(len(data["timeline"]), 0)
        
        # Verify timeline is sorted chronologically (ascending timestamps)
        timestamps = [event.get("timestamp") for event in data["timeline"] if event.get("timestamp")]
        sorted_timestamps = sorted(timestamps)
        self.assertEqual(timestamps, sorted_timestamps)

    def test_evaluate_endpoint(self):
        with patch("backend.api.pilot_router.get_db_session") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            
            mock_execute_res = MagicMock()
            mock_execute_res.scalar.return_value = 0
            mock_session.execute = AsyncMock(return_value=mock_execute_res)
            
            response = self.client.post(
                "/pilot/evaluate",
                json={"workspace_id": "demo_test_ws"}
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["workspace_id"], "demo_test_ws")
            self.assertIn("retrieval_precision", data)
            self.assertIn("retrieval_recall", data)
            self.assertIn("evidence_consistency_score", data)
            self.assertIn("hallucination_rate", data)
            self.assertIn("confidence_calibration_ratio", data)
            self.assertIn("diagnostics", data)


if __name__ == "__main__":
    unittest.main()
