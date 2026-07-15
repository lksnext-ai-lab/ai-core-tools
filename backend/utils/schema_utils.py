import re

def sanitize_identifier(name: str) -> str:
    """
    OpenAI function/tool/schema names must match:
    ^[a-zA-Z0-9_-]+$
    """

    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    if not name:
        name = "id"

    if not re.match(r"^[a-zA-Z_]", name):
        name = f"id_{name}"

    return name


def ensure_json_schema_types(node) -> None:
    """Complete missing ``type`` keys in a JSON Schema so provider function
    schemas validate.

    Some MCP servers emit tool input schemas whose properties omit ``type``,
    which OpenAI (and other providers) reject with
    ``schema must have a 'type' key``. This walks the schema in place and fills
    the missing ``type`` — containers from their shape, leaves defaulting to
    ``string``.

    It is intentionally **additive**: it never changes which fields are
    ``required`` (that would break optional parameters) and never enables strict
    mode. Strict-mode compliance (``additionalProperties: false`` + nullable
    optionals) is only valid for schemas we own, not third-party tool schemas.
    """
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            node.setdefault("type", "object")
            for value in node["properties"].values():
                ensure_json_schema_types(value)
        if "items" in node:
            node.setdefault("type", "array")
            ensure_json_schema_types(node["items"])
        for combinator in ("anyOf", "oneOf", "allOf"):
            if isinstance(node.get(combinator), list):
                for sub in node[combinator]:
                    ensure_json_schema_types(sub)
        # A leaf with neither a container shape nor a combinator/$ref still needs
        # a type for the provider to accept it; string is the safe default.
        if "type" not in node and not any(
            k in node for k in ("properties", "items", "anyOf", "oneOf", "allOf", "$ref")
        ):
            node["type"] = "string"
    elif isinstance(node, list):
        for item in node:
            ensure_json_schema_types(item)
