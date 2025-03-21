from langchain_anthropic import ChatAnthropic
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from app.model.agent import Agent
from app.model.silo import Silo
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
import os
from typing import Any
from langchain.tools.retriever import create_retriever_tool
from app.services.silo_service import SiloService
from app.model.ai_service import ProviderEnum
def create_agent(agent: Agent):
    llm = getLLM(agent)
    if llm is None:
        raise ValueError("No LLM found for agent")
    
    tools = []
    for tool in agent.tool_associations:
        subAgnet = tool.tool
        tools.append(IACTTool(subAgnet))

    if agent.silo_id is not None:
        retrieverTool = getRetrieverTool(agent.silo)
        if retrieverTool is not None:
            tools.append(retrieverTool)
    
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
            subAgent = tool.tool
            tools.append(IACTTool(subAgent))
        state_modifier = SystemMessage(content=agent.system_prompt)

        if agent.silo_id is not None:
            retrieverTool = getRetrieverTool(agent.silo)
            if retrieverTool is not None:
                tools.append(retrieverTool)

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