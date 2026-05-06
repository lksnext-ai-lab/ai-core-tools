"""Plugin entry point. Called by core during FastAPI lifespan."""


def register(app, registry):
    """Register the SharePoint plugin with the Mattin AI core."""
    import importlib.metadata
    try:
        version = importlib.metadata.version("mattin-sharepoint")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    # Router and worker wired in later steps
    registry.register("sharepoint", {"enabled": True, "version": version})
