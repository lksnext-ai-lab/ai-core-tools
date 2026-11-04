"""Unit tests for expiring static-file signatures (AD-12, FR-19, AC-45, AC-46).

Covers:
  - round trip of generate_expiring_signature / verify_expiring_signature
  - expiry enforcement
  - max-TTL enforcement
  - filename binding (tampering with filename is rejected)
  - tampering with path, identity or expires_at is rejected
  - the shifted-colon/length-prefix forgery is rejected (unambiguous encoding)
  - the legacy (non-expiring) and new expiring formats never cross-verify,
    since they are derived from domain-separated HMAC keys
  - verify_static_access: the single pure dispatch point used by the /static route

No database required.

Note: tests that don't specifically exercise the max-TTL ceiling use an
`expires_at` within the default 86400s window of `now` (explicit or real),
so the max-TTL check added alongside this file doesn't incidentally fail
tests that are only trying to prove something else (tampering, round trip...).
"""

import time

from utils.security import (
    generate_signature,
    verify_signature,
    generate_expiring_signature,
    verify_expiring_signature,
    build_expiring_static_url,
    verify_static_access,
)

# A fixed "now" far enough from the epoch that expires_at values derived from it
# stay well inside the default 86400s max-TTL window, used across tests that are
# not specifically exercising expiry or max-TTL.
_NOW = 1_000_000_000
_NOT_EXPIRED = _NOW + 300  # 5 minutes later, well under the 86400s ceiling


class TestExpiringSignatureRoundTrip:
    def test_valid_signature_verifies(self):
        sig = generate_expiring_signature("conversations/1/a.png", "a2a-5", expires_at=_NOT_EXPIRED)
        assert verify_expiring_signature(
            "conversations/1/a.png", "a2a-5", sig, expires_at=_NOT_EXPIRED, now=_NOW
        )

    def test_leading_slash_and_backslash_normalised_like_legacy(self):
        sig_a = generate_expiring_signature("/conversations/1/a.png", "a2a-5", expires_at=_NOT_EXPIRED)
        sig_b = generate_expiring_signature("conversations\\1\\a.png", "a2a-5", expires_at=_NOT_EXPIRED)
        sig_c = generate_expiring_signature("conversations/1/a.png", "a2a-5", expires_at=_NOT_EXPIRED)
        assert sig_a == sig_b == sig_c


class TestExpiringSignatureExpiry:
    def test_not_yet_expired_passes(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=1_000_100)
        assert verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=1_000_100, now=1_000_000)

    def test_exactly_at_expiry_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=1_000_000)
        assert not verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=1_000_000, now=1_000_000)

    def test_past_expiry_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=1_000_000)
        assert not verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=1_000_000, now=1_000_001)


class TestExpiringSignatureMaxTtl:
    def test_within_default_max_ttl_passes(self):
        now = 1_000_000
        expires_at = now + 86400  # exactly at the default ceiling
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=expires_at, now=now)

    def test_beyond_default_max_ttl_fails(self):
        now = 1_000_000
        expires_at = now + 86401  # one second past the default ceiling
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert not verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=expires_at, now=now)

    def test_custom_max_ttl_override_enforced(self):
        now = 1_000_000
        expires_at = now + 120
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=expires_at, now=now, max_ttl_seconds=120
        )
        assert not verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=expires_at, now=now, max_ttl_seconds=119
        )

    def test_env_override_is_honored(self, monkeypatch):
        monkeypatch.setenv("A2A_FILE_URL_MAX_TTL_SECONDS", "60")
        now = 1_000_000
        expires_at = now + 61
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert not verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=expires_at, now=now)


class TestExpiringSignatureFilenameBinding:
    def test_matching_filename_verifies(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED, filename="report.pdf")
        assert verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED, now=_NOW, filename="report.pdf"
        )

    def test_tampered_filename_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED, filename="report.pdf")
        assert not verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED, now=_NOW, filename="other.pdf"
        )

    def test_added_filename_not_originally_signed_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED)  # no filename
        assert not verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED, now=_NOW, filename="report.pdf"
        )

    def test_none_and_empty_string_filename_are_equivalent(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED, filename=None)
        assert verify_expiring_signature(
            "f.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED, now=_NOW, filename=""
        )


