"""Unit tests for middleware.csrf.enforce_csrf (CSRF double-submit dependency).

Locks in the following bug-fix regression scenarios:

1. POST /auth/login with access_token cookie + no X-CSRF-Token → NOT blocked
   (login endpoint is exempt regardless of stale cookie state).
2. POST /auth/set-password with access_token cookie + no X-CSRF-Token → NOT blocked.
3. POST /auth/refresh with access_token cookie + matching csrf cookie BUT no header → 403.
4. POST /auth/refresh with matching csrf cookie AND matching header → passes.
5. GET /anything → never raises (safe methods are always exempt).
6. Request with no access_token cookie → never raises (Bearer / API-key path).
7. A path that merely CONTAINS but does NOT END WITH /auth/login (e.g.
   /internal/auth/login/extra) is NOT exempt — confirms suffix-match safety.

``enforce_csrf`` is a FastAPI dependency declared with ``async def``.  We call
it directly (await) rather than going through a test client so the tests run
with no DB and no app startup cost.

No database required.
"""

import os

import pytest

# Set minimum env before any backend import.
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")

from fastapi import HTTPException

from middleware.csrf import enforce_csrf


# ---------------------------------------------------------------------------
# Helpers: minimal fake Request
# ---------------------------------------------------------------------------


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeRequest:
    """Minimal stand-in for a Starlette Request used by enforce_csrf."""

    def __init__(self, method: str, path: str) -> None:
        self.method = method
        self.url = _FakeURL(path)


# Convenience wrappers so tests read naturally.

async def _call(
    method: str,
    path: str,
    access_token: str | None = None,
    csrf_cookie: str | None = None,
    x_csrf_token: str | None = None,
    authorization: str | None = None,
    x_api_key: str | None = None,
) -> None:
    """Invoke enforce_csrf with the supplied arguments and let any exception propagate."""
    await enforce_csrf(
        request=_FakeRequest(method, path),
        access_token_cookie=access_token,
        csrf_cookie=csrf_cookie,
        x_csrf_token=x_csrf_token,
        authorization=authorization,
        x_api_key=x_api_key,
    )


# ---------------------------------------------------------------------------
# Safe HTTP methods — always pass, no conditions
# ---------------------------------------------------------------------------


class TestSafeMethodsNeverRaise:
    @pytest.mark.asyncio
    async def test_get_with_cookie_no_header_does_not_raise(self):
        """GET requests are always exempt regardless of cookie state."""
        await _call("GET", "/internal/apps", access_token="some-token")

    @pytest.mark.asyncio
    async def test_head_does_not_raise(self):
        await _call("HEAD", "/internal/apps", access_token="some-token")

    @pytest.mark.asyncio
    async def test_options_does_not_raise(self):
        await _call("OPTIONS", "/internal/apps", access_token="some-token")


# ---------------------------------------------------------------------------
# Exempt paths — pre-session auth entry endpoints
# ---------------------------------------------------------------------------


class TestCsrfExemptPaths:
    @pytest.mark.asyncio
    async def test_login_path_with_stale_cookie_is_exempt(self):
        """Regression: POST /auth/login must not be blocked even when access_token
        cookie is present (the client holds a stale session from a previous login
        and cannot produce the matching CSRF header for this new request).
        """
        # access_token present but no csrf_cookie / x_csrf_token → would normally 403.
        await _call(
            "POST",
            "/internal/auth/login",
            access_token="stale-session-token",
            csrf_cookie=None,
            x_csrf_token=None,
        )

    @pytest.mark.asyncio
    async def test_set_password_path_with_stale_cookie_is_exempt(self):
        """Regression: POST /auth/set-password must not be blocked when a stale
        access_token cookie is present.
        """
        await _call(
            "POST",
            "/internal/auth/set-password",
            access_token="stale-session-token",
            csrf_cookie=None,
            x_csrf_token=None,
        )

    @pytest.mark.asyncio
    async def test_login_path_with_no_cookie_is_exempt(self):
        """Pre-session call with no cookie at all — must also pass (belt-and-suspenders)."""
        await _call(
            "POST",
            "/internal/auth/login",
            access_token=None,
        )

    @pytest.mark.asyncio
    async def test_set_password_with_no_cookie_is_exempt(self):
        await _call(
            "POST",
            "/internal/auth/set-password",
            access_token=None,
        )

    @pytest.mark.asyncio
    async def test_delete_on_login_path_is_also_exempt(self):
        """Exemption is by path suffix, not HTTP method — DELETE on an exempt path is safe."""
        await _call(
            "DELETE",
            "/internal/auth/login",
            access_token="stale-token",
        )


# ---------------------------------------------------------------------------
# Suffix-match safety — path CONTAINING but NOT ENDING WITH an exempt suffix
# ---------------------------------------------------------------------------


