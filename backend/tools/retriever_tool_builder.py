"""
Pure-function builders for a silo's dynamic retrieval tool name, description,
and argument schema.

These functions are pure: no database, vector store, or external service access.
All runtime data (distinct metadata field values) must be supplied by the caller
via :func:`collect_distinct_values`.

All admin-supplied strings embedded in LLM tool definitions are passed through
``sanitize_metadata_value`` — never filter values, which must match stored
metadata exactly.

Enum / Literal policy: when a string field has ≤ MAX_ENUM_VALUES (25) distinct
values the schema uses ``Literal``; otherwise the free base type with up to
MAX_EXAMPLE_VALUES (10) example values in the description.
"""

from __future__ import annotations

import keyword
import logging
import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, create_model

from tools.vector_stores.metadata_filters import (
    MAX_ENUM_VALUES,
    MAX_EXAMPLE_VALUES,
    sanitize_metadata_value,
)

logger = logging.getLogger(__name__)

_FILTER_USAGE_POLICY = (
    "Only use this filter if the user's question explicitly mentions it; "
    "never invent a value."
)
_MAX_DESCRIPTION_LENGTH = 2000
_MAX_SLUG_LENGTH = 40

_TYPE_MAP: dict[str, type] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
}


def _resolve_python_type(type_str: str, field_name: str) -> type:
    """Map a UI type string to a Python type. Falls back to ``str`` with a WARNING."""
    resolved = _TYPE_MAP.get((type_str or "").strip().lower())
    if resolved is None:
        logger.warning(
            "retriever_tool_builder: unknown type %r for field %r — falling back to str",
            type_str,
            field_name,
        )
        return str
    return resolved


def _is_valid_identifier(name: str) -> bool:
    """Return True if *name* is a valid Python identifier that does not collide with ``query``."""
    if not name or not name.isidentifier():
        return False
    if keyword.iskeyword(name):
        return False
    if name == "query":
        return False
    return True


def _make_slug(name: str) -> str:
    """Convert *name* to a lowercase ASCII slug (NFKC, ``[a-z0-9_]`` only, truncated)."""
    normalised = unicodedata.normalize("NFKC", name or "").lower()
    slugified = re.sub(r"[^a-z0-9_]", "_", normalised)
    collapsed = re.sub(r"_+", "_", slugified).strip("_")
    return collapsed[:_MAX_SLUG_LENGTH]


def _sanitize_field_description(raw: str) -> str:
    """Sanitize an admin-supplied field description (max_len=200)."""
    return sanitize_metadata_value(raw, max_len=200)


def _build_literal_type(
    base_type: type,
    raw_values: list[str],
    field_name: str,
) -> tuple[type, list[str]]:
    """Build ``Literal[...]`` from sanitised string values, or return the free type.

    Only ``str`` fields produce Literal types.  Returns
    ``(type, sanitised_literals)``; ``sanitised_literals`` is empty when no
    Literal was built.
    """
    if base_type is not str or not raw_values or len(raw_values) > MAX_ENUM_VALUES:
        return base_type, []

    sanitised: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        clean = sanitize_metadata_value(raw)
        if clean and clean not in seen:
            seen.add(clean)
            sanitised.append(clean)

    if not sanitised:
        logger.warning(
            "retriever_tool_builder: all distinct values for field %r were empty "
            "after sanitization — using free str type",
            field_name,
        )
        return str, []

    literal_type = Literal[tuple(sanitised)]  # type: ignore[valid-type]
    return literal_type, sanitised


def _build_field_description(
    raw_description: str,
    field_type_label: str,
    distinct_values: list[str],
    sanitised_literals: list[str],
) -> str:
    """Compose the Field description: admin description, type, examples (when no Literal), policy."""
    parts: list[str] = []

    cleaned_desc = _sanitize_field_description(raw_description or "")
    if cleaned_desc:
        parts.append(cleaned_desc)

    parts.append(f"Type: {field_type_label}.")

    if not sanitised_literals and distinct_values:
        examples: list[str] = []
        seen_ex: set[str] = set()
        for raw in distinct_values:
            clean = sanitize_metadata_value(raw)
            if clean and clean not in seen_ex:
                seen_ex.add(clean)
                examples.append(clean)
            if len(examples) >= MAX_EXAMPLE_VALUES:
                break
        if examples:
            parts.append(f"Example values: {', '.join(examples)}.")

    parts.append(_FILTER_USAGE_POLICY)
    return " ".join(parts)


