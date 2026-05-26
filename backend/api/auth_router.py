import json
import logging
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Header, Depends
from backend.core.services.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Authentication & Workspaces"])
db = DBManager()

# --- Request & Response Models ---
class SignupRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

class WorkspaceCreateRequest(BaseModel):
    workspace_id: str = Field(..., description="Unique alphanumeric workspace ID")
    name: str = Field(..., description="Human-readable name of the workspace")

class SaveConnectorRequest(BaseModel):
    connector_type: str = Field(..., description="notion|slack|jira|gdrive")
    credentials_json: str = Field(..., description="JSON string containing connection details (api_key, tokens, urls, etc.)")

class TestConnectorRequest(BaseModel):
    connector_type: str = Field(..., description="notion|slack|jira|gdrive")
    credentials_json: str = Field(..., description="JSON string containing connection credentials to test")


# --- Helper functions ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    # In this pilot, we use the user_id directly as the session token
    # For production, this could decode a JWT or verify a session in the DB
    return token


# --- Endpoints ---

@router.post("/auth/signup")
async def signup(body: SignupRequest):
    """Registers a new user and creates an initial default workspace."""
    try:
        existing = db.get_user_by_email(body.email)
        if existing:
            raise HTTPException(status_code=400, detail="A user with this email already exists.")
        
        pwd_hash = hash_password(body.password)
        user_info = db.create_user(body.email, pwd_hash)
        
        # Create a default workspace for the new user
        prefix = body.email.split("@")[0].lower()
        ws_id = f"{prefix}_workspace"
        ws_name = f"{prefix.capitalize()}'s Workspace"
        db.create_workspace(ws_id, ws_name, user_info["user_id"])
        
        return {
            "status": "success",
            "message": "User registered successfully.",
            "user": {
                "user_id": user_info["user_id"],
                "email": user_info["email"],
                "default_workspace_id": ws_id
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/login")
async def login(body: LoginRequest):
    """Authenticates a user and returns their token and list of workspaces."""
    try:
        user = db.get_user_by_email(body.email)
        if not user or user["password_hash"] != hash_password(body.password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        
        workspaces = db.get_user_workspaces(user["user_id"])
        default_ws = workspaces[0]["workspace_id"] if workspaces else "default_workspace"
        
        return {
            "status": "success",
            "token": user["user_id"],
            "user": {
                "user_id": user["user_id"],
                "email": user["email"],
                "default_workspace_id": default_ws
            },
            "workspaces": workspaces
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces")
async def get_workspaces(user_id: str = Depends(get_current_user_id)):
    """Lists all workspaces the logged-in user belongs to."""
    try:
        workspaces = db.get_user_workspaces(user_id)
        return {"workspaces": workspaces}
    except Exception as e:
        logger.error(f"Failed to fetch workspaces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces")
async def create_workspace(body: WorkspaceCreateRequest, user_id: str = Depends(get_current_user_id)):
    """Creates a new workspace and associates it with the logged-in user."""
    try:
        ws_id = body.workspace_id.strip().lower()
        import re
        if not re.match(r'^[a-z0-9_-]+$', ws_id):
            raise HTTPException(status_code=400, detail="Workspace ID must contain only alphanumeric characters, underscores, or hyphens.")
        
        # Verify it doesn't already exist
        # If it exists, let's see if the user already has access or if we can link it
        db.create_workspace(ws_id, body.name, user_id)
        
        # Also ensure standard workspace models exist or are setup if needed
        return {
            "status": "success",
            "workspace": {
                "workspace_id": ws_id,
                "name": body.name,
                "owner_id": user_id
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/connectors")
async def get_workspace_connectors(workspace_id: str, user_id: str = Depends(get_current_user_id)):
    """Gets the configuration and connection status of connectors in a workspace."""
    try:
        connectors = ["notion", "slack", "jira", "gdrive"]
        results = []
        for conn in connectors:
            cred = db.get_connector_credentials(workspace_id, conn)
            if cred:
                # Mask credentials
                try:
                    creds_dict = json.loads(cred["credentials_json"])
                    masked = {k: "********" for k in creds_dict.keys()}
                except Exception:
                    masked = {}
                results.append({
                    "connector_type": conn,
                    "connected": True,
                    "status": cred["status"],
                    "updated_at": cred["updated_at"],
                    "config_preview": masked
                })
            else:
                results.append({
                    "connector_type": conn,
                    "connected": False,
                    "status": "not_configured",
                    "updated_at": None,
                    "config_preview": {}
                })
        return {"workspace_id": workspace_id, "connectors": results}
    except Exception as e:
        logger.error(f"Failed to fetch workspace connectors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{workspace_id}/connectors")
async def save_workspace_connector(workspace_id: str, body: SaveConnectorRequest, user_id: str = Depends(get_current_user_id)):
    """Stores or updates connector credentials for a workspace."""
    try:
        # Validate JSON string format
        try:
            json.loads(body.credentials_json)
        except Exception:
            raise HTTPException(status_code=400, detail="Credentials must be a valid JSON string.")
        
        db.save_connector_credentials(workspace_id, body.connector_type, body.credentials_json)
        
        # Also register in the memory vault singleton dynamically
        from backend.core.utils.security import vault
        vault.register_credential(workspace_id, body.connector_type, body.credentials_json)
        
        return {
            "status": "success",
            "message": f"Connector credentials saved for '{body.connector_type}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save connector: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connectors/test")
async def test_connector_connection(body: TestConnectorRequest):
    """Tests connection to a connector using provided keys (supports mocks & live validation)."""
    try:
        config = json.loads(body.credentials_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format for test credentials.")
    
    conn_type = body.connector_type.lower()
    
    # 1. Check for mock/demo values first to allow zero-configuration onboarding
    is_mock = False
    for val in config.values():
        if isinstance(val, str) and (val.startswith("mock") or val.startswith("test") or "secret_notion_default" in val or "default" in val):
            is_mock = True
            break
            
    if is_mock or not config:
        return {
            "success": True,
            "message": f"[Mock Mode] Successfully authenticated with mock {conn_type.capitalize()} server."
        }

    # 2. Run actual integration test queries
    import aiohttp
    try:
        if conn_type == "notion":
            api_key = config.get("api_key") or config.get("token")
            if not api_key:
                return {"success": False, "message": "Missing Notion api_key / token in config."}
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": "2022-06-28"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.notion.com/v1/users", headers=headers) as resp:
                    if resp.status == 200:
                        return {"success": True, "message": "Successfully authenticated with production Notion API."}
                    else:
                        err_data = await resp.json()
                        return {"success": False, "message": f"Notion API error (HTTP {resp.status}): {err_data.get('message', 'Unauthorized')}"}
                        
        elif conn_type == "slack":
            token = config.get("token") or config.get("bot_token")
            if not token:
                return {"success": False, "message": "Missing Slack token / bot_token in config."}
            
            headers = {"Authorization": f"Bearer {token}"}
            async with aiohttp.ClientSession() as session:
                async with session.post("https://slack.com/api/auth.test", headers=headers) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        if res_json.get("ok"):
                            return {"success": True, "message": f"Successfully authenticated Slack bot: '{res_json.get('user')}' in team '{res_json.get('team')}'."}
                        else:
                            return {"success": False, "message": f"Slack Auth failed: {res_json.get('error')}"}
                    else:
                        return {"success": False, "message": f"Slack API connection failed with HTTP status {resp.status}"}

        elif conn_type == "jira":
            url = config.get("url")
            username = config.get("username")
            token = config.get("token") or config.get("api_token")
            
            if not url or not username or not token:
                return {"success": False, "message": "Jira config must contain url, username, and token."}
                
            import base64
            auth_str = f"{username}:{token}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            headers = {"Authorization": f"Basic {auth_b64}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url.rstrip('/')}/rest/api/3/serverInfo", headers=headers) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        return {"success": True, "message": f"Connected to Jira Cloud: {res_json.get('serverTitle', 'Jira Instance')}"}
                    else:
                        return {"success": False, "message": f"Jira API test failed with HTTP status {resp.status}"}
                        
        elif conn_type == "gdrive":
            # For Google Drive we can check if it contains credentials dictionary fields
            if "type" in config and "project_id" in config and "private_key" in config:
                return {"success": True, "message": "Google Service Account key format is valid."}
            else:
                return {"success": False, "message": "Invalid Google Service Account JSON key format. Expected fields (type, project_id, private_key)."}
                
        else:
            return {"success": False, "message": f"Unknown connector type: {conn_type}"}
            
    except Exception as exc:
        logger.warning(f"Connection test query failed for {conn_type}: {exc}")
        return {"success": False, "message": f"Failed to reach API server: {exc}"}


# --- Workspace Synchronization Endpoint ---


@router.post("/workspaces/{workspace_id}/sync")
async def sync_workspace_data(workspace_id: str, user_id: str = Depends(get_current_user_id)):
    """
    Synchronizes workspace memory by fetching data from all configured connectors
    (Notion, Slack, Jira, GDrive) and generating embeddings/indexes downstream.
    """
    try:
        from backend.core.models.store_memory import store_chunks
        from backend.connectors.ingestion.chunker import chunk_text
        from backend.core.models.memory_schema import MemoryDocument
        
        # 1. Notion Connection Sync
        notion_docs = []
        notion_cred = db.get_connector_credentials(workspace_id, "notion")
        if notion_cred:
            try:
                creds = json.loads(notion_cred["credentials_json"])
                api_key = creds.get("api_key") or creds.get("token")
                if api_key:
                    from backend.connectors.notion.notion_connector import NotionConnector
                    connector = NotionConnector(api_key=api_key)
                    notion_docs = await connector.fetch_workspace(start_page_id=creds.get("start_page_id"), normalize=True)
            except Exception as e:
                logger.error(f"Notion sync failed: {e}")
                
        # 2. Slack Connection Sync
        slack_docs = []
        slack_cred = db.get_connector_credentials(workspace_id, "slack")
        if slack_cred:
            try:
                creds = json.loads(slack_cred["credentials_json"])
                token_val = creds.get("token") or creds.get("bot_token")
                if token_val:
                    from backend.connectors.slack.slack_connector import SlackConnector
                    connector = SlackConnector(slack_token=token_val)
                    channels_str = creds.get("channels") or ""
                    channel_filters = [c.strip() for c in channels_str.split(",") if c.strip()] if channels_str else None
                    slack_docs = await connector.fetch_workspace(channel_filters=channel_filters, normalize=True)
            except Exception as e:
                logger.error(f"Slack sync failed: {e}")
                
        # 3. Jira Connection Sync
        jira_docs = []
        jira_cred = db.get_connector_credentials(workspace_id, "jira")
        if jira_cred:
            try:
                from backend.connectors.jira.jira_connector import JiraConnector
                connector = JiraConnector(workspace_id=workspace_id)
                jira_docs = connector.fetch()
            except Exception as e:
                logger.error(f"Jira sync failed: {e}")
            
        # 4. Google Drive Connection Sync
        gdrive_docs = []
        gdrive_cred = db.get_connector_credentials(workspace_id, "gdrive")
        if gdrive_cred:
            try:
                from backend.connectors.gdrive.gdrive_connector import GoogleDriveConnector
                connector = GoogleDriveConnector(workspace_id=workspace_id)
                gdrive_docs = connector.fetch()
            except Exception as e:
                logger.error(f"GDrive sync failed: {e}")
            
        # Aggregate all documents
        all_docs = notion_docs + slack_docs + jira_docs + gdrive_docs
        
        # Ingest and index documents
        total_chunks = 0
        for doc in all_docs:
            # Override doc workspace scope to target active workspace
            doc.workspace_id = workspace_id
            if doc.metadata:
                doc.metadata["workspace_id"] = workspace_id
            else:
                doc.metadata = {"workspace_id": workspace_id}
                
            chunks = chunk_text(doc.content)
            store_chunks(chunks, metadata=doc)
            total_chunks += len(chunks)
            
        return {
            "status": "success",
            "workspace_id": workspace_id,
            "documents_synced": len(all_docs),
            "chunks_created": total_chunks,
            "sources": ["notion", "slack", "jira", "gdrive"],
            "details": {
                "notion": len(notion_docs),
                "slack": len(slack_docs),
                "jira": len(jira_docs),
                "gdrive": len(gdrive_docs)
            }
        }
    except Exception as exc:
        logger.error(f"Workspace sync pipeline failed for workspace {workspace_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

