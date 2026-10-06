import hmac
import hashlib
import os
import time
from urllib.parse import quote, urlencode
from utils.secret_key import get_secret_key

_EXPIRING_KEY_DOMAIN = b"mattin-static-exp-v1"

# Hard ceiling on how far in the future an expiring static signature may expire,
# regardless of what ttl_seconds a caller requests. Overridable via env for ops;
# individual calls can still override it (e.g. in tests) via the `max_ttl_seconds`
# parameter on verify_expiring_signature.
_DEFAULT_MAX_TTL_SECONDS = 86400


def _max_ttl_seconds() -> int:
    """Return the configured ceiling (seconds) for expiring static signature TTLs."""
    return int(os.getenv("A2A_FILE_URL_MAX_TTL_SECONDS", str(_DEFAULT_MAX_TTL_SECONDS)))


def _normalize_path(path: str) -> str:
    """Normalize a static file path the same way for every signature flavor.

    Converts backslashes to forward slashes and strips a single leading slash,
    matching the normalization ``generate_signature`` has always used.
    """
    path = path.replace('\\', '/')
    if path.startswith('/'):
        path = path[1:]
    return path


def generate_signature(path: str, username: str) -> str:
    """Return an HMAC-SHA256 hex signature for a file path and username.

    Args:
        path: Relative file path (e.g. ``'conversations/123/image.png'``).
        username: Username of the requester.

    Returns:
        Hex string signature.
    """
    path = _normalize_path(path)

    message = f"{path}:{username}"
    signature = hmac.new(
        get_secret_key().encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(path: str, username: str, signature: str) -> bool:
    """Verify the HMAC signature for a file path and username.

    Args:
        path: Relative file path.
        username: Username claiming access.
        signature: Signature to verify.

    Returns:
        ``True`` if valid, ``False`` otherwise.
    """
    if not signature or not username:
        return False

    expected_signature = generate_signature(path, username)
    return hmac.compare_digest(expected_signature, signature)


def _expiring_key() -> bytes:
    """Derive the HMAC key used for expiring static signatures.

    This is a separate, domain-separated key derived from the app secret, so
    a legacy (non-expiring) signature can never verify as an expiring one,
    and vice versa.

    Returns:
        32-byte derived key.
    """
    return hmac.new(
        get_secret_key().encode('utf-8'),
        _EXPIRING_KEY_DOMAIN,
        hashlib.sha256,
    ).digest()


def _expiring_message(path: str, identity: str, expires_at: int, filename: str) -> str:
    """Build the unambiguous, length-prefixed message signed for expiring URLs.

    A plain ``f"{path}:{identity}:{expires_at}"`` join is ambiguous: a signature for
    path ``'a:b'``/identity ``'X'`` would also verify for path ``'a'``/identity
    ``'b:X'``, since both collapse to the same joined string. Each field is instead
    prefixed with its own length so field boundaries can never be shifted by crafting
    a path or identity that contains the delimiter.

    Args:
        path: Normalized relative file path.
        identity: Opaque identity string.
        expires_at: Unix timestamp (seconds).
        filename: Suggested download filename, or ``""`` when not bound.

    Returns:
        The message string to HMAC.
    """
    return f"{len(path)}:{path}|{len(identity)}:{identity}|{expires_at}|{len(filename)}:{filename}"


def generate_expiring_signature(
    path: str,
    identity: str,
    expires_at: int,
    filename: str | None = None,
) -> str:
    """Return an HMAC-SHA256 hex signature for a file path that expires.

    Args:
        path: Relative file path (e.g. ``'conversations/123/image.png'``).
        identity: Opaque identity string of the requester/holder of the link.
        expires_at: Unix timestamp (seconds) after which the signature is invalid.
        filename: Optional download filename bound into the signature so a holder
            of a valid URL cannot rename the download. ``None`` is signed as ``""``.

    Returns:
        Hex string signature.
    """
    path = _normalize_path(path)
    filename = filename or ""

    message = _expiring_message(path, identity, expires_at, filename)
    return hmac.new(
        _expiring_key(),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def verify_expiring_signature(
    path: str,
    identity: str,
    signature: str,
    expires_at: int,
    *,
    filename: str | None = None,
    now: int | None = None,
    max_ttl_seconds: int | None = None,
) -> bool:
    """Verify an expiring HMAC signature for a file path.

    Args:
        path: Relative file path.
        identity: Opaque identity string claiming access.
        signature: Signature to verify.
        expires_at: Unix timestamp (seconds) after which the signature is invalid.
        filename: Download filename presented alongside the URL. Must match what was
            signed (``""``/``None`` if the URL carries no filename), otherwise the
            signature can never match.
        now: Current unix timestamp (seconds). Defaults to ``time.time()`` when omitted.
        max_ttl_seconds: Ceiling on ``expires_at - now``. Defaults to
            ``A2A_FILE_URL_MAX_TTL_SECONDS`` (or 86400) when omitted; tests may override.

    Returns:
        ``True`` if valid, not expired and within the max TTL window, ``False`` otherwise.
    """
    if not signature or not identity:
        return False

    if now is None:
        now = int(time.time())
    if now >= expires_at:
        return False

    if max_ttl_seconds is None:
        max_ttl_seconds = _max_ttl_seconds()
    if expires_at - now > max_ttl_seconds:
        return False

    expected_signature = generate_expiring_signature(path, identity, expires_at, filename)
    return hmac.compare_digest(expected_signature, signature)


def build_expiring_static_url(
    base_url: str,
    rel_path: str,
    identity: str,
    ttl_seconds: int,
    filename: str | None = None,
) -> str:
    """Build a fully-qualified, expiring ``/static`` download URL.

    Args:
        base_url: Scheme+host (and optional port/path prefix), no trailing slash required.
        rel_path: Relative file path under ``TMP_BASE_FOLDER``.
        identity: Opaque identity string bound into the signature.
        ttl_seconds: Seconds from now until the signature expires.
        filename: Optional download filename to suggest to the client.

    Returns:
        A ``/static/{rel_path}`` URL with ``user``, ``exp`` and ``sig`` query params
        (and ``filename`` when provided).
    """
    normalized_path = _normalize_path(rel_path)
    effective_ttl = min(int(ttl_seconds), _max_ttl_seconds())
    expires_at = int(time.time()) + effective_ttl
    signature = generate_expiring_signature(normalized_path, identity, expires_at, filename)

    base = base_url.rstrip('/')
    query_params = {"user": identity, "exp": str(expires_at), "sig": signature}
    if filename:
        query_params["filename"] = filename

    return f"{base}/static/{quote(normalized_path)}?{urlencode(query_params)}"


def verify_static_access(
    path: str,
    user: str | None,
    sig: str | None,
    exp_raw: str | None,
    filename: str | None = None,
) -> bool:
    """Decide whether a ``/static`` request may proceed, covering both signature formats.

    Pure function: does no I/O and raises nothing. Holds the ``exp`` int parsing,
    the missing-parameter checks and the expiring-vs-legacy dispatch, so the router
    only needs a single ``if not verify_static_access(...): raise HTTPException(...)``.

    Args:
        path: Raw ``file_path`` path parameter from the request.
        user: ``user`` query parameter.
        sig: ``sig`` query parameter.
        exp_raw: Raw ``exp`` query parameter (unparsed), or ``None`` for a legacy URL.
        filename: ``filename`` query parameter, if any.

    Returns:
        ``True`` if access is allowed, ``False`` otherwise (every failure reason,
        including a malformed ``exp``, collapses to the same ``False``).
    """
    if not user or not sig:
        return False

    if exp_raw is not None:
        try:
            expires_at = int(exp_raw)
        except (TypeError, ValueError):
            return False
        return verify_expiring_signature(path, user, sig, expires_at, filename=filename)

    return verify_signature(path, user, sig)


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hex digest used to tie conversations to an API key.

    The raw key is never stored on a conversation; this digest identifies the
    caller instead (see ``Conversation.api_key_hash``).
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
