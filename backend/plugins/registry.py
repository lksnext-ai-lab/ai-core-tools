"""Plugin registry — a simple in-process dict for tracking installed Mattin AI plugins."""


class PluginRegistry:
    """In-memory store of plugin descriptors. Rebuilt each process startup via entry-point loading."""

    def __init__(self) -> None:
        self._plugins: dict[str, dict] = {}

    def register(self, name: str, descriptor: dict) -> None:
        """Store a plugin descriptor under the given name."""
        self._plugins[name] = descriptor

    def get(self, name: str) -> dict | None:
        """Return the descriptor for a plugin, or None if not registered."""
        return self._plugins.get(name)

    def all(self) -> dict:
        """Return a shallow copy of all registered plugin descriptors."""
        return dict(self._plugins)

    def is_enabled(self, name: str) -> bool:
        """Return True if the plugin is registered and has enabled=True."""
        return name in self._plugins and bool(self._plugins[name].get("enabled", False))


# Module-level singleton — shared across the entire process lifetime.
plugin_registry = PluginRegistry()
