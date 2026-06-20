"""
Integration tests for the metrics plugin capabilities endpoint.

Tests whether the /internal/capabilities endpoint reports the metrics plugin
when registered, and whether the metrics routes are absent when not registered.
"""
import pytest
from fastapi.testclient import TestClient


class TestCapabilityWithoutPlugin:
    """Without plugin registration, metrics key should be absent and routes 404."""

    def test_capabilities_excludes_metrics(self, client, auth_headers):
        """GET /internal/capabilities must NOT include a 'metrics' key."""
        from plugins.registry import plugin_registry
        # Ensure metrics not in registry for this test
        original = plugin_registry._plugins.pop("metrics", None)
        try:
            response = client.get("/internal/capabilities", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "metrics" not in data, f"Unexpected 'metrics' key found: {data}"
        finally:
            if original is not None:
                plugin_registry._plugins["metrics"] = original

    def test_metrics_router_absent(self, client, auth_headers):
        """Without plugin, GET /internal/apps/1/metrics/summary returns 404."""
        from plugins.registry import plugin_registry
        original = plugin_registry._plugins.pop("metrics", None)
        try:
            response = client.get("/internal/apps/1/metrics/summary", headers=auth_headers)
            # The route does not exist without the plugin, so expect 404
            assert response.status_code == 404, (
                f"Expected 404 without plugin, got {response.status_code}"
            )
        finally:
            if original is not None:
                plugin_registry._plugins["metrics"] = original


class TestCapabilityWithPlugin:
    """With plugin registration, metrics key should appear in capabilities."""

    def test_capabilities_includes_metrics(self, client, auth_headers):
        """After registering metrics plugin, GET /internal/capabilities returns metrics.enabled == True."""
        from plugins.registry import plugin_registry
        # Manually register the metrics descriptor (simulates plugin.register())
        original = plugin_registry._plugins.get("metrics")
        plugin_registry.register("metrics", {"enabled": True, "version": "test"})
        try:
            response = client.get("/internal/capabilities", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "metrics" in data, f"'metrics' not in capabilities: {data}"
            assert data["metrics"]["enabled"] is True
        finally:
            if original is not None:
                plugin_registry._plugins["metrics"] = original
            else:
                plugin_registry._plugins.pop("metrics", None)
