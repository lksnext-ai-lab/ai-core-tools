"""SKILL.md frontmatter contract: parse and render.

Pure functions, no DB and no FastAPI imports.

IMPORTANT: ``allowed_tools`` is metadata only. It is preserved for round-trip fidelity and display, and it MUST
NEVER be used to filter, restrict or grant tools at execution time (AD-15).

Security notes:
    * Only ``yaml.safe_load``-equivalent construction is used (a ``SafeLoader`` subclass).
    * The frontmatter block (text between the fences) is capped at 64 KiB, on both parse and render, so an
      exported SKILL.md is always re-importable (checked while scanning for the closing fence, before the body is
      split), YAML anchors/aliases and merge keys (``<<``) are rejected (billion-laughs and hidden-key tricks),
      duplicate keys are rejected and the nesting depth is capped.
    * String values/keys must be encodable as UTF-8 and must not contain NUL, U+0085, U+2028 or U+2029.
    * ``name`` is used later as a sandbox directory name, so it is restricted to ``[a-z0-9._-]``, must not start
      with ``.`` or ``-``, must not end with ``.``, must not contain ``..`` and must not be a Windows device name.
    * Validation of ``bootstrap_script_path`` against package contents is done by the import service, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

MAX_FRONTMATTER_BYTES = 64 * 1024
MAX_NAME_LENGTH = 100
MAX_YAML_DEPTH = 20
_NAME_RE = re.compile(r"^[a-z0-9._-]+$")
_RESERVED_NAMES = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                             *(f"lpt{i}" for i in range(1, 10))})
_LINE_BREAK_CHARS = ("\x85", "\u2028", "\u2029")

# Declared key order for rendering: (field, yaml key).
_DECLARED_KEYS: tuple[tuple[str, str], ...] = (
    ("name", "name"),
    ("display_name", "display_name"),
    ("description", "description"),
    ("when_to_use", "when_to_use"),
    ("disable_model_invocation", "disable-model-invocation"),
    ("allowed_tools", "allowed-tools"),
    ("runtime", "runtime"),
    ("bootstrap_script_path", "bootstrap_script_path"),
    ("runtime_options", "runtime_options"),
)
# Public: names of the fields that have dedicated handling (everything else in a frontmatter is ``extra``).
DECLARED_FIELDS: frozenset[str] = frozenset(name for name, _ in _DECLARED_KEYS)
_KEY_ALIASES: dict[str, str] = {}
for _field, _key in _DECLARED_KEYS:
    _KEY_ALIASES[_key] = _field
    _KEY_ALIASES[_key.replace("-", "_")] = _field
    _KEY_ALIASES[_key.replace("_", "-")] = _field
_STRING_FIELDS = ("display_name", "description", "when_to_use", "runtime", "bootstrap_script_path")


class SkillFrontmatterError(Exception):
    """Raised for any SKILL.md frontmatter failure."""

    def __init__(self, key: str | None, line: int | None, message: str) -> None:
        key = str(key)[:100] if key is not None else None
        self.key = key
        self.line = line
        self.message = message
        parts = []
        if key:
            parts.append(f"key {key!r}")
        if line is not None:
            parts.append(f"line {line}")
        prefix = f"[{', '.join(parts)}] " if parts else ""
        super().__init__(f"{prefix}{message}")


@dataclass
class ParsedSkillMd:
    """Parsed SKILL.md content."""

    name: str
    display_name: str | None = None
    description: str | None = None
    when_to_use: str | None = None
    disable_model_invocation: bool = False
    allowed_tools: list[str] = field(default_factory=list)
    runtime: str | None = None
    bootstrap_script_path: str | None = None
    runtime_options: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    body: str = ""


class _NoAliasSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects anchors, aliases, merge keys and duplicate keys."""

    def compose_node(self, parent: Any, index: Any) -> Any:  # noqa: D102
        if self.check_event(yaml.events.AliasEvent):
            ev = self.peek_event()
            raise SkillFrontmatterError(None, ev.start_mark.line + 2, "YAML aliases are not allowed")
        ev = self.peek_event()
        if getattr(ev, "anchor", None) is not None:
            raise SkillFrontmatterError(None, ev.start_mark.line + 2, "YAML anchors are not allowed")
        return super().compose_node(parent, index)

    def flatten_mapping(self, node: Any) -> None:  # noqa: D102
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise SkillFrontmatterError(None, key_node.start_mark.line + 2, "YAML merge keys are not allowed")

    def construct_mapping(self, node: Any, deep: bool = False) -> Any:  # noqa: D102
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
            seen: set[Any] = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=True)
                try:
                    is_dup = key in seen
                    seen.add(key)
                except TypeError:
                    continue  # unhashable key: the base class raises a proper YAML error
                if is_dup:
                    raise SkillFrontmatterError(str(key), key_node.start_mark.line + 2, "duplicate key")
        return super().construct_mapping(node, deep=deep)


