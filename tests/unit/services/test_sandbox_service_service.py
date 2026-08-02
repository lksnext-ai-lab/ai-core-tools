"""
Unit tests for SandboxServiceService.

The repository is mocked, so no database is needed. Mirrors the coverage
shape used for other *Service classes (e.g. AIServiceService): masked-key
write guard, system+app merge, copy/delete behavior, and detail/list
schema shaping.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.sandbox_service_service import SandboxServiceService, _endpoint_is_disallowed
from schemas.sandbox_service_schemas import CreateUpdateSandboxServiceSchema
from repositories.sandbox_service_repository import SandboxServiceRepository
from tools.sandbox.factory import SandboxProviderUnavailableError
from utils.secret_utils import mask_api_key


def _make_service(
    service_id: int = 1,
    app_id: int | None = 10,
    name: str = "Test Sandbox Service",
    provider: str = "opensandbox",
    api_key: str | None = "sk-real-secret-key",
    endpoint: str = "opensandbox:8080",
    extra_config: str | None = None,
) -> MagicMock:
    svc = MagicMock()
    svc.service_id = service_id
    svc.app_id = app_id
    svc.name = name
    svc.provider = provider
    svc.api_key = api_key
    svc.endpoint = endpoint
    svc.extra_config = extra_config
    svc.create_date = datetime(2024, 1, 1)
    return svc


# ---------------------------------------------------------------------------
# _to_list_item / list merge (system + app)
# ---------------------------------------------------------------------------


class TestToListItem:
    def test_needs_api_key_true_when_missing(self):
        svc = _make_service(api_key=None)
        item = SandboxServiceService._to_list_item(svc)
        assert item.needs_api_key is True

    def test_needs_api_key_false_when_present(self):
        svc = _make_service(api_key="sk-real-secret-key")
        item = SandboxServiceService._to_list_item(svc)
        assert item.needs_api_key is False

    def test_is_system_flag_propagates(self):
        svc = _make_service()
        item = SandboxServiceService._to_list_item(svc, is_system=True)
        assert item.is_system is True


class TestGetSandboxServicesByAppId:
    def test_merges_app_and_system_services(self):
        app_svc = _make_service(service_id=1, app_id=10, name="App Svc")
        system_svc = _make_service(service_id=2, app_id=None, name="System Svc")

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_app_id",
                return_value=[app_svc],
            ),
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_system_services",
                return_value=[system_svc],
            ),
        ):
            result = SandboxServiceService.get_sandbox_services_by_app_id(MagicMock(), 10)

        by_name = {item.name: item for item in result}
        assert by_name["App Svc"].is_system is False
        assert by_name["System Svc"].is_system is True


# ---------------------------------------------------------------------------
# get_sandbox_service_detail
# ---------------------------------------------------------------------------


class TestGetSandboxServiceDetail:
    def test_service_id_zero_returns_blank_form(self):
        result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 0)
        assert result.service_id == 0
        assert result.provider is None
        assert len(result.available_providers) == 3

    def test_missing_service_returns_none(self):
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=None,
        ):
            result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 999)
        assert result is None

    def test_api_key_is_masked(self):
        svc = _make_service(api_key="sk-real-secret-key-1234")
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=svc,
        ):
            result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 1)
        assert result.api_key == mask_api_key("sk-real-secret-key-1234")
        assert "sk-real-secret-key-1234" not in result.api_key

    def test_opensandbox_extra_config_surfaces_image_field(self):
        svc = _make_service(provider="opensandbox", extra_config='{"image": "my/image:v1"}')
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=svc,
        ):
            result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 1)
        assert result.opensandbox_image == "my/image:v1"
        assert result.daytona_target is None
        assert result.e2b_template is None

    def test_daytona_extra_config_surfaces_daytona_fields(self):
        svc = _make_service(
            provider="daytona",
            extra_config='{"target": "eu", "workspace": "workspace", "cpu": 2, "memory_gb": 4}',
        )
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=svc,
        ):
            result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 1)
        assert result.daytona_target == "eu"
        assert result.daytona_workspace == "workspace"
        assert result.daytona_cpu == 2
        assert result.daytona_memory_gb == 4
        assert result.e2b_workspace is None
        assert result.opensandbox_image is None

    def test_e2b_extra_config_surfaces_e2b_fields(self):
        svc = _make_service(
            provider="e2b",
            extra_config='{"template": "tmpl-123", "workspace": "/home/user/workspace"}',
        )
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=svc,
        ):
            result = SandboxServiceService.get_sandbox_service_detail(MagicMock(), 10, 1)
        assert result.e2b_template == "tmpl-123"
        assert result.e2b_workspace == "/home/user/workspace"
        assert result.daytona_workspace is None


# ---------------------------------------------------------------------------
# create_or_update_sandbox_service — masked-key write guard
# ---------------------------------------------------------------------------


class TestCreateOrUpdateSandboxService:
    def _schema(self, **overrides) -> CreateUpdateSandboxServiceSchema:
        defaults = dict(
            name="My Sandbox",
            provider="opensandbox",
            api_key="sk-new-real-key",
            base_url="opensandbox:8080",
        )
        defaults.update(overrides)
        return CreateUpdateSandboxServiceSchema(**defaults)

    def test_create_persists_new_service(self):
        created_holder = {}

        def _fake_create(db, service):
            service.service_id = 42
            created_holder["service"] = service
            return service

        with (
            patch("services.sandbox_service_service.SandboxServiceRepository.create", side_effect=_fake_create),
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                side_effect=lambda db, sid, aid: created_holder.get("service"),
            ),
        ):
            result = SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(), 10, 0, self._schema()
            )

        assert created_holder["service"].app_id == 10
        assert created_holder["service"].api_key == "sk-new-real-key"
        assert result.service_id == 42

    def test_update_missing_service_returns_none(self):
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=None,
        ):
            result = SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(), 10, 999, self._schema()
            )
        assert result is None

    def test_masked_api_key_does_not_overwrite_stored_secret(self):
        existing = _make_service(service_id=1, app_id=10, api_key="sk-original-secret")
        masked_echo = mask_api_key("sk-original-secret")

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                return_value=existing,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.update", return_value=existing),
        ):
            SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(), 10, 1, self._schema(api_key=masked_echo)
            )

        # The masked placeholder must never clobber the real stored secret.
        assert existing.api_key == "sk-original-secret"

    def test_real_new_api_key_does_overwrite(self):
        existing = _make_service(service_id=1, app_id=10, api_key="sk-original-secret")

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                return_value=existing,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.update", return_value=existing),
        ):
            SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(), 10, 1, self._schema(api_key="sk-brand-new-secret")
            )

        assert existing.api_key == "sk-brand-new-secret"

    def test_extra_config_built_for_daytona_provider(self):
        existing = _make_service(service_id=1, app_id=10, provider="daytona")

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                return_value=existing,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.update", return_value=existing),
        ):
            SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(),
                10,
                1,
                self._schema(
                    provider="daytona",
                    daytona_target="eu",
                    daytona_workspace="workspace",
                    daytona_cpu=2,
                    daytona_memory_gb=4,
                ),
            )

        import json
        assert json.loads(existing.extra_config) == {
            "target": "eu",
            "workspace": "workspace",
            "cpu": 2,
            "memory_gb": 4,
        }

    def test_switching_provider_drops_stale_extra_config(self):
        """Switching provider from opensandbox to e2b must not carry over
        the stale 'image' field into the new extra_config."""
        existing = _make_service(service_id=1, app_id=10, provider="opensandbox", extra_config='{"image": "old"}')

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                return_value=existing,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.update", return_value=existing),
        ):
            SandboxServiceService.create_or_update_sandbox_service(
                MagicMock(),
                10,
                1,
                self._schema(provider="e2b", e2b_template="tmpl-123", e2b_workspace="/home/user/workspace"),
            )

        import json
        assert json.loads(existing.extra_config) == {
            "template": "tmpl-123",
            "workspace": "/home/user/workspace",
        }


# ---------------------------------------------------------------------------
# copy_sandbox_service
# ---------------------------------------------------------------------------


class TestCopySandboxService:
    def test_missing_service_returns_none(self):
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=None,
        ):
            result = SandboxServiceService.copy_sandbox_service(MagicMock(), 10, 999)
        assert result is None

    def test_copy_appends_suffix_and_avoids_name_collision(self):
        original = _make_service(service_id=1, app_id=10, name="My Sandbox")
        copy_holder = {}

        def _fake_create(db, service):
            service.service_id = 2
            copy_holder["service"] = service
            return service

        existing_list_items = [
            SandboxServiceService._to_list_item(_make_service(service_id=1, name="My Sandbox")),
            SandboxServiceService._to_list_item(_make_service(service_id=3, name="My Sandbox Copy")),
        ]

        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                side_effect=lambda db, sid, aid: original if sid == 1 else copy_holder.get("service"),
            ),
            patch(
                "services.sandbox_service_service.SandboxServiceService.get_sandbox_services_by_app_id",
                return_value=existing_list_items,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.create", side_effect=_fake_create),
        ):
            SandboxServiceService.copy_sandbox_service(MagicMock(), 10, 1)

        assert copy_holder["service"].name == "My Sandbox Copy 2"
        assert copy_holder["service"].api_key == original.api_key


# ---------------------------------------------------------------------------
# delete_sandbox_service
# ---------------------------------------------------------------------------


class TestDeleteSandboxService:
    def test_returns_false_when_missing(self):
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=None,
        ):
            assert SandboxServiceService.delete_sandbox_service(MagicMock(), 10, 999) is False

    def test_returns_true_and_deletes_when_found(self):
        existing = _make_service(service_id=1, app_id=10)
        with (
            patch(
                "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
                return_value=existing,
            ),
            patch("services.sandbox_service_service.SandboxServiceRepository.delete") as mock_delete,
        ):
            result = SandboxServiceService.delete_sandbox_service(MagicMock(), 10, 1)

        assert result is True
        mock_delete.assert_called_once()


# ---------------------------------------------------------------------------
# test_connection_with_config
# ---------------------------------------------------------------------------


class TestConnectionWithConfig:
    def test_missing_provider_returns_error(self):
        result = SandboxServiceService.test_connection_with_config({"provider": "", "api_key": "sk-real"})
        assert result["status"] == "error"
        assert "Provider is required" in result["message"]

    def test_missing_api_key_returns_error_for_daytona(self):
        result = SandboxServiceService.test_connection_with_config({"provider": "daytona", "api_key": ""})
        assert result["status"] == "error"
        assert "API key is required" in result["message"]

    def test_missing_api_key_returns_error_for_e2b(self):
        result = SandboxServiceService.test_connection_with_config({"provider": "e2b", "api_key": ""})
        assert result["status"] == "error"
        assert "API key is required" in result["message"]

    def test_missing_api_key_is_allowed_for_opensandbox(self):
        """OpenSandbox is self-hosted and commonly run with no auth configured."""
        result = SandboxServiceService.test_connection_with_config({"provider": "opensandbox", "api_key": ""})
        # Should NOT fail on the API-key check specifically; whatever error
        # follows (e.g. SDK not installed, connection refused) is unrelated.
        assert "API key is required" not in result.get("message", "")

    def test_masked_api_key_returns_error(self):
        masked = mask_api_key("sk-real-secret-key")
        result = SandboxServiceService.test_connection_with_config(
            {"provider": "opensandbox", "api_key": masked}
        )
        assert result["status"] == "error"

    def test_unregistered_provider_returns_error(self):
        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": MagicMock()},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "daytona", "api_key": "sk-real-secret-key"}
            )
        assert result["status"] == "error"
        assert "daytona" in result["message"]

    def test_success_path_runs_trivial_code_and_destroys_sandbox(self):
        mock_provider_instance = MagicMock()
        mock_provider_instance.create_sandbox.return_value = "handle-1"
        mock_provider_instance.run_code.return_value = "2"
        mock_provider_class = MagicMock(return_value=mock_provider_instance)

        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": mock_provider_class},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "opensandbox", "api_key": "sk-real-secret-key"}
            )

        assert result["status"] == "success"
        mock_provider_instance.run_code.assert_called_once()
        mock_provider_instance.destroy_sandbox.assert_called_once_with("handle-1")

    def test_provider_error_is_reported_and_sandbox_not_destroyed_if_never_created(self):
        """The raw exception text must NOT reach the caller — connection-refused
        vs TLS-error vs HTTP-status detail is itself a network-reconnaissance
        oracle for a tenant-level role. It's logged server-side instead."""
        mock_provider_instance = MagicMock()
        mock_provider_instance.create_sandbox.side_effect = RuntimeError("boom")
        mock_provider_class = MagicMock(return_value=mock_provider_instance)

        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": mock_provider_class},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "opensandbox", "api_key": "sk-real-secret-key"}
            )

        assert result["status"] == "error"
        assert "boom" not in result["message"]
        mock_provider_instance.destroy_sandbox.assert_not_called()


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_missing_service_returns_error(self):
        with patch(
            "services.sandbox_service_service.SandboxServiceRepository.get_by_id_and_app_id",
            return_value=None,
        ):
            result = SandboxServiceService.test_connection(MagicMock(), 10, 999)
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# _endpoint_is_disallowed — SSRF guard for test_connection_with_config
# ---------------------------------------------------------------------------


