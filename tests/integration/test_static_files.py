"""Integration tests for the ``/static/{file_path:path}`` route (step_005).

Maps to spec FR-19 (signature part), AC-45, AC-46.

Covers:
  - an expiring signed URL downloads the file before expiry
  - an expired expiring URL is rejected with the same 403 body as an invalid
    legacy signature
  - a tampered/non-integer ``exp`` is rejected with the same 403 (not a 422)
  - a legacy (non-expiring) signed URL still downloads unchanged (AC-46)
  - a TTL beyond the max-TTL ceiling is rejected with the same 403
  - a signed ``filename`` query param is bound into the signature; tampering
    with it at request time is rejected with the same 403

The ``/static`` route reads ``main.tmp_base_folder`` once at import time, so
each test monkeypatches that module attribute directly to a pytest ``tmp_path``
instead of relying on the ``TMP_BASE_FOLDER`` env var (which main.py only
reads at import time, before any test can set it).
"""

import time

import main as main_module

from utils.security import generate_signature, generate_expiring_signature

INVALID_SIGNATURE_BODY = {"detail": "Invalid signature or missing parameters"}


def _not_expired() -> int:
    """A future timestamp inside the default 86400s max-TTL window."""
    return int(time.time()) + 60


def _write_file(tmp_path, rel_path: str, content: bytes = b"hello world") -> None:
    full_path = tmp_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)


class TestExpiringSignedStaticUrl:
    def test_valid_expiring_url_downloads_file(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf", b"%PDF-1.4 fake")

        expires_at = _not_expired()
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at)},
        )

        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 fake"

    def test_expired_url_returns_same_403_as_invalid_signature(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")

        expires_at = 1  # already expired
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at)},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_tampered_exp_returns_same_403_not_422(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")

        expires_at = _not_expired()
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at + 1)},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_non_integer_exp_returns_same_403_not_422(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")

        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", _not_expired())

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": "abc"},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_tampered_identity_returns_same_403(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")

        expires_at = _not_expired()
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-99", "sig": sig, "exp": str(expires_at)},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_tampered_path_returns_same_403(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")
        _write_file(tmp_path, "a2a/other.pdf")

        expires_at = _not_expired()
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/other.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at)},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_beyond_max_ttl_returns_same_403(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf")

        expires_at = int(time.time()) + 86401  # one second past the default ceiling
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at)

        resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at)},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_filename_is_bound_to_signature_and_tampering_rejected(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "a2a/file.pdf", b"%PDF-1.4 fake")

        expires_at = _not_expired()
        sig = generate_expiring_signature("a2a/file.pdf", "a2a-42", expires_at, filename="report.pdf")

        valid_resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at), "filename": "report.pdf"},
        )
        assert valid_resp.status_code == 200

        tampered_resp = client.get(
            "/static/a2a/file.pdf",
            params={"user": "a2a-42", "sig": sig, "exp": str(expires_at), "filename": "renamed.pdf"},
        )
        assert tampered_resp.status_code == 403
        assert tampered_resp.json() == INVALID_SIGNATURE_BODY


class TestLegacySignedStaticUrlUnchanged:
    """AC-46: existing non-expiring signed URLs must keep working unchanged."""

    def test_legacy_url_without_exp_still_downloads(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "legacy/file.txt", b"legacy content")

        sig = generate_signature("legacy/file.txt", "alice")

        resp = client.get(
            "/static/legacy/file.txt",
            params={"user": "alice", "sig": sig},
        )

        assert resp.status_code == 200
        assert resp.content == b"legacy content"

    def test_legacy_url_with_invalid_signature_returns_403(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "legacy/file.txt")

        resp = client.get(
            "/static/legacy/file.txt",
            params={"user": "alice", "sig": "not-a-real-signature"},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY

    def test_expiring_signature_rejected_on_legacy_request_without_exp(self, client, tmp_path, monkeypatch):
        """A signature minted via the expiring path must not satisfy the legacy verify."""
        monkeypatch.setattr(main_module, "tmp_base_folder", str(tmp_path))
        _write_file(tmp_path, "legacy/file.txt")

        expiring_sig = generate_expiring_signature("legacy/file.txt", "alice", _not_expired())

        resp = client.get(
            "/static/legacy/file.txt",
            params={"user": "alice", "sig": expiring_sig},
        )

        assert resp.status_code == 403
        assert resp.json() == INVALID_SIGNATURE_BODY
