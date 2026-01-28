"""
MCP (Model Context Protocol) Router

Exposes MCP servers as HTTP endpoints for external clients like Claude Desktop and Cursor.
Supports Streamable HTTP transport.
"""

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Any, Dict

from mcp_handler.auth import authenticate_mcp_request, MCPAuthResult
from mcp_handler.server_handler import MCPServerHandler
from utils.logger import get_logger

logger = get_logger(__name__)

mcp_router = APIRouter()


@mcp_router.post("/{app_slug}/{server_slug}")
async def mcp_endpoint_by_slug(
    app_slug: str,
    server_slug: str,
    request: Request
):
    """
    MCP endpoint using human-readable slugs.

    URL format: /mcp/v1/{app_slug}/{server_slug}

    Example: /mcp/v1/my-app/my-server
    """
    return await _handle_mcp_request(request, app_slug, server_slug, by_id=False)


@mcp_router.post("/id/{app_id}/{server_id}")
async def mcp_endpoint_by_id(
    app_id: str,
    server_id: str,
    request: Request
):
    """
    MCP endpoint using IDs (fallback).

    URL format: /mcp/v1/id/{app_id}/{server_id}

    Example: /mcp/v1/id/1/2
    """
    return await _handle_mcp_request(request, app_id, server_id, by_id=True)


async def _handle_mcp_request(
    request: Request,
    app_identifier: str,
    server_identifier: str,
    by_id: bool
) -> JSONResponse:
    """
    Handle an MCP request.

    Args:
        request: FastAPI request
        app_identifier: App slug or ID
        server_identifier: Server slug or ID
        by_id: Whether identifiers are IDs

    Returns:
        JSON-RPC response
    """
    # Authenticate the request
    try:
        auth_result: MCPAuthResult = authenticate_mcp_request(
            request,
            app_identifier,
            server_identifier,
            by_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )

    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"MCP parse error: {str(e)}")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            },
            status_code=200  # JSON-RPC errors are returned with 200 status
        )

    # Create handler and process request
    # Pass primitive IDs instead of ORM objects to avoid DetachedInstanceError
    handler = MCPServerHandler(
        server_id=auth_result.server_id,
        server_name=auth_result.server_name,
        app_id=auth_result.app_id,
        api_key_id=auth_result.api_key_id
    )

    try:
        response = await handler.handle_request(body)

        # If response is None (notification), return 204 No Content
        if response is None:
            return JSONResponse(content=None, status_code=204)

        return JSONResponse(content=response)

    except Exception as e:
        logger.error(f"MCP handler error: {str(e)}")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": body.get("id") if isinstance(body, dict) else None,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
        )


# SSE endpoint for Server-Sent Events (optional, for future streaming support)
@mcp_router.get("/{app_slug}/{server_slug}/sse")
async def mcp_sse_endpoint_by_slug(
    app_slug: str,
    server_slug: str,
    request: Request
):
    """
    SSE endpoint for MCP streaming (by slug).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSE transport not yet implemented. Use HTTP POST for JSON-RPC."
    )


@mcp_router.get("/id/{app_id}/{server_id}/sse")
async def mcp_sse_endpoint_by_id(
    app_id: str,
    server_id: str,
    request: Request
):
    """
    SSE endpoint for MCP streaming (by ID).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSE transport not yet implemented. Use HTTP POST for JSON-RPC."
    )
