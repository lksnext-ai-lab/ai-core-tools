from langchain.messages import HumanMessage, SystemMessage, AnyMessage
from langchain.agents import create_agent as create_langchain_agent, AgentState
from langchain.agents.middleware import SummarizationMiddleware
from utils.schema_utils import sanitize_identifier, ensure_json_schema_types
from models.agent import Agent
from models.silo import Silo
from langchain.tools import BaseTool, tool
from tools.outputParserTools import get_parser_model_by_id
from tools.aiServiceTools import get_llm, get_output_parser
from tools.ai.fileTools import fetch_file_in_base64
from tools.ai.workspaceTools import create_download_url_tool
from typing import Any, Optional, Dict, List, Tuple
import types as _types
from services.silo_service import SiloService
from db.database import SessionLocal
from langchain_mcp_adapters.client import MultiServerMCPClient
from services.agent_cache_service import CheckpointerCacheService
from langchain_core.documents import Document
from langchain_core.tools import StructuredTool
import json
import asyncio
import os
import base64
import mimetypes
from datetime import datetime
from utils.logger import get_logger
from utils.mcp_auth_utils import prepare_mcp_headers, get_user_token_from_context
from utils.mcp_ssl_utils import inject_ssl_config
from tools.skill_tools import create_skill_loader_tool, generate_skills_system_prompt_section
from tools.python_sandbox_tools import create_python_repl_tool

logger = get_logger(__name__)

class MCPClientManager:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClientManager, cls).__new__(cls)
        return cls._instance

    async def get_client(self, agent: Agent = None, user_context: Optional[Dict] = None):
        """Get or create an MCP client for the given agent with authentication support.
        
        Args:
            agent: The agent to create the client for
            user_context: Optional user context containing authentication tokens
            
        Returns:
            MultiServerMCPClient or None
        """
        # Always create a new client for each agent execution to avoid ClosedResourceError
        # Don't use singleton pattern as the client lifecycle is tied to the agent execution
        if agent is not None:
            connections = {}
            for mcp_assoc in agent.mcp_associations:
                mcp_config = mcp_assoc.mcp
                try:
                    # Get the config from the database
                    connection_config = mcp_config.to_connection_dict()
                    if connection_config:
                        # Add authentication headers if user context is provided
                        if user_context:
                            auth_token = get_user_token_from_context(user_context)
                            if auth_token:
                                # Prepare headers for MCP server authentication
                                headers = prepare_mcp_headers(auth_token)
                                
                                # Add headers to each connection in the config
                                for server_name, server_config in connection_config.items():
                                    if isinstance(server_config, dict):
                                        # If it's an SSE connection with a URL
                                        if 'url' in server_config:
                                            if 'headers' not in server_config:
                                                server_config['headers'] = {}
                                            server_config['headers'].update(headers)
                                            logger.info(f"Added auth headers to MCP server: {server_name}")
                        
                        connections.update(connection_config)
                except ValueError as e:
                    logger.error(f"Error configuring MCP {mcp_config.name}: {e}")
                    continue
                
            if connections:
                # Inject SSL configuration for connections that need it
                # Check each MCP config's ssl_verify setting
                for mcp_assoc in agent.mcp_associations:
                    mcp_cfg = mcp_assoc.mcp
                    ssl_verify = mcp_cfg.ssl_verify if mcp_cfg.ssl_verify is not None else True
                    if not ssl_verify:
                        cfg_dict = mcp_cfg.to_connection_dict()
                        for server_name in cfg_dict:
                            if server_name in connections:
                                inject_ssl_config({server_name: connections[server_name]}, ssl_verify=False)
                
                logger.info(f"Creating new MCP client with connections: {connections}")
                # Create a new client each time - don't reuse the singleton
                # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient cannot be used as a context manager
                client = MultiServerMCPClient(connections=connections)
                return client
            else:
                logger.warning("No valid MCP configurations found for agent")
                return None
                
        return None

    async def close(self):
        # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient doesn't need manual cleanup
        # The client is managed internally by the library
        if self._client is not None:
            self._client = None

