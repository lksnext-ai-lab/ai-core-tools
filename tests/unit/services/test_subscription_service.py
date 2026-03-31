"""Unit tests for SubscriptionService.

The database, Stripe SDK, and email service are fully mocked.
"""
import os
import pytest
from unittest.mock import MagicMock, Mock, patch, call
from fastapi import HTTPException

# Set required env vars via setdefault so we never override a value already set
# by another test module in the same process.
os.environ.setdefault("AICT_DEPLOYMENT_MODE", "self_managed")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
os.environ.setdefault("STRIPE_PRICE_ID_PRO", "price_pro_fake")
os.environ.setdefault("EMAIL_FROM", "noreply@example.com")

from services.subscription_service import SubscriptionService
from models.subscription import SubscriptionTier, BillingStatus


# ---------------------------------------------------------------------------
# Shared fixture: patch is_self_managed → False so webhook paths are entered
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_saas_mode():
    """Patch is_self_managed() to return False for all tests in this module."""
    with patch("services.subscription_service.is_self_managed", return_value=False):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sub(user_id=1, tier=SubscriptionTier.FREE, billing_status=BillingStatus.NONE,
             stripe_customer_id="cus_fake", stripe_subscription_id=None,
             admin_override_tier=None):
    sub = MagicMock()
    sub.user_id = user_id
    sub.tier = tier
    sub.billing_status = billing_status
    sub.stripe_customer_id = stripe_customer_id
    sub.stripe_subscription_id = stripe_subscription_id
    sub.admin_override_tier = admin_override_tier
    sub.trial_end = None
    return sub


def make_stripe_event(event_type: str, obj: dict, event_id: str = "evt_test123") -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": obj},
    }


def make_stripe_sub_obj(customer_id: str, status: str = "active",
                        price_id: str = "price_starter_fake") -> dict:
    return {
        "customer": customer_id,
        "status": status,
        "items": {
            "data": [{"price": {"id": price_id}}]
        },
    }


# ---------------------------------------------------------------------------
# handle_webhook — dispatch
# ---------------------------------------------------------------------------

class TestHandleWebhookDispatch:
    """Verify that handle_webhook routes to the correct private handler."""

    def _run_webhook(self, db, event_type, obj, event_id="evt_dispatch"):
        """Helper: patch Stripe, construct_event, and call handle_webhook."""
        event = make_stripe_event(event_type, obj, event_id)

        # No duplicate event in DB
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("services.subscription_service._get_stripe_client") as mock_client:
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            SubscriptionService.handle_webhook(db, b"payload", "sig")

    def test_invoice_paid_dispatched(self):
        db = MagicMock()
        sub = make_sub(stripe_customer_id="cus_1")
        db.query.return_value.filter.return_value.first.return_value = None

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_invoice_paid", mock_handler),
        ):
            event = make_stripe_event("invoice.paid", {"customer": "cus_1"})
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()

    def test_invoice_payment_failed_dispatched(self):
        db = MagicMock()

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_invoice_payment_failed", mock_handler),
        ):
            event = make_stripe_event("invoice.payment_failed", {"customer": "cus_1"})
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()

    def test_subscription_updated_dispatched(self):
        db = MagicMock()

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_subscription_updated", mock_handler),
        ):
            event = make_stripe_event("customer.subscription.updated",
                                      make_stripe_sub_obj("cus_1"))
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()

    def test_subscription_deleted_dispatched(self):
        db = MagicMock()

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_subscription_deleted", mock_handler),
        ):
            event = make_stripe_event("customer.subscription.deleted",
                                      make_stripe_sub_obj("cus_1"))
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()

    def test_trial_will_end_dispatched(self):
        db = MagicMock()

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_trial_will_end", mock_handler),
        ):
            event = make_stripe_event("customer.subscription.trial_will_end",
                                      make_stripe_sub_obj("cus_1"))
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()

    def test_unknown_event_type_is_silently_ignored(self):
        """Unknown event types should not raise; just no handler is invoked."""
        db = MagicMock()

        with patch("services.subscription_service._get_stripe_client") as mock_client:
            event = make_stripe_event("payment_intent.succeeded", {"id": "pi_1"}, "evt_unknown")
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            # Must not raise
            SubscriptionService.handle_webhook(db, b"p", "s")

        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# handle_webhook — idempotency
