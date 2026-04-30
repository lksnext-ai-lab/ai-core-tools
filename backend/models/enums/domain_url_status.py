import enum


class DomainUrlStatus(str, enum.Enum):
    PENDING = "PENDING"
    CRAWLING = "CRAWLING"
    INDEXED = "INDEXED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    REMOVED = "REMOVED"
    EXCLUDED = "EXCLUDED"