async def create_agent(agent: Agent, search_params=None, session_id=None, user_context: Optional[Dict] = None, working_dir: Optional[str] = None):
    """Create a new agent instance with cached checkpointer if memory is enabled.
    
    Args:
        agent: The agent to create
        search_params: Optional search parameters for silo-based retrieval
        session_id: Optional session ID for memory-enabled agents (used to cache checkpointer)
        user_context: Optional user context containing authentication tokens for MCP
    """
    llm = get_llm(agent)
    if llm is None:
        raise ValueError("No LLM found for agent")

    output_parser = get_output_parser(agent)
    format_instructions = ""
    pydantic_model = None

    if agent.output_parser_id is not None:
        try:
            pydantic_model = get_parser_model_by_id(agent.output_parser_id)
            format_instructions = output_parser.get_format_instructions()
            format_instructions = format_instructions.replace('{', '{{').replace('}', '}}')
        except Exception as e:
            logger.error(f"Error getting Pydantic model: {str(e)}")
            pydantic_model = None

    # Handle checkpointer management for memory-enabled agents
    checkpointer = None
    if agent.has_memory:
        # Use the session_id if provided, otherwise use "default"
        cache_session_id = session_id if session_id else "default"
        # Create the async PostgreSQL checkpointer in the current event loop
        # This ensures the checkpointer uses the same event loop as ainvoke()
        checkpointer = await CheckpointerCacheService.get_async_checkpointer()
        logger.info(f"Using async PostgreSQL checkpointer for agent {agent.agent_id} (session: {cache_session_id})")

    # Build system prompt with optional skills section and format instructions
    # In LangChain v1, system_prompt is a static string passed to create_agent
    system_prompt_content = agent.system_prompt
    # Inject current date to avoid need for a tool call
    current_date = datetime.now().strftime("%Y-%m-%d")
    system_prompt_content += f"\n\nToday's date is {current_date}."
    if hasattr(agent, 'skill_associations') and agent.skill_associations:
        skills_section = generate_skills_system_prompt_section(agent.skill_associations)
        if skills_section:
            system_prompt_content = system_prompt_content + "\n" + skills_section

    if working_dir:
        system_prompt_content = (
            system_prompt_content
            + "\n\n<workspace>\n"
            + f"Working directory: {working_dir}\n"
            + "User-uploaded files are in this directory — reference them by filename only.\n"
            + "Use `download_url_to_workspace` to save any URL (generated image, PDF, report…) "
            + "to this directory so the user can download it from the files panel.\n"
            + "</workspace>"
        )

    if agent.enable_code_interpreter and working_dir:
        system_prompt_content = (
            system_prompt_content
            + "\n\n<code_interpreter>\n"
            + "You have access to a `python_repl` tool that executes Python code.\n"
            + "Reference uploaded files by filename only (e.g. 'report.xlsx').\n"
            + "Save output files to the working directory and print the filename so the user can download it.\n"
            + "Available libraries: pandas, openpyxl, numpy, os, json, csv, re, datetime.\n"
            + "</code_interpreter>"
        )

    if format_instructions:
        system_prompt_content = (
            system_prompt_content
            + "\n<output_format_instructions>"
            + format_instructions
            + "</output_format_instructions>"
        )

    middleware = []
    if agent.has_memory:
        max_tokens = agent.memory_max_tokens or 4000
        max_messages = agent.memory_max_messages or 20
        from models.agent import DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
        trim_tokens = agent.memory_summarize_threshold or DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
        summarization = SummarizationMiddleware(
            model=llm,
            trigger=("tokens", max_tokens),
            keep=("messages", max_messages),
            trim_tokens_to_summarize=trim_tokens,
        )
        middleware.append(summarization)
        logger.info(
            f"SummarizationMiddleware configured for agent {agent.agent_id}: "
            f"trigger=('tokens', {max_tokens}), keep=('messages', {max_messages}), "
            f"trim_tokens_to_summarize={trim_tokens}"
        )

    tools = []

    # Provider-side tools — injected from agent.server_tools using provider-specific formats
    _SERVER_TOOL_FORMATS = {
        "OpenAI":     {"web_search": {"type": "web_search"}, "image_generation": {"type": "image_generation"}, "code_interpreter": {"type": "code_interpreter"}, "file_search": {"type": "file_search"}},
        "Azure":      {"web_search": {"type": "web_search"}, "image_generation": {"type": "image_generation"}, "code_interpreter": {"type": "code_interpreter"}, "file_search": {"type": "file_search"}},
        "Anthropic":  {"web_search": {"type": "web_search_20250305"}, "code_interpreter": {"type": "codeExecution_20250825"}},
        "Google":     {"web_search": {"type": "google_search"}, "code_interpreter": {"type": "code_execution"}},
        "MistralAI":  {},
        "Custom":     {},
    }
    provider_name = agent.ai_service.provider if agent.ai_service else None
    provider_map = _SERVER_TOOL_FORMATS.get(provider_name, {})
    for tool_name in (getattr(agent, 'server_tools', None) or []):
        tool_def = provider_map.get(tool_name)
        if tool_def:
            tools.append(tool_def)
            logger.info("Server-side tool '%s' injected for provider %s", tool_name, provider_name)
        else:
            logger.warning("Server-side tool '%s' not supported by provider %s — skipped", tool_name, provider_name)

    for tool in agent.tool_associations:
        sub_agent = tool.tool
        tools.append(await IACTTool.create(sub_agent, user_context=user_context))

    # Base tools — always available for every agent
    if working_dir:
        tools.append(create_download_url_tool(working_dir))

    if agent.silo_id is not None:
        # Resolve precedence (caller > agent RAG config > system) AND build the tool
        # off the event loop: both precedence resolution (lazy-loads
        # silo.metadata_definition) and construction (distinct-value sampling) do
        # synchronous DB work.
        retriever_tool = await asyncio.to_thread(
            _resolve_and_build_retriever_tool, agent, search_params
        )
        if retriever_tool is not None:
            tools.append(retriever_tool)

    if agent.enable_code_interpreter and working_dir:
        os.makedirs(working_dir, exist_ok=True)
        python_tool = create_python_repl_tool(working_dir=working_dir)
        tools.append(python_tool)
        logger.info(f"Python REPL tool added for agent {agent.agent_id} (working_dir={working_dir})")

    mcp_client = None
    try:
        logger.info("Starting MCP tools loading...")
        mcp_client = await MCPClientManager().get_client(agent, user_context)
        if (mcp_client):
            mcp_tools = await mcp_client.get_tools()
            logger.info(f"MCP tools loaded successfully: {len(mcp_tools)} tools")
            for tool in mcp_tools:
                if hasattr(tool, "args_schema") and isinstance(tool.args_schema, dict):
                    ensure_json_schema_types(tool.args_schema)
            if (mcp_tools):
                tools.extend(mcp_tools)
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}", exc_info=True)
        # As of langchain-mcp-adapters 0.1.0, no manual cleanup needed
        mcp_client = None

    # Add skill loader tool if agent has skills
    if hasattr(agent, 'skill_associations') and agent.skill_associations:
        skill_tool = create_skill_loader_tool(agent.skill_associations)
        if skill_tool:
            tools.append(skill_tool)
            logger.info(f"Skill loader tool added with {len(agent.skill_associations)} skills")

    if pydantic_model:
        # In LangChain v1, response_format accepts the pydantic model directly.
        # It defaults to ProviderStrategy (native structured output) if supported,
        # falling back to ToolStrategy (artificial tool calling) otherwise.
        agent_chain = create_langchain_agent(
            model=llm,
            system_prompt=system_prompt_content,
            response_format=pydantic_model,
            tools=tools,
            checkpointer=checkpointer,
            middleware=middleware or [],
        )
    else:
        agent_chain = create_langchain_agent(
            model=llm,
            system_prompt=system_prompt_content,
            tools=tools,
            checkpointer=checkpointer,
            middleware=middleware or [],
        )

    # Add logging for the created agent
    logger.info(f"Created agent with {len(tools)} tools")
    logger.info(f"Memory enabled: {agent.has_memory}")
    logger.info(f"Output parser: {agent.output_parser_id is not None}")

    return agent_chain, mcp_client


