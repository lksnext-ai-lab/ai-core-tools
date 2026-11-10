"""step_007 addendum: the ``DestinationSettings`` union must mirror the registry, not derive from it."""

import typing

from connectors.registry import (
    LEGACY_DEFAULT_PROVIDER_KEY,
    DestinationSettings,
    list_output_providers,
    registered_keys,
)
from schemas.output_provider_schemas import OutputDestinationCreateSchema


def _union_members() -> set[type]:
    annotated_args = typing.get_args(DestinationSettings)
    return set(typing.get_args(annotated_args[0]))


def test_union_members_equal_parsed_settings_types_of_providers():
    expected = set()
    for provider in list_output_providers():
        example = provider.example_destination()
        expected.add(type(provider.parse_settings(example.public_config, example.credentials)))
    assert _union_members() == expected


def test_each_literal_provider_key_matches_its_descriptor():
    by_type = {}
    for provider in list_output_providers():
        example = provider.example_destination()
        by_type[type(provider.parse_settings(example.public_config, example.credentials))] = provider.descriptor.key
    for member in _union_members():
        field = member.model_fields["provider_key"]
        assert typing.get_args(field.annotation) == (by_type[member],)
        assert field.default == by_type[member]


def test_create_schema_provider_key_literal_matches_registered_output_providers():
    field = OutputDestinationCreateSchema.model_fields["provider_key"]
    assert set(typing.get_args(field.annotation)) == {p.descriptor.key for p in list_output_providers()}


def test_legacy_default_provider_key_is_a_registered_output_provider():
    assert LEGACY_DEFAULT_PROVIDER_KEY in {p.descriptor.key for p in list_output_providers()}
    assert LEGACY_DEFAULT_PROVIDER_KEY in registered_keys()
    assert OutputDestinationCreateSchema.model_fields["provider_key"].default == LEGACY_DEFAULT_PROVIDER_KEY
