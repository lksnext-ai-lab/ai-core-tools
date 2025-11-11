from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from langgraph.prebuilt import create_react_agent
from models.agent import Agent
from models.silo import Silo
from langchain_core.tools import BaseTool, tool
from tools.outputParserTools import get_parser_model_by_id
from tools.aiServiceTools import get_llm, get_output_parser
from typing import Any, Optional, Dict
from langchain.tools.retriever import create_retriever_tool
from services.silo_service import SiloService
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.chat_agent_executor import AgentState
from services.agent_cache_service import CheckpointerCacheService
from services.memory_management_service import MemoryManagementService
from langchain.callbacks.tracers import LangChainTracer
from langsmith import Client
import json
import base64
import asyncio
from datetime import datetime
from utils.logger import get_logger
from utils.mcp_auth_utils import prepare_mcp_headers, get_user_token_from_context

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

async def create_agent(agent: Agent, search_params=None, session_id=None, user_context: Optional[Dict] = None):
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
    
    # Setup tracer for LangSmith if configured
    tracer = setup_tracer(agent)
    
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
    checkpointer_cm = None
    if agent.has_memory:
        # Use the session_id if provided, otherwise use "default"
        cache_session_id = session_id if session_id else "default"
        # Create the async PostgreSQL checkpointer in the current event loop
        # This ensures the checkpointer uses the same event loop as ainvoke()
        checkpointer, checkpointer_cm = await CheckpointerCacheService.get_async_checkpointer()
        logger.info(f"Using async PostgreSQL checkpointer for agent {agent.agent_id} (session: {cache_session_id})")

    def prompt(state: AgentState, config: RunnableConfig) -> list[AnyMessage]:
        """
        Prepare messages for the agent, applying hybrid memory management strategy.
        
        When has_memory=True, automatically applies:
        1. Remove tool messages (reduce noise)
        2. Trim to max_messages
        3. Enforce max_tokens limit if specified
        """
        # Get conversation history
        history = state.get("messages", [])
        
        # Apply hybrid memory management if agent has memory enabled
        if agent.has_memory:
            try:
                history = MemoryManagementService.apply_hybrid_strategy(
                    messages=history,
                    max_messages=agent.memory_max_messages or 20,
                    max_tokens=agent.memory_max_tokens
                )
                
                # Log memory statistics
                stats = MemoryManagementService.get_memory_stats(history)
                logger.info(f"Memory stats for agent {agent.agent_id}: {stats}")
                
            except Exception as e:
                logger.error(f"Error applying memory management: {e}. Using unmodified history.")
        
        # Build final message list
        messages = []
        
        # Add system messages for every turn
        messages.extend([
            SystemMessage(content=agent.system_prompt),
            SystemMessage(content="<output_format_instructions>" + format_instructions + "</output_format_instructions>")
        ])
        
        # Add processed conversation history
        messages.extend(history)
        
        return messages

    tools = []
    for tool in agent.tool_associations:
        sub_agent = tool.tool
        tools.append(IACTTool(sub_agent))

    #add base useful tools
    tools.append(get_current_date)
    tools.append(fetch_file_in_base64)

    if agent.silo_id is not None:
        
        retriever_tool = get_retriever_tool(agent.silo, search_params)
        if retriever_tool is not None:
            tools.append(retriever_tool)

    mcp_client = None
    try:
        logger.info("Starting MCP tools loading...")
        mcp_client = await MCPClientManager().get_client(agent, user_context)
        if (mcp_client):
            mcp_tools = await mcp_client.get_tools()
            logger.info(f"MCP tools loaded successfully: {len(mcp_tools)} tools")
            if (mcp_tools):
                tools.extend(mcp_tools)
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}", exc_info=True)
        # As of langchain-mcp-adapters 0.1.0, no manual cleanup needed
        mcp_client = None
    
    if pydantic_model:
        # Si tenemos un modelo Pydantic, lo usamos como formato de respuesta
        structured_prompt = f"Given the conversation, generate a response following this format: {format_instructions}"
        agent_chain = create_react_agent(
            model=llm,
            prompt=prompt,
            response_format=(structured_prompt, pydantic_model),
            tools=tools, 
            checkpointer=checkpointer,
            debug=True  
        )
    else:
        # Si no hay modelo Pydantic, usamos el agente sin formato estructurado
        agent_chain = create_react_agent(
            model=llm,
            prompt=prompt,
            tools=tools, 
            checkpointer=checkpointer,  
            debug=True
        )

    # Add logging for the created agent
    logger.info(f"Created agent with {len(tools)} tools")
    logger.info(f"Memory enabled: {agent.has_memory}")
    logger.info(f"Output parser: {agent.output_parser_id is not None}")
    logger.info(f"Tracer configured: {tracer is not None}")

    return agent_chain, tracer, mcp_client, checkpointer_cm