def build_retriever_args_schema(
    silo: Any,
    distinct_values: dict[str, list[str]],
) -> type[BaseModel]:
    """Build a Pydantic model for the retrieval tool's call arguments.

    Always includes a mandatory ``query`` field.  One optional typed field is
    added per entry in ``silo.metadata_definition.fields``; invalid identifiers
    and ``query`` collisions are discarded with a WARNING.

    Must be called with the silo attached to a live Session (reads the lazy
    ``metadata_definition`` relationship) — never from inside a tool coroutine
    with a detached instance.
    """
    field_definitions: dict[str, Any] = {
        "query": (
            str,
            Field(
                description=(
                    "Semantic search query over the document content. "
                    "Express what you are looking for in natural language; "
                    "the system will retrieve the most relevant passages."
                )
            ),
        )
    }

    metadata_def = getattr(silo, "metadata_definition", None)
    raw_fields: list[dict[str, Any]] = []
    if metadata_def is not None:
        raw_fields = metadata_def.fields or []

    for field_spec in raw_fields:
        if not isinstance(field_spec, dict):
            continue

        field_name: str = field_spec.get("name", "")
        if not _is_valid_identifier(field_name):
            logger.warning(
                "retriever_tool_builder: field name %r is not a valid Python "
                "identifier or collides with 'query' — skipping",
                field_name,
            )
            continue

        raw_type_str: str = field_spec.get("type", "str")
        base_type = _resolve_python_type(raw_type_str, field_name)
        # Use the canonical type name — the raw editor string is freeform and must
        # not reach the LLM prompt verbatim.
        type_label = base_type.__name__

        field_raw_values: list[str] = distinct_values.get(field_name, [])

        literal_type, sanitised_literals = _build_literal_type(
            base_type, field_raw_values, field_name
        )

        description = _build_field_description(
            raw_description=field_spec.get("description", ""),
            field_type_label=type_label,
            distinct_values=field_raw_values,
            sanitised_literals=sanitised_literals,
        )

        field_definitions[field_name] = (
            Optional[literal_type],
            Field(default=None, description=description),
        )

    model: type[BaseModel] = create_model(
        f"RetrieverArgs_{getattr(silo, 'silo_id', 'unknown')}",
        **field_definitions,
    )
    return model


