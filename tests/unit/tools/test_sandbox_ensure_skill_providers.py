"""
Unit tests — step_021 (P3 verification gate): shared ``ensure_skill`` contract
=================================================================================

Exercises ``SandboxProvider.ensure_skill`` (the ABC default in
``tools/sandbox/provider.py``) against three lightweight **fake** provider
doubles that mirror the CURRENT ``skills_root()`` override contract of each
real provider (step_017/018 final API, see plan.md):

  - ``FakeOpenSandboxLikeProvider``: absolute root ``/workspace/.skills``
    (the ABC default, unoverridden — matches ``OpenSandboxProvider`` not
    overriding ``skills_root``).
  - ``FakeE2BLikeProvider``: absolute root ``/home/user/workspace/.skills``
    (matches ``E2BProvider.skills_root``).
  - ``FakeDaytonaLikeProvider``: bare **relative** root ``.skills`` (matches
    ``DaytonaProvider.skills_root`` — deliberately not absolute, see
    step_017/018's final API notes on why).

None of these doubles override ``_materialise_skill_files`` — they exercise
the ABC's own phase-1 (tar.gz upload+extract) and phase-2 (bootstrap) logic,
faking only ``write_file``/``read_file`` (an in-memory filesystem) and
``run_code`` (a small shell-command interpreter that understands exactly the
command shapes ``ensure_skill`` builds: the cleanup ``rm -rf``, the
``tar -xzf`` extraction, and the bootstrap wrapper).

Covers:
  - AC-15: files land at ``<root>/<name>/`` with matching relative paths/bytes.
  - AC-16: two ``ensure_skill`` calls for a skill with **no bootstrap script**
    → exactly one materialisation, second call is a genuine "already active"
    (round-1 bug: a fresh no-bootstrap activation must not be misdetected as
    already-active on its FIRST call).
  - AC-17: phase-1 failure → explicit ``status="failed"``; bootstrap-only
    failure → ``status="degraded"`` with files still usable.
  - AC-21: the same contract holds across all three provider doubles.
  - OQ-4: a name collision (different ``skill_id``, same normalised name) is
    refused with an explicit collision message — both in-memory (same
    process) and via the on-disk marker (simulated restart: fresh
    ``SandboxHandle``, same backing filesystem).
  - Concurrency: two threads calling ``ensure_skill`` for the same skill on
    the same handle → exactly one materialisation, the other gets the
    "activation already in progress" busy response.
  - Regression: bootstrap output truncation must not evict the success
    sentinel/marker (step_016 review-round bug) — a very large bootstrap
    stdout must still report ``status="active"``, not a false ``"degraded"``.
"""

from __future__ import annotations

import re
import tarfile
import threading
import time
from io import BytesIO
from typing import Dict, List, Tuple

import pytest

from schemas.skill_package_payload import SkillPackagePayload
from tools.sandbox.provider import SandboxExpiredError, SandboxHandle, SandboxProvider

_VERIFIED_SENTINEL_RE = re.compile(r"__SKILL_CMD_OK_[0-9a-f]+__")
_BOOTSTRAP_MARKER_RE = re.compile(r"__SKILL_BOOTSTRAP_RC_[0-9a-f]+__")


