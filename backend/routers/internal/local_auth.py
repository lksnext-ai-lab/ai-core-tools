"""LOCAL auth HTTP endpoints (email+password, httpOnly cookies, CSRF-protected).

Registered only when ``AuthConfig.LOGIN_MODE == 'LOCAL'``.

CSRF note: the login and set-password endpoints are effectively exempt because no
``access_token`` cookie is present on those calls — the ``enforce_csrf`` dependency
is a no-op when the cookie is absent.
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from lks_idprovider import AuthContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from schemas.local_auth_schemas import ChangePasswordRequest, LoginRequest, SetPasswordRequest
from services.auth.credential_service import (
    AccountLockedError,
    CredentialError,
    InactiveAccountError,
    PasswordPolicyError,
    TokenError,
    CredentialService,
)
from services.auth.login_throttle import (
    ERR_TOO_MANY_REQUESTS,
    enforce_login_throttle,
    extract_client_ip,
    hit_account_throttle,
    reset_account_throttle,
)
from services.auth.refresh_service import RefreshService, RefreshTokenError
from utils.auth_cookies import (
    COOKIE_REFRESH_TOKEN,
    clear_session_cookies,
    set_session_cookies,
)
from utils.config import is_omniadmin
from utils.logger import get_logger

logger = get_logger(__name__)

_ERR_INVALID_CREDENTIALS = "Invalid email or password."
_ERR_ACCOUNT_LOCKED = "Account is temporarily locked. Please try again later."
_ERR_ACCOUNT_INACTIVE = "This account has been deactivated."
_ERR_TOKEN_INVALID = "The link is invalid or has already been used."
_ERR_TOKEN_EXPIRED = "The link has expired. Please request a new one."
_ERR_REFRESH_INVALID = "Session is invalid. Please log in again."
_ERR_CHANGE_PASSWORD_WRONG = "Current password is incorrect."
_ERR_PASSWORD_POLICY = "Password does not meet requirements."
_ERR_SESSION_START = "Unable to start session. Please try again."

class LoginResponse(BaseModel):
    """Minimal user info on login success. Tokens are in httpOnly cookies only — never in the body."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    email: str
    name: Optional[str] = None
    is_omniadmin: bool


class SetPasswordResponse(BaseModel):
    message: str


class ChangePasswordResponse(BaseModel):
    message: str


router = APIRouter(tags=["local-auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="LOCAL auth login",
    description="Authenticate with email and password. Session cookies are set on success.",
    dependencies=[Depends(enforce_login_throttle)],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    """Authenticate via email+password and issue httpOnly session cookies."""
    user_agent: Optional[str] = request.headers.get("user-agent")
    client_ip: Optional[str] = extract_client_ip(request)

    # Per-account throttle complements the DB-backed lockout in CredentialService.
    account_state = hit_account_throttle(str(body.email))
    if not account_state.allowed:
        logger.warning(
            "auth:throttle_account_exceeded email=%s ip=%s",
            body.email,
            client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=ERR_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(account_state.retry_after_seconds)},
        )

    try:
        user = await CredentialService.authenticate(
            db, email=str(body.email), password=body.password.get_secret_value()
        )
    except InactiveAccountError:
        # Subclass of CredentialError — must be caught first.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_ERR_ACCOUNT_INACTIVE,
        )
    except AccountLockedError as exc:
        logger.warning("auth:login_locked email=%s ip=%s", body.email, client_ip)
        locked_until = exc.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until is not None:
            retry_after = max(0, int((locked_until - datetime.now(timezone.utc)).total_seconds()))
        else:
            retry_after = 60  # conservative fallback
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_ERR_ACCOUNT_LOCKED,
            headers={"Retry-After": str(retry_after)},
        )
    except CredentialError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_INVALID_CREDENTIALS,
        )

    reset_account_throttle(str(body.email))

    try:
        access_token, refresh_token_plain, _ = RefreshService.issue_session(
            db,
            user,
            user_agent=user_agent,
            ip=client_ip,
        )
        set_session_cookies(response, access_token, refresh_token_plain)
    except Exception as exc:
        logger.error("auth:http_login_session_error user_id=%s — %s", user.user_id, type(exc).__name__)
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_ERR_SESSION_START,
        )

    logger.info(
        "auth:http_login_success user_id=%s ip=%s",
        user.user_id,
        client_ip,
    )

    return LoginResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        is_omniadmin=is_omniadmin(user.email),
    )


