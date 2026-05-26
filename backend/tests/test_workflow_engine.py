"""
Tests for the supervised workflow state engine and coordination coordinator.
Covers: state transitions, escalation routing, and metadata audit transition logs.

Run with: python -m unittest backend/tests/test_workflow_engine.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.intelligence.coordination.engine import WorkflowCoordinator
from backend.intelligence.workflows.schema import WorkflowCreate, WorkflowUpdate
from backend.intelligence.workflows.store import workflow_store


class TestWorkflowEngine(unittest.IsolatedAsyncioTestCase):
    """Tests for the WorkflowStore and WorkflowCoordinator."""

    def setUp(self):
        self.store = workflow_store
        self.coordinator = WorkflowCoordinator()
        self.workspace_id = "default_workspace"

    async def test_create_workflow(self):
        session = AsyncMock()

        payload = WorkflowCreate(
            title="Investigate Pool exhaustion",
            workflow_type="incident_response",
            state="draft",
            assigned_entities=[{"name": "DevOps", "type": "team"}],
            priority="high",
            workspace_id=self.workspace_id,
        )

        workflow = await self.store.create_workflow(session, payload)

        self.assertEqual(workflow.title, "Investigate Pool exhaustion")
        self.assertEqual(workflow.state, "draft")
        self.assertEqual(workflow.priority, "high")
        # Check initial state transition audit trail
        transitions = workflow.metadata_["state_transitions"]
        self.assertEqual(len(transitions), 1)
        self.assertIsNone(transitions[0]["from_state"])
        self.assertEqual(transitions[0]["to_state"], "draft")
        self.assertEqual(transitions[0]["notes"], "Workflow created.")
        session.add.assert_called_once()

    async def test_update_workflow_state(self):
        session = AsyncMock()

        # Mock an existing workflow
        mock_wf = MagicMock()
        mock_wf.id = uuid4()
        mock_wf.state = "draft"
        mock_wf.metadata_ = {"state_transitions": []}
        mock_wf.workspace_id = self.workspace_id

        # Setup store mock on the singleton directly
        with patch.object(workflow_store, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_wf
            updated = await self.store.update_workflow_state(
                session=session,
                workflow_id=mock_wf.id,
                state="pending_review",
                user_notes="Ready for manager approval.",
                workspace_id=self.workspace_id,
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated.state, "pending_review")
            transitions = updated.metadata_["state_transitions"]
            self.assertEqual(len(transitions), 1)
            self.assertEqual(transitions[0]["from_state"], "draft")
            self.assertEqual(transitions[0]["to_state"], "pending_review")
            self.assertEqual(transitions[0]["notes"], "Ready for manager approval.")

    async def test_workflow_coordinator_approve(self):
        session = AsyncMock()
        workflow_id = uuid4()
        
        with patch.object(workflow_store, "update_workflow_state", new_callable=AsyncMock) as mock_update_state:
            mock_update_state.return_value = MagicMock(state="in_progress")
            res = await self.coordinator.approve_workflow(
                session=session,
                workflow_id=workflow_id,
                approval_notes="LGTM",
                workspace_id=self.workspace_id,
            )
            self.assertIsNotNone(res)
            mock_update_state.assert_called_once_with(
                session=session,
                workflow_id=workflow_id,
                state="in_progress",
                user_notes="Approved: LGTM",
                workspace_id=self.workspace_id,
            )

    async def test_workflow_coordinator_escalate_incident(self):
        session = AsyncMock()

        mock_wf = MagicMock()
        mock_wf.id = uuid4()
        mock_wf.title = "Incident DB Saturation"
        mock_wf.workflow_type = "incident_response"
        mock_wf.state = "in_progress"
        mock_wf.workspace_id = self.workspace_id
        mock_wf.metadata_ = {}

        with patch.object(workflow_store, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_wf
            with patch.object(workflow_store, "update_workflow", new_callable=AsyncMock) as mock_update:
                mock_update.return_value = MagicMock(state="escalated")
                
                await self.coordinator.escalate_workflow(
                    session=session,
                    workflow_id=mock_wf.id,
                    escalation_notes="SLA breach imminent",
                    workspace_id=self.workspace_id,
                )

                # Ensure update payload escalated assignee to Director of Engineering
                call_args = mock_update.call_args[0]
                payload = call_args[2]
                self.assertEqual(payload.state, "escalated")
                self.assertEqual(payload.assigned_entities[0]["name"], "Director of Engineering / Incident Commander")

    async def test_workflow_coordinator_escalate_customer(self):
        session = AsyncMock()

        mock_wf = MagicMock()
        mock_wf.id = uuid4()
        mock_wf.title = "High Support Volume"
        mock_wf.workflow_type = "customer_escalation"
        mock_wf.state = "in_progress"
        mock_wf.workspace_id = self.workspace_id
        mock_wf.metadata_ = {}

        with patch.object(workflow_store, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_wf
            with patch.object(workflow_store, "update_workflow", new_callable=AsyncMock) as mock_update:
                mock_update.return_value = MagicMock(state="escalated")
                
                await self.coordinator.escalate_workflow(
                    session=session,
                    workflow_id=mock_wf.id,
                    escalation_notes="Enterprise customer angry",
                    workspace_id=self.workspace_id,
                )

                call_args = mock_update.call_args[0]
                payload = call_args[2]
                self.assertEqual(payload.state, "escalated")
                self.assertEqual(payload.assigned_entities[0]["name"], "Head of Customer Relations")


if __name__ == "__main__":
    unittest.main()
