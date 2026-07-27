"""Unit tests for backend/tools/outputParserTools.py — optional field support.

Tests cover:
1. create_dynamic_pydantic_model with optional fields
2. create_model_from_json_schema with optional=True in schema data
3. Backwards-compatibility: existing parsers with no optional flag
4. LLM prompt hint: optional fields include description annotation
"""

import pytest
from typing import Optional, Union, get_args, get_origin
from pydantic import BaseModel

from tools.outputParserTools import (
    create_dynamic_pydantic_model,
    create_model_from_json_schema,
)


class TestCreateDynamicPydanticModelOptional:
    """Tests for create_dynamic_pydantic_model with field_optionals parameter."""

    def test_all_required_fields(self):
        """Model with no optional fields should require all fields."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["name", "age"],
            [str, int],
            ["Person name", "Person age"],
        )

        instance = Model(name="Alice", age=30)
        assert instance.name == "Alice"
        assert instance.age == 30

        with pytest.raises(Exception):
            Model()  # Missing required fields

    def test_optional_field_accepts_none(self):
        """An optional field should accept None and default to None."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["name", "nickname"],
            [str, str],
            ["Person name", "Nickname"],
            field_optionals=[False, True],
        )

        instance_with_nickname = Model(name="Alice", nickname="Ali")
        assert instance_with_nickname.nickname == "Ali"

        instance_without_nickname = Model(name="Alice")
        assert instance_without_nickname.nickname is None

    def test_optional_field_type_is_optional(self):
        """Optional fields should have Optional[T] type annotation."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["value"],
            [int],
            ["A value"],
            field_optionals=[True],
        )

        annotation = Model.model_fields["value"].annotation
        assert get_origin(annotation) is Union
        assert type(None) in get_args(annotation)
        # The field should accept None
        instance = Model()
        assert instance.value is None

    def test_optional_field_description_includes_hint(self):
        """Optional fields should have '(optional' annotation in their description."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["notes"],
            [str],
            ["User notes"],
            field_optionals=[True],
        )

        description = Model.model_fields["notes"].description
        assert "optional" in description.lower()

    def test_required_field_description_unchanged(self):
        """Required fields should NOT have the optional annotation in their description."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["name"],
            [str],
            ["Person name"],
            field_optionals=[False],
        )

        description = Model.model_fields["name"].description
        assert "optional" not in description.lower()

    def test_mixed_required_and_optional(self):
        """Model with mixed required/optional fields should work correctly."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["name", "age", "email"],
            [str, int, str],
            ["Name", "Age", "Email"],
            field_optionals=[False, False, True],
        )

        # Required fields must be provided
        with pytest.raises(Exception):
            Model(name="Alice")  # Missing required 'age'

        # Optional field can be omitted
        instance = Model(name="Alice", age=30)
        assert instance.email is None

        # Optional field can be provided
        instance_with_email = Model(name="Alice", age=30, email="alice@example.com")
        assert instance_with_email.email == "alice@example.com"

    def test_no_field_optionals_defaults_to_all_required(self):
        """When field_optionals is None, all fields should be required."""
        Model = create_dynamic_pydantic_model(
            "TestModel",
            ["x", "y"],
            [float, float],
            ["X coordinate", "Y coordinate"],
            field_optionals=None,
        )

        with pytest.raises(Exception):
            Model(x=1.0)  # Missing required 'y'

        instance = Model(x=1.0, y=2.0)
        assert instance.x == 1.0


class TestCreateModelFromJsonSchemaOptional:
    """Tests for create_model_from_json_schema with optional flag in schema data."""

    def test_optional_flag_in_schema_data(self):
        """Fields with optional=True in schema data should become Optional."""
        schema_data = [
            {"name": "title", "type": "str", "description": "Title", "optional": False},
            {"name": "subtitle", "type": "str", "description": "Subtitle", "optional": True},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")

        # subtitle is optional, so it can be omitted
        instance = Model(title="Hello")
        assert instance.title == "Hello"
        assert instance.subtitle is None

    def test_missing_optional_flag_defaults_to_required(self):
        """Fields without optional flag should default to required (backwards compat)."""
        schema_data = [
            {"name": "name", "type": "str", "description": "Name"},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")

        with pytest.raises(Exception):
            Model()  # name is required

    def test_optional_false_is_required(self):
        """Fields with optional=False should be required."""
        schema_data = [
            {"name": "required_field", "type": "int", "description": "Required", "optional": False},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")

        with pytest.raises(Exception):
            Model()

    def test_optional_int_field(self):
        """Optional int fields should accept None."""
        schema_data = [
            {"name": "count", "type": "int", "description": "Count", "optional": True},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")
        instance = Model()
        assert instance.count is None

    def test_optional_bool_field(self):
        """Optional bool fields should accept None."""
        schema_data = [
            {"name": "active", "type": "bool", "description": "Active flag", "optional": True},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")
        instance = Model()
        assert instance.active is None

        instance_with_value = Model(active=True)
        assert instance_with_value.active is True

    def test_pydantic_schema_excludes_optional_from_required(self):
        """The generated model's JSON schema should not include optional fields in 'required'."""
        schema_data = [
            {"name": "id", "type": "str", "description": "ID", "optional": False},
            {"name": "note", "type": "str", "description": "Note", "optional": True},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")
        json_schema = Model.model_json_schema()

        assert "id" in json_schema.get("required", [])
        assert "note" not in json_schema.get("required", [])

    def test_all_optional_fields(self):
        """A model where all fields are optional should be instantiable with no arguments."""
        schema_data = [
            {"name": "a", "type": "str", "description": "A", "optional": True},
            {"name": "b", "type": "int", "description": "B", "optional": True},
        ]

        Model = create_model_from_json_schema(schema_data, "TestModel")
        instance = Model()
        assert instance.a is None
        assert instance.b is None

    def test_backwards_compatible_no_optional_flag(self):
        """Existing parsers without optional flag continue to work as required."""
        schema_data = [
            {"name": "field1", "type": "str", "description": "Field 1"},
            {"name": "field2", "type": "float", "description": "Field 2"},
        ]

        Model = create_model_from_json_schema(schema_data, "LegacyModel")
        json_schema = Model.model_json_schema()

        required = json_schema.get("required", [])
        assert "field1" in required
        assert "field2" in required
