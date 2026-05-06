"""Unit tests for the Mattin AI plugin registry."""
from unittest.mock import MagicMock, patch

from plugins.registry import PluginRegistry


class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        reg.register("myplugin", {"enabled": True, "version": "1.0"})
        descriptor = reg.get("myplugin")
        assert descriptor == {"enabled": True, "version": "1.0"}

    def test_get_unknown_returns_none(self):
        reg = PluginRegistry()
        assert reg.get("doesnotexist") is None

    def test_is_enabled_true(self):
        reg = PluginRegistry()
        reg.register("myplugin", {"enabled": True})
        assert reg.is_enabled("myplugin") is True

    def test_is_enabled_false(self):
        reg = PluginRegistry()
        reg.register("myplugin", {"enabled": False})
        assert reg.is_enabled("myplugin") is False

    def test_is_enabled_unregistered(self):
        reg = PluginRegistry()
        assert reg.is_enabled("ghost") is False

    def test_all_returns_copy(self):
        reg = PluginRegistry()
        reg.register("a", {"enabled": True})
        copy = reg.all()
        copy["injected"] = {"enabled": True}
        # Original registry must not be mutated
        assert reg.get("injected") is None

    def test_all_returns_all_entries(self):
        reg = PluginRegistry()
        reg.register("x", {"enabled": True})
        reg.register("y", {"enabled": False})
        assert set(reg.all().keys()) == {"x", "y"}

    def test_fake_entry_point_loading(self):
        """Simulate the entry-point loader from main.py using a fake entry point."""
        reg = PluginRegistry()

        def fake_register_fn(app, registry):
            registry.register("fake", {"enabled": True})

        fake_ep = MagicMock()
        fake_ep.name = "fake"
        fake_ep.load.return_value = fake_register_fn

        # Replicate the loader loop from main.py
        with patch("importlib.metadata.entry_points", return_value=[fake_ep]):
            import importlib.metadata
            for ep in importlib.metadata.entry_points(group="mattin.plugins"):
                ep.load()(None, reg)

        assert reg.is_enabled("fake")