class _FakeProviderBase(SandboxProvider):
    """A genuine (non-mocked) ``SandboxProvider`` double with an in-memory
    filesystem and a small shell-command interpreter, so the ABC's own
    ``ensure_skill`` logic (locking, idempotency, markers, collision,
    fallback) runs for real against it — only the "sandbox" is fake.
    """

    requires_file_sync = True

    def __init__(self, *, root: str) -> None:
        self._root = root
        self.fs: Dict[str, bytes] = {}
        self.run_code_calls: List[str] = []
        self.fail_substrings: Tuple[str, ...] = ()
        # Command substrings that must raise SandboxExpiredError instead of
        # returning an "[Error] ..." string — simulates a genuinely dead
        # sandbox (as opposed to an ordinary command failure).
        self.expire_on_substrings: Tuple[str, ...] = ()
        # skill_name -> (exit_code, stdout) for the bootstrap phase; default
        # (missing key) is a successful, empty-output bootstrap.
        self.bootstrap_behavior: Dict[str, Tuple[int, str]] = {}
        self.max_output_chars_default = 20000
        self._extraction_delay_s = 0.0
        # Deterministic concurrency synchronization (MEDIUM fix, fix round 1):
        # set the moment extraction actually begins (i.e. after the reservation
        # critical section has been entered/released), so a racing thread can
        # `.wait()` on it instead of guessing an interleaving via time.sleep().
        self._extraction_started_event: threading.Event | None = None
        self._bootstrap_delay_s = 0.0
        self._bootstrap_started_event: threading.Event | None = None

    # -- lifecycle / not exercised here -----------------------------------
    def create_sandbox(self, working_dir, *, session_key=None, existing_sandbox_id=None):
        raise NotImplementedError

    def destroy_sandbox(self, handle):
        raise NotImplementedError

    def list_files(self, handle):
        raise NotImplementedError

    # -- skills_root override, per provider style --------------------------
    def skills_root(self, handle: SandboxHandle) -> str:
        return self._root

    # -- in-memory filesystem ----------------------------------------------
    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        self.fs[filename] = content

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        if filename not in self.fs:
            raise FileNotFoundError(filename)
        return self.fs[filename]

    # -- fake shell interpreter ---------------------------------------------
    def run_code(
        self,
        handle,
        code,
        *,
        language="bash",
        timeout=None,
        max_output_chars=None,
        on_stdout=None,
        on_stderr=None,
    ) -> str:
        self.run_code_calls.append(code)
        max_chars = max_output_chars or self.max_output_chars_default

        if any(s in code for s in self.expire_on_substrings):
            raise SandboxExpiredError("simulated dead sandbox")

        if any(s in code for s in self.fail_substrings):
            return self._apply_output_cap("[Error] simulated failure", max_chars)

        if "__SKILL_BOOTSTRAP_RC_" in code:
            output = self._run_bootstrap(code)
        elif "tar -xzf" in code:
            output = self._run_extraction(code)
        elif "rm -rf " in code:
            output = self._run_cleanup(code)
        else:
            # Generic verified command (mkdir -p, etc.) — succeed.
            sentinel_match = _VERIFIED_SENTINEL_RE.search(code)
            output = f"ok\n{sentinel_match.group(0)}\n" if sentinel_match else "ok"

        return self._apply_output_cap(output, max_chars)

    @staticmethod
    def _apply_output_cap(output: str, max_chars: int) -> str:
        """Mimic a real provider's own run_code truncation: keep the HEAD and
        append a truncation notice — the same shape ``opensandbox_provider``
        and friends use, which is what made the step_016 sentinel-eviction
        bug possible in the first place if the sentinel/marker line weren't
        kept short and last via the bounded ``tail -c 4000`` wrapping."""
        if len(output) <= max_chars:
            return output
        return output[:max_chars] + f"\n[Output truncated at {max_chars} characters]"

    def _run_cleanup(self, code: str) -> str:
        match = re.search(r"rm -rf (\S+)", code)
        if match:
            target = match.group(1)
            for key in list(self.fs):
                if key == target or key.startswith(target + "/"):
                    del self.fs[key]
        sentinel_match = _VERIFIED_SENTINEL_RE.search(code)
        return f"ok\n{sentinel_match.group(0)}\n" if sentinel_match else "ok"

    def _run_extraction(self, code: str) -> str:
        if self._extraction_started_event is not None:
            self._extraction_started_event.set()
        if self._extraction_delay_s:
            time.sleep(self._extraction_delay_s)
        match = re.search(r"tar -xzf (\S+) -C (\S+)", code)
        assert match, f"could not parse extraction command: {code!r}"
        archive_path, target_dir = match.group(1), match.group(2)
        archive_bytes = self.fs.get(archive_path)
        if archive_bytes is None:
            return "[Error] archive not found"
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                extracted = tar.extractfile(member)
                self.fs[f"{target_dir}/{member.name}"] = extracted.read() if extracted else b""
        self.fs.pop(archive_path, None)
        sentinel_match = _VERIFIED_SENTINEL_RE.search(code)
        return f"ok\n{sentinel_match.group(0)}\n" if sentinel_match else "ok"

    def _run_bootstrap(self, code: str) -> str:
        if self._bootstrap_started_event is not None:
            self._bootstrap_started_event.set()
        if self._bootstrap_delay_s:
            time.sleep(self._bootstrap_delay_s)
        marker_match = _BOOTSTRAP_MARKER_RE.search(code)
        assert marker_match, f"could not find bootstrap rc marker in: {code!r}"
        marker = marker_match.group(0)
        script_match = re.search(r"bash (\S+)", code)
        script = script_match.group(1) if script_match else "<unknown>"
        rc, stdout = self.bootstrap_behavior.get(script, (0, ""))
        # Shell-faithful (H1 fix, fix round 1): this must NOT re-implement the
        # truncation-avoidance safety mechanism under test — it must parse the
        # ACTUAL constructed command and only bound the echoed output the way
        # that specific command shape says it will. If the command redirects
        # the script's stdout to a log file and echoes a bounded `tail -c N`
        # of it before the marker (the real, current production shape), we
        # mirror exactly that bound. If that wrapper is ABSENT (e.g. a
        # regression back to the round-1 shape that echoes the script's full,
        # unbounded stdout straight through before the marker), we echo the
        # FULL stdout instead — letting the caller's own `_apply_output_cap`
        # (simulating the provider's real max_output_chars HEAD-truncation)
        # decide whether the marker survives, exactly as a real sandbox would.
        tail_match = re.search(r"tail -c (\d+) (\S+)", code)
        if tail_match:
            bound = int(tail_match.group(1))
            tail = stdout[-bound:] if len(stdout) > bound else stdout
        else:
            tail = stdout
        return f"{tail}\n{marker}={rc}\n"