_DEFAULT_RECURSION_LIMIT = 50


def _load_recursion_limit() -> int:
    """Read AICT_AGENT_RECURSION_LIMIT from the environment once at module load.

    Logs a WARNING and falls back to 50 when the value is absent, non-integer, or
    below 1 (LangGraph requires recursion_limit >= 1; a value < 1 fails every turn).
    """
    raw = os.getenv("AICT_AGENT_RECURSION_LIMIT")
    if raw is None:
        return _DEFAULT_RECURSION_LIMIT
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "prepare_agent_config: AICT_AGENT_RECURSION_LIMIT=%r is not a valid integer; "
            "using default %d",
            raw, _DEFAULT_RECURSION_LIMIT,
        )
        return _DEFAULT_RECURSION_LIMIT
    if value < 1:
        logger.warning(
            "prepare_agent_config: AICT_AGENT_RECURSION_LIMIT=%r is < 1 (invalid); "
            "using default %d",
            raw, _DEFAULT_RECURSION_LIMIT,
        )
        return _DEFAULT_RECURSION_LIMIT
    return value


AICT_AGENT_RECURSION_LIMIT: int = _load_recursion_limit()


def _resolve_and_build_retriever_tool(agent, caller_search_params):
    """Resolve RAG precedence then build the dynamic retriever tool for *agent*.

    Runs synchronous DB work — precedence resolution lazy-loads
    ``silo.metadata_definition`` and ``get_retriever_tool`` samples distinct values.
    MUST be invoked via ``asyncio.to_thread`` so it never blocks the event loop.
    """
    from services.silo_service import resolve_search_params  # noqa: PLC0415 — avoids import cycle

    resolved_sp, resolved_pinned = resolve_search_params(agent, caller_search_params)
    return get_retriever_tool(
        agent.silo,
        resolved_sp,
        getattr(agent, "rag_max_retrieval_calls", None),
        resolved_pinned,
    )