class TestEndpointIsDisallowed:
    def test_rejects_loopback(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("127.0.0.1:8080") is True
        assert _endpoint_is_disallowed("http://localhost:8080") is True

    def test_rejects_rfc1918_private_ranges(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("10.0.0.5:5432") is True
        assert _endpoint_is_disallowed("172.16.0.5:8080") is True
        assert _endpoint_is_disallowed("192.168.1.10:8080") is True

    def test_rejects_link_local_metadata_endpoint(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("169.254.169.254") is True

    def test_accepts_normal_public_endpoint(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("https://8.8.8.8:8080") is False
        assert _endpoint_is_disallowed("api.daytona.example.com") is False

    def test_none_or_empty_endpoint_is_allowed(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed(None) is False
        assert _endpoint_is_disallowed("") is False

    def test_unresolvable_hostname_is_allowed_through(self, monkeypatch):
        """A DNS failure isn't itself an SSRF signal — let the provider call fail naturally."""
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        import socket as socket_module

        with patch.object(socket_module, "getaddrinfo", side_effect=socket_module.gaierror("nope")):
            assert _endpoint_is_disallowed("this-does-not-resolve.invalid") is False

    def test_hostname_resolving_to_private_ip_is_rejected(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        import socket as socket_module

        fake_result = [(socket_module.AF_INET, None, None, "", ("10.1.2.3", 8080))]
        with patch.object(socket_module, "getaddrinfo", return_value=fake_result):
            assert _endpoint_is_disallowed("internal.example.corp:8080") is True

    def test_rejects_cgnat_range(self, monkeypatch):
        """100.64.0.0/10 (RFC 6598) is used by some cloud metadata services
        (e.g. Alibaba Cloud's 100.100.100.200) and is NOT covered by
        ipaddress.is_private — must be checked explicitly."""
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("100.100.100.200:80") is True
        assert _endpoint_is_disallowed("100.64.0.1") is True

    def test_rejects_multicast_and_unspecified(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        assert _endpoint_is_disallowed("224.0.0.1") is True
        assert _endpoint_is_disallowed("0.0.0.0") is True

    def test_allow_private_env_var_disables_the_check(self, monkeypatch):
        """Operator opt-out for self-hosted deployments (e.g. opensandbox:8080 on a Docker network)."""
        monkeypatch.setenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", "true")
        assert _endpoint_is_disallowed("127.0.0.1:8080") is False
        assert _endpoint_is_disallowed("10.0.0.5:5432") is False

    def test_test_connection_with_config_rejects_disallowed_endpoint(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        mock_provider_class = MagicMock()
        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": mock_provider_class},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "opensandbox", "api_key": "sk-real", "endpoint": "169.254.169.254"}
            )

        assert result["status"] == "error"
        assert result["message"] == "Invalid or disallowed endpoint"
        mock_provider_class.assert_not_called()

    def test_test_connection_with_config_accepts_normal_endpoint(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        mock_provider_instance = MagicMock()
        mock_provider_instance.create_sandbox.return_value = "handle-1"
        mock_provider_instance.run_code.return_value = "2"
        mock_provider_class = MagicMock(return_value=mock_provider_instance)

        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": mock_provider_class},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "opensandbox", "api_key": "sk-real", "endpoint": "8.8.8.8:8080"}
            )

        assert result["status"] == "success"
        mock_provider_instance.destroy_sandbox.assert_called_once_with("handle-1")


# ---------------------------------------------------------------------------
# test_connection_with_config — bounded timeout for the blocking provider probe
# ---------------------------------------------------------------------------


class TestConnectionWithConfigTimeout:
    def test_timed_out_probe_returns_clean_error(self, monkeypatch):
        import time

        monkeypatch.setenv("SANDBOX_TEST_CONNECTION_TIMEOUT_S", "0")

        mock_provider_instance = MagicMock()
        mock_provider_instance.create_sandbox.side_effect = lambda *a, **k: time.sleep(0.3) or "handle-1"
        mock_provider_class = MagicMock(return_value=mock_provider_instance)

        with patch(
            "tools.sandbox.factory._PROVIDER_REGISTRY",
            {"opensandbox": mock_provider_class},
        ):
            result = SandboxServiceService.test_connection_with_config(
                {"provider": "opensandbox", "api_key": "sk-real"}
            )

        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()


# ---------------------------------------------------------------------------
# SANDBOX_ALLOWED_PROVIDERS enforcement — create_or_update_sandbox_service
# ---------------------------------------------------------------------------


class TestValidateProviderAllowed:
    def test_allows_everything_when_allowlist_unset(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", [], raising=False)
        SandboxServiceService._validate_provider_allowed("daytona")  # must not raise

    def test_allows_provider_present_in_allowlist(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", ["opensandbox"], raising=False)
        SandboxServiceService._validate_provider_allowed("opensandbox")  # must not raise

    def test_rejects_provider_absent_from_allowlist(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", ["opensandbox"], raising=False)
        with pytest.raises(SandboxProviderUnavailableError):
            SandboxServiceService._validate_provider_allowed("daytona")

    def test_create_or_update_rejects_disallowed_provider(self, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_ALLOWED_PROVIDERS", ["opensandbox"], raising=False)
        schema = CreateUpdateSandboxServiceSchema(
            name="My Sandbox",
            provider="daytona",
            api_key="sk-new-real-key",
            base_url="https://daytona.example",
        )
        with pytest.raises(SandboxProviderUnavailableError):
            SandboxServiceService.create_or_update_sandbox_service(MagicMock(), 10, 0, schema)


class TestCreateOrUpdateSandboxServiceEndpointValidation:
    """The SSRF guard must also apply at save-time, not just to the optional
    'Test Connection' diagnostic probe — an endpoint that's never tested
    would otherwise reach real sandbox creation on every subsequent agent
    turn with a loopback/link-local/private target."""

    def test_rejects_disallowed_endpoint_on_save(self, monkeypatch):
        monkeypatch.delenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", raising=False)
        schema = CreateUpdateSandboxServiceSchema(
            name="My Sandbox",
            provider="opensandbox",
            api_key="",
            base_url="169.254.169.254:80",
        )
        with pytest.raises(ValueError, match="disallowed endpoint"):
            SandboxServiceService.create_or_update_sandbox_service(MagicMock(), 10, 0, schema)

    def test_accepts_normal_endpoint_when_allow_private_set(self, monkeypatch):
        """Self-hosted deployments pointing at their own internal OpenSandbox
        server (e.g. opensandbox:8080) must still be able to save that config."""
        monkeypatch.setenv("SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE", "true")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        schema = CreateUpdateSandboxServiceSchema(
            name="My Sandbox",
            provider="opensandbox",
            api_key="",
            base_url="opensandbox:8080",
        )
        with patch.object(
            SandboxServiceRepository, "create", side_effect=lambda db, svc: svc
        ), patch.object(
            SandboxServiceService,
            "get_sandbox_service_detail",
            return_value="ok",
        ):
            result = SandboxServiceService.create_or_update_sandbox_service(db, 10, 0, schema)
        assert result == "ok"