class FakeOpenSandboxLikeProvider(_FakeProviderBase):
    """Absolute root, ABC default (mirrors OpenSandboxProvider's inherited
    ``skills_root`` when it isn't specifically exercising the bulk
    ``_materialise_skill_files`` override — that override is covered
    separately in ``test_sandbox_opensandbox_ensure_skill_fix.py``)."""

    def __init__(self) -> None:
        super().__init__(root="/workspace/.skills")


class FakeE2BLikeProvider(_FakeProviderBase):
    def __init__(self) -> None:
        super().__init__(root="/home/user/workspace/.skills")


class FakeDaytonaLikeProvider(_FakeProviderBase):
    """Deliberately a bare relative root — see ``DaytonaProvider.skills_root``'s
    docstring: Daytona's bash commands already run with ``cwd`` set to the
    workspace, so an absolute-prefixed root would double-nest."""

    def __init__(self) -> None:
        super().__init__(root=".skills")


ALL_FAKE_PROVIDERS = [FakeOpenSandboxLikeProvider, FakeE2BLikeProvider, FakeDaytonaLikeProvider]


def _make_handle(provider: _FakeProviderBase) -> SandboxHandle:
    return SandboxHandle(sandbox_id="fake-sbx", working_dir="/tmp", provider_name="fake")


def _payload(
    skill_id: int = 1,
    name: str = "myskill",
    files: Tuple[Tuple[str, bytes], ...] = (("SKILL.md", b"# My Skill\n"), ("notes/a.txt", b"hello world")),
    bootstrap_script_path: str | None = None,
) -> SkillPackagePayload:
    return SkillPackagePayload(
        skill_id=skill_id, name=name, files=files, bootstrap_script_path=bootstrap_script_path
    )


@pytest.fixture(autouse=True)
def _sandbox_settings(monkeypatch):
    monkeypatch.setattr("config.SANDBOX_DEFAULT_TIMEOUT_S", 5, raising=False)
    monkeypatch.setattr("config.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S", 30, raising=False)
    monkeypatch.setattr("config.SANDBOX_MAX_OUTPUT_CHARS", 20000, raising=False)
    monkeypatch.setattr("config.SKILL_IMPORT_MAX_TOTAL_BYTES", 50 * 1024 * 1024, raising=False)