def build_retriever_description(
    silo: Any,
    distinct_values: dict[str, list[str]],
) -> str:
    """Build the tool description: purpose blurb, filterable fields, usage policy.

    Total length is capped at ``_MAX_DESCRIPTION_LENGTH``.  Must be called with
    the silo attached to a live Session (reads ``metadata_definition`` and
    ``domain`` lazy relationships) — never from a detached instance.
    """
    silo_type_raw: str = str(getattr(silo, "silo_type", "") or "")
    silo_type_upper = silo_type_raw.upper()

    if silo_type_upper == "REPO":
        purpose = (
            "Search for relevant documents in the document repository. "
            "Use this tool to find specific files, passages, or structured data."
        )
    elif silo_type_upper == "DOMAIN":
        domain = getattr(silo, "domain", None)
        domain_desc = ""
        if domain is not None:
            raw_domain_desc = getattr(domain, "description", "") or ""
            domain_desc = sanitize_metadata_value(raw_domain_desc, max_len=200)
        if domain_desc:
            purpose = (
                f"Search for information from a crawled web site. "
                f"Site description: {domain_desc}"
            )
        else:
            purpose = "Search for information from a crawled web site."
    else:
        silo_desc = sanitize_metadata_value(
            getattr(silo, "description", "") or "", max_len=200
        )
        if silo_desc:
            purpose = f"Search for documents and information about {silo_desc}."
        else:
            purpose = "Search for relevant documents and information."

    metadata_def = getattr(silo, "metadata_definition", None)
    raw_fields: list[dict[str, Any]] = []
    if metadata_def is not None:
        raw_fields = metadata_def.fields or []

    fields_lines: list[str] = []
    for field_spec in raw_fields:
        if not isinstance(field_spec, dict):
            continue
        field_name = field_spec.get("name", "")
        if not field_name or not _is_valid_identifier(field_name):
            continue

        # Use canonical type name — raw editor string must not reach the prompt.
        field_type = _resolve_python_type(field_spec.get("type", "str"), field_name).__name__
        field_desc_raw = field_spec.get("description", "") or ""
        # max_len=120 (vs 200 in args schema): description has a 2000-char global budget.
        field_desc = sanitize_metadata_value(field_desc_raw, max_len=120)

        field_raw_values = distinct_values.get(field_name, [])
        examples: list[str] = []
        seen_ex: set[str] = set()
        for raw in field_raw_values:
            clean = sanitize_metadata_value(raw)
            if clean and clean not in seen_ex:
                seen_ex.add(clean)
                examples.append(clean)
            if len(examples) >= MAX_EXAMPLE_VALUES:
                break

        line = f"- {field_name} ({field_type}): {field_desc}."
        if examples:
            line += f" Example values: {', '.join(examples)}."

        fields_lines.append(line)

    usage_policy = (
        "When to filter: apply a metadata filter only when the user's question "
        "explicitly mentions a value for that field. "
        "If a filtered search returns zero results, retry without filters and "
        "show the available field values to help the user refine their query."
    )

    sections: list[str] = [purpose]

    if fields_lines:
        fields_block = "Filterable metadata fields:\n" + "\n".join(fields_lines)
        sections.append(fields_block)

    sections.append(usage_policy)

    full_text = "\n\n".join(sections)
    if len(full_text) <= _MAX_DESCRIPTION_LENGTH:
        return full_text

    # Shorten fields block first, then purpose blurb.
    budget = _MAX_DESCRIPTION_LENGTH - len(usage_policy) - 4  # "\n\n" separators

    if fields_lines:
        truncated_fields: list[str] = []
        used = len("Filterable metadata fields:\n")
        for line in fields_lines:
            candidate = used + len(line) + 1  # +1 for newline
            if candidate > budget - len(purpose) - 4:
                truncated_fields.append("...")
                break
            truncated_fields.append(line)
            used = candidate
        fields_block = "Filterable metadata fields:\n" + "\n".join(truncated_fields)
        result = "\n\n".join([purpose, fields_block, usage_policy])
    else:
        result = "\n\n".join([purpose, usage_policy])

    return result[:_MAX_DESCRIPTION_LENGTH]


def build_retriever_tool_name(silo: Any) -> str:
    """Build a stable unique tool name: ``search_{slug}_{silo_id}``.

    Falls back to ``search_silo_{silo_id}`` when the name slug is empty.
    """
    silo_id = getattr(silo, "silo_id", "unknown")
    raw_name: str = getattr(silo, "name", "") or ""
    slug = _make_slug(raw_name)

    if not slug:
        return f"search_silo_{silo_id}"
    return f"search_{slug}_{silo_id}"


def collect_distinct_values(silo: Any, db: Any) -> dict[str, list[str]]:
    """Collect distinct metadata field values for all fields in a silo.

    Errors on individual fields are caught and logged; the corresponding key is
    absent from the result.

    Returns:
        ``{field_name: [value, ...]}`` mapping.
    """
    # Deferred import to avoid circular dependency at module load time.
    from services.metadata_values_cache_service import MetadataValuesCacheService  # noqa: PLC0415

    metadata_def = getattr(silo, "metadata_definition", None)
    if metadata_def is None:
        return {}

    raw_fields: list[dict[str, Any]] = metadata_def.fields or []
    result: dict[str, list[str]] = {}

    for field_spec in raw_fields:
        if not isinstance(field_spec, dict):
            continue
        field_name = field_spec.get("name", "")
        if not field_name:
            continue

        try:
            values = MetadataValuesCacheService.get_distinct_values(
                silo_id=silo.silo_id,
                field=field_name,
                db=db,
            )
            result[field_name] = values
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "retriever_tool_builder.collect_distinct_values: "
                "error fetching values for silo=%s field=%r: %s — key omitted",
                getattr(silo, "silo_id", "?"),
                field_name,
                exc,
            )

    return result
