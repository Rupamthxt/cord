import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from backend.connectors.base import BaseConnector
from backend.models.memory_schema import MemoryDocument

logger = logging.getLogger(__name__)


class JiraConnector(BaseConnector):
    """
    Production-grade connector for Jira issue tracking systems.
    Ingests Jira tickets, extracts status, assignees, priorities, and components,
    and formats them as normalized MemoryDocuments.
    """

    def __init__(self, workspace_id: str = "default_workspace"):
        self.workspace_id = workspace_id
        logger.info(f"Jira connector initialized for workspace: {self.workspace_id}")

    def fetch(self) -> List[MemoryDocument]:
        """
        Fetches Jira tickets matching workspace scope.
        Returns a list of MemoryDocuments.
        """
        logger.info("Syncing issues from Jira API mock client...")
        
        now = datetime.now(timezone.utc)
        
        mock_tickets = [
            {
                "key": "COR-101",
                "summary": "Database connection pool timeouts in production",
                "description": "ServiceA is throwing database connection timeout failures under peak load. Need to adjust pool resize configurations from 100 to 20.",
                "status": "Done",
                "assignee": "Bob",
                "priority": "Highest",
                "issue_type": "Bug",
                "project_key": "COR",
                "created": now - timedelta(minutes=60),
                "updated": now - timedelta(minutes=15)
            },
            {
                "key": "COR-102",
                "summary": "Scale PostgreSQL replica configurations",
                "description": "Increase connection pool size to postgres instances and setup readonly endpoints for general search routing.",
                "status": "In Progress",
                "assignee": "Alice",
                "priority": "Medium",
                "issue_type": "Task",
                "project_key": "COR",
                "created": now - timedelta(days=1),
                "updated": now - timedelta(hours=4)
            },
            {
                "key": "APO-201",
                "summary": "Epic: Payment provider onboarding migration",
                "description": "Track task groups for migrating payment provider webhook integration APIs.",
                "status": "To Do",
                "assignee": "Charlie",
                "priority": "High",
                "issue_type": "Epic",
                "project_key": "APO",
                "created": now - timedelta(days=5),
                "updated": now - timedelta(days=2)
            },
            {
                "key": "APO-202",
                "summary": "Payments API webhook signature verification fails",
                "description": "Stripe webhook calls fail validation due to signature secret mismatches. Security issue blocking onboarding sandbox deployments.",
                "status": "Resolved",
                "assignee": "Bob",
                "priority": "High",
                "issue_type": "Bug",
                "project_key": "APO",
                "created": now - timedelta(days=3),
                "updated": now - timedelta(days=1)
            }
        ]

        documents = []
        for t in mock_tickets:
            doc_id = f"jira_issue_{t['key']}"
            
            # Put ticket metadata
            meta = {
                "ticket_key": t["key"],
                "status": t["status"],
                "assignee": t["assignee"],
                "priority": t["priority"],
                "issue_type": t["issue_type"],
                "project_key": t["project_key"],
                "workspace_id": self.workspace_id,
                "source": "jira"
            }
            
            doc = MemoryDocument(
                id=doc_id,
                source="jira",
                source_id=t["key"],
                workspace_id=self.workspace_id,
                parent_id=None,
                path=f"/Jira/Projects/{t['project_key']}/{t['key']}",
                title=f"Jira Issue {t['key']}: {t['summary']}",
                content=f"Summary: {t['summary']}\nStatus: {t['status']}\nAssignee: {t['assignee']}\nPriority: {t['priority']}\nType: {t['issue_type']}\n\nDescription:\n{t['description']}",
                url=f"https://jira.company.com/browse/{t['key']}",
                author=t["assignee"],
                created_time=t["created"],
                last_edited_time=t["updated"],
                tags=["jira", "ticket", t["status"].lower(), t["issue_type"].lower()],
                metadata=meta
            )
            documents.append(doc)

        logger.info(f"Jira sync fetched {len(documents)} tickets.")
        return documents
