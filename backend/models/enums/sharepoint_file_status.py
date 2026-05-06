import enum


class SharePointFileStatus(str, enum.Enum):
    PENDING = "PENDING"
    INDEXED = "INDEXED"
    ERROR = "ERROR"
