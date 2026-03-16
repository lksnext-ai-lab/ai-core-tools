"""Integration tests for Stripe webhook handling.

These tests require a real PostgreSQL test database (port 5433).
Run with: pytest tests/integration/test_stripe_webhooks.py -v

Strategy:
- Use SubscriptionService.handle_webhook with mocked Stripe.Webhook.construct_event
  (so we never hit the real Stripe API)
- Verify DB state after each event type
- Test idempotency: same event ID twice → only one state change
"""
import os
import pytest
from datetime import date
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Environment fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def saas_env(monkeypatch):
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_fake")
    monkeypatch.setenv("EMAIL_FROM", "noreply@test.com")

    import importlib, deployment_mode as dm
    importlib.reload(dm)
    import services.subscription_service as ss
    importlib.reload(ss)

    yield

    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
    importlib.reload(dm)
    importlib.reload(ss)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_stripe_event(event_type: str, obj: dict, event_id: str = "evt_test") -> dict:
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


def make_stripe_sub_payload(customer_id: str, status: str = "active",
                             price_id: str = "price_starter_fake",
                             stripe_sub_id: str = "sub_123") -> dict:
    return {
        "customer": customer_id,
        "id": stripe_sub_id,
        "status": status,
        "items": {"data": [{"price": {"id": price_id}}]},
    }


def call_webhook(db, event: dict):
    """Helper: call handle_webhook with Stripe signature verification mocked."""
    import services.subscription_service as ss
    with patch("services.subscription_service._get_stripe_client") as mock_client:
        stripe_mock = MagicMock()
        stripe_mock.Webhook.construct_event.return_value = event
        mock_client.return_value = stripe_mock
        ss.SubscriptionService.handle_webhook(db, b"payload", "sig_fake")


@pytest.fixture(scope="function")
def webhook_user(db):
    """A Free-tier user with a Stripe customer ID on their subscription."""
    from models.user import User
    from models.subscription import Subscription, SubscriptionTier, BillingStatus

    user = User(email="webhook@test.com", name="Webhook User", is_active=True)
    db.add(user)
    db.flush()

    sub = Subscription(
        user_id=user.user_id,
        tier=SubscriptionTier.FREE,
        billing_status=BillingStatus.NONE,
        stripe_customer_id="cus_webhook_test",
    )
    db.add(sub)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# invoice.paid → billing_status = ACTIVE
# ---------------------------------------------------------------------------

class TestInvoicePaid:

    def test_invoice_paid_sets_billing_status_active(self, db, webhook_user):
        from models.subscription import Subscription, BillingStatus

        invoice = {"customer": "cus_webhook_test", "subscription": "sub_123"}
        event = make_stripe_event("invoice.paid", invoice, "evt_invoice_paid_1")

        call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.billing_status == BillingStatus.ACTIVE

    def test_invoice_paid_resets_usage_period(self, db, webhook_user):
        """invoice.paid should reset or create the usage record for the new billing period."""
        from models.subscription import Subscription
        from models.usage_record import UsageRecord

        # Add some existing usage
        usage = UsageRecord(
            user_id=webhook_user.user_id,
            billing_period_start=date.today().replace(day=1),
            call_count=42,
        )
        db.add(usage)
        db.flush()

        invoice = {"customer": "cus_webhook_test", "subscription": "sub_123"}
        event = make_stripe_event("invoice.paid", invoice, "evt_invoice_paid_2")
        call_webhook(db, event)

        # Usage should be reset
        usage = db.query(UsageRecord).filter(UsageRecord.user_id == webhook_user.user_id).first()
        assert usage is not None
        assert usage.call_count == 0


# ---------------------------------------------------------------------------
# invoice.payment_failed → billing_status = PAST_DUE
# ---------------------------------------------------------------------------

class TestInvoicePaymentFailed:

    def test_payment_failed_sets_past_due(self, db, webhook_user):
        from models.subscription import Subscription, BillingStatus

        invoice = {"customer": "cus_webhook_test", "subscription": "sub_123"}
        event = make_stripe_event("invoice.payment_failed", invoice, "evt_pay_fail_1")

        with patch("services.email_service.EmailService"):
            call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.billing_status == BillingStatus.PAST_DUE


# ---------------------------------------------------------------------------
# customer.subscription.deleted → tier=FREE, status=CANCELLED
# ---------------------------------------------------------------------------

class TestSubscriptionDeleted:

    def test_subscription_deleted_downgrades_to_free(self, db, webhook_user):
        from models.subscription import Subscription, SubscriptionTier, BillingStatus, BillingStatus

        stripe_sub = make_stripe_sub_payload("cus_webhook_test", status="canceled")
        event = make_stripe_event("customer.subscription.deleted", stripe_sub, "evt_sub_del_1")

        call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.tier == SubscriptionTier.FREE
        assert sub.billing_status == BillingStatus.CANCELLED


# ---------------------------------------------------------------------------
# customer.subscription.updated → tier synced to price_id
# ---------------------------------------------------------------------------

class TestSubscriptionUpdated:

    def test_subscription_updated_to_starter(self, db, webhook_user):
        from models.subscription import Subscription, SubscriptionTier

        stripe_sub = make_stripe_sub_payload(
            "cus_webhook_test", status="active", price_id="price_starter_fake"
        )
        event = make_stripe_event("customer.subscription.updated", stripe_sub, "evt_sub_upd_1")

        call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.tier == SubscriptionTier.STARTER

    def test_subscription_updated_to_pro(self, db, webhook_user):
        from models.subscription import Subscription, SubscriptionTier

        stripe_sub = make_stripe_sub_payload(
            "cus_webhook_test", status="active", price_id="price_pro_fake"
        )
        event = make_stripe_event("customer.subscription.updated", stripe_sub, "evt_sub_upd_pro")

        call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.tier == SubscriptionTier.PRO


# ---------------------------------------------------------------------------
# Idempotency: same event ID processed twice → no second state change
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_duplicate_event_id_causes_no_state_change(self, db, webhook_user):
        """Processing the same event_id twice must be a no-op on the second call."""
        from models.subscription import Subscription, BillingStatus

        invoice = {"customer": "cus_webhook_test", "subscription": "sub_123"}
        event = make_stripe_event("invoice.paid", invoice, "evt_idem_1")

        # First call
        call_webhook(db, event)
        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        assert sub.billing_status == BillingStatus.ACTIVE

        # Manually change status to simulate out-of-band change
        sub.billing_status = BillingStatus.PAST_DUE
        db.flush()

        # Second call with same event_id → must be skipped
        call_webhook(db, event)

        sub = db.query(Subscription).filter(Subscription.user_id == webhook_user.user_id).first()
        # Status must remain PAST_DUE (unchanged by the duplicate)
        assert sub.billing_status == BillingStatus.PAST_DUE
