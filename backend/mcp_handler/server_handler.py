"""
MCP Server Handler

Implements the MCP (Model Context Protocol) for exposing agents as tools.
Supports JSON-RPC 2.0 over HTTP with Streamable HTTP transport.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.mcp_server import MCPServer, MCPServerAgent
from models.agent import Agent
from services.agent_execution_service import AgentExecutionService
from db.database import SessionLocal
from utils.logger import get_logger

logger = get_logger(__name__)

# MCP Protocol constants
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "mattin-ai-mcp"
MCP_SERVER_VERSION = "1.0.0"


class MCPError(Exception):
    """MCP Protocol Error"""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# JSON-RPC Error codes
class JSONRPCError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


class MCPServerHandler:
    """Handles MCP protocol requests for an MCP server"""

    def __init__(self, server_id: int, server_name: str, app_id: int, api_key_id: Optional[int] = None):
        self.server_id = server_id
        self.server_name = server_name
        self.app_id = app_id
        self.api_key_id = api_key_id
        self.agent_execution_service = AgentExecutionService()

    def _get_mcp_server(self, session: Session) -> Optional[MCPServer]:
        """Load the MCP server with a fresh session"""
        from repositories.mcp_server_repository import MCPServerRepository
        return MCPServerRepository.get_by_id_and_app_id(session, self.server_id, self.app_id)

    async def handle_request(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an MCP JSON-RPC request.

        Args:
            request_body: The JSON-RPC request body

        Returns:
            JSON-RPC response
        """
        # Validate JSON-RPC request
        if not isinstance(request_body, dict):
            return self._error_response(None, JSONRPCError.INVALID_REQUEST, "Invalid request format")

        jsonrpc = request_body.get("jsonrpc")
        method = request_body.get("method")
        params = request_body.get("params", {})
        request_id = request_body.get("id")

        if jsonrpc != "2.0":
            return self._error_response(request_id, JSONRPCError.INVALID_REQUEST, "Invalid JSON-RPC version")

        if not method:
            return self._error_response(request_id, JSONRPCError.INVALID_REQUEST, "Method is required")

        try:
            result = await self._dispatch_method(method, params)

            # If it's a notification (no id), don't return a response
            if request_id is None:
                return None

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

        except MCPError as e:
            return self._error_response(request_id, e.code, e.message, e.data)
        except Exception as e:
            logger.error(f"MCP request error: {str(e)}")
            return self._error_response(request_id, JSONRPCError.INTERNAL_ERROR, str(e))

    async def _dispatch_method(self, method: str, params: Dict[str, Any]) -> Any:
        """Dispatch MCP method to appropriate handler"""
        handlers = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "notifications/initialized": self._handle_initialized_notification,
        }

        handler = handlers.get(method)
        if not handler:
            raise MCPError(JSONRPCError.METHOD_NOT_FOUND, f"Method not found: {method}")

        return await handler(params)

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request"""
        client_info = params.get("clientInfo", {})
        logger.info(f"MCP client initializing: {client_info.get('name', 'unknown')}")

        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": f"{MCP_SERVER_NAME}-{self.server_name}",
                "version": MCP_SERVER_VERSION
            }
        }

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request"""
        return {}

    async def _handle_initialized_notification(self, params: Dict[str, Any]) -> None:
        """Handle initialized notification"""
        logger.info(f"MCP client initialized for server {self.server_id}")
        return None

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request - return agents as tools"""
        session = SessionLocal()
        try:
            # Load MCP server with fresh session
            mcp_server = self._get_mcp_server(session)
            if not mcp_server:
                raise MCPError(JSONRPCError.INTERNAL_ERROR, "MCP server not found")

            tools = []

            for assoc in mcp_server.agent_associations:
                agent = assoc.agent
                if not agent:
                    continue

                # Filter out agents that are no longer marked as tools
                if not agent.is_tool:
                    logger.debug(f"Skipping agent {agent.agent_id} ({agent.name}): not marked as tool")
                    continue

                # Use override names/descriptions if provided
                tool_name = assoc.tool_name_override or self._generate_tool_name(agent.name)
                tool_description = assoc.tool_description_override or agent.description or f"Execute the {agent.name} agent"

                tool = {
                    "name": tool_name,
                    "description": tool_description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "The message or query to send to the agent"
                            }
                        },
                        "required": ["message"]
                    }
                }

                # Add agent_id as metadata for internal reference
                tool["_agent_id"] = agent.agent_id

                tools.append(tool)

            return {"tools": tools}

        finally:
            session.close()

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request - execute an agent"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise MCPError(JSONRPCError.INVALID_PARAMS, "Tool name is required")

        # Find the agent by tool name
        session = SessionLocal()
        try:
            # Load MCP server with fresh session
            mcp_server = self._get_mcp_server(session)
            if not mcp_server:
                raise MCPError(JSONRPCError.INTERNAL_ERROR, "MCP server not found")

            agent = None
            for assoc in mcp_server.agent_associations:
                assoc_agent = assoc.agent
                if not assoc_agent:
                    continue

                expected_name = assoc.tool_name_override or self._generate_tool_name(assoc_agent.name)
                if expected_name == tool_name:
                    agent = assoc_agent
                    break

            if not agent:
                raise MCPError(JSONRPCError.INVALID_PARAMS, f"Tool not found: {tool_name}")

            # Verify the agent is still marked as a tool
            if not agent.is_tool:
                raise MCPError(
                    JSONRPCError.INVALID_PARAMS,
                    f"Tool '{tool_name}' is no longer available (agent is not marked as a tool)"
                )

            # Extract message from arguments
            message = arguments.get("message")
            if not message:
                raise MCPError(JSONRPCError.INVALID_PARAMS, "Message argument is required")

            # Execute the agent
            user_context = {
                "api_key_id": self.api_key_id,
                "mcp_server_id": self.server_id,
                "source": "mcp"
            }

            result = await self.agent_execution_service.execute_agent_chat(
                agent_id=agent.agent_id,
                message=message,
                files=None,
                search_params=None,
                user_context=user_context,
                db=session
            )

            # Format response
            response_content = result.get("response", "")
            if isinstance(response_content, dict):
                response_text = json.dumps(response_content, indent=2)
            else:
                response_text = str(response_content)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": response_text
                    }
                ],
                "isError": False
            }

        except MCPError:
            raise
        except HTTPException as e:
            raise MCPError(JSONRPCError.INTERNAL_ERROR, e.detail)
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {str(e)}"
                    }
                ],
                "isError": True
            }
        finally:
            session.close()

    def _generate_tool_name(self, agent_name: str) -> str:
        """Generate a valid MCP tool name from agent name"""
        # Convert to lowercase, replace spaces with underscores
        name = agent_name.lower().replace(" ", "_").replace("-", "_")
        # Remove any non-alphanumeric characters except underscores
        name = "".join(c if c.isalnum() or c == "_" else "" for c in name)
        # Ensure it starts with a letter
        if name and not name[0].isalpha():
            name = "tool_" + name
        return name or "unnamed_tool"

    def _error_response(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: Any = None
    ) -> Dict[str, Any]:
        """Create a JSON-RPC error response"""
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error
        }
