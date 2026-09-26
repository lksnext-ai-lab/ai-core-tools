import enum


class AgentExecutionCallerType(str, enum.Enum):
    INTERNAL_PLAYGROUND = "INTERNAL_PLAYGROUND"
    PUBLIC_API = "PUBLIC_API"
    MCP = "MCP"
    AGENT_AS_TOOL = "AGENT_AS_TOOL"
