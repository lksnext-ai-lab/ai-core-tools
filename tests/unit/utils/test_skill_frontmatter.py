"""Unit tests for utils.skill_frontmatter (parse/render contract and hardening). No database."""
import datetime
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from utils.skill_frontmatter import (
    MAX_FRONTMATTER_BYTES, ParsedSkillMd, SkillFrontmatterError, normalize_skill_name, parse_skill_md,
    render_skill_md,
)

CONTROL = ("\x00", "\x85", " ", " ")


def doc(fm: str, body: str = "body\n") -> str:
    return f"---\n{fm}\n---\n{body}"


def err(raw: str) -> SkillFrontmatterError:
    with pytest.raises(SkillFrontmatterError) as exc:
        parse_skill_md(raw)
    return exc.value


def render_from(p: ParsedSkillMd) -> str:
    d = asdict(p)
    return render_skill_md(**d)


class TestModuleContract:
    def test_error_is_not_value_error(self):
        assert not issubclass(SkillFrontmatterError, ValueError)
        assert issubclass(SkillFrontmatterError, Exception)

    def test_importable_without_database_env(self):
        import os
        env = {k: v for k, v in os.environ.items() if k != "SQLALCHEMY_DATABASE_URI"}
        backend = str(Path(__file__).resolve().parents[3] / "backend")
        env["PYTHONPATH"] = backend
        code = (
            "import sys, utils.skill_frontmatter, utils.skill_paths, utils.safe_zip;"
            "print('db.database' in sys.modules)"
        )
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "False"