def prepare_agent_config(agent):
    """Helper function to prepare agent configuration."""
    config = {
        "configurable": {
            "thread_id": f"thread_{agent.agent_id}"
        },
        "recursion_limit": AICT_AGENT_RECURSION_LIMIT,
    }
    return config


def parse_agent_response(response_text, agent):
    """Helper function to parse agent response.
    
    In LangChain v1, structured output is returned in the 'structured_response' key
    of the agent result when response_format is used with create_agent.
    """
    if agent.output_parser_id is not None:
        # If response is already a dict (from structured output), return it directly
        if isinstance(response_text, dict):
            return response_text
        
        # If response is a Pydantic model instance, convert to dict
        if hasattr(response_text, 'model_dump'):
            return response_text.model_dump()
        
        # If response is a string, try to parse it as JSON
        content = response_text.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return response_text
    return response_text


def build_human_message(
    agent: Agent,
    message: str,
    image_files: List[Dict],
    user_context: Optional[Dict] = None,
) -> HumanMessage:
    """Build the HumanMessage that will be fed into the agent chain.

    When ``image_files`` is non-empty the content becomes a multimodal list of
    text + image_url blocks.  Images are served via a signed URL when
    ``AICT_BASE_URL`` is set (production), or inlined as base64 data URIs in
    development mode.

    Args:
        agent: The (freshly loaded) Agent ORM instance.
        message: The already-enhanced text message (with file content appended
            if applicable).
        image_files: List of image-file dicts (``file_path`` key required).
        user_context: Caller context dict used to generate signed URLs.

    Returns:
        A ``HumanMessage`` instance ready for ``agent_chain.ainvoke()`` /
        ``agent_chain.astream()``.
    """
    from utils.config import get_app_config

    formatted_message = agent.prompt_template.format(question=message)

    if not image_files:
        return HumanMessage(content=formatted_message)

    app_config = get_app_config()
    tmp_base_folder = app_config["TMP_BASE_FOLDER"]
    aict_base_url = os.getenv("AICT_BASE_URL")

    content: List[Dict] = [{"type": "text", "text": formatted_message}]

    for img in image_files:
        file_path: str = img.get("file_path", "")
        if not file_path:
            logger.warning("Image file has no file_path — skipping: %s", img)
            continue

        # Normalise to forward slashes and strip leading slash
        file_path = file_path.replace("\\", "/").lstrip("/")

        if aict_base_url:
            # Production mode — generate a signed static URL
            aict_base_url = aict_base_url.rstrip("/")
            user_email: Optional[str] = (
                user_context.get("email") if user_context else None
            )
            if user_email:
                from utils.security import generate_signature

                sig = generate_signature(file_path, user_email)
                url = (
                    f"{aict_base_url}/static/{file_path}"
                    f"?user={user_email}&sig={sig}"
                )
            else:
                url = f"{aict_base_url}/static/{file_path}"

            logger.info("Adding image to message using signed URL: %s", url)
            content.append({"type": "image_url", "image_url": {"url": url}})
        else:
            # Development mode — inline as base64 data URI
            full_path = os.path.join(tmp_base_folder, file_path)
            if os.path.exists(full_path):
                try:
                    mime_type, _ = mimetypes.guess_type(full_path)
                    if not mime_type:
                        mime_type = "image/jpeg"
                    with open(full_path, "rb") as fh:
                        encoded = base64.b64encode(fh.read()).decode("utf-8")
                    data_url = f"data:{mime_type};base64,{encoded}"
                    logger.info(
                        "Adding image as base64 (length: %d)", len(encoded)
                    )
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                except Exception as exc:
                    logger.error(
                        "Error encoding image as base64: %s — falling back to URL",
                        exc,
                    )
                    url = f"http://localhost:8000/static/{file_path}"
                    content.append(
                        {"type": "image_url", "image_url": {"url": url}}
                    )
            else:
                url = f"http://localhost:8000/static/{file_path}"
                logger.warning(
                    "Image not found at %s — falling back to URL: %s",
                    full_path,
                    url,
                )
                content.append(
                    {"type": "image_url", "image_url": {"url": url}}
                )

    return HumanMessage(content=content)