class TestExpiringSignatureTampering:
    def test_tampered_path_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("g.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED, now=_NOW)

    def test_tampered_identity_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("f.pdf", "a2a-2", sig, expires_at=_NOT_EXPIRED, now=_NOW)

    def test_tampered_expires_at_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("f.pdf", "a2a-1", sig, expires_at=_NOT_EXPIRED + 1, now=_NOW)

    def test_missing_signature_fails(self):
        assert not verify_expiring_signature("f.pdf", "a2a-1", "", expires_at=_NOT_EXPIRED, now=_NOW)

    def test_missing_identity_fails(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("f.pdf", "", sig, expires_at=_NOT_EXPIRED, now=_NOW)

    def test_shifted_colon_forgery_fails(self):
        """A signature for path 'a:b'/identity 'X' must not verify for path 'a'/identity 'b:X'.

        Both pairs collapse to the same naive ":"-joined string, so this is only safe
        because the signed message is length-prefixed per field.
        """
        sig = generate_expiring_signature("a:b", "X", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("a", "b:X", sig, expires_at=_NOT_EXPIRED, now=_NOW)
        # Sanity: it does verify against the original, unshifted pair.
        assert verify_expiring_signature("a:b", "X", sig, expires_at=_NOT_EXPIRED, now=_NOW)

    def test_shifted_pipe_forgery_fails(self):
        """Same shifted-boundary attack using the new '|' field delimiter itself."""
        sig = generate_expiring_signature("a|1:a", "X", expires_at=_NOT_EXPIRED)
        assert not verify_expiring_signature("a", "1:a|X", sig, expires_at=_NOT_EXPIRED, now=_NOW)


class TestDomainSeparationFromLegacySignature:
    def test_legacy_signature_fails_expiring_verification(self):
        legacy_sig = generate_signature("f.pdf", "alice")
        assert not verify_expiring_signature(
            "f.pdf", "alice", legacy_sig, expires_at=_NOT_EXPIRED, now=_NOW
        )

    def test_expiring_signature_fails_legacy_verification(self):
        expiring_sig = generate_expiring_signature("f.pdf", "alice", expires_at=_NOT_EXPIRED)
        assert not verify_signature("f.pdf", "alice", expiring_sig)


class TestBuildExpiringStaticUrl:
    def test_builds_url_with_expected_query_params(self):
        url = build_expiring_static_url(
            "http://localhost:8000", "conversations/1/a.png", "a2a-5", ttl_seconds=3600, filename="a.png"
        )

        assert url.startswith("http://localhost:8000/static/conversations/1/a.png?")
        assert "user=a2a-5" in url
        assert "filename=a.png" in url
        assert "exp=" in url
        assert "sig=" in url

    def test_url_is_independently_verifiable(self):
        url = build_expiring_static_url(
            "http://localhost:8000", "conversations/1/a.png", "a2a-5", ttl_seconds=3600
        )

        # Parse back the query params and confirm they verify.
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        exp = int(qs["exp"][0])
        sig = qs["sig"][0]
        user = qs["user"][0]

        assert verify_expiring_signature("conversations/1/a.png", user, sig, expires_at=exp)

    def test_url_with_filename_is_independently_verifiable(self):
        url = build_expiring_static_url(
            "http://localhost:8000", "conversations/1/a.png", "a2a-5", ttl_seconds=3600, filename="report.pdf"
        )

        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        exp = int(qs["exp"][0])
        sig = qs["sig"][0]
        user = qs["user"][0]
        filename = qs["filename"][0]

        assert verify_expiring_signature(
            "conversations/1/a.png", user, sig, expires_at=exp, filename=filename
        )
        # Renaming the download at request time must break verification.
        assert not verify_expiring_signature(
            "conversations/1/a.png", user, sig, expires_at=exp, filename="renamed.pdf"
        )

    def test_strips_trailing_slash_from_base_url(self):
        url = build_expiring_static_url(
            "http://localhost:8000/", "a.png", "a2a-5", ttl_seconds=60
        )
        assert url.startswith("http://localhost:8000/static/a.png?")
        assert "//static" not in url

    def test_ttl_is_clamped_to_max_ttl_seconds(self):
        url = build_expiring_static_url(
            "http://localhost:8000", "a.png", "a2a-5", ttl_seconds=10_000_000
        )

        from urllib.parse import urlparse, parse_qs

        qs = parse_qs(urlparse(url).query)
        exp = int(qs["exp"][0])
        # Clamped to the default 86400s ceiling, with a generous tolerance for test runtime.
        assert exp <= int(time.time()) + 86400 + 5


class TestVerifyStaticAccess:
    def test_valid_legacy_request_allowed(self):
        sig = generate_signature("f.pdf", "alice")
        assert verify_static_access("f.pdf", "alice", sig, None, None)

    def test_invalid_legacy_signature_denied(self):
        assert not verify_static_access("f.pdf", "alice", "bogus", None, None)

    def test_valid_expiring_request_allowed(self):
        expires_at = int(time.time()) + 60
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert verify_static_access("f.pdf", "a2a-1", sig, str(expires_at), None)

    def test_expired_expiring_request_denied(self):
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=1)
        assert not verify_static_access("f.pdf", "a2a-1", sig, "1", None)

    def test_non_integer_exp_denied(self):
        expires_at = int(time.time()) + 60
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at)
        assert not verify_static_access("f.pdf", "a2a-1", sig, "abc", None)

    def test_missing_user_denied(self):
        sig = generate_signature("f.pdf", "alice")
        assert not verify_static_access("f.pdf", None, sig, None, None)

    def test_missing_sig_denied(self):
        assert not verify_static_access("f.pdf", "alice", None, None, None)

    def test_filename_tampering_denied_for_expiring_request(self):
        expires_at = int(time.time()) + 60
        sig = generate_expiring_signature("f.pdf", "a2a-1", expires_at=expires_at, filename="report.pdf")
        assert verify_static_access("f.pdf", "a2a-1", sig, str(expires_at), "report.pdf")
        assert not verify_static_access("f.pdf", "a2a-1", sig, str(expires_at), "renamed.pdf")
