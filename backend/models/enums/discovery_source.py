import enum


class DiscoverySource(str, enum.Enum):
    SITEMAP = "SITEMAP"
    CRAWL = "CRAWL"
    MANUAL = "MANUAL"