class IACTTool(BaseTool):
    name: str = "agent_tool"
    description: str = "Search for a repository"
    agent: Agent
    user_context: Optional[Dict] = None
    react_agent: Any = None
    mcp_client: Any = None
    llm: Any = None

    def __init__(self, agent: Agent, user_context: Optional[Dict] = None) -> None:
        super().__init__(agent=agent, user_context=user_context)

        self.agent = agent
        self.user_context = user_context
        self.name = sanitize_identifier(agent.name)
        self.description = agent.description or "Agent tool"
        self.llm = get_llm(agent)
        if self.llm is None:
            raise ValueError("No LLM found for agent")
        self.react_agent = None
        self.mcp_client = None

    @classmethod
    async def create(cls, agent: Agent, user_context: Optional[Dict] = None) -> "IACTTool":
        """Build an agent-as-tool, including the sub-agent's MCP tools.

        MCP tools are loaded with an awaited MultiServerMCPClient, which is not
        possible inside a synchronous ``__init__``; hence this async factory. It
        is the only supported way to obtain a ready-to-use ``IACTTool``.
        """
        instance = cls(agent, user_context=user_context)

        tools = []
        # Add nested tool agents recursively
        for tool in agent.tool_associations:
            sub_agent = tool.tool
            tools.append(await IACTTool.create(sub_agent, user_context=user_context))

        # Add base useful tools
        tools.append(fetch_file_in_base64)

        # Add silo retriever if configured. The sub-agent uses the same dynamic
        # metadata-aware tool as the root agent, driven by its OWN RAG config
        # (rag_k / rag_search_type / rag_score_threshold / rag_fixed_filters /
        # rag_max_retrieval_calls). Caller search params are NOT propagated from the
        # root agent (caller_search_params=None) — sub-agents are self-contained (FR-12).
        if agent.silo_id is not None:
            # Caller params NOT propagated (None) — the sub-agent uses its OWN config.
            # Off the event loop: resolution + construction do synchronous DB work.
            retriever_tool = await asyncio.to_thread(
                _resolve_and_build_retriever_tool, agent, None
            )
            if retriever_tool is not None:
                tools.append(retriever_tool)

        # Add MCP tools — mirrors create_agent. A failing MCP server degrades the
        # sub-agent but never breaks its construction.
        try:
            logger.info(f"Starting MCP tools loading for sub-agent {agent.agent_id}...")
            instance.mcp_client = await MCPClientManager().get_client(agent, user_context)
            if instance.mcp_client:
                mcp_tools = await instance.mcp_client.get_tools()
                logger.info(
                    f"MCP tools loaded successfully for sub-agent {agent.agent_id}: "
                    f"{len(mcp_tools)} tools"
                )
                if mcp_tools:
                    tools.extend(mcp_tools)
        except Exception as e:
            logger.error(
                f"Error loading MCP tools for sub-agent {agent.agent_id}: {e}",
                exc_info=True,
            )
            instance.mcp_client = None

        # Build system prompt with optional skills section (LangChain v1 pattern)
        tool_system_prompt = agent.system_prompt or ""
        # Inject current date to avoid need for a tool call
        current_date = datetime.now().strftime("%Y-%m-%d")
        tool_system_prompt += f"\n\nToday's date is {current_date}."
        if agent.system_prompt and hasattr(agent, 'skill_associations') and agent.skill_associations:
            skills_section = generate_skills_system_prompt_section(agent.skill_associations)
            if skills_section:
                tool_system_prompt = tool_system_prompt + "\n" + skills_section

        # Create sub-agent
        instance.react_agent = create_langchain_agent(
            model=instance.llm,
            tools=tools,
            system_prompt=tool_system_prompt if tool_system_prompt else None,
        )
        return instance

    def _run(self, query: str, *args, **kwargs) -> str:
        """Synchronous execution of the agent tool"""
        if self.react_agent is None:
            raise RuntimeError(
                "IACTTool must be built via 'await IACTTool.create(...)' before use."
            )
        try:
            # Format the message using prompt_template if available, otherwise use query directly
            if self.agent.prompt_template:
                try:
                    formatted_prompt = self.agent.prompt_template.format(question=query)
                except KeyError:
                    # If 'question' is not in template, try other common placeholders
                    try:
                        formatted_prompt = self.agent.prompt_template.format(query=query)
                    except KeyError:
                        # If no placeholder works, just use the query
                        logger.warning(f"Could not format prompt_template for agent {self.agent.name}, using query directly")
                        formatted_prompt = query
            else:
                formatted_prompt = query
            
            messages = [HumanMessage(content=formatted_prompt)]
            result = self.react_agent.invoke({"messages": messages})
            
            # Extract the content from the last AI message
            if isinstance(result, dict) and "messages" in result:
                messages_list = result["messages"]
                # Find the last AI message with content
                for msg in reversed(messages_list):
                    if hasattr(msg, 'content') and msg.content:
                        return str(msg.content)
                # Fallback: return the last message content
                if messages_list:
                    last_msg = messages_list[-1]
                    return str(last_msg.content) if hasattr(last_msg, 'content') else str(last_msg)
            
            # If result is a string, return it directly
            return str(result)
            
        except Exception as e:
            logger.error(f"Error executing agent tool {self.name}: {str(e)}")
            return f"Error executing agent tool: {str(e)}"
    
    async def _arun(self, query: str, *args, **kwargs) -> str:
        """Asynchronous execution of the agent tool"""
        if self.react_agent is None:
            raise RuntimeError(
                "IACTTool must be built via 'await IACTTool.create(...)' before use."
            )
        try:
            # Format the message using prompt_template if available, otherwise use query directly
            if self.agent.prompt_template:
                try:
                    formatted_prompt = self.agent.prompt_template.format(question=query)
                except KeyError:
                    # If 'question' is not in template, try other common placeholders
                    try:
                        formatted_prompt = self.agent.prompt_template.format(query=query)
                    except KeyError:
                        # If no placeholder works, just use the query
                        logger.warning(f"Could not format prompt_template for agent {self.agent.name}, using query directly")
                        formatted_prompt = query
            else:
                formatted_prompt = query
            
            messages = [HumanMessage(content=formatted_prompt)]
            result = await self.react_agent.ainvoke({"messages": messages})
            
            # Extract the content from the last AI message
            if isinstance(result, dict) and "messages" in result:
                messages_list = result["messages"]
                # Find the last AI message with content
                for msg in reversed(messages_list):
                    if hasattr(msg, 'content') and msg.content:
                        return str(msg.content)
                # Fallback: return the last message content
                if messages_list:
                    last_msg = messages_list[-1]
                    return str(last_msg.content) if hasattr(last_msg, 'content') else str(last_msg)
            
            # If result is a string, return it directly
            return str(result)
            
        except Exception as e:
            logger.error(f"Error executing agent tool {self.name} (async): {str(e)}")
            return f"Error executing agent tool: {str(e)}"

