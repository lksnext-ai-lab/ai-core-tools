"""Plugin entry point. Called by core during FastAPI lifespan."""
import asyncio
import importlib.metadata

from utils.logger import get_logger

logger = get_logger(__name__)


def register(app, registry) -> None:
    """Register the SharePoint plugin with the Mattin AI core.

    Called once during FastAPI lifespan startup by the entry-point loader in main.py.
    1. Mounts the SharePoint router under /internal.
    2. Schedules the sync worker to start in the running event loop.
    3. Inserts a descriptor into PluginRegistry.
    """
    from mattin_sharepoint.router import router as sharepoint_router
    app.include_router(sharepoint_router, prefix="/internal", tags=["SharePoint"])

    # Schedule the worker start. Since register() is called inside the lifespan
    # async context, we can use asyncio.ensure_future.
    async def _start_worker():
        from mattin_sharepoint.worker import start_sharepoint_worker
        tasks = await start_sharepoint_worker()
        if not hasattr(app.state, 'sharepoint_tasks'):
            app.state.sharepoint_tasks = []
        app.state.sharepoint_tasks.extend(tasks)

    asyncio.ensure_future(_start_worker())

    try:
        version = importlib.metadata.version("mattin-sharepoint")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"

    registry.register("sharepoint", {"enabled": True, "version": version})
    logger.info(f"SharePoint plugin registered (version={version})")