class TestParseValid:
    def test_full_frontmatter(self):
        raw = (
            "---\n"
            "name: My-Skill\n"
            "display_name: My Skill\n"
            "description: Does things\n"
            "when_to_use: When needed\n"
            "disable-model-invocation: true\n"
            "allowed-tools: Read, Write\n"
            "runtime: python3.11\n"
            "bootstrap_script_path: scripts/setup.sh\n"
            "runtime_options:\n  timeout: 30\n  flags: [a, b]\n"
            "license: MIT\n"
            "---\n# Body\n\ntext\n"
        )
        p = parse_skill_md(raw)
        assert p.name == "my-skill"
        assert p.display_name == "My Skill"
        assert p.description == "Does things"
        assert p.when_to_use == "When needed"
        assert p.disable_model_invocation is True
        assert p.allowed_tools == ["Read", "Write"]
        assert p.runtime == "python3.11"
        assert p.bootstrap_script_path == "scripts/setup.sh"
        assert p.runtime_options == {"timeout": 30, "flags": ["a", "b"]}
        assert p.extra == {"license": "MIT"}
        assert p.body == "# Body\n\ntext\n"

    def test_minimal(self):
        p = parse_skill_md(doc("name: x"))
        assert p.name == "x" and p.description is None and p.allowed_tools == [] and p.runtime_options == {}
        assert p.disable_model_invocation is False and p.extra == {}

    def test_no_frontmatter_block_requires_name(self):
        e = err("# Just markdown\n")
        assert e.key == "name"

    def test_empty_frontmatter_requires_name(self):
        assert err("---\n---\nbody").key == "name"

    def test_non_string_input(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(b"---\nname: x\n---\n")  # type: ignore[arg-type]

    def test_frontmatter_must_be_mapping(self):
        e = err("---\n- a\n- b\n---\nbody")
        assert e.line == 2

    def test_bad_yaml_reports_line(self):
        e = err("---\nname: a\nfoo: [1, 2\n---\nbody")
        assert isinstance(e.line, int) and e.line >= 3
        assert f"line {e.line}" in str(e)

    def test_bad_yaml_line_on_tab_indent(self):
        e = err("---\nname: a\nk:\n\t- x\n---\nbody")
        assert e.line is not None


class TestName:
    @pytest.mark.parametrize("raw, expected", [
        ("My Skill", "my-skill"), ("  spaced   out ", "spaced-out"), ("a.b_c-d", "a.b_c-d"), ("x" * 100, "x" * 100),
        ("Con-tools", "con-tools"), ("confirm", "confirm"),
    ])
    def test_valid_normalised(self, raw, expected):
        assert normalize_skill_name(raw) == expected

    @pytest.mark.parametrize("bad", [
        ".", "..", "a/b", ".hidden", "-lead", "trail.", "a..b", "con", "CON", "nul", "com1", "lpt9", "con.txt",
        "x" * 101, "", "   ", "über", "a b/c", "a\\b",
    ])
    def test_invalid(self, bad):
        with pytest.raises(SkillFrontmatterError):
            normalize_skill_name(bad)

    @pytest.mark.parametrize("value", ["123", "[a]", "{a: b}", "true", "null"])
    def test_non_string_name_in_document(self, value):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: {value}"))

    def test_missing_name(self):
        assert err(doc("description: x")).key == "name"

    @pytest.mark.parametrize("bad", ["a/b", "..", ".", "con"])
    def test_invalid_name_in_document(self, bad):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: '{bad}'"))


class TestKeyMapping:
    @pytest.mark.parametrize("key, attr, value", [
        ("display-name", "display_name", "D"),
        ("when-to-use", "when_to_use", "W"),
        ("bootstrap-script-path", "bootstrap_script_path", "s.sh"),
        ("disable_model_invocation", "disable_model_invocation", True),
        ("allowed_tools", "allowed_tools", ["A"]),
        ("runtime-options", "runtime_options", {"a": 1}),
    ])
    def test_alternate_forms_map_to_field(self, key, attr, value):
        import json
        p = parse_skill_md(doc(f"name: x\n{key}: {json.dumps(value)}"))
        assert getattr(p, attr) == value
        assert p.extra == {}

    @pytest.mark.parametrize("a, b", [
        ("display_name", "display-name"),
        ("when_to_use", "when-to-use"),
        ("allowed-tools", "allowed_tools"),
        ("disable-model-invocation", "disable_model_invocation"),
    ])
    def test_duplicate_forms_rejected(self, a, b):
        val = "true" if "disable" in a else "x"
        e = err(doc(f"name: x\n{a}: {val}\n{b}: {val}"))
        assert "duplicate" in e.message

    def test_unknown_keys_preserved_in_extra(self):
        p = parse_skill_md(doc("name: x\nlicense: MIT\nmetadata:\n  a: [1, 2]\n  b: {c: d}\nversion: 1.5"))
        assert p.extra == {"license": "MIT", "metadata": {"a": [1, 2], "b": {"c": "d"}}, "version": 1.5}

    def test_non_string_frontmatter_key_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\n1: a"))


class TestAllowedTools:
    @pytest.mark.parametrize("yaml_value, expected", [
        ("Read, Write,, Bash", ["Read", "Write", "Bash"]),
        ("Read", ["Read"]),
        ("''", []),
        ("' , '", []),
        ("[Read, ' ', ' Bash ', '']", ["Read", "Bash"]),
        ("[]", []),
        ("null", []),
        ("", []),
    ])
    def test_forms(self, yaml_value, expected):
        assert parse_skill_md(doc(f"name: x\nallowed-tools: {yaml_value}")).allowed_tools == expected

    @pytest.mark.parametrize("yaml_value", ["5", "[1]", "{a: b}", "[[a]]", "true"])
    def test_invalid(self, yaml_value):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nallowed-tools: {yaml_value}"))

    @pytest.mark.parametrize("bad", ["\\u2028", "\\0"])
    def test_control_chars_in_items(self, bad):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\nallowed-tools: ["a{bad}"]'))


class TestTypedFields:
    @pytest.mark.parametrize("field", ["display_name", "description", "when_to_use", "runtime", "bootstrap_script_path"])
    def test_non_string_rejected(self, field):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\n{field}: 5"))

    def test_disable_model_invocation_must_be_bool(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\ndisable-model-invocation: 'yes'"))

    def test_runtime_options_must_be_mapping(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nruntime_options: [1]"))

    def test_date_in_runtime_options_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nruntime_options:\n  d: 2020-01-01"))

    def test_date_in_extra_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nwhen: 2020-01-01"))

    def test_nesting_depth_capped(self):
        deep = "[" * 25 + "]" * 25
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nk: {deep}"))

    def test_very_deep_nesting_is_frontmatter_error_not_recursion_error(self):
        deep = "[" * 5000 + "]" * 5000
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nk: {deep}"))


class TestYamlHardening:
    @pytest.mark.parametrize("fm", [
        "name: x\n<<: {a: 1}",
        "name: x\n<<: [{a: 1}, {b: 2}]",
        "name: x\n<<: 1",
        "name: x\n<<:",
        "name: x\nruntime_options:\n  <<: {a: 1}",
        "name: x\nk:\n  - <<: {a: 1}",
        "name: x\n? <<\n: {a: 1}",
    ])
    def test_merge_keys_rejected(self, fm):
        e = err(doc(fm))
        assert "merge" in e.message

    @pytest.mark.parametrize("fm, word", [
        ("name: x\na: &anc 1", "anchor"),
        ("name: x\na: &anc 1\nb: *anc", "anchor"),
        ("name: x\na: &anc [1]\nruntime_options:\n  z: *anc", "anchor"),
        ("name: x\na: &anc\n  q: 1", "anchor"),
    ])
    def test_anchors_and_aliases_rejected(self, fm, word):
        assert word in err(doc(fm)).message

    def test_billion_laughs_rejected_fast(self):
        fm = "name: x\na: &a [x, x, x, x]\nb: &b [*a, *a, *a, *a]\nc: &c [*b, *b, *b, *b]"
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(fm))

    def test_duplicate_keys_rejected(self):
        e = err(doc("name: x\ndescription: a\ndescription: b"))
        assert "duplicate" in e.message and e.line is not None

    def test_duplicate_nested_keys_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nruntime_options:\n  a: 1\n  a: 2"))

    def test_python_object_tags_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nk: !!python/object/apply:os.system ['echo']"))

    def test_oversized_frontmatter_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md("---\nname: x\nk: " + "a" * (MAX_FRONTMATTER_BYTES + 10) + "\n---\nb")


class TestNumbers:
    def test_5000_digit_int_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nn: {'9' * 5000}"))

    def test_5000_digit_int_in_runtime_options_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nruntime_options:\n  n: {'9' * 5000}"))

    def test_int64_max_accepted(self):
        assert parse_skill_md(doc(f"name: x\nn: {2**63 - 1}")).extra["n"] == 2**63 - 1

    def test_int64_min_accepted(self):
        assert parse_skill_md(doc(f"name: x\nn: {-(2**63)}")).extra["n"] == -(2**63)

    @pytest.mark.parametrize("n", [2**63, -(2**63) - 1])
    def test_beyond_int64_rejected(self, n):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nn: {n}"))

    @pytest.mark.parametrize("lit", [".nan", ".NaN", ".inf", "-.inf", "+.inf"])
    def test_non_finite_floats_rejected(self, lit):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f"name: x\nn: {lit}"))

    def test_non_finite_in_runtime_options_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc("name: x\nruntime_options:\n  n: .inf"))

    def test_bool_is_not_range_checked_as_int(self):
        assert parse_skill_md(doc("name: x\nflag: true")).extra["flag"] is True


