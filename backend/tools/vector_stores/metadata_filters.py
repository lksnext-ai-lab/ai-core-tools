"""
Metadata-aware filter construction for vector store retrieval.

Self-contained: no imports from ``tools.agentTools`` or ``services.silo_service``
to avoid circular import cycles.

Neither store's translation layer handles ``$and`` as a top-level key, so
``merge_filters_and`` combines filters field-by-field.  When the same (field, op)
pair appears in two dicts with different values the *first* dict wins (pinned /
agent-configured filters take priority over LLM-inferred ones).  Conflicts are
logged as WARNING without logging actual values (injection guard).

Security note: ``sanitize_metadata_value`` must NOT be applied to filter values —
filter values must match stored metadata exactly and are passed as SQL bind
parameters.  It is reserved for descriptions and enum labels embedded in LLM tool
definitions.  Applying it to filter values would silently corrupt matches.
"""

import logging
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)


PGVECTOR_OPS: frozenset[str] = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in"})
QDRANT_OPS: frozenset[str] = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in"})

MAX_ENUM_VALUES: int = 25
MAX_EXAMPLE_VALUES: int = 10

# Fields written during indexation that are always filterable regardless of metadata_definition.
SYSTEM_METADATA_FIELDS: frozenset[str] = frozenset({"page", "name", "url", "file_type"})

_SYSTEM_FIELD_TYPES: dict[str, str] = {
    "page": "int",
    "name": "str",
    "url": "str",
    "file_type": "str",
}

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+.*?instructions?", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"forget\s+(?:all\s+)?(?:previous\s+)?instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+(?:now\s+)?", re.IGNORECASE),
    re.compile(r"act\s+as\s+", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"prompt\s+injection", re.IGNORECASE),
]


class MetadataFilterClause(BaseModel):
    """A single metadata filter predicate.

    For ``$in`` the value must be a list.  Field and op are validated at
    construction; ``validate_clauses`` applies per-backend operator whitelisting
    at runtime.
    """

    model_config = ConfigDict(arbitrary_types_allowed=False)

    field: str
    op: str
    value: Any

    @field_validator("field")
    @classmethod
    def field_must_be_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("MetadataFilterClause.field must be a non-empty string")
        return stripped

    @field_validator("op")
    @classmethod
    def op_must_be_known(cls, v: str) -> str:
        all_ops = PGVECTOR_OPS | QDRANT_OPS
        if v not in all_ops:
            raise ValueError(
                f"MetadataFilterClause.op '{v}' is not in the known operator set "
                f"{sorted(all_ops)}"
            )
        return v


def ops_for_backend(vector_db_type: str) -> frozenset[str]:
    """Return the operator whitelist for the given backend. Defaults to QDRANT_OPS for unknowns."""
    if (vector_db_type or "").upper() == "PGVECTOR":
        return PGVECTOR_OPS
    return QDRANT_OPS


def validate_clauses(
    clauses: list[MetadataFilterClause],
    metadata_definition: Any | None,
    backend_ops: frozenset[str],
) -> list[MetadataFilterClause]:
    """Discard clauses that reference unknown fields or unsupported operators.

    When ``metadata_definition`` is None only ``SYSTEM_METADATA_FIELDS`` are
    allowed.  Rejected clauses are logged as WARNING without values.  Never raises.
    """
    if metadata_definition is not None:
        raw_fields: list[dict[str, Any]] = metadata_definition.fields or []
        allowed_fields: frozenset[str] = frozenset(
            f["name"] for f in raw_fields if isinstance(f, dict) and f.get("name")
        ) | SYSTEM_METADATA_FIELDS
    else:
        allowed_fields = SYSTEM_METADATA_FIELDS

    valid: list[MetadataFilterClause] = []
    for clause in clauses:
        if clause.field not in allowed_fields:
            logger.warning(
                "metadata_filters.validate_clauses: field '%s' not in allowed fields; clause discarded",
                clause.field,
            )
            continue
        if clause.op not in backend_ops:
            logger.warning(
                "metadata_filters.validate_clauses: op '%s' on field '%s' not in backend whitelist; clause discarded",
                clause.op,
                clause.field,
            )
            continue
        valid.append(clause)
    return valid


def _convert_single_value(value: Any, field_type: str, field: str) -> tuple[Any, bool]:
    """Coerce *value* to *field_type*. Returns ``(converted, ok)``; ok=False on failure."""
    if value is None:
        logger.warning(
            "metadata_filters.convert_clause_types: None value for field '%s'; clause discarded",
            field,
        )
        return None, False

    try:
        if field_type == "int":
            return int(value), True
        if field_type == "float":
            return float(value), True
        if field_type == "bool":
            if isinstance(value, bool):
                return value, True
            as_str = str(value).strip().lower()
            if as_str in {"true", "1", "yes"}:
                return True, True
            if as_str in {"false", "0", "no"}:
                return False, True
            raise ValueError(f"Cannot convert {value!r} to bool")
        return str(value) if not isinstance(value, str) else value, True
    except (ValueError, TypeError):
        logger.warning(
            "metadata_filters.convert_clause_types: cannot convert value for field '%s' to type '%s'; clause discarded",
            field,
            field_type,
        )
        return None, False


