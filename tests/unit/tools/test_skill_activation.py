"""
Unit tests — step_021 (P3 verification gate): ``load_skill`` tool-level activation
======================================================================================

``tests/unit/tools/test_skill_tools.py`` already covers most of the
``load_skill`` tool's degradation/error-handling paths in depth
(``TestLoadSkillGracefulDegradation``, ``TestActivationFailureResponse``,
``TestAlreadyActiveDetection``, ``TestLoadSkillSurfacesReactivationErrorOnEveryPath``).
This module fills the two AC-15/AC-18 assertions that weren't pinned as their
own dedicated test yet:

  - AC-15: the tool's *result text* explicitly names the sandbox files
    directory (not just that ``SkillActivationResult.files_dir`` is set
    correctly — that part is covered at the provider level in
    ``test_sandbox_ensure_skill_providers.py``).
  - AC-18: when no sandbox is available this turn at all (``sandbox_handle``
    is ``None``, the common real-world "no code interpreter" case, not just
    ``sandbox_provider=None`` as the one existing test exercises), the tool
    returns content-only and calls **zero** provider methods — enforced here
    with a provider double that raises if any of its methods are invoked.
"""

from __future__ import annotations

from tools.sandbox.provider import SkillActivationResult, SkillPhaseResult
from tools.skill_tools import SkillSnapshot, create_skill_loader_tool


def _snapshot(skill_id: int = 1, name: str = "alpha", content: str = "ALPHA CONTENT HERE") -> SkillSnapshot:
    return SkillSnapshot(skill_id=skill_id, name=name, content=content)


class _NeverCalledProvider:
    """Explodes if any method is invoked — proves AC-18's "zero provider
    calls" claim rather than just inferring it from a passing test."""

    def __getattr__(self, item):
        raise AssertionError(f"provider.{item} must never be accessed when no sandbox is available")


def _never_called_payload_provider(skill_id):
    raise AssertionError("payload_provider must never be called when no sandbox is available")


class TestAC18NoSandboxIsContentOnlyWithZeroProviderCalls:
    def test_sandbox_handle_none_is_content_only_and_calls_nothing(self):
        """The realistic "no code interpreter enabled this turn" case: no
        sandbox_handle at all (not even a proxy object)."""
        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=None,
            sandbox_provider=_NeverCalledProvider(),
            payload_provider=_never_called_payload_provider,
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "ALPHA CONTENT HERE" in result
        assert "Files directory" not in result
        assert "[Sandbox status" not in result

    def test_sandbox_provider_none_is_content_only_and_calls_nothing(self):
        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=object(),
            sandbox_provider=None,
            payload_provider=_never_called_payload_provider,
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "ALPHA CONTENT HERE" in result
        assert "[Sandbox status" not in result

    def test_payload_provider_none_is_content_only_and_calls_nothing(self):
        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=object(),
            sandbox_provider=_NeverCalledProvider(),
            payload_provider=None,
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "ALPHA CONTENT HERE" in result
        assert "[Sandbox status" not in result

    def test_no_skills_configured_with_sandbox_absent_returns_none_tool(self):
        assert create_skill_loader_tool([], sandbox_handle=None, sandbox_provider=None, payload_provider=None) is None


class TestAC15ToolResultNamesTheFilesDirectory:
    def test_active_result_names_the_directory(self):
        class FakeHandle:
            pass

        class FakeProvider:
            def ensure_skill(self, handle, payload):
                return SkillActivationResult(
                    skill_name="alpha",
                    skill_id=1,
                    files_dir="/workspace/.skills/alpha",
                    phases=(
                        SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=5),
                    ),
                    status="active",
                )

        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=FakeHandle(),
            sandbox_provider=FakeProvider(),
            payload_provider=lambda skill_id: object(),
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "ALPHA CONTENT HERE" in result
        assert "Files directory: /workspace/.skills/alpha" in result
        assert "activated" in result

    def test_degraded_result_still_names_the_directory(self):
        class FakeHandle:
            pass

        class FakeProvider:
            def ensure_skill(self, handle, payload):
                return SkillActivationResult(
                    skill_name="alpha",
                    skill_id=1,
                    files_dir=".skills/alpha",  # Daytona-style relative root
                    phases=(
                        SkillPhaseResult(phase="files", status="ok", detail="materialised", duration_ms=5),
                        SkillPhaseResult(
                            phase="bootstrap", status="failed", detail="pip install failed", duration_ms=10
                        ),
                    ),
                    status="degraded",
                )

        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=FakeHandle(),
            sandbox_provider=FakeProvider(),
            payload_provider=lambda skill_id: object(),
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "ALPHA CONTENT HERE" in result
        assert "Files directory: .skills/alpha" in result
        assert "did not complete successfully" in result

    def test_failed_result_reports_error_without_naming_a_directory_as_success(self):
        class FakeHandle:
            pass

        class FakeProvider:
            def ensure_skill(self, handle, payload):
                return SkillActivationResult(
                    skill_name="alpha",
                    skill_id=1,
                    files_dir="/workspace/.skills/alpha",
                    phases=(
                        SkillPhaseResult(
                            phase="files", status="failed", detail="a different skill is already materialised",
                            duration_ms=1,
                        ),
                    ),
                    status="failed",
                )

        tool = create_skill_loader_tool(
            [_snapshot()],
            sandbox_handle=FakeHandle(),
            sandbox_provider=FakeProvider(),
            payload_provider=lambda skill_id: object(),
        )
        result = tool.invoke({"skill_name": "alpha"})

        assert "Error loading skill 'alpha'" in result
        assert "[Sandbox status" not in result
