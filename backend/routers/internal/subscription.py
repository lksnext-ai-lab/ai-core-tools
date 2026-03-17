"""Subscription and usage management endpoints (SaaS mode only)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from db.database import get_db
from schemas.subscription_schemas import (
    SubscriptionRead,
    CheckoutSessionCreate,
    CheckoutSessionResponse,
    PortalSessionResponse,
)
from schemas.usage_schemas import UsageRead
from services.subscription_service import SubscriptionService
from services.usage_tracking_service import UsageTrackingService
from routers.internal.auth_utils import get_current_user_oauth
from lks_idprovider.models.auth import AuthContext
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["subscription"])


@router.get("/subscription", response_model=SubscriptionRead)
async def get_subscription(
    auth: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Return the current user's subscription info with usage and limits."""
    from services.user_service import UserService
    user, _ = UserService.get_or_create_user(db, auth.identity.email, auth.identity.name)
    return SubscriptionService.get_subscription(db, user.user_id)


@router.post("/subscription/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: CheckoutSessionCreate,
    auth: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session for upgrading to a paid tier."""
    from services.user_service import UserService
    user, _ = UserService.get_or_create_user(db, auth.identity.email, auth.identity.name)
    url = SubscriptionService.create_checkout_session(db, user.user_id, body.tier)
    return CheckoutSessionResponse(url=url)


@router.post("/subscription/portal", response_model=PortalSessionResponse)
async def create_portal_session(
    auth: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Create a Stripe Customer Portal session for self-serve billing management."""
    from services.user_service import UserService
    user, _ = UserService.get_or_create_user(db, auth.identity.email, auth.identity.name)
    url = SubscriptionService.create_portal_session(db, user.user_id)
    return PortalSessionResponse(url=url)


@router.post("/subscription/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle incoming Stripe webhook events. Verifies Stripe signature before processing."""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    SubscriptionService.handle_webhook(db, payload, sig_header)
    return {"received": True}


@router.get("/usage", response_model=UsageRead)
async def get_usage(
    auth: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Return the current user's system LLM quota usage for the billing period."""
    from services.user_service import UserService
    user, _ = UserService.get_or_create_user(db, auth.identity.email, auth.identity.name)
    return UsageTrackingService.get_usage(db, user.user_id)
