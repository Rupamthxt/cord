import os
import uuid
import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
import stripe

from backend.core.services.db_manager import DBManager
from backend.api.auth_router import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])
db = DBManager()

# Setup Stripe API Key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "price_pro_default")

class CheckoutSessionRequest(BaseModel):
    workspace_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

class PortalSessionRequest(BaseModel):
    workspace_id: str
    return_url: Optional[str] = None

@router.post("/checkout-session")
async def create_checkout_session(body: CheckoutSessionRequest, user_id: str = Depends(get_current_user_id)):
    """
    Creates a Stripe Checkout Session for upgrading a workspace.
    Supports a mock simulation mode if no Stripe Secret Key is configured.
    """
    try:
        # Check authorization: user must have access to the workspace
        user_workspaces = db.get_user_workspaces(user_id)
        is_authorized = any(w["workspace_id"] == body.workspace_id for w in user_workspaces)
        if not is_authorized:
            raise HTTPException(status_code=403, detail="Not authorized to manage this workspace")
            
        workspace = db.get_workspace(body.workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
            
        success_url = body.success_url or "http://localhost:8000/dashboard?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = body.cancel_url or "http://localhost:8000/dashboard"
        
        stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
        is_mock = not stripe_key or "dummy" in stripe_key or "mock" in stripe_key
        
        if is_mock:
            mock_session_id = f"cs_test_{uuid.uuid4()}"
            redirect_url = success_url.replace("{CHECKOUT_SESSION_ID}", mock_session_id)
            
            # Run background task to simulate webhook upgrading the workspace
            import threading
            def simulate_stripe_upgrade():
                import time
                time.sleep(0.1)
                try:
                    db.update_workspace_subscription(
                        workspace_id=body.workspace_id,
                        stripe_customer_id=f"cus_mock_{uuid.uuid4()}",
                        stripe_subscription_id=f"sub_mock_{uuid.uuid4()}",
                        subscription_status="active",
                        plan_level="pro"
                    )
                    logger.info(f"Mock stripe checkout completed. Workspace {body.workspace_id} upgraded to pro.")
                except Exception as e:
                    logger.error(f"Error in mock checkout background task: {e}")
                    
            threading.Thread(target=simulate_stripe_upgrade, daemon=True).start()
            return {"url": redirect_url, "session_id": mock_session_id}
            
        else:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price": STRIPE_PRO_PRICE_ID,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=body.workspace_id,
                metadata={
                    "workspace_id": body.workspace_id
                }
            )
            return {"url": session.url, "session_id": session.id}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/portal-session")
async def create_portal_session(body: PortalSessionRequest, user_id: str = Depends(get_current_user_id)):
    """
    Creates a Stripe Portal Session for subscription billing management.
    """
    try:
        user_workspaces = db.get_user_workspaces(user_id)
        is_authorized = any(w["workspace_id"] == body.workspace_id for w in user_workspaces)
        if not is_authorized:
            raise HTTPException(status_code=403, detail="Not authorized to manage this workspace")
            
        workspace = db.get_workspace(body.workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
            
        return_url = body.return_url or "http://localhost:8000/dashboard"
        
        stripe_customer_id = workspace.get("stripe_customer_id")
        stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
        is_mock = not stripe_key or "dummy" in stripe_key or "mock" in stripe_key
        
        if is_mock or not stripe_customer_id:
            # Simulated portal behavior: return dashboard URL
            return {"url": return_url}
        else:
            session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url
            )
            return {"url": session.url}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create customer portal session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
