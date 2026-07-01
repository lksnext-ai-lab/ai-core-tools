"""Unit tests for schemas.local_auth_schemas — password policy validation.

Covers:
- Minimum-length rejection (< 12 chars).
- Common-password denylist rejection.
- Strong passphrase accepted.
- No forced composition rule: a long all-lowercase passphrase passes.

No database or external services required.  All tests are pure-Python,
exercising Pydantic validation on SetPasswordRequest (the simplest schema
that runs the full policy).
"""

import pytest
from pydantic import ValidationError

from schemas.local_auth_schemas import (
    SetPasswordRequest,
    ChangePasswordRequest,
    AdminSetPasswordRequest,
    AdminCreateUserRequest,
    LoginRequest,
    _MIN_LENGTH,
    _COMMON_PASSWORDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_password_request(password: str) -> SetPasswordRequest:
    """Construct a SetPasswordRequest with a dummy token and the given password."""
    return SetPasswordRequest(token="dummy-token", new_password=password)


def _get_one_common_password() -> str:
    """Return a single deterministic entry from the common-password denylist."""
    # "password" is always present in the denylist and is > 12 chars when
    # suffixed, but on its own it is 8 chars — choose one that is long enough
    # to pass the length gate but still denylisted.
    candidates = [p for p in _COMMON_PASSWORDS if len(p) >= _MIN_LENGTH]
    if candidates:
        # Deterministic: sorted order, first entry.
        return sorted(candidates)[0]
    # Fall back to a short one padded to meet the length gate — but the
    # original entry is still in the denylist so comparison after .lower()
    # will match.  We pick "password123456" which is 14 chars and denylisted.
    return "password123456"


# ---------------------------------------------------------------------------
# Minimum-length enforcement
# ---------------------------------------------------------------------------


class TestMinLengthPolicy:
    def test_password_shorter_than_min_is_rejected(self):
        """A password exactly one character below the minimum is rejected."""
        too_short = "a" * (_MIN_LENGTH - 1)
        with pytest.raises(ValidationError) as exc_info:
            _set_password_request(too_short)

        errors = exc_info.value.errors()
        assert any("characters" in str(e["msg"]).lower() or "length" in str(e["msg"]).lower()
                   for e in errors), errors

    def test_password_at_min_length_is_not_rejected_by_length_rule(self):
        """A password exactly at the minimum length clears the length gate.

        It may still fail the denylist check, but not for length.  We use a
        unique string that is not in the denylist.
        """
        at_min = "x" * _MIN_LENGTH  # 'xxxxxxxxxxxx' — not in the denylist
        req = _set_password_request(at_min)
        assert req.new_password.get_secret_value() == at_min

    def test_password_much_shorter_than_min_is_rejected(self):
        """A very short password (e.g., 3 chars) is clearly rejected."""
        with pytest.raises(ValidationError):
            _set_password_request("abc")


# ---------------------------------------------------------------------------
# Common-password denylist
# ---------------------------------------------------------------------------


class TestDenylistPolicy:
    def test_common_password_exactly_in_list_is_rejected(self):
        """A literal entry from _COMMON_PASSWORDS that meets length is rejected."""
        denied = _get_one_common_password()
        # Sanity: the candidate must meet the length gate so the denylist error
        # is what triggers (not the length error).
        assert len(denied) >= _MIN_LENGTH, (
            f"Test setup: chosen denylist entry {denied!r} is shorter than "
            f"_MIN_LENGTH={_MIN_LENGTH}; pick a longer one."
        )
        with pytest.raises(ValidationError) as exc_info:
            _set_password_request(denied)

        errors = exc_info.value.errors()
        assert any("common" in str(e["msg"]).lower() for e in errors), errors

    def test_common_password_case_insensitive_rejection(self):
        """Denylist comparison is case-insensitive (NIST SP 800-63B)."""
        denied = _get_one_common_password()
        assert len(denied) >= _MIN_LENGTH
        upper = denied.upper()
        with pytest.raises(ValidationError) as exc_info:
            _set_password_request(upper)

        errors = exc_info.value.errors()
        assert any("common" in str(e["msg"]).lower() for e in errors), errors

    def test_known_short_common_password_is_rejected_by_length_not_denylist(self):
        """A very common but short password like 'abc123' is rejected for length."""
        short_common = "abc123"  # len=6, < 12
        assert short_common in _COMMON_PASSWORDS
        with pytest.raises(ValidationError) as exc_info:
            _set_password_request(short_common)

        errors = exc_info.value.errors()
        # Length error fires first; message should mention character count.
        assert any("characters" in str(e["msg"]).lower() or "length" in str(e["msg"]).lower()
                   for e in errors), errors


# ---------------------------------------------------------------------------
# Accepted passwords
# ---------------------------------------------------------------------------


class TestAcceptedPasswords:
    def test_strong_passphrase_is_accepted(self):
        """A long mixed-case passphrase with symbols passes all policy checks."""
        strong = "Horse!Battery@Staple#2024"
        req = _set_password_request(strong)
        assert req.new_password.get_secret_value() == strong

    def test_long_all_lowercase_passphrase_passes(self):
        """No forced composition rule: all-lowercase long phrase is accepted.

        NIST SP 800-63B explicitly forbids mandatory complexity rules.
        """
        lowercase_phrase = "correcthorsebatterystaple"  # 25 chars, all lowercase, not in denylist
        assert lowercase_phrase not in _COMMON_PASSWORDS
        req = _set_password_request(lowercase_phrase)
        assert req.new_password.get_secret_value() == lowercase_phrase

    def test_all_digits_passphrase_passes_when_not_denylisted(self):
        """A long numeric string not in the denylist is accepted (no composition rule)."""
        numeric = "13579246801357924680"  # 20 chars, not in denylist
        assert numeric not in _COMMON_PASSWORDS
        req = _set_password_request(numeric)
        assert req.new_password.get_secret_value() == numeric

    def test_unicode_password_passes(self):
        """A password with non-ASCII chars is accepted if long enough and not denylisted."""
        unicode_pass = "contraseñaMuySegura2024"  # Spanish chars, 23 chars
        assert unicode_pass.lower() not in _COMMON_PASSWORDS
        req = _set_password_request(unicode_pass)
        assert req.new_password.get_secret_value() == unicode_pass


# ---------------------------------------------------------------------------
# SecretStr behaviour — no accidental leakage
# ---------------------------------------------------------------------------


class TestSecretStrBehaviour:
    def test_password_not_in_repr(self):
        """The plaintext password must never appear in the model repr."""
        req = _set_password_request("correcthorsebatterystaple")
        assert "correcthorsebatterystaple" not in repr(req)
        assert "correcthorsebatterystaple" not in str(req)

    def test_get_secret_value_returns_plaintext(self):
        """get_secret_value() must return the original string."""
        plain = "correcthorsebatterystaple"
        req = _set_password_request(plain)
        assert req.new_password.get_secret_value() == plain


# ---------------------------------------------------------------------------
# Other schemas apply the same policy
# ---------------------------------------------------------------------------


class TestOtherSchemasApplyPolicy:
    def test_change_password_request_enforces_policy(self):
        """ChangePasswordRequest's new_password field runs the same validator."""
        short = "short"
        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="any-current-pass", new_password=short)

    def test_admin_set_password_request_enforces_policy(self):
        """AdminSetPasswordRequest's new_password field runs the same validator."""
        denied = _get_one_common_password()
        assert len(denied) >= _MIN_LENGTH
        with pytest.raises(ValidationError):
            AdminSetPasswordRequest(new_password=denied)

    def test_change_password_request_accepts_strong_password(self):
        """ChangePasswordRequest accepts a valid new password."""
        req = ChangePasswordRequest(
            current_password="irrelevant-current",
            new_password="correcthorsebatterystaple",
        )
        assert req.new_password.get_secret_value() == "correcthorsebatterystaple"


