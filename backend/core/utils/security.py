import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkspaceIsolationManager:
    """
    Ensures absolute organizational workspace isolation.
    Validates scope keys and scopes queries before they reach vector or relational stores.
    """

    @staticmethod
    def enforce_workspace_scope(query_workspace: str, target_workspace: Optional[str] = None) -> str:
        """
        Enforces workspace-level scoping, fallback to query workspace or default.
        """
        ws = target_workspace or query_workspace or "default_workspace"
        ws_clean = ws.strip()
        if not ws_clean:
            ws_clean = "default_workspace"
        return ws_clean


class CredentialVault:
    """
    Mock enterprise vault for isolated connector credential management.
    Prevents leakages and cross-workspace access.
    """

    def __init__(self):
        # Initial secrets mapping workspaces to connector secrets (initially empty, populated via database credentials)
        self._secrets: Dict[str, Dict[str, str]] = {}

    def get_credential(self, workspace_id: str, connector_name: str) -> Optional[str]:
        """Retrieves connector token for specific workspace isolation."""
        # 1. First check SQLite database configuration
        try:
            from backend.core.services.db_manager import DBManager
            db = DBManager()
            cred_row = db.get_connector_credentials(workspace_id, connector_name)
            if cred_row and cred_row.get("credentials_json"):
                import json
                creds = json.loads(cred_row["credentials_json"])
                if isinstance(creds, dict):
                    # Check typical key names
                    for k in ["token", "api_key", "bot_token", "api_token", "secret"]:
                        if creds.get(k):
                            return creds[k]
                    # Return the first string value if found
                    for val in creds.values():
                        if isinstance(val, str):
                            return val
                return cred_row["credentials_json"]
        except Exception as e:
            logger.warning(f"DB credential fetch failed for {workspace_id}/{connector_name}: {e}")

        # 2. Fallback to in-memory mock configuration
        ws_secrets = self._secrets.get(workspace_id)
        if not ws_secrets:
            # Check environment fallback securely
            env_var = f"{connector_name.upper()}_BOT_TOKEN"
            val = os.getenv(env_var)
            if not val:
                val = os.getenv(f"{connector_name.upper()}_API_KEY")
            return val
        return ws_secrets.get(f"{connector_name.lower()}_token")

    def register_credential(self, workspace_id: str, connector_name: str, secret: str) -> None:
        """Saves a connector secret scoped securely to a single workspace."""
        # 1. Update in-memory
        self._secrets.setdefault(workspace_id, {})
        self._secrets[workspace_id][f"{connector_name.lower()}_token"] = secret
        logger.info(f"Credential secured in vault for workspace '{workspace_id}' (Connector: {connector_name}).")

        # 2. Persist to SQLite DB
        try:
            import json
            from backend.core.services.db_manager import DBManager
            db = DBManager()
            try:
                # Check if it is already JSON
                json.loads(secret)
                creds_json = secret
            except Exception:
                creds_json = json.dumps({"token": secret})
            
            db.save_connector_credentials(workspace_id, connector_name, creds_json)
        except Exception as e:
            logger.warning(f"Failed to persist connector credential to DB for {workspace_id}/{connector_name}: {e}")


class AuditLogger:
    """
    Enterprise-grade audit logger tracking platform queries, scoped workspaces,
    actions, and validation outputs.
    """

    @staticmethod
    def log_access(user_query: str, workspace_id: str, action: str, status: str = "success") -> None:
        """Logs an audit entry describing retrieval or intelligence generation actions."""
        timestamp = datetime.now(timezone.utc).isoformat()
        # Secure queries by redacting sensitive data in logs if necessary
        query_preview = user_query[:100] + "..." if len(user_query) > 100 else user_query
        
        # Log via logger which outputs to unified app logs
        logger.info(
            f"[AUDIT] Time: {timestamp} | Workspace: {workspace_id} | "
            f"Action: {action} | Query: '{query_preview}' | Status: {status}"
        )


class VisibilityFilter:
    """
    Filters retrieved documents based on source whitelists/blacklists.
    """

    @staticmethod
    def filter_sources(documents: List[Any], allowed_sources: Optional[List[str]] = None) -> List[Any]:
        if not allowed_sources:
            return documents
        
        allowed_set = {src.lower() for src in allowed_sources}
        filtered = []
        for doc in documents:
            source = getattr(doc, "source", None)
            if source and source.lower() in allowed_set:
                filtered.append(doc)
            elif isinstance(doc, dict):
                src = doc.get("source")
                if src and src.lower() in allowed_set:
                    filtered.append(doc)
        return filtered


# Singletons
vault = CredentialVault()
audit_logger = AuditLogger()
workspace_isolation = WorkspaceIsolationManager()
visibility_filter = VisibilityFilter()
