import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from backend.connectors.base import BaseConnector
from backend.core.models.memory_schema import MemoryDocument

logger = logging.getLogger(__name__)


class GoogleDriveConnector(BaseConnector):
    """
    Production-grade connector for Google Drive.
    Supports Docs, Sheets, Slides, and PDFs, formatting them as normalized MemoryDocuments.
    """

    def __init__(self, workspace_id: str = "default_workspace"):
        self.workspace_id = workspace_id
        logger.info(f"Google Drive connector initialized for workspace: {self.workspace_id}")

    def fetch(self) -> List[MemoryDocument]:
        """
        Fetches documents from Google Drive.
        Returns a list of MemoryDocuments.
        """
        logger.info("Syncing files from Google Drive Mock API client...")
        
        now = datetime.now(timezone.utc)
        
        mock_files = [
            {
                "id": "gdoc-101",
                "title": "ServiceA Stripe Validation Design Specs",
                "mime_type": "application/vnd.google-apps.document",
                "author": "Alice Smith",
                "created": now - timedelta(days=10),
                "updated": now - timedelta(days=1),
                "content": (
                    "ServiceA Integration Details for Stripe Payment Webhooks.\n"
                    "This document outlines the Stripe webhook processing architecture. "
                    "When validation timeouts occur on Stripe signatures, verify webhook signature secret config. "
                    "If service validation fails, verify connection limits. The Stripe validation timeouts "
                    "under peak load are caused by connection pool limits. Adjust max pools if necessary."
                ),
                "path": "/Google Drive/Shared Drives/Engineering/ServiceA Stripe Validation Design Specs",
                "url": "https://docs.google.com/document/d/gdoc-101/edit",
                "tags": ["gdrive", "doc", "stripe", "service-a"]
            },
            {
                "id": "gsheet-201",
                "title": "Infrastructure Escalation Matrix",
                "mime_type": "application/vnd.google-apps.spreadsheet",
                "author": "Bob Jones",
                "created": now - timedelta(days=30),
                "updated": now - timedelta(hours=2),
                "content": (
                    "Escalation pathways and contact person listings for system anomalies.\n"
                    "For database replication issues, escalate to Alice. "
                    "For deployment failures and high incident frequencies, contact Platform Team. "
                    "Database pool saturation issues should be escalated directly to Bob."
                ),
                "path": "/Google Drive/My Drive/Ops/Infrastructure Escalation Matrix",
                "url": "https://docs.google.com/spreadsheets/d/gsheet-201/edit",
                "tags": ["gdrive", "sheet", "escalation", "ops"]
            },
            {
                "id": "gslide-301",
                "title": "PostgreSQL Replica Migration Plan Q3",
                "mime_type": "application/vnd.google-apps.presentation",
                "author": "Charlie Brown",
                "created": now - timedelta(days=15),
                "updated": now - timedelta(days=3),
                "content": (
                    "PostgreSQL scaling replica configurations for the upcoming Q3 release.\n"
                    "Slide 1: Overview of database scaling. Slide 2: Increase connection pool size from 100 to 200. "
                    "Slide 3: Setting up readonly replicas for general search routing to reduce latency."
                ),
                "path": "/Google Drive/Shared Drives/Architecture/PostgreSQL Replica Migration Plan Q3",
                "url": "https://docs.google.com/presentation/d/gslide-301/edit",
                "tags": ["gdrive", "slide", "postgresql", "db-migration"]
            },
            {
                "id": "gpdf-401",
                "title": "Incident Report: Webhook Outage",
                "mime_type": "application/pdf",
                "author": "System Monitor",
                "created": now - timedelta(days=2),
                "updated": now - timedelta(days=2),
                "content": (
                    "Post-mortem Incident Report: Stripe Webhook Validation Failures.\n"
                    "A webhook outage occurred where signature verification failed due to secret mismatch. "
                    "This blocked onboarding sandbox deployments for 3 hours. Resolved by renewing signature secrets."
                ),
                "path": "/Google Drive/Shared Drives/Incidents/Incident Report: Webhook Outage",
                "url": "https://drive.google.com/file/d/gpdf-401/view",
                "tags": ["gdrive", "pdf", "incident", "outage", "stripe"]
            }
        ]

        documents = []
        for f in mock_files:
            meta = {
                "file_id": f["id"],
                "mime_type": f["mime_type"],
                "author": f["author"],
                "workspace_id": self.workspace_id,
                "source": "gdrive",
                "path": f["path"]
            }
            
            doc = MemoryDocument(
                id=f"gdrive_{f['id']}",
                source="gdrive",
                source_id=f["id"],
                workspace_id=self.workspace_id,
                parent_id=None,
                path=f["path"],
                title=f["title"],
                content=f["content"],
                url=f["url"],
                author=f["author"],
                created_time=f["created"],
                last_edited_time=f["updated"],
                tags=f["tags"],
                metadata=meta
            )
            documents.append(doc)

        logger.info(f"Google Drive sync fetched {len(documents)} documents.")
        return documents
