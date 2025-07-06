from services.agent_cache_service import AgentCacheService
from tools.agentTools import create_agent
from langchain_core.messages import AIMessage
from langchain.callbacks.tracers import LangChainTracer
from langsmith import Client
import json
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentUtils:
    @staticmethod
    async def get_or_create_agent(agent, search_params=None):
        """Helper function to get cached agent or create new one."""
        agent_x = None
        
        '''if agent.has_memory:
           agent_x = AgentCacheService.get_cached_agent(agent.agent_id)
        '''
        
        if agent_x is None:
            logger.info("Creating new agent instance")
            agent_x = await create_agent(agent, search_params)
            if agent.has_memory:
                AgentCacheService.cache_agent(agent.agent_id, agent_x)
                logger.info("Agent cached successfully")
            else:
                logger.info("Agent not cached as it has no memory enabled")
        return agent_x

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def setup_tracer(agent):
        """Setup tracer if configured."""
        tracer = None
        if agent.app.langsmith_api_key:
            client = Client(api_key=agent.app.langsmith_api_key)
            tracer = LangChainTracer(client=client, project_name=agent.app.name)
        return tracer 