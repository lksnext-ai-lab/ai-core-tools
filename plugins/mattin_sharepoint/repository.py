"""Re-exports core repositories for use within the plugin.

backend/ is on sys.path when the plugin is loaded by the core, so these
imports resolve correctly at runtime.
"""
from repositories.sharepoint_source_repository import SharePointSourceRepository
from repositories.sharepoint_file_repository import SharePointFileRepository

__all__ = ["SharePointSourceRepository", "SharePointFileRepository"]