_SEARCH_ERROR_MSG = "The knowledge base search failed; try rephrasing or removing filters."


def _format_docs_with_metadata(docs: List[Document]) -> str:
    """Serialize retrieved documents as a text block with metadata for the LLM."""
    parts: List[str] = []
    for doc in docs:
        metadata_str = json.dumps(doc.metadata, ensure_ascii=False) if doc.metadata else "{}"
        parts.append(f"Content: {doc.page_content}\nMetadata: {metadata_str}")
    return "\n\n---\n\n".join(parts)


def _capture_silo_data(silo: Silo) -> dict:
    """Extract all silo ORM data needed by the retrieval coroutine into plain values.

    After this call the coroutine never accesses the ORM object or its lazy
    relationships, avoiding DetachedInstanceError.
    """
    metadata_definition = getattr(silo, "metadata_definition", None)
    captured_fields_list: List[dict] = []
    if metadata_definition is not None:
        for fspec in (metadata_definition.fields or []):
            if isinstance(fspec, dict) and fspec.get("name"):
                captured_fields_list.append(dict(fspec))

    return {
        "silo_id": silo.silo_id,
        "vector_db_type": getattr(silo, "vector_db_type", None) or "PGVECTOR",
        "captured_fields_list": captured_fields_list,
        "captured_metadata_def": (
            _types.SimpleNamespace(fields=captured_fields_list)
            if captured_fields_list
            else None
        ),
        "metadata_field_types": {
            f["name"]: f.get("type", "str") for f in captured_fields_list
        },
    }


def _build_pinned_filter(
    raw_caller_filter: dict,
    captured_metadata_def: Any,
    vector_db_type: str,
) -> dict:
    """Convert the caller's flat {field: value} filter to a backend filter dict.

    Skips the field whitelist (validate_clauses) so undeclared fields pass through —
    pinned filters come from trusted caller code, not the LLM. Type coercion is applied
    using declared field types; undeclared fields are treated as str.
    """
    from tools.vector_stores.metadata_filters import (
        MetadataFilterClause,
        convert_clause_types,
        to_backend_filter,
    )

    clauses: List[MetadataFilterClause] = []
    for field, value in raw_caller_filter.items():
        try:
            clauses.append(MetadataFilterClause(field=field, op="$eq", value=value))
        except Exception:
            logger.warning(
                "get_retriever_tool: could not build pinned clause for field '%s' — skipped",
                field,
            )

    if not clauses:
        return {}

    typed = convert_clause_types(clauses, captured_metadata_def)
    return to_backend_filter(typed)


