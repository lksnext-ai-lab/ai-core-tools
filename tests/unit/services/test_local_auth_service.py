"""Unit tests for LocalAuthService.

The database is fully mocked (no DB connection required).
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException

# Ensure deployment mode defaults to non-SaaS so validation gates are not hit
os.environ.setdefault("AICT_DEPLOYMENT_MODE", "self_managed")

from services.local_auth_service import (
    LocalAuthService,
    _hash_password,
    _verify_password,
    _get_serializer,
    _TOKEN_SALT_VERIFY,
    _TOKEN_SALT_RESET,
    _VERIFY_TOKEN_MAX_AGE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(user_id=1, email="user@example.com", auth_method="local"):
    user = MagicMock()
    user.user_id = user_id
    user.email = email
    user.auth_method = auth_method
    return user


def make_cred(user_id=1, hashed_password=None, is_verified=False, verification_token=None,
              verification_token_expiry=None, reset_token=None, reset_token_expiry=None):
    cred = MagicMock()
    cred.user_id = user_id
    cred.hashed_password = hashed_password or _hash_password("secret123")
    cred.is_verified = is_verified
    cred.verification_token = verification_token
    cred.verification_token_expiry = verification_token_expiry
    cred.reset_token = reset_token
    cred.reset_token_expiry = reset_token_expiry
    return cred


# ---------------------------------------------------------------------------
# Password hashing round-trip
# ---------------------------------------------------------------------------

def test_hash_and_verify_password():
    plain = "MySecurePassword123!"
    hashed = _hash_password(plain)
    assert hashed != plain
    assert _verify_password(plain, hashed)


def test_wrong_password_fails_verification():
    hashed = _hash_password("correct-horse")
    assert not _verify_password("wrong-horse", hashed)


# ---------------------------------------------------------------------------
# Token generation and expiry
# ---------------------------------------------------------------------------

def test_generate_and_decode_verification_token():
    email = "test@example.com"
    token = LocalAuthService._generate_verification_token(email)
    decoded = LocalAuthService._decode_token(token, salt=_TOKEN_SALT_VERIFY)
    assert decoded == email


def test_generate_and_decode_reset_token():
    email = "reset@example.com"
    token = LocalAuthService._generate_reset_token(email)
    decoded = LocalAuthService._decode_token(token, salt=_TOKEN_SALT_RESET)
    assert decoded == email


def test_tampered_token_raises_400():
    token = LocalAuthService._generate_verification_token("a@b.com") + "tampered"
    with pytest.raises(HTTPException) as exc_info:
        LocalAuthService._decode_token(token, salt=_TOKEN_SALT_VERIFY)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Registration: raises on duplicate email
# ---------------------------------------------------------------------------

def test_register_raises_on_duplicate_email():
    db = MagicMock()
    existing_user = make_user()

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository"),
        patch("services.local_auth_service.SubscriptionRepository"),
    ):
        MockUserRepo.return_value.get_by_email.return_value = existing_user

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.register(db, "user@example.com", "password123")

        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

def test_verify_email_marks_user_verified():
    email = "verify@example.com"
    token = LocalAuthService._generate_verification_token(email)
    db = MagicMock()
    user = make_user(email=email)
    cred = make_cred(
        is_verified=False,
        verification_token=token,
        verification_token_expiry=datetime.utcnow() + timedelta(hours=1),
    )

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred
        MockCredRepo.return_value.mark_verified.return_value = cred

        result = LocalAuthService.verify_email(db, token)

    assert result == user
    db.commit.assert_called()


def test_verify_email_raises_on_expired_token():
    email = "expire@example.com"
    token = LocalAuthService._generate_verification_token(email)
    db = MagicMock()
    user = make_user(email=email)
    cred = make_cred(
        is_verified=False,
        verification_token=token,
        verification_token_expiry=datetime.utcnow() - timedelta(hours=1),  # expired
    )

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.verify_email(db, token)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_with_correct_credentials_returns_user():
    plain = "validpassword"
    email = "login@example.com"
    db = MagicMock()
    user = make_user(email=email)
    cred = make_cred(hashed_password=_hash_password(plain), is_verified=True)

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred

        result = LocalAuthService.login(db, email, plain)

    assert result == user


def test_login_with_wrong_password_raises_401():
    email = "login@example.com"
    db = MagicMock()
    user = make_user(email=email)
    cred = make_cred(hashed_password=_hash_password("correct"), is_verified=True)

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.login(db, email, "wrong")

        assert exc_info.value.status_code == 401


def test_login_unverified_user_raises_403():
    plain = "password"
    email = "unverified@example.com"
    db = MagicMock()
    user = make_user(email=email)
    cred = make_cred(hashed_password=_hash_password(plain), is_verified=False)

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred

        with pytest.raises(HTTPException) as exc_info:
            LocalAuthService.login(db, email, plain)

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Password reset flow
# ---------------------------------------------------------------------------

def test_password_reset_flow():
    email = "reset@example.com"
    db = MagicMock()
    user = make_user(email=email)
    token = LocalAuthService._generate_reset_token(email)
    cred = make_cred(
        reset_token=token,
        reset_token_expiry=datetime.utcnow() + timedelta(hours=1),
    )

    with (
        patch("services.local_auth_service.UserRepository") as MockUserRepo,
        patch("services.local_auth_service.UserCredentialRepository") as MockCredRepo,
    ):
        MockUserRepo.return_value.get_by_email.return_value = user
        MockCredRepo.return_value.get_by_user_id.return_value = cred

        result = LocalAuthService.complete_password_reset(db, token, "newpassword")

    assert result == user
    db.commit.assert_called()
