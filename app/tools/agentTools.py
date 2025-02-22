from langchain_anthropic import ChatAnthropic
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from app.model.agent import Agent
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
import os
from typing import Any

def create_agent(agent: Agent):
    llm = getLLM(agent)
    if llm is None:
        raise ValueError("No LLM found for agent")
    
    tools = []
    for tool in agent.tool_associations:
        subAgnet = tool.tool
        tools.append(IACTTool(subAgnet))
    state_modifier = SystemMessage(content=agent.system_prompt)
    return create_react_agent(llm, tools, debug=True, state_modifier=state_modifier)



def getLLM(agent):
    if agent.model is None:
        return None
    if agent.model.provider == "OpenAI":
        return ChatOpenAI(model=agent.model.name, api_key=os.getenv('OPENAI_API_KEY'))
    if agent.model.provider == "Anthropic":
        return ChatAnthropic(model=agent.model.name, api_key=os.getenv('ANTHROPIC_API_KEY'))
    if agent.model.provider == "MistralAI":
        return ChatMistralAI(model=agent.model.name, api_key=os.getenv('MISTRAL_API_KEY'))
    return None



class IACTTool(BaseTool):
    name: str = "agent_tool"
    description: str = "Search for a repository"
    agent: Agent
    react_agent: Any = None
    llm: Any = None

    def __init__(self, agent: Agent) -> None:
        # Pass the agent to the parent class initialization
        super().__init__(agent=agent)
        
        self.agent = agent  # Store the agent reference
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
        self.react_agent = create_react_agent(self.llm, tools, debug=True, state_modifier=state_modifier)

    def _run(self, query: str, *args, **kwargs) -> str:
        # Format the prompt template safely using .format() instead of %
        formatted_prompt = self.agent.prompt_template.format(question=query)
        messages = [HumanMessage(content=formatted_prompt)]
        return self.react_agent.invoke({"messages": messages})