# ---------------------------------------------------------------------------

class TestHandleWebhookIdempotency:

    def test_duplicate_event_is_skipped(self):
        """Processing the same event ID a second time must be a no-op."""
        db = MagicMock()
        existing_setting = MagicMock()  # non-None → duplicate detected

        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_invoice_paid") as mock_handler,
        ):
            event = make_stripe_event("invoice.paid", {"customer": "cus_1"}, "evt_dup")
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            # Simulate that the event was already recorded in system_settings
            db.query.return_value.filter.return_value.first.return_value = existing_setting

            SubscriptionService.handle_webhook(db, b"p", "s")

        # Handler must NOT have been called
        mock_handler.assert_not_called()
        # DB commit must NOT have been called
        db.commit.assert_not_called()

    def test_first_event_is_processed_and_marked(self):
        """A new event ID is processed and then marked in the DB."""
        db = MagicMock()

        mock_handler = Mock()
        with (
            patch("services.subscription_service._get_stripe_client") as mock_client,
            patch.object(SubscriptionService, "_on_invoice_paid", mock_handler),
        ):
            event = make_stripe_event("invoice.paid", {"customer": "cus_1"}, "evt_new")
            stripe_mock = MagicMock()
            stripe_mock.Webhook.construct_event.return_value = event
            mock_client.return_value = stripe_mock
            db.query.return_value.filter.return_value.first.return_value = None

            SubscriptionService.handle_webhook(db, b"p", "s")

        mock_handler.assert_called_once()
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# handle_webhook — tier transitions via _on_subscription_updated
# ---------------------------------------------------------------------------