class TestExemptSuffixSafety:
    @pytest.mark.asyncio
    async def test_path_with_extra_segment_after_login_is_not_exempt(self):
        """A path like /internal/auth/login/extra does NOT end with /auth/login
        so it must NOT be exempt — and must raise 403 when cookie-authenticated
        without a header.
        """
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/login/extra",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token=None,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_path_with_query_string_after_set_password_is_not_exempt(self):
        """Path /internal/auth/set-password/confirm is not exempt."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/set-password/confirm",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token=None,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unrelated_path_with_login_in_middle_is_not_exempt(self):
        """A path like /api/v2/auth/login/verify is not exempt."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/api/v2/auth/login/verify",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token=None,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# No access_token cookie → no CSRF enforcement (Bearer / API-key path)
# ---------------------------------------------------------------------------


class TestNoCookieSessionSkipsCsrf:
    @pytest.mark.asyncio
    async def test_post_without_access_token_cookie_does_not_raise(self):
        """A Bearer-authenticated POST carries no access_token cookie;
        CSRF enforcement must be skipped entirely.
        """
        await _call(
            "POST",
            "/internal/apps",
            access_token=None,
            authorization="Bearer eyJ...",
        )

    @pytest.mark.asyncio
    async def test_post_with_api_key_no_cookie_does_not_raise(self):
        await _call(
            "POST",
            "/internal/apps",
            access_token=None,
            x_api_key="sk-testkey123",
        )

    @pytest.mark.asyncio
    async def test_delete_without_access_token_cookie_does_not_raise(self):
        await _call(
            "DELETE",
            "/internal/apps/42",
            access_token=None,
        )

    @pytest.mark.asyncio
    async def test_put_without_access_token_cookie_does_not_raise(self):
        await _call(
            "PUT",
            "/internal/apps/42",
            access_token=None,
        )


# ---------------------------------------------------------------------------
# Cookie-authenticated requests that ARE subject to CSRF enforcement
# ---------------------------------------------------------------------------


class TestCookieSessionCsrfEnforcement:
    # --- Missing token raises 403 ---

    @pytest.mark.asyncio
    async def test_post_with_cookie_but_missing_csrf_header_raises_403(self):
        """Cookie session without X-CSRF-Token header must be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/refresh",
                access_token="session-token",
                csrf_cookie="csrf-value-abc",
                x_csrf_token=None,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_cookie_but_missing_csrf_cookie_raises_403(self):
        """Cookie session with header but no csrf_token cookie must be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/refresh",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token="csrf-value-abc",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_cookie_and_both_tokens_missing_raises_403(self):
        """Cookie session with neither csrf_cookie nor header must be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/change-password",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token=None,
            )
        assert exc_info.value.status_code == 403

    # --- Mismatch raises 403 ---

    @pytest.mark.asyncio
    async def test_post_with_mismatched_tokens_raises_403(self):
        """csrf_token cookie and X-CSRF-Token header must match; mismatch → 403."""
        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/logout",
                access_token="session-token",
                csrf_cookie="csrf-correct",
                x_csrf_token="csrf-WRONG",
            )
        assert exc_info.value.status_code == 403

    # --- Matching pair passes ---

    @pytest.mark.asyncio
    async def test_post_with_matching_tokens_does_not_raise(self):
        """Cookie session with matching csrf_token cookie and header must pass."""
        await _call(
            "POST",
            "/internal/auth/refresh",
            access_token="session-token",
            csrf_cookie="csrf-abc-123",
            x_csrf_token="csrf-abc-123",
        )

    @pytest.mark.asyncio
    async def test_delete_with_matching_tokens_does_not_raise(self):
        await _call(
            "DELETE",
            "/internal/apps/99",
            access_token="session-token",
            csrf_cookie="csrf-xyz",
            x_csrf_token="csrf-xyz",
        )

    @pytest.mark.asyncio
    async def test_put_with_matching_tokens_does_not_raise(self):
        await _call(
            "PUT",
            "/internal/apps/99",
            access_token="session-token",
            csrf_cookie="csrf-xyz",
            x_csrf_token="csrf-xyz",
        )

    @pytest.mark.asyncio
    async def test_patch_with_matching_tokens_does_not_raise(self):
        await _call(
            "PATCH",
            "/internal/agents/7",
            access_token="session-token",
            csrf_cookie="csrf-xyz",
            x_csrf_token="csrf-xyz",
        )

    # --- Error detail is generic (no information leak) ---

    @pytest.mark.asyncio
    async def test_403_detail_is_generic_message(self):
        """The 403 detail must not reveal whether cookie or header was missing/mismatched."""
        from middleware.csrf import _CSRF_ERROR_MESSAGE

        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/auth/refresh",
                access_token="session-token",
                csrf_cookie=None,
                x_csrf_token=None,
            )
        assert exc_info.value.detail == _CSRF_ERROR_MESSAGE

    @pytest.mark.asyncio
    async def test_mismatch_403_detail_is_same_generic_message(self):
        """The mismatch path uses the same generic detail as the missing-token path."""
        from middleware.csrf import _CSRF_ERROR_MESSAGE

        with pytest.raises(HTTPException) as exc_info:
            await _call(
                "POST",
                "/internal/apps",
                access_token="session-token",
                csrf_cookie="real-token",
                x_csrf_token="fake-token",
            )
        assert exc_info.value.detail == _CSRF_ERROR_MESSAGE
