import logging
import json
import httpx
from typing import Dict, Any, Optional

from backend.core.services.db_manager import DBManager
from backend.intelligence.pipeline import OperationalIntelligencePipeline

logger = logging.getLogger(__name__)
db_manager = DBManager()

async def dispatch_proactive_alert_context(
    workspace_id: str,
    alert_title: str,
    alert_summary: str,
    severity: str = "high"
) -> Optional[Dict[str, Any]]:
    """
    Proactively executes the diagnostics pipeline for a telemetry alert, 
    and posts the context summary thread to Slack if credentials are configured.
    """
    logger.info(f"Running proactive diagnostics for alert '{alert_title}' in workspace '{workspace_id}'")
    
    # 1. Run the Operational Intelligence Pipeline
    try:
        pipeline = OperationalIntelligencePipeline()
        results = await pipeline.execute(query=alert_title, limit=3, workspace_id=workspace_id)
        insight = results.get("insight", {})
        summary = insight.get("summary", "No direct root cause identified.")
        confidence = insight.get("confidence_score", 0.85)
        findings = insight.get("key_findings", [])
    except Exception as e:
        logger.error(f"Failed to execute proactive diagnostic pipeline: {e}", exc_info=True)
        return None

    # 2. Formulate Slack message payload
    findings_bullets = ""
    for f in findings[:2]:
        findings_bullets += f"\n• *{f.get('source', 'doc')}*: \"{f.get('finding', '')[:100]}...\""
        
    slack_message = (
        f"🚨 *CORD Contextual Diagnostic Report* 🚨\n"
        f"*Alert Triggered*: `{alert_title}`\n"
        f"*Severity*: `{severity.upper()}` | *Diagnostic Confidence*: `{int(confidence * 100)}%`\n\n"
        f"*RCA Summary*:\n{summary}\n\n"
        f"*Primary Supporting Evidence*:{findings_bullets or ' No vector documents linked.'}\n"
    )

    # 3. Retrieve Slack connection credentials
    creds_row = db_manager.get_connector_credentials(workspace_id, "slack")
    slack_token = None
    target_channel = "#incidents"  # Default fallback channel
    
    if creds_row and creds_row.get("credentials_json"):
        try:
            creds = json.loads(creds_row["credentials_json"])
            slack_token = creds.get("token")
            # Parse configured channels
            channels_str = creds.get("channels", "")
            if channels_str:
                # Grab the first whitelisted channel
                target_channel = [c.strip() for c in channels_str.split(",") if c.strip()][0]
        except Exception as e:
            logger.warning(f"Failed to parse Slack credentials JSON: {e}")

    # 4. Post to Slack API
    if slack_token:
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {slack_token}",
                        "Content-Type": "application/json; charset=utf-8"
                    },
                    json={
                        "channel": target_channel,
                        "text": slack_message
                    },
                    timeout=10.0
                )
                res_data = response.json()
                if not res_data.get("ok"):
                    logger.warning(f"Slack postMessage API failed: {res_data.get('error')}")
                else:
                    logger.info(f"Successfully posted alert context to Slack channel {target_channel}")
        except Exception as e:
            logger.error(f"HTTP request to Slack API failed: {e}", exc_info=True)
    else:
        logger.info(
            f"[PROACTIVE SLACK LOG] (No token configured). "
            f"Target Channel: {target_channel}. Payload:\n{slack_message}"
        )

    return {
        "posted": slack_token is not None,
        "channel": target_channel,
        "message": slack_message,
        "rca_summary": summary
    }
