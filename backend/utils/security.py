import hmac
import hashlib
from utils.secret_key import get_secret_key

def generate_signature(path: str, username: str) -> str:
    """Return an HMAC-SHA256 hex signature for a file path and username.

    Args:
        path: Relative file path (e.g. ``'conversations/123/image.png'``).
        username: Username of the requester.

    Returns:
        Hex string signature.
    """
    # Normalise to forward slashes and strip any leading slash.
    path = path.replace('\\', '/')
    if path.startswith('/'):
        path = path[1:]

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
