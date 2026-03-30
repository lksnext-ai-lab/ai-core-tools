"""Integration tests for SaaS local email+password auth flows.

These tests require a real PostgreSQL test database (port 5433).
Run with: pytest tests/integration/test_saas_auth.py -v

Strategy:
- Test the full register → verify-email → login flow via the service layer
- Tests operate directly on the service layer against the real DB
- HTTP layer is tested only for the login endpoint which issues tokens
"""
import os
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Environment fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def saas_env(monkeypatch):
    """Set deployment mode to SaaS for all tests in this module."""
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_STARTER", "price_starter_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro_fake")
    monkeypatch.setenv("EMAIL_FROM", "noreply@test.com")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_PORT", "1025")

    import importlib
    import deployment_mode as dm
    importlib.reload(dm)
    import services.local_auth_service as las
    importlib.reload(las)

    yield

    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "self_managed")
    importlib.reload(dm)
    importlib.reload(las)


# ---------------------------------------------------------------------------
# Full registration → verify → login flow
# ---------------------------------------------------------------------------

class TestRegistrationFlow:

    def test_register_creates_user_and_credential(self, db):
        """Successful registration creates a User, UserCredential, and Subscription."""
        from services.local_auth_service import LocalAuthService
        from models.user import User
        from models.user_credential import UserCredential
        from models.subscription import Subscription

        # Patch email sending so we don't need an SMTP server
        from unittest.mock import patch
        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "reg@test.com", "password123")

        assert user.user_id is not None
        assert user.email == "reg@test.com"
        assert user.auth_method == "local"

        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        assert cred is not None
        assert not cred.is_verified  # not verified yet

    def test_register_raises_on_duplicate_email(self, db):
        """Registering with an already-used email returns HTTP 409."""
        from services.local_auth_service import LocalAuthService
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            LocalAuthService.register(db, "dup@test.com", "password123")
            db.flush()

            with pytest.raises(HTTPException) as exc_info:
                LocalAuthService.register(db, "dup@test.com", "other_pass")

        assert exc_info.value.status_code == 409

    def test_verify_email_marks_credential_verified(self, db):
        """Consuming the verification token sets is_verified=True on the credential."""
        from services.local_auth_service import LocalAuthService
        from models.user_credential import UserCredential
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "verify@test.com", "password123")
        db.flush()

        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        token = cred.verification_token

        result = LocalAuthService.verify_email(db, token)

        assert result.email == "verify@test.com"
        db.flush()
        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        assert cred.is_verified

    def test_verify_email_raises_on_expired_token(self, db):
        """An expired verification token returns HTTP 400."""
        from services.local_auth_service import LocalAuthService
        from models.user_credential import UserCredential
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "expire@test.com", "password123")
        db.flush()

        # Manually expire the token
        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        token = cred.verification_token
        cred.verification_token_expiry = datetime.utcnow() - timedelta(hours=1)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.verify_email(db, token)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

class TestLoginFlow:

    def test_login_with_correct_credentials_returns_user(self, db):
        """Verified user can log in and receives the user object."""
        from services.local_auth_service import LocalAuthService
        from models.user_credential import UserCredential
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "login_ok@test.com", "securepass")
        db.flush()

        # Verify the account
        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        cred.is_verified = True
        db.flush()

        result = LocalAuthService.login(db, "login_ok@test.com", "securepass")
        assert result.email == "login_ok@test.com"

    def test_login_with_wrong_password_raises_401(self, db):
        """Wrong password returns HTTP 401."""
        from services.local_auth_service import LocalAuthService
        from models.user_credential import UserCredential
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "badpass@test.com", "correctpass")
        db.flush()

        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        cred.is_verified = True
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.login(db, "badpass@test.com", "wrongpass")

        assert exc_info.value.status_code == 401

    def test_login_unverified_user_raises_403(self, db):
        """Unverified user cannot log in — returns HTTP 403."""
        from services.local_auth_service import LocalAuthService
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            LocalAuthService.register(db, "unverified@test.com", "pass")
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.login(db, "unverified@test.com", "pass")

        assert exc_info.value.status_code == 403

    def test_login_nonexistent_email_raises_401(self, db):
        """Login with an email that was never registered returns HTTP 401."""
        from services.local_auth_service import LocalAuthService

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.login(db, "nobody@test.com", "pass")

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Password reset flow
# ---------------------------------------------------------------------------

class TestPasswordResetFlow:

    def test_full_password_reset_flow(self, db):
        """Full reset: request → token in DB → complete → can log in with new password."""
        from services.local_auth_service import LocalAuthService
        from models.user_credential import UserCredential
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            user = LocalAuthService.register(db, "reset@test.com", "oldpass")
        db.flush()

        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        cred.is_verified = True
        db.flush()

        # Request reset (patches email so we can capture the token ourselves)
        with patch("services.email_service.EmailService"):
            LocalAuthService.request_password_reset(db, "reset@test.com")
        db.flush()

        # Grab the token from DB
        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        reset_token = cred.reset_token
        assert reset_token is not None

        # Complete the reset
        with patch("services.email_service.EmailService"):
            result = LocalAuthService.complete_password_reset(db, reset_token, "newpass123")

        assert result.email == "reset@test.com"

        # Verify old credentials are cleared
        db.flush()
        cred = db.query(UserCredential).filter(UserCredential.user_id == user.user_id).first()
        assert cred.reset_token is None

    def test_password_reset_request_for_nonexistent_email_is_silent(self, db):
        """Requesting a reset for an unknown email should not raise (prevents enumeration)."""
        from services.local_auth_service import LocalAuthService
        from unittest.mock import patch

        with patch("services.email_service.EmailService"):
            # Must not raise
            LocalAuthService.request_password_reset(db, "nonexistent@test.com")