def convert_clause_types(
    clauses: list[MetadataFilterClause],
    metadata_definition: Any | None,
) -> list[MetadataFilterClause]:
    """Coerce clause values to the declared Python type for each field.

    System fields use ``_SYSTEM_FIELD_TYPES``; unknown types default to ``str``.
    For ``$in``, every element is converted individually — any failure discards
    the whole clause.  Failed conversions are logged as WARNING (no values).
    Never raises.
    """
    if metadata_definition is not None:
        raw_fields: list[dict[str, Any]] = metadata_definition.fields or []
        field_type_map: dict[str, str] = {
            f["name"]: f.get("type", "str")
            for f in raw_fields
            if isinstance(f, dict) and f.get("name")
        }
    else:
        field_type_map = {}

    # System field types take precedence over user-declared types.
    effective_type_map: dict[str, str] = {**field_type_map, **_SYSTEM_FIELD_TYPES}

    result: list[MetadataFilterClause] = []
    for clause in clauses:
        field_type = effective_type_map.get(clause.field, "str")

        if clause.op == "$in":
            if not isinstance(clause.value, list):
                logger.warning(
                    "metadata_filters.convert_clause_types: $in value for field '%s' is not a list; clause discarded",
                    clause.field,
                )
                continue

            converted_list: list[Any] = []
            ok = True
            for item in clause.value:
                converted, item_ok = _convert_single_value(item, field_type, clause.field)
                if not item_ok:
                    ok = False
                    break
                converted_list.append(converted)

            if not ok:
                continue
            if not converted_list:
                logger.warning(
                    "metadata_filters.convert_clause_types: $in list for field '%s' is empty after conversion; clause discarded",
                    clause.field,
                )
                continue
            result.append(MetadataFilterClause(field=clause.field, op=clause.op, value=converted_list))
        else:
            converted, ok = _convert_single_value(clause.value, field_type, clause.field)
            if not ok:
                continue
            result.append(MetadataFilterClause(field=clause.field, op=clause.op, value=converted))

    return result


def to_backend_filter(clauses: list[MetadataFilterClause]) -> dict[str, Any]:
    """Translate clauses to a ``{field: {op: value}}`` dict accepted by both stores.

    Multiple clauses on the same field are merged into one field dict
    (AND at field level).  Duplicate (field, op) pairs keep the first value
    and log a WARNING.
    """
    result: dict[str, Any] = {}
    for clause in clauses:
        if clause.field not in result:
            result[clause.field] = {}
        if clause.op in result[clause.field]:
            if result[clause.field][clause.op] != clause.value:
                logger.warning(
                    "metadata_filters.to_backend_filter: duplicate (field='%s', op='%s'); keeping first value",
                    clause.field,
                    clause.op,
                )
        else:
            result[clause.field][clause.op] = clause.value
    return result


def merge_filters_and(*filter_dicts: dict[str, Any]) -> dict[str, Any]:
    """Merge Mongo-style filter dicts with AND semantics.

    Neither store supports a ``$and`` top-level key, so merging is done at the
    field / operator level.  The first dict wins on (field, op) conflicts —
    pinned / agent-level filters always beat LLM-inferred ones when passed first.
    Conflicts are logged as WARNING without logging actual values.
    """
    merged: dict[str, Any] = {}

    for filter_dict in filter_dicts:
        for field, spec in filter_dict.items():
            if field not in merged:
                merged[field] = dict(spec) if isinstance(spec, dict) else spec
                continue

            if not isinstance(spec, dict):
                if merged[field] != spec:
                    logger.warning(
                        "metadata_filters.merge_filters_and: conflict on field '%s'; keeping first value",
                        field,
                    )
                continue

            if not isinstance(merged[field], dict):
                logger.warning(
                    "metadata_filters.merge_filters_and: conflict on field '%s' (plain vs op dict); keeping first value",
                    field,
                )
                continue

            for op, value in spec.items():
                if op in merged[field]:
                    if merged[field][op] != value:
                        logger.warning(
                            "metadata_filters.merge_filters_and: conflict on field '%s' op '%s'; keeping first value",
                            field,
                            op,
                        )
                else:
                    merged[field][op] = value

    return merged


def sanitize_metadata_value(value: str, max_len: int = 80) -> str:
    """Sanitize a string for safe embedding in LLM tool definitions.

    Must NOT be applied to filter values — filter values must match stored
    metadata exactly and are passed as SQL bind parameters.  Applying this
    function to filter values would silently corrupt matches.

    Applies in order: NFKC normalization, whitespace collapse, removal of
    injection-facilitating punctuation (`` ` <>{} ``), neutralization of
    known prompt-injection patterns, re-collapse, truncation to *max_len*.
    Never raises.
    """
    if not isinstance(value, str):
        return value  # type: ignore[return-value]

    sanitized = unicodedata.normalize("NFKC", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    sanitized = sanitized.translate(str.maketrans("", "", "`<>{}"))

    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub("", sanitized)

    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:max_len]


def build_filter_dict(
    clauses: list[MetadataFilterClause],
    metadata_definition: Any | None,
    vector_db_type: str,
) -> dict[str, Any]:
    """Build a backend-ready filter dict from a list of clauses.

    Runs the full pipeline: ``ops_for_backend`` → ``validate_clauses`` →
    ``convert_clause_types`` → ``to_backend_filter``.  Invalid clauses are
    discarded with WARNING log entries (no values logged).  Never raises.
    """
    backend_ops = ops_for_backend(vector_db_type)
    valid = validate_clauses(clauses, metadata_definition, backend_ops)
    typed = convert_clause_types(valid, metadata_definition)
    return to_backend_filter(typed)
