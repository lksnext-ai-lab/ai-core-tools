"""Subscription management service: Stripe integration, tier transitions, webhook handling."""
import os
import stripe
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from deployment_mode import is_self_managed
from models.subscription import Subscription, SubscriptionTier, BillingStatus
from models.system_setting import SystemSetting
from repositories.subscription_repository import SubscriptionRepository
from repositories.tier_config_repository import TierConfigRepository
from repositories.usage_record_repository import UsageRecordRepository
from schemas.subscription_schemas import SubscriptionRead
from utils.logger import get_logger

logger = get_logger(__name__)

# Stripe event ID idempotency: store processed event IDs in DB via SystemSetting
_PROCESSED_EVENTS_KEY = "stripe_processed_event_ids"
_STRIPE_TRIAL_DAYS = 7


def _get_stripe_client():
    stripe.api_key = os.getenv("STRIPE_API_KEY", "")
    return stripe


def _effective_tier(sub: Subscription) -> str:
    """Return the effective tier, respecting admin override."""
    if sub.admin_override_tier:
        return sub.admin_override_tier
    return sub.tier.value if sub.tier else "free"


class SubscriptionService:

    @staticmethod
    def get_subscription(db: Session, user_id: int) -> SubscriptionRead:
        """Return subscription info with current usage and limits."""
        sub_repo = SubscriptionRepository(db)
        tier_repo = TierConfigRepository(db)
        usage_repo = UsageRecordRepository(db)

        sub = sub_repo.get_by_user_id(user_id)
        if not sub:
            # Auto-create a Free subscription if missing
            sub = sub_repo.create(user_id)
            db.commit()

        eff_tier = _effective_tier(sub)
        call_limit = tier_repo.get_limit(eff_tier, "llm_calls")
        usage_record = usage_repo.get_current(user_id)
        call_count = usage_record.call_count if usage_record else 0
        pct_used = (call_count / call_limit) if call_limit > 0 else 0.0

        return SubscriptionRead(
            tier=eff_tier,
            billing_status=sub.billing_status.value if sub.billing_status else "none",
            trial_end=sub.trial_end,
            stripe_customer_id=sub.stripe_customer_id,
            call_count=call_count,
            call_limit=call_limit,
            pct_used=pct_used,
            max_apps=tier_repo.get_limit(eff_tier, "apps"),
            agents_per_app=tier_repo.get_limit(eff_tier, "agents"),
            silos_per_app=tier_repo.get_limit(eff_tier, "silos"),
            skills_per_app=tier_repo.get_limit(eff_tier, "skills"),
            mcp_servers_per_app=tier_repo.get_limit(eff_tier, "mcp_servers"),
            collaborators_per_app=tier_repo.get_limit(eff_tier, "collaborators"),
            admin_override_tier=sub.admin_override_tier,
        )

    @staticmethod
    def create_checkout_session(db: Session, user_id: int, tier: str) -> str:
        """Create a Stripe Checkout session for upgrading to a paid tier.

        Returns the Stripe Checkout URL.
        """
        if is_self_managed():
            raise HTTPException(status_code=400, detail="Billing is not available in self-managed mode.")

        tier_to_price = {
            "starter": os.getenv("STRIPE_PRICE_ID_STARTER", ""),
            "pro": os.getenv("STRIPE_PRICE_ID_PRO", ""),
        }
        price_id = tier_to_price.get(tier.lower())
        if not price_id:
            raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}")

        sub_repo = SubscriptionRepository(db)
        sub = sub_repo.get_by_user_id(user_id)

        stripe_client = _get_stripe_client()
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

        # Get or create Stripe customer
        customer_id = sub.stripe_customer_id if sub else None
        if not customer_id:
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_id(user_id)
            customer = stripe_client.Customer.create(email=user.email)
            customer_id = customer.id
            if sub:
                sub_repo.update_tier(
                    user_id=user_id,
                    tier=sub.tier,
                    billing_status=sub.billing_status,
                    stripe_customer_id=customer_id,
                )
                db.commit()

        session = stripe_client.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            subscription_data={"trial_period_days": _STRIPE_TRIAL_DAYS},
            success_url=f"{frontend_url}/subscription?checkout=success",
            cancel_url=f"{frontend_url}/subscription?checkout=cancelled",
        )
        return session.url

    @staticmethod
    def create_portal_session(db: Session, user_id: int) -> str:
        """Create a Stripe Customer Portal session URL for self-serve billing management."""
        if is_self_managed():
            raise HTTPException(status_code=400, detail="Billing is not available in self-managed mode.")

        sub_repo = SubscriptionRepository(db)
        sub = sub_repo.get_by_user_id(user_id)
        if not sub or not sub.stripe_customer_id:
            raise HTTPException(status_code=400, detail="No Stripe customer found. Please subscribe first.")

        stripe_client = _get_stripe_client()
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

        portal = stripe_client.billing_portal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{frontend_url}/subscription",
        )
        return portal.url

    @staticmethod
    def handle_webhook(db: Session, payload: bytes, sig_header: str) -> None:
        """Verify Stripe signature and dispatch the event to the appropriate handler."""
        if is_self_managed():
            return

        stripe_client = _get_stripe_client()
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        try:
            event = stripe_client.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}")

        event_id = event["id"]
        if SubscriptionService._is_duplicate_event(db, event_id):
            logger.info("Duplicate Stripe event %s — skipping", event_id)
            return

        event_type = event["type"]
        logger.info("Processing Stripe event %s (%s)", event_id, event_type)

        handlers = {
            "invoice.paid": SubscriptionService._on_invoice_paid,
            "invoice.payment_failed": SubscriptionService._on_invoice_payment_failed,
            "customer.subscription.updated": SubscriptionService._on_subscription_updated,
            "customer.subscription.deleted": SubscriptionService._on_subscription_deleted,
            "customer.subscription.trial_will_end": SubscriptionService._on_trial_will_end,
        }
        handler = handlers.get(event_type)
        if handler:
            handler(db, event["data"]["object"])

        SubscriptionService._mark_event_processed(db, event_id)
        db.commit()

    # ── Private webhook handlers ──────────────────────────────────────────────

    @staticmethod
    def _find_user_by_stripe_customer(db: Session, customer_id: str):
        """Look up a user's subscription by Stripe customer ID."""
        from models.subscription import Subscription
        return db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first()

    @staticmethod
    def _on_invoice_paid(db: Session, invoice: dict) -> None:
        customer_id = invoice.get("customer")
        sub_stripe = invoice.get("subscription")
        sub = SubscriptionService._find_user_by_stripe_customer(db, customer_id)
        if not sub:
            return

        sub_repo = SubscriptionRepository(db)
        sub_repo.update_tier(
            user_id=sub.user_id,
            tier=sub.tier,
            billing_status=BillingStatus.ACTIVE,
            stripe_subscription_id=sub_stripe,
        )
        # Reset usage period
        period_start = date.today().replace(day=1)
        usage_repo = UsageRecordRepository(db)
        usage_repo.reset_period(sub.user_id, period_start)

    @staticmethod
    def _on_invoice_payment_failed(db: Session, invoice: dict) -> None:
        customer_id = invoice.get("customer")
        sub = SubscriptionService._find_user_by_stripe_customer(db, customer_id)
        if not sub:
            return

        sub_repo = SubscriptionRepository(db)
        sub_repo.update_tier(
            user_id=sub.user_id,
            tier=sub.tier,
            billing_status=BillingStatus.PAST_DUE,
        )

        # Trigger dunning email
        try:
            from repositories.user_repository import UserRepository
            from services.email_service import EmailService
            user = UserRepository(db).get_by_id(sub.user_id)
            if user:
                EmailService.send_dunning_email(to=user.email, days_remaining=7)
        except Exception as exc:
            logger.warning("Failed to send dunning email: %s", exc)

    @staticmethod
    def _on_subscription_updated(db: Session, stripe_sub: dict) -> None:
        customer_id = stripe_sub.get("customer")
        sub = SubscriptionService._find_user_by_stripe_customer(db, customer_id)
        if not sub:
            return

        # Map Stripe status to our BillingStatus
        stripe_status = stripe_sub.get("status", "")
        status_map = {
            "active": BillingStatus.ACTIVE,
            "trialing": BillingStatus.TRIALING,
            "past_due": BillingStatus.PAST_DUE,
            "canceled": BillingStatus.CANCELLED,
        }
        billing_status = status_map.get(stripe_status, BillingStatus.NONE)

        # Determine tier from price
        tier = SubscriptionService._tier_from_stripe_sub(stripe_sub)

        sub_repo = SubscriptionRepository(db)
        sub_repo.update_tier(
            user_id=sub.user_id,
            tier=tier,
            billing_status=billing_status,
        )

    @staticmethod
    def _on_subscription_deleted(db: Session, stripe_sub: dict) -> None:
        customer_id = stripe_sub.get("customer")
        sub = SubscriptionService._find_user_by_stripe_customer(db, customer_id)
        if not sub:
            return

        sub_repo = SubscriptionRepository(db)
        sub_repo.update_tier(
            user_id=sub.user_id,
            tier=SubscriptionTier.FREE,
            billing_status=BillingStatus.CANCELLED,
        )

        # Apply freeze for resources now over Free limits
        try:
            from services.freeze_service import FreezeService
            FreezeService.apply_freeze(db, sub.user_id, SubscriptionTier.FREE.value)
        except Exception as exc:
            logger.error("FreezeService.apply_freeze failed for user %s: %s", sub.user_id, exc)

    @staticmethod
    def _on_trial_will_end(db: Session, stripe_sub: dict) -> None:
        customer_id = stripe_sub.get("customer")
        sub = SubscriptionService._find_user_by_stripe_customer(db, customer_id)
        if not sub:
            return

        try:
            from repositories.user_repository import UserRepository
            from services.email_service import EmailService
            user = UserRepository(db).get_by_id(sub.user_id)
            if user:
                EmailService.send_dunning_email(to=user.email, days_remaining=3)
        except Exception as exc:
            logger.warning("Failed to send trial-will-end email: %s", exc)

    @staticmethod
    def _tier_from_stripe_sub(stripe_sub: dict) -> SubscriptionTier:
        """Determine SubscriptionTier from Stripe subscription items."""
        starter_price = os.getenv("STRIPE_PRICE_ID_STARTER", "")
        pro_price = os.getenv("STRIPE_PRICE_ID_PRO", "")
        items = stripe_sub.get("items", {}).get("data", [])
        for item in items:
            price_id = item.get("price", {}).get("id", "")
            if price_id == pro_price:
                return SubscriptionTier.PRO
            if price_id == starter_price:
                return SubscriptionTier.STARTER
        return SubscriptionTier.FREE

    # ── Idempotency helpers ───────────────────────────────────────────────────

    @staticmethod
    def _is_duplicate_event(db: Session, event_id: str) -> bool:
        """Return True if this Stripe event ID has already been processed."""
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == f"stripe_event_{event_id}"
        ).first()
        return setting is not None

    @staticmethod
    def _mark_event_processed(db: Session, event_id: str) -> None:
        """Record that a Stripe event ID has been processed."""
        setting = SystemSetting(
            key=f"stripe_event_{event_id}",
            value="processed",
            type="string",
            category="stripe_idempotency",
        )
        db.add(setting)
        db.flush()