# ---------------------------------------------------------------------------
# Email normalisation — LoginRequest and AdminCreateUserRequest must align
# ---------------------------------------------------------------------------


class TestEmailNormalisation:
    """Both write and read paths must produce the same canonical lowercase email.

    Finding A fix: an admin creating ``Bob@Acme.com`` must store
    ``bob@acme.com`` so that ``LoginRequest`` normalisation (strip+lower) can
    find the row with a case-sensitive exact match.
    """

    def test_login_request_lowercases_email(self):
        """LoginRequest strips and lowercases the email."""
        req = LoginRequest(email="  Bob@Acme.COM  ", password="correcthorsebatterystaple")
        assert str(req.email) == "bob@acme.com"

    def test_login_request_strips_whitespace(self):
        req = LoginRequest(email=" user@example.com ", password="correcthorsebatterystaple")
        assert str(req.email) == "user@example.com"

    def test_admin_create_user_request_lowercases_email(self):
        """AdminCreateUserRequest normalises email to canonical lowercase.

        This is the invariant that prevents ``Bob@Acme.com`` from being stored
        verbatim while login lookups use ``bob@acme.com``.
        """
        req = AdminCreateUserRequest(email="Bob@Acme.COM", name="Bob")
        assert str(req.email) == "bob@acme.com"

    def test_admin_create_user_request_strips_whitespace(self):
        req = AdminCreateUserRequest(email="  alice@example.com  ", name="Alice")
        assert str(req.email) == "alice@example.com"

    def test_admin_create_and_login_normalise_to_same_value(self):
        """Round-trip: admin-create email and login email normalise identically."""
        raw_admin = "  Admin@MyOrg.COM  "
        raw_login = "admin@myorg.com"

        create_req = AdminCreateUserRequest(email=raw_admin, name="Admin")
        login_req = LoginRequest(email=raw_login, password="correcthorsebatterystaple")

        assert str(create_req.email) == str(login_req.email)
