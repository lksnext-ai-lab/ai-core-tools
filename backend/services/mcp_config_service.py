from typing import Optional, List
from models.mcp_config import MCPConfig
from repositories.mcp_config_repository import MCPConfigRepository
from sqlalchemy.orm import Session
from datetime import datetime
import json
import asyncio
from schemas.mcp_config_schemas import MCPConfigListItemSchema, MCPConfigDetailSchema, CreateUpdateMCPConfigSchema
from langchain_mcp_adapters.client import MultiServerMCPClient
from utils.logger import get_logger
from utils.mcp_ssl_utils import inject_ssl_config

# httpx is an optional dependency used by the MCP client.  It may not be
# installed in lightweight test environments, so import lazily.
try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - ci environments sometimes omit this lib
    httpx = None

logger = get_logger(__name__)

class MCPConfigService:
    @staticmethod
    def list_mcp_configs(db: Session, app_id: int) -> List[MCPConfigListItemSchema]:
        """Get all MCP configs for a specific app as list items"""
        configs = MCPConfigRepository.get_all_by_app_id(db, app_id)
        
        result = []
        for config in configs:
            result.append(MCPConfigListItemSchema(
                config_id=config.config_id,
                name=config.name,
                description=config.description or "",
                created_at=config.create_date
            ))
        
        return result

    @staticmethod
    def get_mcp_config_detail(db: Session, app_id: int, config_id: int) -> Optional[MCPConfigDetailSchema]:
        """Get detailed information about a specific MCP config"""
        if config_id == 0:
            # New MCP config
            return MCPConfigDetailSchema(
                config_id=0,
                name="",
                description="",
                config="{}",
                ssl_verify=True,
                created_at=None
            )
        
        # Existing MCP config
        config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
        
        if not config:
            return None
        
        # Serialize config to JSON string if it's a dict
        config_str = json.dumps(config.config) if isinstance(config.config, dict) else config.config
        
        return MCPConfigDetailSchema(
            config_id=config.config_id,
            name=config.name,
            description=config.description or "",
            config=config_str,
            ssl_verify=config.ssl_verify if config.ssl_verify is not None else True,
            created_at=config.create_date
        )

    @staticmethod
    def create_or_update_mcp_config(
        db: Session, 
        app_id: int, 
        config_id: int, 
        config_data: CreateUpdateMCPConfigSchema
    ) -> MCPConfig:
        """Create a new MCP config or update an existing one"""
        if config_id == 0:
            # Create new MCP config
            config = MCPConfig()
            config.app_id = app_id
            config.create_date = datetime.now()
        else:
            # Update existing MCP config
            config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
            
            if not config:
                return None
        
        # Update config data
        config.name = config_data.name
        config.description = config_data.description
        config.ssl_verify = config_data.ssl_verify
        
        # Parse config JSON field
        try:
            config.config = json.loads(config_data.config) if isinstance(config_data.config, str) else config_data.config
        except json.JSONDecodeError:
            config.config = {}
        
        # Use repository to save
        if config_id == 0:
            return MCPConfigRepository.create(db, config)
        else:
            return MCPConfigRepository.update(db, config)

    @staticmethod
    def delete_mcp_config(db: Session, app_id: int, config_id: int) -> bool:
        """Delete an MCP config"""
        return MCPConfigRepository.delete_by_id_and_app_id(db, config_id, app_id)

    @staticmethod
    async def test_connection(db: Session, app_id: int, config_id: int) -> dict:
        """Test connection to MCP server and list tools"""
        config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
        if not config:
            return {"status": "error", "message": "MCP config not found"}
            
        connection_config = config.to_connection_dict()
        ssl_verify = config.ssl_verify if config.ssl_verify is not None else True
        return await MCPConfigService.test_connection_with_config(connection_config, ssl_verify=ssl_verify)

    @staticmethod
    async def test_connection_with_config(connection_config: dict, ssl_verify: bool = True) -> dict:
        """Test connection to MCP server with provided config.

        We perform a few extra sanity checks up front so that users see a clear
        error message instead of a wrapped exception from the underlying
        `MultiServerMCPClient`.  The library tends to raise generic exceptions
        (often during the "register action" step) which end up buried inside
        ``str(e)``; callers would only see "Error testing MCP connection" in the
        UI.  That's exactly what the user reported in the bug – the real
        problem (e.g. missing url, malformed server entry, authentication
        failure) was being wrapped and lost.  The changes below add:

        * explicit validation of the connection dict structure
        * early feedback when required fields (url/playwright command) are
          missing
        * specialized handling of common httpx/network errors
        * unwrapping of ``__cause__``/``__context__`` chains so the underlying
          message is included
        * pattern matching for "register"/"action" phrases so we can add a
          hint about tool registration problems
        """
        # Basic sanity checks before even instantiating the client
        if not connection_config:
            return {
                "status": "error",
                "message": "Configuration must contain at least one MCP server entry"
            }

        if not isinstance(connection_config, dict):
            return {"status": "error", "message": "MCP configuration must be a JSON object"}

        # each server entry should itself be a dict with either a url or a
        # playwright command; try to catch the most common misconfigurations
        for name, cfg in connection_config.items():
            if not isinstance(cfg, dict):
                return {
                    "status": "error",
                    "message": f"MCP server '{name}' configuration must be an object/dictionary"
                }
            if 'url' not in cfg and 'playwright' not in cfg and 'command' not in cfg:
                return {
                    "status": "error",
                    "message": (
                        f"MCP server '{name}' missing required 'url' or 'playwright' command"
                    )
                }

        # Inject SSL configuration once we've validated the structure
        connection_config = inject_ssl_config(connection_config, ssl_verify=ssl_verify)

        client = None
        try:
            # instantiating the client may itself raise if the config is
            # syntactically invalid; capture those messages explicitly
            try:
                client = MultiServerMCPClient(connections=connection_config)
            except Exception as e:
                base_msg = str(e)
                return {"status": "error", "message": f"Invalid MCP configuration: {base_msg}"}

            # Get tools with timeout
            try:
                tools = await asyncio.wait_for(client.get_tools(), timeout=30.0)
            except asyncio.TimeoutError:
                return {
                    "status": "error",
                    "message": "Connection timeout: MCP server did not respond within 30 seconds"
                }

            # Format tools for display
            tool_list = []
            for tool in tools:
                args_schema = {}
                if tool.args_schema:
                    if hasattr(tool.args_schema, 'schema'):
                        args_schema = tool.args_schema.schema()
                    elif isinstance(tool.args_schema, dict):
                        args_schema = tool.args_schema
                    else:
                        args_schema = str(tool.args_schema)

                tool_list.append({
                    "name": tool.name,
                    "description": tool.description,
                    "args": args_schema
                })

            return {
                "status": "success",
                "message": f"Successfully connected. Found {len(tools)} tools.",
                "tools": tool_list
            }
        except Exception as e:
            import traceback

            def _flatten_exceptions(exc) -> list:
                """Recursively collect leaf exceptions from ExceptionGroup trees."""
                if isinstance(exc, BaseExceptionGroup):
                    leaves = []
                    for sub in exc.exceptions:
                        leaves.extend(_flatten_exceptions(sub))
                    return leaves
                return [exc]

            def _friendly_message(exc) -> str:
                """Return a human-readable message for a single exception."""
                # McpError "Session terminated" is raised by the MCP library when
                # the server returns HTTP 404 for the MCP endpoint.  The library
                # swallows the HTTP status and raises this synthetic error instead,
                # so we must pattern-match on the message text.
                try:
                    from mcp.shared.exceptions import McpError as _McpError
                    if isinstance(exc, _McpError):
                        msg = str(exc).lower()
                        if "session terminated" in msg:
                            return (
                                "MCP session terminated immediately after connecting. "
                                "The server returned HTTP 404 — the MCP endpoint URL "
                                "is likely wrong. Check the URL in your config "
                                "(e.g. it should end with /mcp, /sse or similar "
                                "depending on the transport type)."
                            )
                        return f"MCP protocol error: {exc}"
                except ImportError:
                    pass

                if httpx is not None:
                    if isinstance(exc, httpx.HTTPStatusError):
                        code = exc.response.status_code
                        hints = {
                            401: "Authentication required — check the API key or token in your MCP config headers.",
                            403: "Access forbidden — the API key/token does not have permission.",
                            404: "MCP endpoint not found — verify the URL in your config.",
                            503: "MCP server unavailable — it may be down or overloaded.",
                        }
                        hint = hints.get(code, "")
                        return (
                            f"MCP server returned HTTP {code} for {exc.request.url}"
                            + (f": {hint}" if hint else "")
                        )
                    if isinstance(exc, httpx.ConnectError):
                        return f"Unable to reach MCP server ({exc}). Check that the URL is correct and the server is running."
                    if isinstance(exc, httpx.TimeoutException):
                        return "Connection timed out reaching the MCP server."
                return str(exc)

            leaves = _flatten_exceptions(e)
            if leaves and leaves != [e]:
                # ExceptionGroup was unwrapped — build a clear summary
                messages = [_friendly_message(leaf) for leaf in leaves]
                if len(messages) == 1:
                    err_msg = messages[0]
                else:
                    err_msg = "; ".join(f"[{i+1}] {m}" for i, m in enumerate(messages))
            else:
                err_msg = _friendly_message(e)

            # Additional pattern hints
            if 'register' in err_msg.lower() and 'action' in err_msg.lower():
                err_msg += " — Check that the MCP server is returning valid action schemas."

            error_details = traceback.format_exc()
            logger.error(f"Error testing MCP connection: {err_msg}")
            logger.error(f"Full traceback: {error_details}")
            return {
                "status": "error",
                "message": err_msg,
                "details": error_details if logger.level <= 10 else None
            }
        finally:
            # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient doesn't need manual cleanup
            # The client is managed internally by the library
            pass