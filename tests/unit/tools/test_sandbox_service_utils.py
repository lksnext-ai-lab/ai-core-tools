"""
Unit tests for tools.sandbox_service_utils — SandboxService extra_config
build/parse round-trip, one per supported provider (OpenSandbox, Daytona, E2B).
"""

from __future__ import annotations

import json

import pytest

from tools.sandbox_service_utils import (
    PROVIDER_EXTRA_CONFIG_FIELDS,
    build_extra_config,
    parse_extra_config,
)


class TestBuildExtraConfig:
    def test_opensandbox_keeps_only_image(self):
        raw = build_extra_config("opensandbox", image="my/image:v1", target="ignored")
        assert json.loads(raw) == {"image": "my/image:v1"}

    def test_daytona_keeps_target_workspace_cpu_memory(self):
        raw = build_extra_config(
            "daytona", target="eu", workspace="workspace", cpu=2, memory_gb=4, template="ignored"
        )
        assert json.loads(raw) == {
            "target": "eu",
            "workspace": "workspace",
            "cpu": 2,
            "memory_gb": 4,
        }

    def test_e2b_keeps_template_and_workspace(self):
        raw = build_extra_config("e2b", template="tmpl-123", workspace="/home/user/workspace", image="ignored")
        assert json.loads(raw) == {"template": "tmpl-123", "workspace": "/home/user/workspace"}

    def test_returns_none_when_nothing_to_persist(self):
        assert build_extra_config("opensandbox") is None
        assert build_extra_config("opensandbox", image=None) is None
        assert build_extra_config("opensandbox", image="") is None

    def test_unknown_provider_returns_none(self):
        assert build_extra_config("unknown-provider", image="x") is None

    def test_provider_name_is_case_insensitive(self):
        raw = build_extra_config("OpenSandbox", image="my/image:v1")
        assert json.loads(raw) == {"image": "my/image:v1"}

    def test_strips_whitespace_from_string_values(self):
        raw = build_extra_config("opensandbox", image="  my/image:v1  ")
        assert json.loads(raw) == {"image": "my/image:v1"}

    def test_switching_provider_drops_stale_fields(self):
        """Building extra_config for a new provider must never carry over the
        previous provider's fields, even if the caller passes them all."""
        raw = build_extra_config(
            "e2b",
            image="stale-opensandbox-image",
            target="stale-daytona-target",
            cpu=99,
            memory_gb=99,
            template="tmpl-123",
            workspace="/home/user/workspace",
        )
        assert json.loads(raw) == {"template": "tmpl-123", "workspace": "/home/user/workspace"}


class TestParseExtraConfig:
    def test_round_trips_opensandbox(self):
        raw = build_extra_config("opensandbox", image="my/image:v1")
        assert parse_extra_config("opensandbox", raw) == {"image": "my/image:v1"}

    def test_round_trips_daytona(self):
        raw = build_extra_config("daytona", target="eu", workspace="workspace", cpu=2, memory_gb=4)
        assert parse_extra_config("daytona", raw) == {
            "target": "eu",
            "workspace": "workspace",
            "cpu": 2,
            "memory_gb": 4,
        }

    def test_round_trips_e2b(self):
        raw = build_extra_config("e2b", template="tmpl-123", workspace="/home/user/workspace")
        assert parse_extra_config("e2b", raw) == {
            "template": "tmpl-123",
            "workspace": "/home/user/workspace",
        }

    def test_none_returns_empty_dict(self):
        assert parse_extra_config("opensandbox", None) == {}

    def test_empty_string_returns_empty_dict(self):
        assert parse_extra_config("opensandbox", "") == {}

    def test_malformed_json_returns_empty_dict(self):
        assert parse_extra_config("opensandbox", "{not valid json") == {}

    def test_already_parsed_dict_is_accepted(self):
        assert parse_extra_config("opensandbox", {"image": "x"}) == {"image": "x"}

    def test_non_dict_json_returns_empty_dict(self):
        assert parse_extra_config("opensandbox", "[1, 2, 3]") == {}

    def test_filters_out_fields_not_in_providers_allowlist(self):
        """A stale extra_config left over from switching providers must not
        leak fields belonging to a different provider."""
        raw = json.dumps({"image": "stale", "target": "eu", "cpu": 2})
        # Now read it back as though the service's provider is opensandbox:
        # only 'image' is in that provider's allowlist.
        assert parse_extra_config("opensandbox", raw) == {"image": "stale"}

    def test_unknown_provider_returns_empty_dict(self):
        raw = json.dumps({"image": "x"})
        assert parse_extra_config("unknown-provider", raw) == {}


class TestProviderExtraConfigFieldsAllowlist:
    def test_covers_all_three_providers(self):
        assert set(PROVIDER_EXTRA_CONFIG_FIELDS.keys()) == {"opensandbox", "daytona", "e2b"}

    @pytest.mark.parametrize(
        "provider,expected_fields",
        [
            ("opensandbox", {"image"}),
            ("daytona", {"target", "workspace", "cpu", "memory_gb"}),
            ("e2b", {"template", "workspace"}),
        ],
    )
    def test_field_sets_match_provider_env_vars(self, provider, expected_fields):
        assert set(PROVIDER_EXTRA_CONFIG_FIELDS[provider]) == expected_fields