def _check_string(value: str, key: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise SkillFrontmatterError(key, None, "contains invalid Unicode (lone surrogate)") from None
    if "\x00" in value:
        raise SkillFrontmatterError(key, None, "contains a NUL character")
    if any(c in value for c in _LINE_BREAK_CHARS):
        raise SkillFrontmatterError(key, None, "contains an unsupported line separator (U+0085, U+2028, U+2029)")


def normalize_skill_name(value: Any, *, key: str = "name") -> str:
    """Normalise and validate a skill name.

    Args:
        value: Raw name value.
        key: Key reported in errors.

    Returns:
        The normalised name (stripped, whitespace collapsed to ``-``, lowercase).

    Raises:
        SkillFrontmatterError: If the name is missing, not a string or not a safe identifier.
    """
    if not isinstance(value, str):
        raise SkillFrontmatterError(key, None, "must be a string")
    _check_string(value, key)
    name = re.sub(r"\s+", "-", value.strip()).lower()
    if not name:
        raise SkillFrontmatterError(key, None, "is required and must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise SkillFrontmatterError(key, None, f"must be at most {MAX_NAME_LENGTH} characters")
    if not _NAME_RE.fullmatch(name):
        raise SkillFrontmatterError(key, None, "may only contain lowercase letters, digits, '.', '_' and '-'")
    if name[0] in ".-" or ".." in name or name.endswith("."):
        raise SkillFrontmatterError(key, None, "must not start with '.' or '-', end with '.' or contain '..'")
    if name.split(".")[0] in _RESERVED_NAMES:
        raise SkillFrontmatterError(key, None, "is a reserved device name")
    return name


def _check_body(body: str) -> None:
    try:
        body.encode("utf-8")
    except UnicodeEncodeError:
        raise SkillFrontmatterError("body", None, "contains invalid Unicode (lone surrogate)") from None
    if "\x00" in body:
        raise SkillFrontmatterError("body", None, "contains a NUL character")


def _check_safe_value(value: Any, key: str, depth: int = 0) -> None:
    if depth > MAX_YAML_DEPTH:
        raise SkillFrontmatterError(key, None, f"nesting deeper than {MAX_YAML_DEPTH} levels")
    if isinstance(value, str):
        _check_string(value, key)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise SkillFrontmatterError(key, None, "non-finite numbers are not allowed")
    elif isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value < 2**63:
            raise SkillFrontmatterError(key, None, "integer out of range (64-bit signed)")
    elif value is None or isinstance(value, bool):
        return
    elif isinstance(value, list):
        for item in value:
            _check_safe_value(item, key, depth + 1)
    elif isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise SkillFrontmatterError(key, None, "mapping keys must be strings")
            _check_string(k, key)
            _check_safe_value(v, key, depth + 1)
    else:
        raise SkillFrontmatterError(key, None, f"unsupported value type '{type(value).__name__}'")


def _split_frontmatter(raw: str) -> tuple[str | None, str]:
    text = raw[1:] if raw.startswith("\ufeff") else raw
    first_end = text.find("\n")
    first = text if first_end == -1 else text[:first_end]
    if first.rstrip("\r\n").rstrip() != "---":
        return None, text
    start = first_end + 1 if first_end != -1 else len(text)
    pos = start
    while pos < len(text):
        if pos - start > MAX_FRONTMATTER_BYTES:  # characters <= bytes, so this only rejects what _load_yaml rejects
            raise SkillFrontmatterError(
                None, None, f"frontmatter exceeds {MAX_FRONTMATTER_BYTES // 1024} KiB or is not closed with '---'"
            )
        end = text.find("\n", pos)
        line_end = len(text) if end == -1 else end + 1
        stripped = text[pos:line_end].rstrip("\r\n").rstrip()
        if stripped == "---":  # column-0 only; an indented '---' belongs to YAML (e.g. a block scalar)
            return text[start:pos], text[line_end:]
        pos = line_end
    raise SkillFrontmatterError(None, 1, "frontmatter block is not closed with '---'")


def _load_yaml(fm_text: str) -> dict[str, Any]:
    if len(fm_text.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise SkillFrontmatterError(None, None, f"frontmatter exceeds {MAX_FRONTMATTER_BYTES // 1024} KiB")
    try:
        data = yaml.load(fm_text, Loader=_NoAliasSafeLoader)  # noqa: S506 - SafeLoader subclass
    except SkillFrontmatterError:
        raise
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 2 if mark is not None else None  # +1 for 1-based, +1 for the opening '---'
        raise SkillFrontmatterError(None, line, f"invalid YAML: {exc.problem or 'syntax error'}") from None
    except yaml.YAMLError:
        raise SkillFrontmatterError(None, None, "invalid YAML") from None
    except (ValueError, TypeError, OverflowError):
        raise SkillFrontmatterError(None, None, "invalid YAML value") from None
    except RecursionError:
        raise SkillFrontmatterError(None, None, "YAML nesting too deep") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SkillFrontmatterError(None, 2, "frontmatter must be a YAML mapping")
    return data


def _parse_allowed_tools(value: Any) -> list[str]:
    key = "allowed-tools"
    if value is None:
        return []
    if isinstance(value, str):
        _check_string(value, key)
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise SkillFrontmatterError(key, None, "list items must be strings")
            _check_string(item, key)
            if item.strip():
                out.append(item.strip())
        return out
    raise SkillFrontmatterError(key, None, "must be a list or a comma-separated string")


def parse_skill_md(raw: str) -> ParsedSkillMd:
    """Parse the text of a SKILL.md file.

    Args:
        raw: Full file contents.

    Returns:
        The parsed frontmatter fields and the body.

    Raises:
        SkillFrontmatterError: On any invalid input (never a raw ``yaml`` or ``TypeError``).
    """
    if not isinstance(raw, str):
        raise SkillFrontmatterError(None, None, "SKILL.md content must be text")
    fm_text, body = _split_frontmatter(raw)
    data = _load_yaml(fm_text) if fm_text is not None else {}

    fields: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            raise SkillFrontmatterError(str(k), None, "frontmatter keys must be strings")
        _check_string(k, k)
        target = _KEY_ALIASES.get(k)
        if target is None:
            _check_safe_value(v, k)
            extra[k] = v
        elif target in fields:
            raise SkillFrontmatterError(k, None, "duplicate key (hyphen and underscore forms)")
        else:
            fields[target] = v

    if "name" not in fields:
        raise SkillFrontmatterError("name", None, "is required")
    _check_body(body)
    result = ParsedSkillMd(name=normalize_skill_name(fields["name"]), extra=extra, body=body)
    for fname in _STRING_FIELDS:
        val = fields.get(fname)
        if val is not None:
            if not isinstance(val, str):
                raise SkillFrontmatterError(fname, None, "must be a string")
            _check_string(val, fname)
            setattr(result, fname, val)
    dmi = fields.get("disable_model_invocation")
    if dmi is not None:
        if not isinstance(dmi, bool):
            raise SkillFrontmatterError("disable-model-invocation", None, "must be a boolean")
        result.disable_model_invocation = dmi
    result.allowed_tools = _parse_allowed_tools(fields.get("allowed_tools"))
    opts = fields.get("runtime_options")
    if opts is not None:
        if not isinstance(opts, dict):
            raise SkillFrontmatterError("runtime_options", None, "must be a mapping")
        _check_safe_value(opts, "runtime_options")
        result.runtime_options = opts
    return result


def render_skill_md(
    *,
    name: str,
    display_name: str | None = None,
    description: str | None = None,
    when_to_use: str | None = None,
    allowed_tools: list[str] | None = None,
    runtime: str | None = None,
    bootstrap_script_path: str | None = None,
    runtime_options: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    body: str = "",
    disable_model_invocation: bool = False,
) -> str:
    """Render a SKILL.md file with deterministic key order.

    Declared keys come first in a fixed order (empty/default values omitted), then ``extra`` keys sorted.

    Returns:
        The SKILL.md text; ``parse_skill_md`` of it yields the same field values.

    Raises:
        SkillFrontmatterError: If ``name`` or an ``extra`` value is invalid.
    """
    for fname, val in (
        ("display_name", display_name),
        ("description", description),
        ("when_to_use", when_to_use),
        ("runtime", runtime),
        ("bootstrap_script_path", bootstrap_script_path),
    ):
        if val is not None:
            if not isinstance(val, str):
                raise SkillFrontmatterError(fname, None, "must be a string")
            _check_string(val, fname)
    if not isinstance(disable_model_invocation, bool):
        raise SkillFrontmatterError("disable-model-invocation", None, "must be a boolean")
    if runtime_options is not None:
        if not isinstance(runtime_options, dict):
            raise SkillFrontmatterError("runtime_options", None, "must be a mapping")
        _check_safe_value(runtime_options, "runtime_options")
    if not isinstance(body, str):
        raise SkillFrontmatterError("body", None, "must be a string")
    _check_body(body)
    tools = _parse_allowed_tools(allowed_tools)
    values: dict[str, Any] = {
        "name": normalize_skill_name(name),
        "display_name": display_name,
        "description": description,
        "when_to_use": when_to_use,
        "disable_model_invocation": True if disable_model_invocation else None,
        "allowed_tools": tools or None,
        "runtime": runtime,
        "bootstrap_script_path": bootstrap_script_path,
        "runtime_options": dict(runtime_options) if runtime_options else None,
    }
    doc: dict[str, Any] = {}
    for fname, key in _DECLARED_KEYS:
        if values[fname] is not None:
            doc[key] = values[fname]
    for k in sorted((extra or {}), key=str):
        if not isinstance(k, str):
            raise SkillFrontmatterError(str(k), None, "extra keys must be strings")
        _check_string(k, k)
        if k in _KEY_ALIASES or k in doc:
            raise SkillFrontmatterError(k, None, "extra key collides with a declared key")
        _check_safe_value(extra[k], k)
        doc[k] = extra[k]
    dumped = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10**6)
    if any(ln.rstrip() == "---" for ln in dumped.splitlines()):
        # Never expected from PyYAML; fall back to double-quoted scalars so no line can look like a fence.
        dumped = yaml.safe_dump(
            doc, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10**6, default_style='"'
        )
        if any(ln.rstrip() == "---" for ln in dumped.splitlines()):
            raise SkillFrontmatterError(None, None, "cannot render a safe frontmatter block")
    if len(dumped.encode("utf-8")) > MAX_FRONTMATTER_BYTES:  # same accounting as _load_yaml: render ok => parse ok
        raise SkillFrontmatterError(None, None, f"rendered frontmatter exceeds {MAX_FRONTMATTER_BYTES} bytes")
    return f"---\n{dumped}---\n{body}"
