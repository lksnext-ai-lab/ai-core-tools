import enum


class AgentToolCallStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
