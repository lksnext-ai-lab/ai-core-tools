"""ChatToolCallLogMiddleware adds NO graph node (every extra node costs graph steps per model call)."""
import asyncio

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from services.internal_chat.resolved_config import TurnDiagnostics
from tools.middleware.chat_tool_log import ChatToolCallLogMiddleware


@tool
def probe(x: str = "") -> str:
    """probe tool"""
    return "ok"


class ThreeToolCalls(BaseChatModel):
    n: int = 0

    @property
    def _llm_type(self):
        return "three-tool-calls"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.n += 1
        call = [{"name": "probe", "args": {}, "id": f"c{self.n}"}] if self.n <= 3 else []
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="" if call else "done", tool_calls=call))])


class NodeAddingMiddleware(AgentMiddleware):
    """What the logger used to be: a ``before_model`` hook (adds a node)."""

    def before_model(self, state, runtime):
        return None

    async def abefore_model(self, state, runtime):
        return None


def _tasks(middleware) -> int:
    async def run():
        graph = create_agent(model=ThreeToolCalls(), tools=[probe], middleware=middleware, checkpointer=InMemorySaver())
        tasks = 0
        async for event in graph.astream(
            {"messages": [HumanMessage("go")]}, {"configurable": {"thread_id": "t"}, "recursion_limit": 100},
            stream_mode="debug",
        ):
            tasks += event["type"] == "task"
        return tasks

    return asyncio.run(run())


def test_the_logger_costs_no_extra_graph_steps_while_a_before_model_hook_does():
    diag = TurnDiagnostics()
    baseline = _tasks([])
    with_logger = _tasks([ChatToolCallLogMiddleware(diag)])
    with_node = _tasks([NodeAddingMiddleware()])
    assert with_logger == baseline == 7  # 4 model calls + 3 tool calls, nothing else
    assert with_node == baseline + 4  # one extra node execution per model call
    assert diag.model_calls == 4 and diag.tool_counts == {"probe": 3}
