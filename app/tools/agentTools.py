from langchain_anthropic import ChatAnthropic
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from model.agent import Agent
from model.silo import Silo
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
import os
from typing import Any
from langchain.tools.retriever import create_retriever_tool
from langchain_mcp_adapters.tools import load_mcp_tools
from services.silo_service import SiloService
from model.ai_service import ProviderEnum
from langchain_mcp_adapters.client import MultiServerMCPClient
import logging

logger = logging.getLogger(__name__)

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

async def create_agent(agent: Agent):
    llm = getLLM(agent)
    if llm is None:
        raise ValueError("No LLM found for agent")
    
    tools = []
    for tool in agent.tool_associations:
        sub_agent = tool.tool
        tools.append(IACTTool(sub_agent))

    if agent.silo_id is not None:
        retriever_tool = getRetrieverTool(agent.silo)
        if retriever_tool is not None:
            tools.append(retriever_tool)

    try:
        logger.info("Starting MCP tools loading...")
        mcp_client = await MCPClientManager().get_client(agent)
        if mcp_client:
            mcp_tools = mcp_client.get_tools()
            logger.info(f"MCP tools loaded successfully: {mcp_tools}")
            if mcp_tools:
                tools.extend(mcp_tools)
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}", exc_info=True)
    
    state_modifier = SystemMessage(content=agent.system_prompt)
    return create_react_agent(llm, tools, debug=True, state_modifier=state_modifier)


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
        self.llm = getLLM(agent)
        if self.llm is None:
            raise ValueError("No LLM found for agent")
        
        tools = []
        for tool in agent.tool_associations:
            sub_agent = tool.tool
            tools.append(IACTTool(sub_agent))
        state_modifier = SystemMessage(content=agent.system_prompt)

        if agent.silo_id is not None:
            retriever_tool = getRetrieverTool(agent.silo)
            if retriever_tool is not None:
                tools.append(retriever_tool)

        self.react_agent = create_react_agent(self.llm, tools, debug=True, state_modifier=state_modifier)

    def _run(self, query: str, *args, **kwargs) -> str:
        formatted_prompt = self.agent.prompt_template.format(question=query)
        messages = [HumanMessage(content=formatted_prompt)]
        return self.react_agent.invoke({"messages": messages})
    
def getLLM(agent):
    if agent.ai_service is None:
        return None
    if agent.ai_service.provider == ProviderEnum.OpenAI.value:
        return ChatOpenAI(model=agent.ai_service.name, api_key=os.getenv('OPENAI_API_KEY'))
    if agent.ai_service.provider == ProviderEnum.Anthropic.value:
        return ChatAnthropic(model=agent.ai_service.name, api_key=os.getenv('ANTHROPIC_API_KEY'))
    if agent.ai_service.provider == ProviderEnum.MistralAI.value:
        return ChatMistralAI(model=agent.ai_service.name, api_key=os.getenv('MISTRAL_API_KEY'))
    return None

def getRetrieverTool(silo: Silo):
    if silo.silo_id is not None:
        retriever = SiloService.get_silo_retriever(silo.silo_id)
        name = "silo_retriever"
        description = "Use this tool to search for documents in the pgvector collection."
        if silo.repository is not None:
            #todo: add description to repository model to compose description
            description = "Use this tool to search for relevant documents in the repository."
        elif silo.domain is not None:
            description = f"Use this tool to search for documents. This tool stores information about a web site and this is its description: {silo.domain.description}"
        else:
            description = f"Use this tool to search for documents in a repository about {silo.description}"
        
        return  create_retriever_tool(retriever, name=name, description=description)
    return None