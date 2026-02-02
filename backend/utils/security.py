import hmac
import hashlib
import os
from config import SECRET_KEY

def generate_signature(path: str, username: str) -> str:
    """
    Generate HMAC signature for a file path and username.
    
    Args:
        path: The relative file path (e.g. 'conversations/123/image.png')
        username: The username of the requester
        
    Returns:
        Hex string signature
    """
    # Normalize path to ensure consistency (forward slashes)
    path = path.replace('\\', '/')
    if path.startswith('/'):
        path = path[1:]
        
    message = f"{path}:{username}"
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(path: str, username: str, signature: str) -> bool:
    """
    Verify the signature for a file path and username.
    
    Args:
        path: The relative file path
        username: The username claiming access
        signature: The provided signature
        
    Returns:
        True if valid, False otherwise
    """
    if not signature or not username:
        return False
        
    expected_signature = generate_signature(path, username)
    return hmac.compare_digest(expected_signature, signature)
