import logging
import json
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Response
from fastapi.responses import HTMLResponse

from backend.core.services.db_manager import DBManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Integrations OAuth 2.0 Authorization"])
db_manager = DBManager()


@router.get("/slack/callback")
async def slack_oauth_callback(
    code: str = Query(..., description="OAuth authorization grant code"),
    state: str = Query("default_workspace", description="Target workspace ID")
):
    """
    Exchanges authorization code for Slack Bot User OAuth Token and saves credentials.
    """
    logger.info(f"Received Slack OAuth callback code for workspace '{state}'")
    
    # 1. Exchange OAuth code for Slack Bot Token
    # Mocking external Slack API exchange
    mock_token = f"xoxb-mock-token-{state}-{int(datetime.now(timezone.utc).timestamp())}"
    credentials = {
        "token": mock_token,
        "channels": "#incidents, #alerts",
        "scopes": ["chat:write", "channels:read", "groups:read"]
    }
    
    # 2. Save credentials
    try:
        db_manager.save_connector_credentials(
            workspace_id=state,
            connector_type="slack",
            credentials_json=json.dumps(credentials)
        )
        logger.info(f"Slack OAuth credentials saved successfully for workspace '{state}'")
    except Exception as e:
        logger.error(f"Failed to save Slack OAuth credentials: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save credentials")

    # Render a friendly HTML completion success window
    html_content = f"""
    <html>
        <head><title>Slack Connected</title></head>
        <body style="font-family: sans-serif; background: #0f1115; color: #fff; text-align: center; padding: 3rem;">
            <h2 style="color: #4cd964;">Slack Connection Successful!</h2>
            <p>CORD has been successfully authorized for workspace <strong>{state}</strong>.</p>
            <p style="color: #8a8a8a;">You can close this tab and return to the CORD dashboard.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/notion/callback")
async def notion_oauth_callback(
    code: str = Query(..., description="Notion OAuth grant code"),
    state: str = Query("default_workspace", description="Target workspace ID")
):
    """
    Exchanges authorization code for Notion API token.
    """
    logger.info(f"Received Notion OAuth callback for workspace '{state}'")
    
    mock_token = f"secret_mock_notion_{state}_{int(datetime.now(timezone.utc).timestamp())}"
    credentials = {
        "token": mock_token,
        "parent_page_id": "parent_mock_page_123",
        "workspace_name": "Notion Teamspace"
    }

    try:
        db_manager.save_connector_credentials(
            workspace_id=state,
            connector_type="notion",
            credentials_json=json.dumps(credentials)
        )
        logger.info(f"Notion credentials saved successfully for workspace '{state}'")
    except Exception as e:
        logger.error(f"Failed to save Notion credentials: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save credentials")

    html_content = f"""
    <html>
        <head><title>Notion Connected</title></head>
        <body style="font-family: sans-serif; background: #0f1115; color: #fff; text-align: center; padding: 3rem;">
            <h2 style="color: #4cd964;">Notion Connection Successful!</h2>
            <p>CORD has been successfully authorized to access Notion pages in workspace <strong>{state}</strong>.</p>
            <p style="color: #8a8a8a;">You can close this tab and return to the CORD dashboard.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/jira/callback")
async def jira_oauth_callback(
    code: str = Query(..., description="Jira OAuth grant code"),
    state: str = Query("default_workspace", description="Target workspace ID")
):
    """
    Exchanges authorization code for Jira API token.
    """
    logger.info(f"Received Jira OAuth callback for workspace '{state}'")
    
    mock_token = f"jira_mock_oauth_{state}_{int(datetime.now(timezone.utc).timestamp())}"
    credentials = {
        "token": mock_token,
        "cloud_id": "cloud_id_mock_123",
        "url": "https://api.atlassian.com/ex/jira/cloud_id_mock_123"
    }

    try:
        db_manager.save_connector_credentials(
            workspace_id=state,
            connector_type="jira",
            credentials_json=json.dumps(credentials)
        )
        logger.info(f"Jira credentials saved successfully for workspace '{state}'")
    except Exception as e:
        logger.error(f"Failed to save Jira credentials: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save credentials")

    html_content = f"""
    <html>
        <head><title>Jira Connected</title></head>
        <body style="font-family: sans-serif; background: #0f1115; color: #fff; text-align: center; padding: 3rem;">
            <h2 style="color: #4cd964;">Jira Connection Successful!</h2>
            <p>CORD has been successfully authorized to access Jira ticket metadata in workspace <strong>{state}</strong>.</p>
            <p style="color: #8a8a8a;">You can close this tab and return to the CORD dashboard.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)