class TestControlCharacters:
    ESC = {"\x00": "\\0", "\x85": "\\x85", " ": "\\u2028", " ": "\\u2029"}

    @pytest.mark.parametrize("ch", CONTROL)
    @pytest.mark.parametrize("field", ["description", "display_name", "when_to_use", "runtime", "bootstrap_script_path"])
    def test_rejected_in_string_fields(self, ch, field):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\n{field}: "a{self.ESC[ch]}b"'))

    @pytest.mark.parametrize("ch", CONTROL)
    def test_rejected_in_keys(self, ch):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\n"a{self.ESC[ch]}b": 1'))

    @pytest.mark.parametrize("ch", CONTROL)
    def test_rejected_in_extra_values_nested(self, ch):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\nk:\n  - [{{a: "z{self.ESC[ch]}"}}]'))

    @pytest.mark.parametrize("ch", CONTROL)
    def test_rejected_in_runtime_options_values_and_keys(self, ch):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\nruntime_options:\n  a: "z{self.ESC[ch]}"'))
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md(doc(f'name: x\nruntime_options:\n  "k{self.ESC[ch]}": 1'))

    def test_lone_surrogate_rejected_everywhere(self):
        for fm in ('description: "\\ud800"', 'k: "\\ud800"', '"\\ud800": 1', 'runtime_options: {a: "\\ud800"}'):
            with pytest.raises(SkillFrontmatterError):
                parse_skill_md(doc(f"name: x\n{fm}"))

    def test_lone_surrogate_in_name_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            normalize_skill_name("a\ud800")

    def test_body_nul_rejected(self):
        e = err("---\nname: x\n---\nhello\x00world")
        assert e.key == "body"

    def test_body_lone_surrogate_rejected(self):
        assert err("---\nname: x\n---\nhi \ud800").key == "body"

    def test_body_u2028_accepted(self):
        assert parse_skill_md("---\nname: x\n---\na b c\x85d").body == "a b c\x85d"

    def test_error_messages_never_contain_raw_control_chars(self):
        cases = [
            'name: x\n"a\\u2028b": 1',
            'name: x\n"a\\0b": 1',
            'name: x\ndescription: "\\x85"',
        ]
        for fm in cases:
            msg = str(err(doc(fm)))
            assert not any(c in msg for c in CONTROL)
            assert all(ord(c) >= 0x20 for c in msg)

    def test_key_truncated_to_100_and_repr_d(self):
        e = err(doc('name: x\n"' + "k" * 300 + '\\u2028": 1'))
        assert len(e.key) == 100
        assert len(str(e)) < 300
        e2 = SkillFrontmatterError("k " + "z" * 200, None, "m")
        assert len(e2.key) == 100
        assert " " not in str(e2) and "\\u2028" in str(e2)