# ---------------------------------------------------------------------------
# AC-15 / AC-21: files land correctly, across all three provider doubles.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
class TestEnsureSkillContractAcrossProviders:
    def test_ac15_files_land_with_matching_relative_paths_and_bytes(self, provider_cls):
        provider = provider_cls()
        handle = _make_handle(provider)
        payload = _payload()

        result = provider.ensure_skill(handle, payload)

        assert result.status == "active"
        assert result.files_dir == f"{provider._root}/myskill"
        assert self._file_bytes(provider, "myskill", "SKILL.md") == b"# My Skill\n"
        assert self._file_bytes(provider, "myskill", "notes/a.txt") == b"hello world"

    @staticmethod
    def _file_bytes(provider: _FakeProviderBase, name: str, rel_path: str) -> bytes:
        key = f"{provider._root}/{name}/{rel_path}"
        assert key in provider.fs, f"expected {key!r} in fake filesystem, got {sorted(provider.fs)}"
        return provider.fs[key]

    def test_fr18_tar_extraction_failure_falls_back_to_per_file_writes(self, provider_cls):
        """FR-18 (MEDIUM fix, fix round 1): the ABC's own tar→per-file
        fallback was claimed but never actually proven — the existing AC-17
        test failed the *cleanup* step, not extraction, so this specific
        fallback path had zero coverage. Fail `tar -xzf` itself (cleanup
        still succeeds) and assert the result is still `status="active"` via
        the per-file fallback, with the same byte-for-byte content
        assertions used in the AC-15 test."""
        provider = provider_cls()
        provider.fail_substrings = ("tar -xzf",)
        handle = _make_handle(provider)
        payload = _payload()

        result = provider.ensure_skill(handle, payload)

        assert result.status == "active"
        files_phase = next(p for p in result.phases if p.phase == "files")
        assert files_phase.status == "ok"
        assert "per-file writes (fallback)" in files_phase.detail
        assert self._file_bytes(provider, "myskill", "SKILL.md") == b"# My Skill\n"
        assert self._file_bytes(provider, "myskill", "notes/a.txt") == b"hello world"

    def test_ac16_second_call_is_one_materialisation_and_already_active(self, provider_cls):
        """No bootstrap script — the round-1 bug this pins: a FRESH first-time
        activation with no bootstrap must not itself read as 'already active'."""
        provider = provider_cls()
        handle = _make_handle(provider)
        payload = _payload(bootstrap_script_path=None)

        first = provider.ensure_skill(handle, payload)
        assert first.status == "active"
        first_files_phase = next(p for p in first.phases if p.phase == "files")
        assert first_files_phase.status == "ok"  # NOT "skipped" — genuinely fresh.

        extraction_calls_after_first = sum(1 for c in provider.run_code_calls if "tar -xzf" in c)
        assert extraction_calls_after_first == 1

        second = provider.ensure_skill(handle, payload)
        assert second.status == "active"
        # The idempotent-repeat call appends a new "skipped" files phase after the
        # original (preserved) phases — assert on the LAST phase, not the first
        # files-phase match, which would still be the original "ok" one.
        second_files_phase = second.phases[-1]
        assert second_files_phase.phase == "files"
        assert second_files_phase.status == "skipped"
        assert "already active" in second_files_phase.detail

        # Still exactly one materialisation — the second call never re-extracted.
        extraction_calls_after_second = sum(1 for c in provider.run_code_calls if "tar -xzf" in c)
        assert extraction_calls_after_second == 1

    def test_ac17_phase1_failure_returns_explicit_failed_status(self, provider_cls):
        provider = provider_cls()
        # Failing the cleanup ("rm -rf") step fails phase 1 outright, with no
        # per-file fallback available (the fallback only exists for archive
        # build/upload/extraction failures downstream of a successful cleanup) —
        # this genuinely exercises AC-17's explicit-failure path rather than the
        # graceful per-file degradation that a failing "tar -xzf" alone would
        # transparently recover from.
        provider.fail_substrings = ("rm -rf",)
        handle = _make_handle(provider)
        payload = _payload()

        result = provider.ensure_skill(handle, payload)

        assert result.status == "failed"
        files_phase = next(p for p in result.phases if p.phase == "files")
        assert files_phase.status == "failed"

    def test_ac17_bootstrap_only_failure_is_degraded_with_content_and_dir(self, provider_cls):
        provider = provider_cls()
        provider.bootstrap_behavior["setup.sh"] = (1, "pip install failed\n")
        handle = _make_handle(provider)
        payload = _payload(bootstrap_script_path="setup.sh")

        result = provider.ensure_skill(handle, payload)

        assert result.status == "degraded"
        assert result.files_dir == f"{provider._root}/myskill"
        # Files are still usable — phase 1 succeeded.
        files_phase = next(p for p in result.phases if p.phase == "files")
        assert files_phase.status == "ok"
        bootstrap_phase = next(p for p in result.phases if p.phase == "bootstrap")
        assert bootstrap_phase.status == "failed"
        assert self._file_bytes(provider, "myskill", "SKILL.md") == b"# My Skill\n"

    def test_bootstrap_success_is_active(self, provider_cls):
        provider = provider_cls()
        provider.bootstrap_behavior["setup.sh"] = (0, "installed fine\n")
        handle = _make_handle(provider)
        payload = _payload(bootstrap_script_path="setup.sh")

        result = provider.ensure_skill(handle, payload)

        assert result.status == "active"
        bootstrap_phase = next(p for p in result.phases if p.phase == "bootstrap")
        assert bootstrap_phase.status == "ok"


# ---------------------------------------------------------------------------
# OQ-4: name collision refusal.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
class TestOQ4NameCollision:
    def test_in_memory_collision_is_refused(self, provider_cls):
        provider = provider_cls()
        handle = _make_handle(provider)

        first = provider.ensure_skill(handle, _payload(skill_id=1, name="myskill"))
        assert first.status == "active"

        second = provider.ensure_skill(handle, _payload(skill_id=2, name="myskill"))

        assert second.status == "failed"
        files_phase = next(p for p in second.phases if p.phase == "files")
        assert "already materialised" in files_phase.detail or "different skill" in files_phase.detail

    def test_marker_based_collision_survives_a_simulated_restart(self, provider_cls):
        provider = provider_cls()
        handle = _make_handle(provider)
        first = provider.ensure_skill(handle, _payload(skill_id=1, name="myskill"))
        assert first.status == "active"

        # Simulate a restart / resumed sandbox: fresh in-process SandboxHandle
        # (empty active_skills), same backing filesystem (the marker persists).
        fresh_handle = _make_handle(provider)
        second = provider.ensure_skill(fresh_handle, _payload(skill_id=2, name="myskill"))

        assert second.status == "failed"
        files_phase = next(p for p in second.phases if p.phase == "files")
        assert "different skill" in files_phase.detail or "already materialised" in files_phase.detail

    def test_marker_hit_restores_status_not_hardcoded_active(self, provider_cls):
        """A marker written after a degraded activation must read back as
        degraded on a simulated restart — never silently upgraded."""
        provider = provider_cls()
        provider.bootstrap_behavior["setup.sh"] = (1, "boom")
        handle = _make_handle(provider)
        first = provider.ensure_skill(handle, _payload(bootstrap_script_path="setup.sh"))
        assert first.status == "degraded"

        fresh_handle = _make_handle(provider)
        second = provider.ensure_skill(fresh_handle, _payload(bootstrap_script_path="setup.sh"))

        assert second.status == "degraded"


# ---------------------------------------------------------------------------
# Concurrency: two threads racing ensure_skill for the same skill.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_concurrent_ensure_skill_calls_materialise_exactly_once(provider_cls):
    provider = provider_cls()
    provider._extraction_delay_s = 0.15  # keep t1's extraction in flight while t2 races it
    provider._extraction_started_event = threading.Event()
    handle = _make_handle(provider)
    payload = _payload()

    results: List = [None, None]

    def _call(idx: int) -> None:
        results[idx] = provider.ensure_skill(handle, payload)

    t1 = threading.Thread(target=_call, args=(0,))
    t2 = threading.Thread(target=_call, args=(1,))
    t1.start()
    # Deterministic sync (MEDIUM fix, fix round 1): wait for t1 to have
    # actually entered extraction (i.e. past the reservation critical
    # section) instead of guessing an interleaving via time.sleep().
    assert provider._extraction_started_event.wait(timeout=2), "t1 never reached extraction"
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    extraction_calls = sum(1 for c in provider.run_code_calls if "tar -xzf" in c)
    assert extraction_calls == 1, "exactly one materialisation must have occurred"

    files_phases = [next(p for p in r.phases if p.phase == "files") for r in results]
    busy = [p for p in files_phases if "activation already in progress" in p.detail]
    materialised = [p for p in files_phases if p.status == "ok"]
    assert len(busy) == 1
    assert len(materialised) == 1


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_reservation_is_released_after_sandbox_expired_error(provider_cls):
    """MEDIUM fix (fix round 1): a SandboxExpiredError raised during phase 1
    must not leak the ``_activating_skills`` reservation — otherwise every
    subsequent call for that skill name on this handle would be permanently,
    incorrectly told "activation already in progress" even though the
    activating call already died."""
    provider = provider_cls()
    provider.expire_on_substrings = ("rm -rf",)  # phase-1 cleanup raises
    handle = _make_handle(provider)
    payload = _payload()

    with pytest.raises(SandboxExpiredError):
        provider.ensure_skill(handle, payload)

    # The reservation must have been released, not leaked.
    assert "myskill" not in handle._activating_skills

    # A subsequent call (sandbox "recovered") must materialise normally,
    # proving the reservation wasn't leaked.
    provider.expire_on_substrings = ()
    result = provider.ensure_skill(handle, payload)
    assert result.status == "active"
    files_phase = next(p for p in result.phases if p.phase == "files")
    assert files_phase.status == "ok"
    assert "activation already in progress" not in files_phase.detail


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_concurrent_retry_true_calls_yield_exactly_one_busy(provider_cls):
    """MEDIUM fix (fix round 1): two concurrent ``retry=True`` calls for the
    same already-active skill must mirror the non-retry concurrency
    contract above — exactly one busy result, never two bootstraps racing
    each other on the same skill."""
    provider = provider_cls()
    handle = _make_handle(provider)
    payload = _payload(bootstrap_script_path="setup.sh")
    provider.bootstrap_behavior["setup.sh"] = (0, "installed\n")

    first = provider.ensure_skill(handle, payload)
    assert first.status == "active"

    provider._bootstrap_delay_s = 0.15
    provider._bootstrap_started_event = threading.Event()

    results: List = [None, None]

    def _call(idx: int) -> None:
        results[idx] = provider.ensure_skill(handle, payload, retry=True)

    t1 = threading.Thread(target=_call, args=(0,))
    t2 = threading.Thread(target=_call, args=(1,))
    t1.start()
    assert provider._bootstrap_started_event.wait(timeout=2), "t1 never reached bootstrap"
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    def _is_busy(r) -> bool:
        return any("activation already in progress" in p.detail for p in r.phases)

    busy = [r for r in results if _is_busy(r)]
    materialised = [r for r in results if not _is_busy(r)]
    assert len(busy) == 1
    assert len(materialised) == 1
    assert materialised[0].status == "active"


# ---------------------------------------------------------------------------
# Regression: bootstrap output truncation must not evict the success marker.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_large_bootstrap_output_does_not_evict_success_sentinel(provider_cls, monkeypatch):
    """step_016 review-round bug: a verbose (but successful) bootstrap script
    must not have its rc-marker truncated away by max_output_chars — the
    real wrapper's ``tail -c 4000`` + trailing-marker shape keeps the marker
    alive even when the script prints far more than the output cap."""
    provider = provider_cls()
    huge_output = "line of chatty pip install output\n" * 2000  # ~70000 chars
    assert len(huge_output) > 20000
    provider.bootstrap_behavior["setup.sh"] = (0, huge_output)
    handle = _make_handle(provider)
    payload = _payload(bootstrap_script_path="setup.sh")

    result = provider.ensure_skill(handle, payload)

    assert result.status == "active"
    bootstrap_phase = next(p for p in result.phases if p.phase == "bootstrap")
    assert bootstrap_phase.status == "ok"


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_bootstrap_command_construction_redirects_and_tails_before_marker(provider_cls):
    """H1 fix (fix round 1): a direct assertion on the CONSTRUCTED command
    string itself, not just on the observed outcome — the real production
    bug (round-1 shape) had no output redirect and no bounded tail before
    the rc-marker, so a fake that only checks outcomes can't distinguish
    the fixed shape from the buggy one. This pins the actual command shape
    ``_run_skill_bootstrap`` must build: redirect the script's own stdout to
    a log file, echo a bounded ``tail -c N`` of that log, and ONLY THEN echo
    the rc-marker — never a raw/unbounded echo of the script's stdout ahead
    of the marker."""
    provider = provider_cls()
    provider.bootstrap_behavior["setup.sh"] = (0, "hello\n")
    handle = _make_handle(provider)
    payload = _payload(bootstrap_script_path="setup.sh")

    provider.ensure_skill(handle, payload)

    bootstrap_calls = [c for c in provider.run_code_calls if _BOOTSTRAP_MARKER_RE.search(c)]
    assert len(bootstrap_calls) == 1
    cmd = bootstrap_calls[0]

    # 1) the script's own stdout/stderr is redirected to a log file, not
    #    streamed straight into the command's own unbounded output.
    redirect_match = re.search(r"\)\s*>\s*(\S+?)\s+2>&1", cmd)
    assert redirect_match, f"expected a redirect-to-logfile in bootstrap command, got: {cmd!r}"
    log_path = redirect_match.group(1)

    # 2) a *bounded* tail of that same log file is echoed back.
    tail_match = re.search(r"tail -c (\d+) (\S+?);", cmd)
    assert tail_match, f"expected a bounded `tail -c N` of the log file, got: {cmd!r}"
    assert tail_match.group(2) == log_path, "tail must read the SAME log file the script was redirected to"
    assert int(tail_match.group(1)) <= 4000, "the tail bound must stay well under the default output cap"

    # 3) the marker line comes strictly AFTER the bounded tail — never a raw,
    #    unbounded echo of the script's own stdout ahead of the marker.
    marker_match = _BOOTSTRAP_MARKER_RE.search(cmd)
    assert marker_match
    assert cmd.index(tail_match.group(0)) < cmd.index(marker_match.group(0)), (
        "the bounded tail must be positioned before the rc-marker in the command"
    )


@pytest.mark.parametrize("provider_cls", ALL_FAKE_PROVIDERS)
def test_bootstrap_marker_survives_at_near_output_cap_boundary(provider_cls, monkeypatch):
    """H1 fix (fix round 1): the exact boundary plan.md names as the condition
    that reopens the round-1 bug — ``SANDBOX_MAX_OUTPUT_CHARS`` lowered to
    ~4100 (far tighter than the 20000 default, but still just barely above
    the wrapper's own ``tail -c 4000`` bound). A chatty bootstrap script that
    would blow this tight budget must still have its rc-marker survive,
    because the wrapper's bounded tail — not the raw script stdout — is what
    the provider-level cap ever sees."""
    monkeypatch.setattr("config.SANDBOX_MAX_OUTPUT_CHARS", 4100, raising=False)
    provider = provider_cls()
    huge_output = "chatty bootstrap line\n" * 1000  # ~23000 chars, way over 4100
    assert len(huge_output) > 4100
    provider.bootstrap_behavior["setup.sh"] = (0, huge_output)
    handle = _make_handle(provider)
    payload = _payload(bootstrap_script_path="setup.sh")

    result = provider.ensure_skill(handle, payload)

    assert result.status == "active", (
        "the rc-marker must survive the tight 4100-char output cap boundary; "
        f"phases={result.phases!r}"
    )
    bootstrap_phase = next(p for p in result.phases if p.phase == "bootstrap")
    assert bootstrap_phase.status == "ok"