def prepare_agent_config(agent, tracer):
    """Helper function to prepare agent configuration."""
    config = {
        "configurable": {
            "thread_id": f"thread_{agent.agent_id}"
        },
        "recursion_limit": 200,
    }
    if tracer is not None:
        config["callbacks"] = [tracer]
    return config


def parse_agent_response(response_text, agent):
    """Helper function to parse agent response."""
    if agent.output_parser_id is not None:
        # If response is already a dict (from JsonOutputParser), return it directly
        if isinstance(response_text, dict):
            return response_text
        
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


def setup_tracer(agent):
    """Setup tracer if configured."""
    tracer = None
    if agent.app.langsmith_api_key:
        client = Client(api_key=agent.app.langsmith_api_key)
        tracer = LangChainTracer(client=client, project_name=agent.app.name)
    return tracer


class IACTTool(BaseTool):
    name: str = "agent_tool"
    description: str = "Search for a repository"
    agent: Agent
    react_agent: Any = None
    llm: Any = None

    def __init__(self, agent: Agent) -> None:
        super().__init__(agent=agent)
        
        self.agent = agent  
        self.name = agent.name.replace(" ", "_")
        self.description = agent.description or "Agent tool"
        self.llm = get_llm(agent)
        if self.llm is None:
            raise ValueError("No LLM found for agent")
        
        tools = []
        # Add nested tool agents recursively
        for tool in agent.tool_associations:
            sub_agent = tool.tool
            tools.append(IACTTool(sub_agent))
        
        # Add base useful tools
        tools.append(get_current_date)
        tools.append(fetch_file_in_base64)
        
        # Add silo retriever if configured
        if agent.silo_id is not None:
            retriever_tool = get_retriever_tool(agent.silo)
            if retriever_tool is not None:
                tools.append(retriever_tool)
        
        # Use system_prompt as state_modifier
        state_modifier = SystemMessage(content=agent.system_prompt) if agent.system_prompt else None

        self.react_agent = create_react_agent(
            self.llm, 
            tools, 
            debug=False,
            state_modifier=state_modifier
        )

    def _run(self, query: str, *args, **kwargs) -> str:
        """Synchronous execution of the agent tool"""
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

def convert_search_params_to_types(search_params: dict, metadata_definition) -> dict:
    """
    Convert search parameters to their proper types based on metadata definition.
    The search_params dictionary should have a 'filter' key containing the metadata filters.
    
    Args:
        search_params: Dictionary containing search parameters with a 'filter' key
        metadata_definition: OutputParser instance containing field definitions
        
    Returns:
        Dictionary with converted parameter values
    """
    if not search_params or not metadata_definition:
        return search_params
        
    # Create a copy of search_params to avoid modifying the original
    converted_params = search_params.copy()
    
    # Only process the 'filter' key if it exists
    if 'filter' in search_params and search_params['filter']:
        field_definitions = {f['name']: f for f in metadata_definition.fields}
        converted_filter = {}
        
        for key, value in search_params['filter'].items():
            if key in field_definitions:
                field_type = field_definitions[key]['type']
                try:
                    if field_type == 'int':
                        converted_filter[key] = int(value)
                    elif field_type == 'float':
                        converted_filter[key] = float(value)
                    elif field_type == 'bool':
                        converted_filter[key] = bool(value)
                    else:
                        converted_filter[key] = value
                except (ValueError, TypeError):
                    # If conversion fails, keep original value
                    converted_filter[key] = value
            else:
                converted_filter[key] = value
                
        converted_params['filter'] = converted_filter
            
    return converted_params

def get_retriever_tool(silo: Silo, search_params=None):
    
    if silo.silo_id is not None:
        # Convert search parameters to proper types based on metadata definition
        if search_params:
            search_params = convert_search_params_to_types(search_params, silo.metadata_definition)

        retriever = SiloService.get_silo_retriever(silo.silo_id, search_params)
        name = "silo_retriever"
        description = "Use this tool to search for documents in the pgvector collection."
        if silo.repository is not None:
            #todo: add description to repository model to compose description
            description = "Use this tool to search for relevant documents in the repository."
        elif silo.domain is not None:
            description = f"Use this tool to search for documents. This tool stores information about a web site and this is its description: {silo.domain.description}"
        else:
            description = f"Use this tool to search for documents in a repository about {silo.description}"

        return  create_retriever_tool(retriever=retriever, name=name, description=description)
    return None

@tool
def get_current_date():
    """This tool is useful to get the current date."""
    return datetime.now().strftime("%Y-%m-%d")

@tool
def fetch_file_in_base64(file_path: str):
    """This tool is useful to get the file in base64 format."""
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")