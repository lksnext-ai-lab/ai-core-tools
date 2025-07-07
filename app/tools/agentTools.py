from langchain_anthropic import ChatAnthropic
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from model.agent import Agent
from model.silo import Silo
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool
import os
from tools.outputParserTools import get_parser_model_by_id
from tools.aiServiceTools import get_llm, get_output_parser
from typing import Any
from langchain.tools.retriever import create_retriever_tool
from langchain_mcp_adapters.tools import load_mcp_tools
from services.silo_service import SiloService
from model.ai_service import ProviderEnum
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.chat_agent_executor import AgentState
from services.agent_cache_service import CheckpointerCacheService
from langchain.callbacks.tracers import LangChainTracer
from langsmith import Client
import json
from utils.logger import get_logger
import logging

logger = get_logger(__name__)

class MCPClientManager:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClientManager, cls).__new__(cls)
        return cls._instance

    async def get_client(self, agent: Agent = None):
        if self._client is None and agent is not None:
            connections = {}
            for mcp_assoc in agent.mcp_associations:
                mcp_config = mcp_assoc.mcp
                try:
                    # Store the config directly without additional wrapping
                    connection_config = mcp_config.to_connection_dict()
                    if connection_config:
                        connections.update(connection_config)
                except ValueError as e:
                    logger.error(f"Error configuring MCP {mcp_config.name}: {e}")
                    continue
                
            if connections:
                logger.info(f"Creating MCP client with connections: {connections}")
                self._client = MultiServerMCPClient(connections=connections)
                await self._client.__aenter__()
            else:
                logger.warning("No valid MCP configurations found for agent")
                
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

async def create_agent(agent: Agent, search_params=None):
    """Create a new agent instance with cached checkpointer if memory is enabled."""
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
        # Try to get cached checkpointer for this agent and session
        checkpointer = CheckpointerCacheService.get_cached_checkpointer(agent.agent_id)
        
        if checkpointer is None:
            # Create new checkpointer and cache it
            checkpointer = InMemorySaver()
            CheckpointerCacheService.cache_checkpointer(agent.agent_id, checkpointer)
            logger.info("Created and cached new checkpointer for agent")
        else:
            logger.info("Using cached checkpointer for agent")

    def prompt(state: AgentState, config: RunnableConfig) -> list[AnyMessage]:
        # Get the initial question from config
        initial_question = config.get("configurable", {}).get("question", "")
        formatted_human_prompt = agent.prompt_template.format(question=initial_question)
        
        messages = []
        
        # Add system messages only if this is the first message in the conversation
        history = state.get("messages", [])
        messages.extend([
            SystemMessage(content=agent.system_prompt),
            SystemMessage(content="<output_format_instructions>" + format_instructions + "</output_format_instructions>")
        ])
        
        # Add conversation history
        messages.extend(history)
        
        # Only add human message if the last message wasn't a tool message
        from langchain_core.messages import ToolMessage
        if not history or not any(isinstance(msg, ToolMessage) for msg in history[-1:]):
            messages.append(HumanMessage(content=formatted_human_prompt))
        
        return messages

    tools = []
    for tool in agent.tool_associations:
        sub_agent = tool.tool
        tools.append(IACTTool(sub_agent))

    if agent.silo_id is not None:
        retriever_tool = get_retriever_tool(agent.silo, search_params)
        if retriever_tool is not None:
            tools.append(retriever_tool)

    try:
        logger.info("Starting MCP tools loading...")
        mcp_client = await MCPClientManager().get_client(agent)
        if (mcp_client):
            mcp_tools = mcp_client.get_tools()
            logger.info(f"MCP tools loaded successfully: {mcp_tools}")
            if (mcp_tools):
                tools.extend(mcp_tools)
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}", exc_info=True)
    
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

    return agent_chain


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
        self.description = agent.description
        self.llm = get_llm(agent)
        if self.llm is None:
            raise ValueError("No LLM found for agent")
        
        tools = []
        for tool in agent.tool_associations:
            sub_agent = tool.tool
            tools.append(IACTTool(sub_agent))
        state_modifier = SystemMessage(content=agent.system_prompt)

        if agent.silo_id is not None:
            retriever_tool = get_retriever_tool(agent.silo)
            if retriever_tool is not None:
                tools.append(retriever_tool)

        self.react_agent = create_react_agent(
            self.llm, 
            tools, 
            debug=False,  # Set debug to False
            state_modifier=state_modifier
        )

    def _run(self, query: str, *args, **kwargs) -> str:
        formatted_prompt = self.agent.prompt_template.format(question=query)
        messages = [HumanMessage(content=formatted_prompt)]
        return self.react_agent.invoke({"messages": messages})

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
        
        prompt = PromptTemplate.from_template("""Name of the document: {name}\n
        Page number: {page}\n
        Page content: {page_content}
        """)
        return  create_retriever_tool(retriever=retriever, name=name, description=description, document_prompt=prompt)
    return None