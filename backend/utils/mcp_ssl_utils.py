"""Utilities for handling SSL verification in MCP connections."""

import httpx
from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)


def create_insecure_httpx_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient that skips SSL certificate verification.
    
    This factory follows the McpHttpClientFactory protocol from langchain_mcp_adapters.
    """
    return httpx.AsyncClient(
        verify=False,
        headers=headers,
        timeout=timeout,
        auth=auth,
    )


def inject_ssl_config(connection_config: Dict[str, Any], ssl_verify: bool = True) -> Dict[str, Any]:
    """Inject SSL configuration into MCP connection config.
    
    When ssl_verify is False, adds an httpx_client_factory that disables SSL
    verification for SSE and streamable_http transport connections.
    
    Args:
        connection_config: The connection configuration dict for MultiServerMCPClient.
        ssl_verify: Whether to verify SSL certificates. Default True.
        
    Returns:
        The modified connection config dict.
    """
    if ssl_verify:
        return connection_config
    
    for server_name, server_config in connection_config.items():
        if isinstance(server_config, dict):
            transport = server_config.get('transport', '')
            has_url = 'url' in server_config
            
            # Inject for URL-based transports (SSE, streamable_http, http)
            # or URL-based connections without explicit transport (defaults to SSE)
            # stdio and websocket don't use httpx
            if has_url and transport in ('sse', 'streamable_http', 'http', ''):
                server_config['httpx_client_factory'] = create_insecure_httpx_client
                logger.info(f"Disabled SSL verification for MCP server: {server_name}")
    
    return connection_config
