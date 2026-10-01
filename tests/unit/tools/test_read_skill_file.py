"""
Unit tests — step_021 (P3 verification gate): AC-19 ``read_skill_file`` core behaviour
==========================================================================================

``tests/unit/tools/test_skill_tools.py`` already has extensive coverage of
``read_skill_file`` FOR the step_020 "surface a reactivation error on every
return path" fix (``TestReadSkillFileSurfacesReactivationErrorOnEveryPath``)
and of the available-paths cap. This module covers the plain AC-19 behaviours
that were only ever exercised *combined* with a reactivation-error fixture
there, plus the ones not exercised at all yet: binary-file notice (never raw
bytes), the plain not-found + available-paths listing (no reactivation
confound), and a skill not attached to / disabled for this agent being
refused — mirroring the equivalent ``load_skill`` coverage in
``TestCreateSkillLoaderTool.test_disabled_skill_not_loadable``, which
``read_skill_file`` never had its own version of.
"""

from __future__ import annotations

from tools.skill_tools import SkillSnapshot, create_skill_file_reader_tool


def _snapshot(skill_id: int = 1, name: str = "alpha", content: str = "c") -> SkillSnapshot:
    return SkillSnapshot(skill_id=skill_id, name=name, content=content)


class TestReadSkillFileTextContent:
    def test_returns_text_content_as_is(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("readme.txt", "text/plain", 11, "abc", True)],
            file_content_provider=lambda skill_id, path: (True, "hello world"),
        )
        result = tool.invoke({"skill_name": "alpha", "path": "readme.txt"})

        assert "hello world" in result

    def test_scopes_lookup_to_the_requested_skill_id(self):
        """list_paths_provider/file_content_provider are called with the resolved
        skill's own skill_id — never a caller-supplied or cross-skill id."""
        seen_skill_ids = []

        def list_paths(skill_id):
            seen_skill_ids.append(skill_id)
            return [("readme.txt", "text/plain", 11, "abc", True)]

        def content_provider(skill_id, path):
            seen_skill_ids.append(skill_id)
            return (True, "hello world")

        tool = create_skill_file_reader_tool(
            [_snapshot(skill_id=42, name="alpha")],
            list_paths_provider=list_paths,
            file_content_provider=content_provider,
        )
        tool.invoke({"skill_name": "alpha", "path": "readme.txt"})

        assert seen_skill_ids == [42, 42]

    def test_very_large_text_content_is_truncated(self, monkeypatch):
        import config as settings

        monkeypatch.setattr(settings, "SANDBOX_MAX_OUTPUT_CHARS", 50, raising=False)
        big_content = "x" * 500

        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("big.txt", "text/plain", 500, "abc", True)],
            file_content_provider=lambda skill_id, path: (True, big_content),
        )
        result = tool.invoke({"skill_name": "alpha", "path": "big.txt"})

        assert "truncated" in result
        assert "x" * 500 not in result


class TestReadSkillFileBinaryNotice:
    def test_binary_file_declared_by_metadata_returns_notice_not_content(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("image.png", "image/png", 2048, "abc", False)],
            file_content_provider=lambda skill_id, path: (False, b"\x89PNG\r\n\x1a\n"),
        )
        result = tool.invoke({"skill_name": "alpha", "path": "image.png"})

        assert "binary file" in result
        assert "2048 bytes" in result
        # Never the raw bytes/text-decoded content.
        assert "PNG" not in result
        assert "\x89" not in result

    def test_binary_notice_short_circuits_before_fetching_content(self):
        """The metadata alone (is_text=False) is enough to report the binary
        notice — the file content is never even fetched."""
        calls = []

        def content_provider(skill_id, path):
            calls.append((skill_id, path))
            raise AssertionError("must not be called for a file already known to be binary")

        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("image.png", "image/png", 2048, "abc", False)],
            file_content_provider=content_provider,
        )
        result = tool.invoke({"skill_name": "alpha", "path": "image.png"})

        assert "binary file" in result
        assert calls == []

    def test_provider_disagreeing_with_metadata_is_still_treated_as_binary(self):
        """Defensive: even if list_paths_provider said is_text=True but the actual
        fetched content comes back non-text (or raw bytes), never forward it as
        text — this is the defence-in-depth branch, not the metadata fast path."""
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("mystery.dat", None, 10, "abc", True)],
            file_content_provider=lambda skill_id, path: (False, b"\x00\x01\x02"),
        )
        result = tool.invoke({"skill_name": "alpha", "path": "mystery.dat"})

        assert "binary file" in result
        assert "\x00" not in result

    def test_raw_bytes_content_is_never_forwarded_even_if_flagged_text(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [("mystery.dat", None, 10, "abc", True)],
            file_content_provider=lambda skill_id, path: (True, b"\x00\x01\x02raw bytes"),
        )
        result = tool.invoke({"skill_name": "alpha", "path": "mystery.dat"})

        assert "binary file" in result
        assert "raw bytes" not in result


