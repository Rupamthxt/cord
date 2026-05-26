"""
backend/notifications/sender.py
-------------------------------
Stub/simulation layer for sending Slack webhook messages and HTML emails.
Supports digest distribution and workflow state change alerts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """
    Handles dispatching alerts and digests to external notification channels.
    Simulated for supervised execution and human-in-the-loop validation.
    """

    async def send_slack(
        self,
        webhook_url: Optional[str] = None,
        channel: str = "#ops-insights",
        text: str = "",
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Simulates sending a Slack message, supporting Block Kit layout elements.
        """
        logger.info(
            "Sending Slack notification to channel %s. Text summary: %r. Blocks count: %d",
            channel,
            text[:60] + "..." if len(text) > 60 else text,
            len(blocks) if blocks else 0,
        )
        # Log formatted blocks if present
        if blocks:
            logger.debug("Slack block kit payload: %r", blocks)
        return True

    async def send_email(
        self,
        recipient: str,
        subject: str,
        html_body: str,
    ) -> bool:
        """
        Simulates sending a fully styled HTML email.
        """
        logger.info(
            "Sending HTML Email to %s. Subject: %r. Body length: %d chars",
            recipient,
            subject,
            len(html_body),
        )
        return True

    async def dispatch_workflow_alert(
        self,
        workflow_id: str,
        title: str,
        state: str,
        priority: str,
        assignee_entities: Optional[List[Dict[str, Any]]] = None,
        workspace_id: str = "default_workspace",
    ) -> bool:
        """
        Formats and dispatches a notification when a workflow state changes.
        """
        assignee_names = (
            ", ".join([e.get("name", "Unknown") for e in assignee_entities])
            if assignee_entities
            else "Unassigned"
        )
        message_text = f"Workflow Alert in workspace '{workspace_id}': '{title}' has been moved to {state.upper()} (Priority: {priority.upper()}). Assigned to: {assignee_names}."
        
        # Dispatch Slack message
        await self.send_slack(
            channel="#workflows-updates",
            text=message_text,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Workflow State Transition Update*\n*Title:* {title}\n*State:* `{state.upper()}`\n*Priority:* `{priority.upper()}`\n*Assignee(s):* {assignee_names}\n*Workspace:* `{workspace_id}`",
                    },
                }
            ],
        )

        # Dispatch Email if there's an assignee
        if assignee_entities:
            for assignee in assignee_entities:
                if assignee.get("type") == "person":
                    email_addr = f"{assignee.get('name', 'user').lower().replace(' ', '.')}@company.internal"
                    subject = f"[Workflow Update] {title} -> {state.upper()}"
                    html_body = f"""
                    <html>
                    <body style="font-family: sans-serif; color: #333333; line-height: 1.5;">
                        <h2 style="color: #4A90E2;">Workflow Status Changed</h2>
                        <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">Workflow Title</td>
                                <td style="padding: 8px; border: 1px solid #dee2e6;">{title}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">New State</td>
                                <td style="padding: 8px; border: 1px solid #dee2e6;"><span style="background-color: #e2e3e5; padding: 2px 6px; border-radius: 4px;">{state.upper()}</span></td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">Priority</td>
                                <td style="padding: 8px; border: 1px solid #dee2e6;">{priority.upper()}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">Workflow ID</td>
                                <td style="padding: 8px; border: 1px solid #dee2e6; font-size: 12px; font-family: monospace;">{workflow_id}</td>
                            </tr>
                        </table>
                        <p style="margin-top: 20px;">Please check the Cord Dashboard to complete outstanding tasks.</p>
                    </body>
                    </html>
                    """
                    await self.send_email(email_addr, subject, html_body)

        return True


# Module singleton
notification_dispatcher = NotificationDispatcher()
