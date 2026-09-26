import enum


class AgentToolCallType(str, enum.Enum):
    AGENT = "AGENT"
    MCP = "MCP"
    RETRIEVER = "RETRIEVER"
    BUILTIN = "BUILTIN"  # platform tools: sandbox, skills, file helpers
