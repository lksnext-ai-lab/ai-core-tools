# Import all models to ensure SQLAlchemy relationships are resolved
# Import order matters for circular dependencies

from .user import User
from .app import App
from .app_collaborator import AppCollaborator
from .api_key import APIKey
from .ai_service import AIService
from .embedding_service import EmbeddingService
from .output_parser import OutputParser
from .mcp_config import MCPConfig
from .silo import Silo
from .skill import Skill
from .agent import Agent
from .agent_marketplace_profile import AgentMarketplaceProfile
from .agent_marketplace_rating import AgentMarketplaceRating
from .skill import Skill
from .ocr_agent import OCRAgent
from .conversation import Conversation
from .repository import Repository
from .resource import Resource
from .folder import Folder
from .domain import Domain
# New crawling pipeline models (Domain must be imported before its children)
from .domain_url import DomainUrl
from .crawl_policy import CrawlPolicy
from .crawl_job import CrawlJob
from .media import Media
from .mcp_server import MCPServer, MCPServerAgent
from .system_setting import SystemSetting
from .marketplace_usage import MarketplaceUsage
from .subscription import Subscription, SubscriptionTier, BillingStatus
from .tier_config import TierConfig
from .usage_record import UsageRecord
from .user_credential import UserCredential

__all__ = [
    'User', 'App', 'AppCollaborator', 'APIKey',
    'AIService', 'EmbeddingService', 'OutputParser', 'MCPConfig', 'Silo', 'Skill',
    'Agent', 'AgentMarketplaceProfile', 'AgentMarketplaceRating', 'OCRAgent', 'Conversation',
    'Repository', 'Resource', 'Folder', 'Domain',
    'DomainUrl', 'CrawlPolicy', 'CrawlJob',
    'AIService', 'EmbeddingService', 'OutputParser', 'MCPConfig', 'Silo',
    'Agent', 'Skill', 'OCRAgent', 'Conversation', 'Repository', 'Resource', 'Folder', 'Domain',
    'Media',
    'MCPServer', 'MCPServerAgent',
    'SystemSetting',
    'MarketplaceUsage',
    'Subscription', 'SubscriptionTier', 'BillingStatus',
    'TierConfig',
    'UsageRecord',
    'UserCredential',
]