class TestReadSkillFileUnknownPath:
    def test_unknown_path_lists_available_paths(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [
                ("readme.txt", "text/plain", 5, "abc", True),
                ("config.yaml", "text/yaml", 5, "def", True),
            ],
            file_content_provider=lambda skill_id, path: None,
        )
        result = tool.invoke({"skill_name": "alpha", "path": "does_not_exist.txt"})

        assert "not found" in result
        assert "readme.txt" in result
        assert "config.yaml" in result

    def test_no_files_bundled_reports_empty_listing(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=lambda skill_id: [],
            file_content_provider=lambda skill_id, path: None,
        )
        result = tool.invoke({"skill_name": "alpha", "path": "anything.txt"})

        assert "not found" in result
        assert "no files bundled with this skill" in result

    def test_invalid_path_rejected_before_any_provider_call(self):
        calls = []

        def list_paths(skill_id):
            calls.append(skill_id)
            return []

        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=list_paths,
            file_content_provider=lambda skill_id, path: None,
        )
        result = tool.invoke({"skill_name": "alpha", "path": "../../etc/passwd"})

        assert "Invalid path" in result
        assert calls == []


class TestReadSkillFileUnattachedOrDisabledSkillRefused:
    def test_skill_not_attached_to_this_agent_is_refused(self):
        """Only snapshots actually passed in (i.e. skills resolve_agent_skills
        already scoped to this agent) are reachable — anything else, even a
        real skill name that exists elsewhere, is refused."""
        tool = create_skill_file_reader_tool(
            [_snapshot(skill_id=1, name="alpha")],
            list_paths_provider=lambda skill_id: [("readme.txt", "text/plain", 5, "abc", True)],
            file_content_provider=lambda skill_id, path: (True, "hello"),
        )
        result = tool.invoke({"skill_name": "some-other-skill", "path": "readme.txt"})

        assert "not found or not attached to this agent" in result
        assert "alpha" in result  # names the one skill that IS available

    def test_disabled_skill_dropped_upstream_is_unreachable(self):
        """resolve_agent_skills (step_013/AD-13) already drops disabled skills
        before building this tool's snapshot list — a disabled skill is
        therefore simply never in `skills_or_associations` and is refused
        exactly like any other unknown name."""
        # Only the ENABLED skill's snapshot reaches create_skill_file_reader_tool
        # — this mirrors what resolve_agent_skills would have produced for an
        # agent with one enabled and one disabled skill attached.
        tool = create_skill_file_reader_tool(
            [_snapshot(skill_id=1, name="enabled-skill")],
            list_paths_provider=lambda skill_id: [("readme.txt", "text/plain", 5, "abc", True)],
            file_content_provider=lambda skill_id, path: (True, "hello"),
        )
        result = tool.invoke({"skill_name": "disabled-skill", "path": "readme.txt"})

        assert "not found or not attached to this agent" in result

    def test_no_skills_at_all_returns_none_tool(self):
        tool = create_skill_file_reader_tool(
            [],
            list_paths_provider=lambda skill_id: [],
            file_content_provider=lambda skill_id, path: None,
        )
        assert tool is None

    def test_no_providers_returns_none_tool(self):
        tool = create_skill_file_reader_tool(
            [_snapshot()],
            list_paths_provider=None,
            file_content_provider=None,
        )
        assert tool is None
