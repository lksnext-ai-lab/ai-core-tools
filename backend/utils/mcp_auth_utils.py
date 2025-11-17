"""
MCP Authentication Utilities

This module provides utilities for handling authentication when connecting to MCP servers
(both internal and external). It supports passing JWT tokens from authenticated users to 
MCP servers for authorization.

The authentication flow:
1. User authenticates → receives JWT token
2. User makes request → token in Authorization header  
3. Backend extracts token from request
4. Token passed to agent execution via user_context
5. MCPClientManager injects token into MCP server connections
6. External MCP servers verify token using shared secret

For external MCP servers to work with this system, they need to:
- Use FastMCP with JWTVerifier
- Share the same JWT secret (SECRET_KEY from .env)
- Use HS256 algorithm

See docs/EXTERNAL_MCP_AUTHENTICATION.md for complete guide.
"""

from typing import Dict, Optional, Any
from utils.logger import get_logger

logger = get_logger(__name__)


def extract_auth_token(user_context: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Extract authentication token from user context.
    
    Args:
        user_context: Dictionary containing user authentication information
                     Can contain:
                     - 'token': JWT token (for OAuth authenticated users)
                     - 'api_key': API key (for API key authenticated users)
                     - 'oauth': Boolean indicating OAuth authentication
    
    Returns:
        JWT token string or None if not available
    """
    if not user_context:
        logger.debug("No user context provided for MCP authentication")
        return None
    
    # Check if this is an OAuth-authenticated user with a JWT token
    if user_context.get('oauth') and 'token' in user_context:
        token = user_context['token']
        return token
    
    # For API key authentication, we don't pass the API key to MCP servers
    # as they expect OAuth tokens. You could implement API key -> JWT conversion
    # or use a different authentication strategy for API key users
    if user_context.get('api_key'):
        logger.debug("API key authentication detected - MCP servers require OAuth tokens")
        return None
    
    logger.debug("No authentication token found in user context")
    return None


def prepare_mcp_auth_headers(token: Optional[str]) -> Dict[str, str]:
    """
    Prepare HTTP headers for authenticated MCP server connections.
    
    According to MCP specification and FastMCP implementation, authentication
    is done via standard HTTP Authorization Bearer tokens.
    
    Args:
        token: JWT token to include in headers
    
    Returns:
        Dictionary of HTTP headers to include in MCP client requests
    """
    headers = {}
    
    if token:
        headers['Authorization'] = f'Bearer {token}'
        logger.debug("Prepared Authorization header for MCP connection")
    else:
        logger.debug("No token provided - MCP connection will be unauthenticated")
    
    return headers


def get_mcp_connection_config(
    base_config: Dict[str, Any],
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enhance MCP connection configuration with authentication headers.
    
    This function takes a base MCP server configuration and adds authentication
    headers if a token is provided. It supports both stdio and HTTP-based MCP servers.
    
    Args:
        base_config: Base MCP server configuration (command, args, env, etc.)
        auth_token: Optional JWT token for authentication
    
    Returns:
        Enhanced configuration with authentication headers
    
    Example base_config:
        {
            "auth-test-server": {
                "url": "http://localhost:8000",
                "transport": "sse"
            }
        }
    """
    if not base_config:
        return {}
    
    enhanced_config = base_config.copy()
    
    # Add authentication headers to HTTP-based MCP servers
    if auth_token:
        auth_headers = prepare_mcp_auth_headers(auth_token)
        
        # For each MCP server in the config, add authentication headers
        for server_name, server_config in enhanced_config.items():
            if isinstance(server_config, dict):
                # Check if this is an HTTP-based server (has 'url' key)
                if 'url' in server_config:
                    # Add or update headers in the server configuration
                    if 'headers' not in server_config:
                        server_config['headers'] = {}
                    server_config['headers'].update(auth_headers)
                    logger.info(f"Added authentication headers to MCP server: {server_name}")
                else:
                    # This is a stdio-based server (has 'command' key)
                    # stdio servers inherit security from the local environment
                    logger.debug(f"Skipping auth headers for stdio server: {server_name}")
    
    return enhanced_config


def validate_mcp_auth_config(mcp_config: Dict[str, Any]) -> bool:
    """
    Validate that MCP server configuration is properly set up for authentication.
    
    Args:
        mcp_config: MCP server configuration to validate
    
    Returns:
        True if configuration is valid, False otherwise
    """
    if not mcp_config:
        logger.warning("Empty MCP configuration")
        return False
    
    for server_name, server_config in mcp_config.items():
        if not isinstance(server_config, dict):
            logger.warning(f"Invalid config format for server {server_name}")
            return False
        
        # HTTP-based servers should have a URL
        if 'url' in server_config:
            if not server_config['url'].startswith(('http://', 'https://')):
                logger.warning(f"Invalid URL for server {server_name}: {server_config['url']}")
                return False
        
        # stdio-based servers should have a command
        elif 'command' not in server_config:
            logger.warning(f"Server {server_name} missing both 'url' and 'command'")
            return False
    
    return True


def create_authenticated_mcp_config(
    server_name: str,
    server_url: str,
    auth_token: Optional[str] = None,
    transport: str = "sse"
) -> Dict[str, Any]:
    """
    Create a complete MCP server configuration with authentication.
    
    This is a convenience function for creating new MCP server configurations
    that include authentication from the start.
    
    Args:
        server_name: Name identifier for the MCP server
        server_url: Base URL of the MCP server
        auth_token: Optional JWT token for authentication
        transport: Transport type ('sse' or 'http')
    
    Returns:
        Complete MCP server configuration dictionary
    
    Example:
        config = create_authenticated_mcp_config(
            "auth-test-server",
            "http://localhost:8000",
            "eyJhbGciOiJIUzI1NiIs...",
            "sse"
        )
    """
    config = {
        server_name: {
            "url": server_url,
            "transport": transport
        }
    }
    
    if auth_token:
        auth_headers = prepare_mcp_auth_headers(auth_token)
        config[server_name]['headers'] = auth_headers
        logger.info(f"Created authenticated MCP config for {server_name}")
    else:
        logger.info(f"Created unauthenticated MCP config for {server_name}")
    
    return config


# Aliases for backward compatibility
get_user_token_from_context = extract_auth_token
prepare_mcp_headers = prepare_mcp_auth_headers
