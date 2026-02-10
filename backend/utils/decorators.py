"""
Decorators for FastAPI routes.

Note: Legacy Flask decorators have been removed as the project uses FastAPI.
App access validation is now handled through FastAPI dependencies in routers/controls/.
"""
from functools import wraps
from utils.logger import get_logger

logger = get_logger(__name__)