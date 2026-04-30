import enum


class CrawlTrigger(str, enum.Enum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
