import enum


class AgentToolCallType(str, enum.Enum):
    AGENT = "AGENT"
    MCP = "MCP"
    RETRIEVER = "RETRIEVER"