def _build_llm_filter(
    metadata_kwargs: dict,
    metadata_field_types: dict,
    captured_metadata_def: Any,
    vector_db_type: str,
    tool_name: str,
) -> dict:
    """Build a backend filter dict from LLM-inferred kwargs.

    Applies the strict field whitelist (only declared fields pass) — LLM input
    is untrusted.
    """
    from tools.vector_stores.metadata_filters import MetadataFilterClause, build_filter_dict

    llm_clauses: List[MetadataFilterClause] = []
    for field, value in metadata_kwargs.items():
        if value is None:
            continue
        if field not in metadata_field_types:
            logger.warning(
                "get_retriever_tool[%s]: field '%s' not in metadata_definition — skipped (AC-5)",
                tool_name,
                field,
            )
            continue
        try:
            llm_clauses.append(MetadataFilterClause(field=field, op="$eq", value=value))
        except Exception:
            logger.warning(
                "get_retriever_tool[%s]: could not build LLM clause for field '%s' — skipped",
                tool_name,
                field,
            )

    if not llm_clauses:
        return {}
    return build_filter_dict(llm_clauses, captured_metadata_def, vector_db_type)


async def _run_retrieval(
    silo_id: int,
    call_search_params: Optional[dict],
    query: str,
) -> List[Document]:
    """Invoke SiloService.get_silo_retriever off the event loop, then run ainvoke."""
    retriever = await asyncio.to_thread(
        SiloService.get_silo_retriever, silo_id, call_search_params
    )
    return await retriever.ainvoke(query)


async def _build_fallback_notice(
    silo_id: int,
    llm_filter_fields: List[str],
    distinct_values: dict,
    tool_name: str,
) -> str:
    """Build the [notice] string for AC-8 fallback, fetching missing values via thread."""
    from tools.vector_stores.metadata_filters import sanitize_metadata_value, MAX_EXAMPLE_VALUES
    from services.metadata_values_cache_service import MetadataValuesCacheService

    def _fetch(f: str) -> List[str]:
        with SessionLocal() as s:
            return MetadataValuesCacheService.get_distinct_values(
                silo_id=silo_id, field=f, db=s
            )

    notice_parts: List[str] = []
    for field in llm_filter_fields:
        cached_vals = distinct_values.get(field, [])
        if not cached_vals:
            try:
                cached_vals = await asyncio.to_thread(_fetch, field)
            except Exception:
                logger.warning(
                    "get_retriever_tool[%s]: could not fetch distinct values for field '%s'",
                    tool_name,
                    field,
                )
                cached_vals = []

        sanitized = [
            sanitize_metadata_value(str(v))
            for v in cached_vals
            if v is not None
        ]
        sanitized = [v for v in sanitized if v][:MAX_EXAMPLE_VALUES]
        if sanitized:
            notice_parts.append(f"{field}: {', '.join(sanitized)}")

    notice = (
        f"[notice] No results with the inferred filter {llm_filter_fields}; "
        f"retried without it."
    )
    if notice_parts:
        notice += " Existing values — " + "; ".join(notice_parts) + "."
    return notice