class TestFenceHandling:
    def test_column0_fence_terminates(self):
        p = parse_skill_md("---\nname: x\n---\nbody\n---\nmore")
        assert p.body == "body\n---\nmore"

    def test_indented_fence_inside_block_scalar_is_content(self):
        # Uses an `extra` key (not `description`) because this test targets fence-scan
        # robustness (an indented '---' inside a YAML block scalar must not be mistaken
        # for the closing fence) — `extra` values are not subject to the declared
        # single-line-field newline restriction added for description/when_to_use/etc
        # (see TestLineBreakRejection below).
        p = parse_skill_md("---\nname: x\nk: |\n  line\n  ---\n  more\n---\nbody")
        assert p.extra["k"] == "line\n---\nmore\n"
        assert p.body == "body"

    def test_unclosed_fence(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md("---\nname: x\ndescription: y\n")

    def test_unclosed_fence_huge(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md("---\nname: x\n" + "k: v\n" * 30000)

    def test_bom_accepted(self):
        assert parse_skill_md("﻿---\nname: x\n---\nb").name == "x"

    def test_crlf_accepted(self):
        p = parse_skill_md("---\r\nname: x\r\ndescription: d\r\n---\r\nbody\r\n")
        assert (p.name, p.description) == ("x", "d")
        assert p.body == "body\r\n"

    def test_fence_with_trailing_spaces(self):
        assert parse_skill_md("---  \nname: x\n---  \nb").body == "b"

    def test_dashes_prefix_is_not_a_fence(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md("----\nname: x\n----\nb")

    def test_body_only_when_no_block(self):
        # A document that does not start with the fence has no frontmatter at all.
        assert err("text\n---\nname: x\n---\n").key == "name"


class TestRenderValidation:
    def test_date_in_runtime_options(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", runtime_options={"d": datetime.date(2020, 1, 1)})

    def test_date_in_extra(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", extra={"d": datetime.date(2020, 1, 1)})

    @pytest.mark.parametrize("kw", [
        {"description": 5}, {"display_name": ["a"]}, {"when_to_use": 1.5}, {"runtime": b"x"},
        {"bootstrap_script_path": 0},
    ])
    def test_non_string_fields(self, kw):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", **kw)

    @pytest.mark.parametrize("flag", ["yes", 1, None])
    def test_non_bool_flag(self, flag):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", disable_model_invocation=flag)

    @pytest.mark.parametrize("tools", [[1], ["a", None], 5, {"a": 1}])
    def test_bad_allowed_tools(self, tools):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", allowed_tools=tools)

    def test_non_mapping_runtime_options(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", runtime_options=[1])  # type: ignore[arg-type]

    def test_non_string_body(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", body=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ["a\x00", "a ", "a\x85", "a\ud800"])
    def test_control_chars_rejected_in_fields(self, bad):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", description=bad)
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", extra={"k": bad})
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", runtime_options={"k": bad})
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", extra={bad: "v"})

    def test_body_nul_rejected(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", body="a\x00")

    def test_invalid_name(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="../x")

    def test_extra_key_collision_with_declared_key(self):
        for k in ("description", "display-name", "allowed_tools", "name"):
            with pytest.raises(SkillFrontmatterError):
                render_skill_md(name="x", extra={k: "v"})

    def test_non_string_extra_key(self):
        with pytest.raises(SkillFrontmatterError):
            render_skill_md(name="x", extra={1: "v"})  # type: ignore[dict-item]

    def test_extra_number_range_and_nonfinite(self):
        for v in (2**63, float("nan"), float("inf")):
            with pytest.raises(SkillFrontmatterError):
                render_skill_md(name="x", extra={"n": v})


class TestRoundTrip:
    CANONICAL = (
        "---\n"
        "name: my-skill\n"
        "display_name: My Skill\n"
        "description: Does things\n"
        "when_to_use: When needed\n"
        "disable-model-invocation: true\n"
        "allowed-tools:\n- Read\n- Write\n"
        "runtime: python3.11\n"
        "bootstrap_script_path: scripts/setup.sh\n"
        "runtime_options:\n  timeout: 30\n"
        "license: MIT\n"
        "---\n# Body\n"
    )

    def test_canonical_sample_is_stable(self):
        assert render_from(parse_skill_md(self.CANONICAL)) == self.CANONICAL

    def test_parse_render_parse_equal(self):
        p = parse_skill_md(self.CANONICAL)
        assert parse_skill_md(render_from(p)) == p

    def test_second_render_byte_identical(self):
        r1 = render_from(parse_skill_md(self.CANONICAL))
        r2 = render_from(parse_skill_md(r1))
        assert r1 == r2

    def test_extra_and_disable_model_invocation_round_trip(self):
        r = render_skill_md(name="x", disable_model_invocation=True, extra={"z": [1, {"a": None}], "a": 1.5})
        p = parse_skill_md(r)
        assert p.disable_model_invocation is True
        assert p.extra == {"a": 1.5, "z": [1, {"a": None}]}
        assert list(p.extra) == ["a", "z"] or set(p.extra) == {"a", "z"}
        assert r.index("a: 1.5") < r.index("z:")  # extra keys sorted

    def test_defaults_are_omitted(self):
        assert render_skill_md(name="X y") == "---\nname: x-y\n---\n"

    def test_declared_key_order(self):
        r = render_skill_md(name="x", runtime="r", description="d", display_name="D", when_to_use="w")
        keys = [ln.split(":")[0] for ln in r.splitlines()[1:-1]]
        assert keys == ["name", "display_name", "description", "when_to_use", "runtime"]

    HOSTILE = [
        "", " ", "\n", "x\n---\ny", "x\n...\ny", "---", "--- ", "...", "a: b", "a #b", "# c", "'q'", '"dq"',
        "it's", 'say "hi"', "back\\slash", "colon: at end:", ": lead", "- item", "? key", "!tag", "&anchor",
        "*alias", "<<", "%YAML 1.1", "@at", "`tick`", "{a: 1}", "[1, 2]", "null", "true", "no", "~", "123",
        "1e3", "0x1f", "2020-01-01", " lead", "trail ", "  both  ", "a\r\nb", "a\rb", "a\tb", "multi\nline\n",
        "trailing\n\n", "unicode é 日本 😀", "﻿bom", "x" * 300, "long " * 500,
    ]

    # Declared single-line fields (display_name/description/when_to_use/runtime/
    # bootstrap_script_path) reject embedded `\n`/`\r` (see TestLineBreakRejection) —
    # `extra`/`runtime_options` values and `body` do not carry that restriction, so this
    # subset (no `\n`/`\r`) is what's exercised against the declared fields below, while
    # the full HOSTILE list (including line breaks) still exercises extra/runtime_options/body.
    HOSTILE_SINGLE_LINE = [s for s in HOSTILE if "\n" not in s and "\r" not in s]

    @pytest.mark.parametrize("s", HOSTILE_SINGLE_LINE, ids=lambda s: repr(s)[:30])
    def test_hostile_strings_round_trip(self, s):
        r = render_skill_md(
            name="x", description=s, when_to_use=s, display_name=s, runtime=s, bootstrap_script_path=s,
            extra={"k": s, "nested": [s, {"d": s}]}, runtime_options={"o": s, "l": [s]}, body="body\n",
        )
        assert not any(ln.rstrip() == "---" for ln in r.split("---\n", 2)[1].splitlines())
        p = parse_skill_md(r)
        assert (p.description, p.when_to_use, p.display_name, p.runtime, p.bootstrap_script_path) == (s,) * 5
        assert p.extra == {"k": s, "nested": [s, {"d": s}]}
        assert p.runtime_options == {"o": s, "l": [s]}
        assert p.body == "body\n"
        assert render_from(p) == r

    @pytest.mark.parametrize("s", HOSTILE, ids=lambda s: repr(s)[:30])
    def test_hostile_strings_as_extra_values_round_trip(self, s):
        # `extra`/`runtime_options` values are not declared single-line fields, so the
        # full HOSTILE list (including embedded line breaks) is exercised here —
        # coverage for those two moved out of test_hostile_strings_round_trip above,
        # which now only feeds line-break-free strings into the declared fields.
        r = render_skill_md(
            name="x", extra={"k": s, "nested": [s, {"d": s}]}, runtime_options={"o": s, "l": [s]}, body="body\n",
        )
        p = parse_skill_md(r)
        assert p.extra == {"k": s, "nested": [s, {"d": s}]}
        assert p.runtime_options == {"o": s, "l": [s]}
        assert render_from(p) == r

    @pytest.mark.parametrize("s", HOSTILE, ids=lambda s: repr(s)[:30])
    def test_hostile_strings_as_extra_keys(self, s):
        r = render_skill_md(name="x", extra={s: "v"})
        assert parse_skill_md(r).extra == {s: "v"}


class TestLineBreakRejection:
    """Security (review-round Finding 1, belt-and-braces write-side fix): the declared
    single-line fields (`display_name`, `description`, `when_to_use`, `runtime`,
    `bootstrap_script_path`) must reject embedded `\\n`/`\\r` at both parse time (an
    imported/hand-authored SKILL.md) and render time (an admin-authored value from the
    UI) — this is what makes the `</available_skills>`-breakout class of payload
    impossible to ever get stored, and also closes the admin-review blind spot in the
    single-line `truncate` table cells that render these fields.
    """

    FIELDS = ["display_name", "description", "when_to_use", "runtime", "bootstrap_script_path"]

    # YAML double-quoted scalar escapes (`\n`/`\r` as literal backslash-n / backslash-r)
    # so the frontmatter text itself stays syntactically valid single-line YAML while
    # the *parsed* Python string still ends up containing a real line-break character —
    # exactly the shape an imported/hand-authored SKILL.md attack would take.
    YAML_ESCAPED_BAD = ['"a\\nb"', '"a\\rb"', '"a\\r\\nb"', '"\\n"', '"\\r"']

    @pytest.mark.parametrize("field", FIELDS)
    @pytest.mark.parametrize("bad", YAML_ESCAPED_BAD)
    def test_parse_rejects_line_breaks(self, field, bad):
        with pytest.raises(SkillFrontmatterError) as exc:
            parse_skill_md(f"---\nname: x\n{field}: {bad}\n---\nbody")
        assert exc.value.key == field

    @pytest.mark.parametrize("field", FIELDS)
    @pytest.mark.parametrize("bad", ["a\nb", "a\rb", "a\r\nb", "\n", "\r"])
    def test_render_rejects_line_breaks(self, field, bad):
        with pytest.raises(SkillFrontmatterError) as exc:
            render_skill_md(name="x", **{field: bad})
        assert exc.value.key == field

    @pytest.mark.parametrize("body", ["", "\n", "---\nnot fm\n---\n", "a b", "no trailing newline", "\r\n"])
    def test_body_round_trip(self, body):
        assert parse_skill_md(render_skill_md(name="x", body=body)).body == body


class TestRenderSizeCap:
    FIXED = len("name: x\ndescription: \n".encode())

    @staticmethod
    def _try(ch: str, n: int):
        try:
            r = render_skill_md(name="x", description=ch * n)
        except SkillFrontmatterError:
            return None
        return r

    def test_value_at_cap_renders_and_parses_back(self):
        n = MAX_FRONTMATTER_BYTES - self.FIXED
        r = self._try("a", n)
        assert r is not None
        assert parse_skill_md(r).description == "a" * n

    def test_value_above_cap_raises(self):
        assert self._try("a", MAX_FRONTMATTER_BYTES - self.FIXED + 1) is None

    @pytest.mark.parametrize("ch", ["a", "é", "日"])
    def test_no_unstable_band_around_boundary(self, ch):
        width = len(ch.encode())
        centre = (MAX_FRONTMATTER_BYTES - self.FIXED) // width
        outcomes = []
        for n in range(centre - 3, centre + 4):
            r = self._try(ch, n)
            outcomes.append(r is not None)
            if r is not None:
                assert parse_skill_md(r).description == ch * n, f"rendered but not re-parseable at n={n}"
        assert outcomes[0] is True and outcomes[-1] is False
        # monotonic: once it fails it keeps failing
        first_fail = outcomes.index(False)
        assert not any(outcomes[first_fail:])

    def test_parse_rejects_hand_written_oversize(self):
        with pytest.raises(SkillFrontmatterError):
            parse_skill_md("---\nname: x\ndescription: " + "a" * MAX_FRONTMATTER_BYTES + "\n---\n")