@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token",
    description=(
        "Exchange the current refresh-token cookie for a fresh token pair. "
        "Requires X-CSRF-Token header (double-submit CSRF protection is active "
        "because the access_token cookie is present on this call)."
    ),
    dependencies=[Depends(enforce_login_throttle)],
)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias=COOKIE_REFRESH_TOKEN),
) -> LoginResponse:
    """Rotate the refresh token and issue fresh session cookies."""
    if not refresh_token_cookie:
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_REFRESH_INVALID,
        )

    user_agent: Optional[str] = request.headers.get("user-agent")
    client_ip: Optional[str] = extract_client_ip(request)

    try:
        access_token, new_refresh_plain, _ = RefreshService.rotate(
            db,
            refresh_token_cookie,
            user_agent=user_agent,
            ip=client_ip,
        )
    except RefreshTokenError as exc:
        logger.warning("auth:refresh_failed reason=%s ip=%s", exc, client_ip)
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_REFRESH_INVALID,
        )

    set_session_cookies(response, access_token, new_refresh_plain)
    logger.debug("auth:token_rotated ip=%s", client_ip)

    # Decode the freshly minted token to build the response — avoids an extra DB round-trip.
    from utils.local_auth_tokens import decode_access_token
    import jwt

    try:
        payload = decode_access_token(access_token)
    except jwt.InvalidTokenError:
        logger.error("auth:refresh_decode_failure — newly minted token failed decode")
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_REFRESH_INVALID,
        )

    user_email: str = payload.get("email", "")
    user_id: int = int(payload.get("sub", 0))
    user_name: Optional[str] = payload.get("name")

    return LoginResponse(
        user_id=user_id,
        email=user_email,
        name=user_name,
        is_omniadmin=is_omniadmin(user_email),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout (current device)",
    description=(
        "Revoke the current device's refresh token and clear session cookies. "
        "Requires X-CSRF-Token header when the access_token cookie is present."
    ),
)
async def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias=COOKIE_REFRESH_TOKEN),
) -> dict:
    """Revoke the current device session and clear auth cookies. Idempotent (safe to call when already logged out)."""
    if refresh_token_cookie:
        RefreshService.revoke_current(db, refresh_token_cookie)

    clear_session_cookies(response)
    logger.info("auth:http_logout")
    return {"message": "Logged out successfully."}


@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
    summary="Logout all devices",
    description=(
        "Revoke all refresh tokens for the authenticated user (all devices). "
        "Requires a valid session (access_token cookie or Bearer) and X-CSRF-Token header."
    ),
)
async def logout_all(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> dict:
    """Revoke all refresh tokens for the current user across all devices."""
    user_id = int(auth_context.identity.id)
    RefreshService.revoke_all(db, user_id)
    clear_session_cookies(response)
    logger.info("auth:http_logout_all user_id=%s", user_id)
    return {"message": "All sessions revoked."}


@router.post(
    "/set-password",
    response_model=SetPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Set password via one-time token",
    description=(
        "Consume a set-password token (first-time setup or admin-triggered reset) "
        "and apply the new password. No session is created — the user must log in "
        "after completing this flow. "
        "CSRF no-op: no access_token cookie is present before the user logs in."
    ),
    dependencies=[Depends(enforce_login_throttle)],
)
async def set_password(
    body: SetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SetPasswordResponse:
    """Consume a one-time set-password token and apply the new password. No session is created."""
    try:
        await CredentialService.consume_set_password_token(
            db, body.token, body.new_password.get_secret_value()
        )
    except PasswordPolicyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_ERR_PASSWORD_POLICY,
        )
    except TokenError as exc:
        msg = str(exc)
        if "expired" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_ERR_TOKEN_EXPIRED,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_ERR_TOKEN_INVALID,
        )
    except CredentialError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_ERR_TOKEN_INVALID,
        )

    return SetPasswordResponse(message="Password set successfully. You can now log in.")


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Change own password",
    description=(
        "Authenticated self-service password change. "
        "Verifies the current password, applies the new one, and revokes all "
        "refresh sessions — the user must re-authenticate on all devices. "
        "Requires X-CSRF-Token header."
    ),
)
async def change_password(
    body: ChangePasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> ChangePasswordResponse:
    """Verify current password, apply new password, and revoke all refresh sessions."""
    from repositories.user_repository import UserRepository

    user_id = int(auth_context.identity.id)
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_INVALID_CREDENTIALS,
        )

    try:
        await CredentialService.change_password(
            db,
            user,
            current_password=body.current_password.get_secret_value(),
            new_password=body.new_password.get_secret_value(),
        )
    except PasswordPolicyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_ERR_PASSWORD_POLICY,
        )
    except CredentialError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_CHANGE_PASSWORD_WRONG,
        )

    logger.info("auth:http_change_password_success user_id=%s", user_id)
    return ChangePasswordResponse(
        message="Password changed successfully. Please log in again on all devices."
    )