def get_retriever_tool(
    silo: Silo,
    search_params: Optional[dict] = None,
    max_retrieval_calls: Optional[int] = None,
    pinned_filter: Optional[dict] = None,
) -> Optional[StructuredTool]:
    """Build the dynamic retrieval tool for *silo*.

    All silo ORM state is captured in plain variables at construction time.
    The coroutine never accesses the ORM object directly, avoiding DetachedInstanceError.

    Args:
        silo: Attached Silo ORM instance.
        search_params: Optional caller-level search parameters (tuning only — no
            'filter' key expected when ``pinned_filter`` is provided).
        max_retrieval_calls: Optional ceiling on tool invocations per agent turn.
        pinned_filter: Optional pre-built backend filter dict
            ``{field: {op: value}}``.  When provided it is used directly as the
            pinned filter and ``_build_pinned_filter`` is skipped.  When None the
            existing behaviour is preserved: the ``filter`` key from
            ``search_params`` is translated via ``_build_pinned_filter``.

    Returns:
        A StructuredTool whose coroutine performs metadata-aware retrieval,
        or None when silo.silo_id is falsy.
    """
    if not silo.silo_id:
        return None

    from tools.retriever_tool_builder import (
        build_retriever_args_schema,
        build_retriever_description,
        build_retriever_tool_name,
        collect_distinct_values,
    )
    from tools.vector_stores.metadata_filters import merge_filters_and

    captured = _capture_silo_data(silo)
    silo_id: int = captured["silo_id"]
    vector_db_type: str = captured["vector_db_type"]
    captured_fields_list: List[dict] = captured["captured_fields_list"]
    captured_metadata_def = captured["captured_metadata_def"]
    metadata_field_types: dict[str, str] = captured["metadata_field_types"]

    with SessionLocal() as db_session:
        distinct_values: dict[str, List[str]] = collect_distinct_values(silo, db=db_session)

    effective_search_params: Optional[dict] = search_params

    if pinned_filter is not None:
        # Pre-built filter supplied by resolve_search_params — use directly.
        _pinned_filter: dict[str, Any] = pinned_filter
        if _pinned_filter:
            effective_search_params = {**(search_params or {}), "filter": _pinned_filter}
    else:
        # Legacy path: translate search_params["filter"] flat dict.
        _pinned_filter = {}
        if search_params and search_params.get("filter"):
            _pinned_filter = _build_pinned_filter(
                search_params["filter"], captured_metadata_def, vector_db_type
            )
            if _pinned_filter:
                effective_search_params = {**search_params, "filter": _pinned_filter}

    # Alias for closure capture
    resolved_pinned = _pinned_filter

    tool_name: str = build_retriever_tool_name(silo)
    tool_description: str = build_retriever_description(silo, distinct_values)
    args_schema = build_retriever_args_schema(silo, distinct_values)

    # Not async-safe under parallel tool calls; safe with LangGraph's serialized model.
    _call_count: List[int] = [0]

    async def _search(query: str, **metadata_kwargs: Any) -> Tuple[str, List[Document]]:
        if max_retrieval_calls is not None and _call_count[0] >= max_retrieval_calls:
            logger.info(
                "get_retriever_tool[%s]: retrieval ceiling reached (%d/%d)",
                tool_name, _call_count[0], max_retrieval_calls,
            )
            return (
                "Search limit reached — answer with the information you already have "
                "or state what is missing.",
                [],
            )
        _call_count[0] += 1

        llm_filter = _build_llm_filter(
            metadata_kwargs, metadata_field_types, captured_metadata_def,
            vector_db_type, tool_name,
        )
        merged_filter = merge_filters_and(resolved_pinned, llm_filter)

        if merged_filter:
            base = dict(effective_search_params) if effective_search_params else {}
            call_search_params: Optional[dict] = {**base, "filter": merged_filter}
        else:
            call_search_params = effective_search_params

        applied_fields = list(merged_filter.keys()) if merged_filter else []
        logger.info(
            "get_retriever_tool[%s]: call #%d — applied filter fields=%s",
            tool_name, _call_count[0], applied_fields or "(none)",
        )

        try:
            docs: List[Document] = await _run_retrieval(silo_id, call_search_params, query)
        except Exception as exc:
            logger.error(
                "get_retriever_tool[%s]: vector store error",
                tool_name, exc_info=True,
            )
            return (_SEARCH_ERROR_MSG, [])

        if not docs and llm_filter:
            logger.info(
                "get_retriever_tool[%s]: 0 results with LLM filter — retrying with pinned only (AC-8)",
                tool_name,
            )
            notice = await _build_fallback_notice(
                silo_id, list(llm_filter.keys()), distinct_values, tool_name
            )

            try:
                docs = await _run_retrieval(silo_id, effective_search_params, query)
            except Exception as exc:
                logger.error(
                    "get_retriever_tool[%s]: fallback vector store error",
                    tool_name, exc_info=True,
                )
                return (_SEARCH_ERROR_MSG, [])

            filter_label = f"with filter {resolved_pinned}" if resolved_pinned else "(no metadata filter)"
            content = (
                f"{notice}\n\n"
                f"{len(docs)} results {filter_label}\n\n"
                f"{_format_docs_with_metadata(docs)}"
            )
            logger.info(
                "get_retriever_tool[%s]: fallback retrieved %d docs for silo_id=%d",
                tool_name, len(docs), silo_id,
            )
            return (content, docs)

        filter_label = f"with filter {merged_filter}" if merged_filter else "(no metadata filter)"
        content = (
            f"{len(docs)} results {filter_label}\n\n"
            f"{_format_docs_with_metadata(docs)}"
        )
        logger.info(
            "get_retriever_tool[%s]: retrieved %d docs for silo_id=%d, filter_fields=%s",
            tool_name, len(docs), silo_id, applied_fields or "(none)",
        )
        return (content, docs)

    return StructuredTool.from_function(
        coroutine=_search,
        name=tool_name,
        description=tool_description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )

