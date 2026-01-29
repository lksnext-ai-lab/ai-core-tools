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
from .agent import Agent
from .ocr_agent import OCRAgent
from .conversation import Conversation
from .repository import Repository
from .resource import Resource
from .folder import Folder
from .domain import Domain
from .url import Url
from .media import Media

__all__ = [
    'User', 'App', 'AppCollaborator', 'APIKey',
    'AIService', 'EmbeddingService', 'OutputParser', 'MCPConfig', 'Silo',
    'Agent', 'OCRAgent', 'Conversation', 'Repository', 'Resource', 'Folder', 'Domain', 'Url',
    'Media'
] 