class TestTierTransitions:

    def _call_on_subscription_updated(self, db, stripe_sub_obj):
        SubscriptionService._on_subscription_updated(db, stripe_sub_obj)

    def test_free_to_starter_transition(self):
        db = MagicMock()
        sub = make_sub(user_id=10, tier=SubscriptionTier.FREE, stripe_customer_id="cus_10")

        stripe_sub = make_stripe_sub_obj(
            "cus_10", status="active", price_id="price_starter_fake"
        )

        with patch("services.subscription_service.SubscriptionRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.update_tier.return_value = sub
            # _find_user_by_stripe_customer uses db.query directly
            db.query.return_value.filter.return_value.first.return_value = sub

            self._call_on_subscription_updated(db, stripe_sub)

        repo_instance.update_tier.assert_called_once_with(
            user_id=10,
            tier=SubscriptionTier.STARTER,
            billing_status=BillingStatus.ACTIVE,
        )

    def test_starter_to_pro_transition(self):
        db = MagicMock()
        sub = make_sub(user_id=11, tier=SubscriptionTier.STARTER, stripe_customer_id="cus_11")

        stripe_sub = make_stripe_sub_obj(
            "cus_11", status="active", price_id="price_pro_fake"
        )

        with patch("services.subscription_service.SubscriptionRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.update_tier.return_value = sub
            db.query.return_value.filter.return_value.first.return_value = sub

            self._call_on_subscription_updated(db, stripe_sub)

        repo_instance.update_tier.assert_called_once_with(
            user_id=11,
            tier=SubscriptionTier.PRO,
            billing_status=BillingStatus.ACTIVE,
        )

    def test_pro_to_free_via_subscription_deleted(self):
        """subscription.deleted event must downgrade to FREE with CANCELLED status."""
        db = MagicMock()
        sub = make_sub(user_id=12, tier=SubscriptionTier.PRO, stripe_customer_id="cus_12")

        stripe_sub = make_stripe_sub_obj("cus_12", status="canceled")

        with (
            patch("services.subscription_service.SubscriptionRepository") as MockRepo,
            # FreezeService is imported lazily inside _on_subscription_deleted
            patch("services.freeze_service.FreezeService") as MockFreeze,
        ):
            repo_instance = MockRepo.return_value
            repo_instance.update_tier.return_value = sub
            db.query.return_value.filter.return_value.first.return_value = sub

            SubscriptionService._on_subscription_deleted(db, stripe_sub)

        repo_instance.update_tier.assert_called_once_with(
            user_id=12,
            tier=SubscriptionTier.FREE,
            billing_status=BillingStatus.CANCELLED,
        )

    def test_subscription_deleted_triggers_freeze(self):
        """After downgrade-to-free the FreezeService.apply_freeze must be called."""
        db = MagicMock()
        sub = make_sub(user_id=13, stripe_customer_id="cus_13")
        stripe_sub = make_stripe_sub_obj("cus_13")
        db.query.return_value.filter.return_value.first.return_value = sub

        with (
            patch("services.subscription_service.SubscriptionRepository"),
        ):
            # Patch the lazy import inside the handler
            import services.freeze_service as freeze_module
            original_freeze = freeze_module.FreezeService.apply_freeze
            called_with = {}

            def fake_apply_freeze(db_, user_id, new_tier):
                called_with["args"] = (db_, user_id, new_tier)

            freeze_module.FreezeService.apply_freeze = staticmethod(fake_apply_freeze)
            try:
                SubscriptionService._on_subscription_deleted(db, stripe_sub)
            finally:
                freeze_module.FreezeService.apply_freeze = original_freeze

        assert called_with["args"][1] == 13
        assert called_with["args"][2] == SubscriptionTier.FREE.value

    def test_past_due_status_on_payment_failed(self):
        db = MagicMock()
        sub = make_sub(user_id=14, stripe_customer_id="cus_14")
        invoice = {"customer": "cus_14", "subscription": "sub_14"}
        db.query.return_value.filter.return_value.first.return_value = sub

        with (
            patch("services.subscription_service.SubscriptionRepository") as MockRepo,
            # UserRepository and EmailService are lazy imports inside the handler
            patch("repositories.user_repository.UserRepository"),
            patch("services.email_service.EmailService"),
        ):
            repo_instance = MockRepo.return_value
            SubscriptionService._on_invoice_payment_failed(db, invoice)

        repo_instance.update_tier.assert_called_once_with(
            user_id=14,
            tier=sub.tier,
            billing_status=BillingStatus.PAST_DUE,
        )


# ---------------------------------------------------------------------------
# _tier_from_stripe_sub
# ---------------------------------------------------------------------------

class TestTierFromStripeSub:

    def test_maps_starter_price_to_starter(self):
        stripe_sub = make_stripe_sub_obj("cus_x", price_id="price_starter_fake")
        assert SubscriptionService._tier_from_stripe_sub(stripe_sub) == SubscriptionTier.STARTER

    def test_maps_pro_price_to_pro(self):
        stripe_sub = make_stripe_sub_obj("cus_x", price_id="price_pro_fake")
        assert SubscriptionService._tier_from_stripe_sub(stripe_sub) == SubscriptionTier.PRO

    def test_unknown_price_falls_back_to_free(self):
        stripe_sub = make_stripe_sub_obj("cus_x", price_id="price_unknown")
        assert SubscriptionService._tier_from_stripe_sub(stripe_sub) == SubscriptionTier.FREE


# ---------------------------------------------------------------------------
# handle_webhook — invalid signature
# ---------------------------------------------------------------------------

def test_invalid_stripe_signature_raises_400():
    import stripe as stripe_lib

    db = MagicMock()

    with patch("services.subscription_service._get_stripe_client") as mock_client:
        stripe_mock = MagicMock()
        stripe_mock.Webhook.construct_event.side_effect = stripe_lib.error.SignatureVerificationError(
            "bad sig", "sig_header"
        )
        mock_client.return_value = stripe_mock

        with pytest.raises(HTTPException) as exc_info:
            SubscriptionService.handle_webhook(db, b"payload", "bad_sig")

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# handle_webhook — self-managed no-op
# ---------------------------------------------------------------------------

def test_handle_webhook_is_noop_in_self_managed(monkeypatch):
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
    # Must reimport to reload the cached module-level function result
    import importlib
    import services.subscription_service as svc_module
    importlib.reload(svc_module)

    db = MagicMock()
    # Should return immediately without touching db or raising
    svc_module.SubscriptionService.handle_webhook(db, b"payload", "sig")
    db.commit.assert_not_called()

    # Restore for subsequent tests
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    importlib.reload(svc_module)
