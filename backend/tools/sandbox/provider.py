"""
SandboxProvider abstract base class and SandboxHandle dataclass.

Every concrete provider (opensandbox, daytona, e2b, …) must subclass
SandboxProvider and implement all abstract methods.

v2 changes (sandbox-v2-migration Phase 1):
- ``SandboxHandle`` extended with ``session_key``.
- ``SandboxExpiredError`` added for explicit expiry signalling.
- Provider ABC updated: ``create_sandbox`` accepts ``existing_sandbox_id``;
  ``renew_sandbox`` added (default no-op); ``run_code`` gains ``timeout``,
  ``max_output_chars``, and ``on_stderr``; ``run_code_streaming`` helper added.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

import config as settings
from schemas.skill_package_payload import SkillPackagePayload
from utils.logger import get_logger

from .skill_archive import (
    SkillPackageTooLargeError,
    build_tar_gz,
    extraction_command,
    safe_member_name,
)

logger = get_logger(__name__)

#: Cap applied to every human-readable ``detail`` string recorded on a
#: ``SkillPhaseResult`` — bootstrap output and exception-derived messages
#: alike — so no single phase result can blow up logs/DB rows.
_DETAIL_TRUNCATE_CHARS = 2000


def truncate_detail(text: str) -> str:
    """Truncate a phase-result ``detail`` string.

    Public (no leading underscore) because ``opensandbox_provider.py`` — a
    second module — now calls this too, making it a genuine cross-module
    contract rather than a module-private helper.
    """
    return (text or "")[:_DETAIL_TRUNCATE_CHARS]


class SandboxExpiredError(RuntimeError):
    """Raised when a provider sandbox no longer exists and cannot be recovered.

    Callers that catch this error should evict the cached handle and call
    ``create_sandbox`` again.
    """


# ---------------------------------------------------------------------------
# Skill activation (FR-17..FR-19, AD-6)
# ---------------------------------------------------------------------------

#: Sandbox-side root directory under which every activated skill gets its own
#: subdirectory (``SKILLS_ROOT/<normalised skill name>/``). This is the
#: default returned by ``SandboxProvider.skills_root`` — providers with a
#: different filesystem-root convention (E2B, Daytona) override that method
#: instead of this constant (step_018).
SKILLS_ROOT = "/workspace/.skills"

#: Sibling directory (under ``skills_root``, *not* inside any individual
#: skill's own directory) that holds on-disk idempotency markers written
#: after ``ensure_skill`` completes materialisation+bootstrap (H6, round-2
#: MEDIUM fix) — lets ``ensure_skill`` recognise an already-materialised
#: skill even after a backend restart / second worker / resumed sandbox,
#: when ``SandboxHandle.active_skills`` (in-process only) has no record of
#: it. Kept *outside* ``skill_dir(root, name)`` deliberately: a marker living
#: inside the directory it certifies could be shipped as a package file (or
#: overwritten by a bootstrap script), poisoning future restarts into a
#: permanent false "already active" read.
_SKILL_MARKERS_DIRNAME = ".markers"


def skill_dir(root: str, name: str) -> str:
    """Return the absolute sandbox directory for a normalised skill name.

    *root* is the resolved sandbox-side skills root (see
    ``SandboxProvider.skills_root``). This only builds the path string; any
    caller that interpolates *name* (or the returned path) into a shell
    command string run via ``run_code`` must still defensively
    ``shlex.quote`` it there — this helper does not quote its return value
    because most callers pass it to ``write_file``, which never touches a
    shell.
    """
    return f"{root}/{name}"


def _skill_marker_path(root: str, name: str) -> str:
    """Path of the on-disk idempotency marker for *name*, sibling to (not
    inside) ``skill_dir(root, name)`` — see ``_SKILL_MARKERS_DIRNAME``."""
    return f"{root}/{_SKILL_MARKERS_DIRNAME}/{name}.json"


@dataclass(frozen=True)
class SkillPhaseResult:
    """Outcome of one phase of ``SandboxProvider.ensure_skill``."""

    phase: Literal["files", "bootstrap"]
    status: Literal["ok", "skipped", "failed"]
    detail: str
    duration_ms: int


@dataclass(frozen=True)
class SkillActivationResult:
    """Outcome of activating one skill package inside a sandbox."""

    skill_name: str
    skill_id: int
    files_dir: str
    phases: tuple[SkillPhaseResult, ...]
    status: Literal["active", "degraded", "failed"]


@dataclass
class SandboxHandle:
    """Opaque reference to a live sandbox session.

    Passed between the provider and the tool factory so neither side
    needs to know the other's internals.

    Attributes:
        sandbox_id:    Provider-assigned identifier for the remote sandbox.
        working_dir:   Host-side filesystem path used for local file staging.
        provider_name: Name of the provider that created this handle.
        session_key:   Derived session key used by ``SandboxSessionService``
                       (e.g. ``conv_12_456``).  Set after creation.
        metadata:      Provider-internal state (SDK objects, capability flags).
                       Not for application use.
        active_skills: Skills currently materialised in this sandbox, keyed by
                       normalised skill name (the same string used for the
                       sandbox directory name under the resolved skills
                       root). Mutated by ``SandboxProvider.ensure_skill``,
                       which self-synchronizes access via ``_skills_lock``
                       below (NFR-4b) — callers do not need to hold any lock
                       of their own around ``ensure_skill``.

    Note (H3): ``active_skills`` (and the in-flight-activation set below) are
    cached process-wide per ``session_key`` by ``sandbox_session_service`` and
    shared across concurrent turns/proxies that each construct their own
    ``_LazySandboxHandle`` with its own private lock — a lock on the proxy
    does **not** protect this shared dict. The lock therefore lives on the
    state it protects (here), not on the caller.
    """

    sandbox_id: str
    working_dir: str
    provider_name: str
    session_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    active_skills: dict[str, SkillActivationResult] = field(default_factory=dict)
    _skills_lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    _activating_skills: set[str] = field(default_factory=set, repr=False, compare=False)


class SandboxProvider(ABC):
    """Abstract base class for sandbox execution backends.

    Class attribute ``SUPPORTED_LANGUAGES`` declares which language identifiers
    this provider can execute.  Concrete providers override it as a class-level
    list; the default is ``["python"]`` for backward compatibility.

    Language identifiers are lowercase strings (e.g. ``"python"``,
    ``"javascript"``, ``"bash"``).  The set of recognised identifiers is
    intentionally open-ended — providers map them to the runtime primitives they
    support (subprocess interpreters, SDK enum values, etc.).
    """

    SUPPORTED_LANGUAGES: list[str] = ["python"]

    requires_file_sync: bool = True
    """Whether this provider's sandbox filesystem is remote/separate from the
    backend's local ``working_dir`` and therefore needs explicit file push/pull
    to stay in sync.

    Declared as a class attribute so a future provider must consciously set
    it (rather than any caller string-matching on provider names). Defaults
    to ``True`` since every provider that manages a remote sandbox execution
    environment needs file synchronisation; a provider whose sandbox shares
    the backend's local filesystem directly would set this to ``False``.
    """

    def get_supported_languages(self) -> list[str]:
        """Return the list of language identifiers this provider supports.

        Concrete providers that compute the list dynamically (e.g. by reading
        an environment variable) should override this method instead of the
        class attribute.
        """
        return list(self.SUPPORTED_LANGUAGES)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def create_sandbox(
        self,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        """Initialise or resume a sandbox and return a handle to it.

        Providers that support reconnecting should attempt to resume
        *existing_sandbox_id* when it is provided.  If resume fails, a new
        sandbox must be created.  Providers that do not support resume should
        ignore *existing_sandbox_id* and always create a new sandbox.

        Args:
            working_dir:         Host-side filesystem path for local staging.
            session_key:         Session key to store on the returned handle.
            existing_sandbox_id: Provider sandbox id to attempt resumption of.
        """

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        """Extend the provider TTL by *duration*.

        Default implementation is a no-op; providers without TTL support may
        leave this unimplemented.  Providers with TTL support (e.g.
        ``OpenSandboxProvider``) should override this and raise
        :exc:`SandboxExpiredError` if the remote sandbox is gone.
        """

    def touch_sandbox(self, handle: SandboxHandle, idle_timeout_s: int) -> None:
        """Record provider-side activity and refresh the idle timeout.

        The session service owns idle detection. Providers use this hook to keep
        their own timeout/auto-stop setting aligned with that service-level
        activity. The default bridges to the older ``renew_sandbox`` hook.
        """
        self.renew_sandbox(handle, timedelta(seconds=idle_timeout_s))

    @abstractmethod
    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Release all resources held by the sandbox."""

    def destroy_sandbox_id(self, sandbox_id: str) -> None:
        """Best-effort destroy by provider sandbox id.

        Used by persisted-state cleanup after backend restarts, when the live
        SDK object stored in ``SandboxHandle.metadata`` is no longer available.
        Providers with remote resume/connect APIs should override this method.
        """
        self.destroy_sandbox(
            SandboxHandle(
                sandbox_id=sandbox_id,
                working_dir="",
                provider_name=getattr(self, "PROVIDER_NAME", self.__class__.__name__),
            )
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    def run_code(
        self,
        handle: SandboxHandle,
        code: str,
        *,
        language: str = "python",
        timeout: int | None = None,
        max_output_chars: int | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *code* inside the sandbox and return truncated combined output.

        Args:
            handle:           Active sandbox handle.
            code:             Source code to execute.
            language:         Language identifier (e.g. ``"python"``).
                              Must be in :meth:`get_supported_languages`.
            timeout:          Per-execution timeout in seconds.  Falls back to
                              ``settings.SANDBOX_DEFAULT_TIMEOUT_S`` when ``None``.
            max_output_chars: Maximum characters to return.  Falls back to
                              ``settings.SANDBOX_MAX_OUTPUT_CHARS`` when ``None``.
                              Truncated output ends with a marker string.
            on_stdout:        Callback for live stdout lines (non-blocking).
            on_stderr:        Callback for live stderr lines (non-blocking).
        """

    def run_code_streaming(
        self,
        handle: SandboxHandle,
        code: str,
        stream_writer: Callable[[dict], None],
        **kwargs: Any,
    ) -> str:
        """Execute *code* and forward stdout/stderr to a LangGraph stream writer.

        Bridges the provider's ``on_stdout`` / ``on_stderr`` callbacks to
        ``stream_writer`` as ``{"type": "code_output", "stream": ..., "line": ...}``
        events.  Any keyword arguments are forwarded to :meth:`run_code`.

        Args:
            handle:        Active sandbox handle.
            code:          Source code to execute.
            stream_writer: Callable that accepts a dict and forwards it to the
                           LangGraph custom stream.
            **kwargs:      Extra arguments forwarded to :meth:`run_code`
                           (e.g. ``language``, ``timeout``).
        """

        def _stdout(line: str) -> None:
            try:
                stream_writer({"type": "code_output", "stream": "stdout", "line": line})
            except Exception:
                pass

        def _stderr(line: str) -> None:
            try:
                stream_writer({"type": "code_output", "stream": "stderr", "line": line})
            except Exception:
                pass

        return self.run_code(handle, code, on_stdout=_stdout, on_stderr=_stderr, **kwargs)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @abstractmethod
    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        """Write *content* to *filename* inside the sandbox workspace."""

    @abstractmethod
    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        """Return the raw bytes of *filename* from the sandbox workspace."""

    @abstractmethod
    def list_files(self, handle: SandboxHandle) -> list[str]:
        """Return workspace-relative paths of all files in the sandbox workspace.

        Paths are relative to the sandbox working directory.
        """

    # ------------------------------------------------------------------
    # Skill activation (FR-17..FR-19, AD-6)
    # ------------------------------------------------------------------

    def skills_root(self, handle: SandboxHandle) -> str:
        """Return the sandbox-side root directory for skill materialisation.

        Default returns the global ``SKILLS_ROOT`` constant. Providers with a
        different filesystem-root convention (E2B: ``/home/user/workspace``,
        Daytona: ``/home/daytona/workspace``) override this hook instead of
        duplicating the phase-1/phase-2 logic (step_018).
        """
        return SKILLS_ROOT

    def ensure_skill(
        self,
        handle: SandboxHandle,
        payload: SkillPackagePayload,
        *,
        retry: bool = False,
    ) -> SkillActivationResult:
        """Materialise *payload* under ``<skills_root>/<payload.name>/`` and run
        its bootstrap script (if any), returning a structured, typed result.

        This is a **concrete default** built only on ``write_file``/``run_code`` so
        no provider is required to override it (FR-20 overrides are optional
        speed-ups, never load-bearing). Behaviour:

        - **Idempotent**: a second call for an already-active skill (same
          ``payload.skill_id``) is a fast no-op — it returns the *previously
          recorded* result (status included — a prior ``degraded``/``failed``
          result is never silently upgraded to ``active``) with an extra
          ``skipped`` phase appended, and does *not* touch the sandbox, unless
          ``retry=True``, in which case only the bootstrap phase re-runs.
        - **On-disk idempotency marker** (H6): before materialising a skill this
          process has no in-memory record of, a best-effort marker file
          (sibling to the skill's own directory — see ``_SKILL_MARKERS_DIRNAME``)
          is probed so a backend restart / second worker / resumed sandbox
          doesn't blindly re-upload and re-run a (possibly 120s) bootstrap. The
          marker is only written *after* materialisation+bootstrap complete and
          records the resulting ``status`` — a marker hit restores that
          recorded status (never hardcodes ``"active"``; a prior ``degraded``
          activation is read back as ``degraded``, round-2 H-B).
        - **Name-collision refusal** (OQ-4): if a *different* ``skill_id`` is
          already active under the same normalised name (in memory or via the
          on-disk marker), this returns a ``failed`` result naming the
          collision and leaves the existing activation untouched — it never
          overwrites another skill's directory.
        - **Graceful degradation**: a bootstrap script failure or timeout never
          raises — it is recorded as a failed ``bootstrap`` phase and the overall
          status becomes ``degraded`` (the skill's files are still usable). Only
          a genuinely dead sandbox (``SandboxExpiredError``) propagates, so the
          caller can evict and recreate the handle.
        - **Phase-1 fallback**: file materialisation first tries a single
          ``tar.gz`` upload + extraction (fast, one round-trip); if that fails for
          any reason (archive build, upload, or extraction command not
          confirmed successful), it falls back to per-file ``write_file`` calls.

        Locking (NFR-4b): this method self-synchronizes via
        ``handle._skills_lock`` — callers do not need to (and must not try to)
        hold any lock of their own around this call. The lock is only held
        around the read-check-reserve of ``handle.active_skills`` /
        ``handle._activating_skills`` and around recording the final result;
        it is released for the (potentially 120s) phase-1/phase-2 I/O so
        unrelated skill activations on the same handle are never serialised
        behind a single slow bootstrap.
        """
        name = payload.name
        root = self.skills_root(handle)
        files_dir = skill_dir(root, name)
        existing: SkillActivationResult | None = None
        # Tracks whether *this* call actually added `name` to
        # `_activating_skills` — only that caller may discard it in `finally`
        # (round-2 MEDIUM fix: the retry branch below now reserves too, so
        # the old unconditional discard could remove a reservation this call
        # never made).
        reserved = False

        with handle._skills_lock:
            existing = handle.active_skills.get(name)
            if existing is not None:
                if existing.skill_id != payload.skill_id:
                    return self._skill_collision_result(handle, files_dir, name, payload, existing.skill_id)
                if not retry:
                    # H1: preserve the previously recorded status (never
                    # hardcode "active" — a prior degraded/failed result must
                    # stay visible to the caller).
                    return SkillActivationResult(
                        skill_name=existing.skill_name,
                        skill_id=existing.skill_id,
                        files_dir=existing.files_dir,
                        phases=(
                            *existing.phases,
                            SkillPhaseResult(
                                phase="files", status="skipped", detail="already active", duration_ms=0
                            ),
                        ),
                        status=existing.status,
                    )
                # retry=True on an already-active skill: re-run bootstrap only,
                # outside the lock — but still reserve first (round-2 MEDIUM
                # fix) so two concurrent retry=True calls for the same skill
                # can't run bootstrap simultaneously.
                if name in handle._activating_skills:
                    return SkillActivationResult(
                        skill_name=name,
                        skill_id=payload.skill_id,
                        files_dir=existing.files_dir,
                        phases=(
                            SkillPhaseResult(
                                phase="bootstrap",
                                status="skipped",
                                detail="activation already in progress on another call, retry shortly",
                                duration_ms=0,
                            ),
                        ),
                        # Round-2 MEDIUM fix: "busy" is a distinct, unambiguous
                        # signal from "degraded" (which elsewhere means
                        # "bootstrap failed but files are usable") — reusing
                        # "degraded" here conflated the two and returned before
                        # files necessarily existed.
                        status="failed",
                    )
                handle._activating_skills.add(name)
                reserved = True
            elif name in handle._activating_skills:
                # Another concurrent call is already materialising this exact
                # skill name on this handle; don't race the same upload.
                return SkillActivationResult(
                    skill_name=name,
                    skill_id=payload.skill_id,
                    files_dir=files_dir,
                    phases=(
                        SkillPhaseResult(
                            phase="files",
                            status="skipped",
                            detail="activation already in progress on another call, retry shortly",
                            duration_ms=0,
                        ),
                    ),
                    status="failed",
                )
            else:
                handle._activating_skills.add(name)
                reserved = True

        try:
            if existing is not None and retry:
                bootstrap_phase = self._run_skill_bootstrap(handle, payload, name, root)
                status: Literal["active", "degraded"] = (
                    "degraded" if bootstrap_phase.status == "failed" else "active"
                )
                result = SkillActivationResult(
                    skill_name=name,
                    skill_id=payload.skill_id,
                    files_dir=existing.files_dir,
                    phases=(
                        SkillPhaseResult(
                            phase="files", status="skipped", detail="already active", duration_ms=0
                        ),
                        bootstrap_phase,
                    ),
                    status=status,
                )
                with handle._skills_lock:
                    handle.active_skills[name] = result
                self._write_skill_marker(handle, root, name, payload, status)
                self._log_skill_activation(handle, result)
                return result

            marker = self._probe_skill_marker(handle, root, name)
            if marker is not None:
                marker_skill_id = marker.get("skill_id")
                if marker_skill_id == payload.skill_id and marker.get("checksum") == self._skill_checksum(payload):
                    # H-B: restore the status the marker actually recorded —
                    # never hardcode "active". A marker written after a
                    # degraded activation must read back as degraded, not be
                    # silently upgraded. (We deliberately do not re-run the
                    # bootstrap phase on a degraded marker hit here — see
                    # round-2 fix summary for rationale; callers that want a
                    # fresh bootstrap attempt can pass retry=True.)
                    marker_status = marker.get("status")
                    restored_status: Literal["active", "degraded"] = (
                        "degraded" if marker_status == "degraded" else "active"
                    )
                    result = SkillActivationResult(
                        skill_name=name,
                        skill_id=payload.skill_id,
                        files_dir=files_dir,
                        phases=(
                            SkillPhaseResult(
                                phase="files",
                                status="skipped",
                                detail=(
                                    "already active (found on-disk idempotency marker)"
                                    if restored_status == "active"
                                    else "already materialised but bootstrap previously failed "
                                    "(found on-disk idempotency marker, status=degraded)"
                                ),
                                duration_ms=0,
                            ),
                        ),
                        status=restored_status,
                    )
                    with handle._skills_lock:
                        handle.active_skills[name] = result
                    self._log_skill_activation(handle, result)
                    return result
                if marker_skill_id is not None and marker_skill_id != payload.skill_id:
                    return self._skill_collision_result(
                        handle, files_dir, name, payload, marker_skill_id, via_marker=True
                    )
                # Marker exists for the same skill but content changed (or is
                # unreadable/malformed past the dict check) — fall through and
                # re-materialise below.

            files_phase = self._materialise_skill_files(handle, payload, name, root)

            if files_phase.status != "ok":
                # Phase-1 failure: nothing is stored in active_skills (FR-19), so
                # a later call for the same skill retries from scratch rather
                # than being wrongly treated as already active.
                result = SkillActivationResult(
                    skill_name=name,
                    skill_id=payload.skill_id,
                    files_dir=files_dir,
                    phases=(files_phase,),
                    status="failed",
                )
                self._log_skill_activation(handle, result)
                return result

            phases = [files_phase]
            status = "active"
            if payload.bootstrap_script_path:
                bootstrap_phase = self._run_skill_bootstrap(handle, payload, name, root)
                phases.append(bootstrap_phase)
                if bootstrap_phase.status == "failed":
                    status = "degraded"

            # H-B: the marker is only written once the bootstrap outcome is
            # known, and it now records that outcome — writing it earlier (the
            # round-1 shape) meant a degraded activation would resurrect as
            # "active" on the next restart/marker hit.
            self._write_skill_marker(handle, root, name, payload, status)

            result = SkillActivationResult(
                skill_name=name,
                skill_id=payload.skill_id,
                files_dir=files_dir,
                phases=tuple(phases),
                status=status,
            )
            with handle._skills_lock:
                handle.active_skills[name] = result
            self._log_skill_activation(handle, result)
            return result
        finally:
            if reserved:
                with handle._skills_lock:
                    handle._activating_skills.discard(name)

    def _skill_collision_result(
        self,
        handle: SandboxHandle,
        files_dir: str,
        name: str,
        payload: SkillPackagePayload,
        active_skill_id: int,
        *,
        via_marker: bool = False,
    ) -> SkillActivationResult:
        detail = f"a different skill is already materialised at {files_dir}"
        logger.warning(
            "ensure_skill: name collision%s — sandbox=%s name=%r active_skill_id=%s "
            "requested_skill_id=%s",
            " (via on-disk marker)" if via_marker else "",
            handle.sandbox_id, name, active_skill_id, payload.skill_id,
        )
        return SkillActivationResult(
            skill_name=name,
            skill_id=payload.skill_id,
            files_dir=files_dir,
            phases=(SkillPhaseResult(phase="files", status="failed", detail=detail, duration_ms=0),),
            status="failed",
        )

    def _skill_checksum(self, payload: SkillPackagePayload) -> str:
        """Order-independent content hash used to validate the on-disk marker (H6).

        Round-2 MEDIUM fix: also folds in ``bootstrap_script_path``,
        ``runtime`` and ``runtime_options`` — changing only the bootstrap
        entrypoint/runtime without touching any file content must still be
        recognised as a content change and trigger re-materialisation
        (otherwise the marker hit would keep serving the stale bootstrap
        config forever).
        """
        hasher = hashlib.sha256()
        for path, data in sorted(payload.files, key=lambda item: item[0]):
            hasher.update(path.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(data)
            hasher.update(b"\x00")
        hasher.update(b"\x01bootstrap_script_path\x00")
        hasher.update((payload.bootstrap_script_path or "").encode("utf-8"))
        hasher.update(b"\x01runtime\x00")
        hasher.update((payload.runtime or "").encode("utf-8"))
        hasher.update(b"\x01runtime_options\x00")
        hasher.update(json.dumps(payload.runtime_options or {}, sort_keys=True, default=str).encode("utf-8"))
        return hasher.hexdigest()

    def _probe_skill_marker(self, handle: SandboxHandle, root: str, name: str) -> dict | None:
        """Best-effort read of the on-disk idempotency marker (H6).

        Returns ``None`` on any failure other than ``SandboxExpiredError``,
        which is a real signal the sandbox is gone and must propagate so the
        caller can evict/recreate it rather than being folded into "no
        marker found". A marker whose ``skill_id`` field isn't an ``int``
        (round-2 MEDIUM fix) is treated the same as unparseable/corrupt — it
        must not be able to trip the name-collision branch, only a clean
        re-materialise.
        """
        try:
            raw = self.read_file(handle, _skill_marker_path(root, name))
        except SandboxExpiredError:
            raise
        except Exception:
            return None
        try:
            marker = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(marker, dict):
            return None
        skill_id = marker.get("skill_id")
        if skill_id is not None and not isinstance(skill_id, int):
            return None
        return marker

    def _write_skill_marker(
        self,
        handle: SandboxHandle,
        root: str,
        name: str,
        payload: SkillPackagePayload,
        status: Literal["active", "degraded"],
    ) -> None:
        """Write the on-disk idempotency marker (H6).

        Round-2 H-B fix: this must only be called once the bootstrap outcome
        is known (i.e. *after* phase 2, not right after phase 1) and must
        record that outcome via *status* — a marker probed on a later
        restart restores this recorded status instead of unconditionally
        reporting "active", so a degraded activation cannot resurrect as
        active just because its files happen to be on disk.

        Best-effort: a write failure only logs a warning and does not fail
        the activation, except for ``SandboxExpiredError`` which must still
        propagate.
        """
        marker = {
            "skill_id": payload.skill_id,
            "checksum": self._skill_checksum(payload),
            "status": status,
        }
        try:
            self.write_file(handle, _skill_marker_path(root, name), json.dumps(marker).encode("utf-8"))
        except SandboxExpiredError:
            raise
        except Exception as exc:
            logger.warning(
                "ensure_skill: failed to write idempotency marker for skill %r: %s", payload.name, exc
            )

    def _run_verified_command(
        self,
        handle: SandboxHandle,
        command: str,
        *,
        language: str = "bash",
        timeout: int | None = None,
        max_output_chars: int | None = None,
    ) -> tuple[bool, str]:
        """Run *command* and verify it actually succeeded (C1/C2).

        ``run_code`` never raises on ordinary command failure/timeout — only
        ``SandboxExpiredError`` signals a genuinely dead sandbox — so a failed
        command otherwise comes back as a provider ``"[Error] ..."`` string
        (truthy, indistinguishable from success by exception handling alone).
        This appends a per-call sentinel to *command* and requires it to
        appear in the output, with no leading ``"[Error]"`` marker, before
        treating the command as successful.

        Round-2 H-C fix: *command*'s own stdout/stderr is redirected to a
        sandbox-side log file and only a bounded tail of it plus the
        sentinel are echoed back — so a verbose command (large listing,
        chatty ``tar``) can never push the sentinel itself past
        ``max_output_chars`` and evict it via HEAD-truncation (see
        ``opensandbox_provider.run_code``), which would otherwise misreport a
        genuinely successful command as failed.
        """
        nonce = uuid.uuid4().hex
        sentinel = f"__SKILL_CMD_OK_{nonce}__"
        log_path = f"/tmp/.mattin-skill-cmd-{nonce}.log"
        quoted_log_path = shlex.quote(log_path)
        # Round-2 LOW fix (reliability-auditor): the trailing `rm -f` only ran
        # on the normal fall-through path — a timeout or interruption of the
        # outer run_code call (which kills this shell) skipped it, leaking
        # the sandbox-side log file. `trap ... EXIT` fires on any shell exit
        # (normal, killed, or interrupted), so the log is always cleaned up;
        # the explicit `rm -f` at the end is left in place too so the file is
        # gone before the sentinel line is even printed in the common case.
        full_command = (
            f"trap 'rm -f {quoted_log_path}' EXIT; "
            f"( {command} ) > {quoted_log_path} 2>&1; rc=$?; "
            f"tail -c 4000 {quoted_log_path}; "
            f"if [ $rc -eq 0 ]; then echo {sentinel}; fi; "
            f"rm -f {quoted_log_path}"
        )
        output = self.run_code(
            handle, full_command, language=language, timeout=timeout, max_output_chars=max_output_chars
        )
        output_str = output if isinstance(output, str) else str(output)
        ok = sentinel in output_str and not output_str.lstrip().startswith("[Error]")
        return ok, output_str

    def _materialise_skill_files(
        self, handle: SandboxHandle, payload: SkillPackagePayload, name: str, root: str
    ) -> SkillPhaseResult:
        """Phase 1: upload+extract a tar.gz archive; fall back to per-file writes.

        This is a **documented, supported override point** (step_017/018
        round-1 fix H4): providers whose SDK offers a native bulk/filesystem
        upload primitive (e.g. OpenSandbox's ``sandbox.files.write_files``)
        override this method instead of duplicating ``ensure_skill``'s
        locking/idempotency/collision/marker logic, which stays on the ABC.
        ``ensure_skill`` calls this polymorphically (``self._materialise_skill_files(...)``),
        so an override is picked up automatically without touching
        ``ensure_skill`` itself. An override MUST:

        - Return a :class:`SkillPhaseResult` with ``phase="files"`` — never
          raise, except :class:`SandboxExpiredError` (propagated so the
          caller can evict/recreate the handle).
        - Enforce ``settings.SKILL_IMPORT_MAX_TOTAL_BYTES`` itself before
          transferring any bytes — this is *not* inherited for free once the
          override skips ``build_tar_gz`` (the ABC's own enforcement point).
          A payload that exceeds the cap is a **terminal** failure — do not
          fall back to the per-file writer, which would just re-upload the
          same oversized payload one file at a time with no cap check.
        - Re-apply :func:`safe_member_name` (or equivalent path-safety
          rejection) per file before writing — never trust stored paths
          blindly. An unsafe path is also **terminal**, for the same reason
          as the size cap.
        - Positively verify the result before returning ``status="ok"`` —
          a 2xx/no-exception response from a bulk SDK call is not itself
          proof the files landed correctly; confirm via a verified command
          (``_run_verified_command``) or an equivalent read-back before
          reporting success. On verification failure, fall through to
          ``_materialise_skill_files_per_file`` like every other
          non-terminal failure branch.
        - Clean (``rm -rf``) *and* recreate the target directory first, so a
          re-materialisation never leaves stale files from an older skill
          version, and a content-only skill (no bundled files) still ends up
          with an actually-existing ``files_dir``.
        - Fall back to :meth:`_materialise_skill_files_per_file` (inherited,
          not overridden) for any other failure — SDK call errors, missing
          SDK models on an older/mismatched version, unexpected exceptions.

        The ABC default below implements this contract using only
        ``write_file``/``run_code`` so it works for any provider that offers
        no better primitive.
        """
        start = time.monotonic()
        target_dir = skill_dir(root, name)
        archive_path = f"{root}/{name}.tar.gz"

        # Round-2 MEDIUM fix: clean the destination directory before
        # (re-)materialising. Without this, a re-materialisation (marker hit
        # with a changed checksum) left old files from a previous version of
        # the skill on disk alongside the new ones — a file removed in a
        # newer skill package version stayed live in an already-running
        # sandbox forever. Harmless (and cheap) on a genuinely first-time
        # materialisation, where the directory doesn't exist yet.
        # `_run_verified_command` so a failure here is detected (returned as
        # a failed phase) rather than silently ignored — the fallback
        # per-file path also starts from `_materialise_skill_files_per_file`
        # via the branches below, so this single cleanup covers both.
        clean_ok, clean_output = self._run_verified_command(
            handle,
            f"rm -rf {shlex.quote(target_dir)}",
            language="bash",
            timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
        )
        if not clean_ok:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "ensure_skill: could not clean previous directory for skill %r before "
                "materialisation: %s",
                name, clean_output,
            )
            return SkillPhaseResult(
                phase="files",
                status="failed",
                detail=truncate_detail(
                    f"could not clean previous skill directory before materialisation: {clean_output}"
                ),
                duration_ms=duration_ms,
            )

        try:
            archive_bytes = build_tar_gz(payload)
        except SandboxExpiredError:
            raise
        except ValueError as path_exc:
            # A path rejected by build_tar_gz's safety check is a terminal
            # failure, not a reason to fall back to the per-file writer — the
            # fallback re-applies the same check, but treating this as
            # terminal here avoids ever depending on that second line of
            # defence to catch a traversal attempt.
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("ensure_skill: rejecting skill %r — unsafe file path: %s", name, path_exc)
            return SkillPhaseResult(
                phase="files",
                status="failed",
                detail=truncate_detail(f"rejected unsafe file path in skill package: {path_exc}"),
                duration_ms=duration_ms,
            )
        except SkillPackageTooLargeError as size_exc:
            # Same reasoning as the ValueError branch above: a payload that
            # exceeds the configured cap must never fall back to the
            # per-file writer, which would just re-upload the same
            # oversized payload one file at a time without any size check.
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("ensure_skill: rejecting skill %r — payload too large: %s", name, size_exc)
            return SkillPhaseResult(
                phase="files",
                status="failed",
                detail=truncate_detail(f"skill package too large: {size_exc}"),
                duration_ms=duration_ms,
            )
        except Exception as archive_exc:
            logger.warning(
                "ensure_skill: archive build failed for skill %r, falling back to per-file writes: %s",
                name, archive_exc,
            )
            return self._materialise_skill_files_per_file(handle, payload, name, root, start)

        try:
            # H7 (follow-up for step_017/018): write_file has no timeout on the
            # abstract signature, and at least OpenSandbox's concrete
            # implementation doesn't bound this upload either — an unbounded
            # wait on a shared worker thread if the archive is large or the
            # connection stalls. Tracked, not fixed here to avoid a
            # provider-wide signature rewrite in this step.
            self.write_file(handle, archive_path, archive_bytes)
            ok, output = self._run_verified_command(
                handle,
                extraction_command(root, name),
                language="bash",
                timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
            )
            if not ok:
                raise RuntimeError(f"extraction command did not confirm success: {output}")
            duration_ms = int((time.monotonic() - start) * 1000)
            return SkillPhaseResult(
                phase="files",
                status="ok",
                detail=f"materialised {len(payload.files)} file(s) via archive extraction",
                duration_ms=duration_ms,
            )
        except SandboxExpiredError:
            raise
        except Exception as archive_exc:
            logger.warning(
                "ensure_skill: archive materialisation failed for skill %r, falling back to "
                "per-file writes: %s",
                name, archive_exc,
            )
            # MEDIUM: best-effort cleanup of the leftover archive — the
            # extraction command's own "&& rm -f" only runs when the whole
            # chain (including tar) succeeds, so a failed tar leaves it behind.
            try:
                self.run_code(
                    handle,
                    f"rm -f {shlex.quote(archive_path)}",
                    language="bash",
                    timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
                )
            except SandboxExpiredError:
                raise
            except Exception:
                pass
            return self._materialise_skill_files_per_file(handle, payload, name, root, start)

    def _materialise_skill_files_per_file(
        self,
        handle: SandboxHandle,
        payload: SkillPackagePayload,
        name: str,
        root: str,
        start: float | None = None,
    ) -> SkillPhaseResult:
        """Phase-1 fallback: write every package file individually (no archive/tar)."""
        start = time.monotonic() if start is None else start
        target_dir = skill_dir(root, name)
        try:
            try:
                # Best-effort — most providers' write_file creates parent dirs on
                # its own; this just makes an empty-file skill directory exist too.
                ok, _output = self._run_verified_command(
                    handle,
                    f"mkdir -p {shlex.quote(target_dir)}",
                    language="bash",
                    timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
                )
                if not ok:
                    logger.warning(
                        "ensure_skill: mkdir -p did not confirm success for skill %r target=%s",
                        name, target_dir,
                    )
            except SandboxExpiredError:
                raise
            except Exception:
                pass
            for path, data in payload.files:
                # MEDIUM: re-apply the same path-safety check the archive
                # builder uses — this loop must never trust stored data
                # blindly, in case it is ever reached without having gone
                # through build_tar_gz's validation first.
                safe_path = safe_member_name(path)
                self.write_file(handle, f"{target_dir}/{safe_path}", data)
            duration_ms = int((time.monotonic() - start) * 1000)
            return SkillPhaseResult(
                phase="files",
                status="ok",
                detail=f"materialised {len(payload.files)} file(s) via per-file writes (fallback)",
                duration_ms=duration_ms,
            )
        except SandboxExpiredError:
            raise
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "ensure_skill: per-file fallback also failed for skill %r: %s", name, exc
            )
            return SkillPhaseResult(
                phase="files",
                status="failed",
                detail=truncate_detail(f"could not materialise skill files: {exc}"),
                duration_ms=duration_ms,
            )

    @staticmethod
    def _extract_marker_exit_code(output: str, marker: str) -> int | None:
        """Parse the ``<marker>=<exit code>`` sentinel appended to the bootstrap
        command (C2). Returns ``None`` if the marker is missing or malformed."""
        if not isinstance(output, str):
            return None
        prefix = f"{marker}="
        idx = output.rfind(prefix)
        if idx == -1:
            return None
        digits = ""
        for ch in output[idx + len(prefix):]:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _run_skill_bootstrap(
        self, handle: SandboxHandle, payload: SkillPackagePayload, name: str, root: str
    ) -> SkillPhaseResult:
        """Phase 2: run the bootstrap script from the skill directory, if any."""
        if not payload.bootstrap_script_path:
            return SkillPhaseResult(
                phase="bootstrap", status="skipped", detail="no bootstrap script", duration_ms=0
            )
        start = time.monotonic()
        target_dir = skill_dir(root, name)
        nonce = uuid.uuid4().hex
        rc_marker = f"__SKILL_BOOTSTRAP_RC_{nonce}__"
        log_path = f"/tmp/.mattin-skill-bootstrap-{nonce}.log"
        quoted_log_path = shlex.quote(log_path)
        # Round-2 H-C fix: the documented bootstrap use case (`pip install`)
        # routinely emits well over `SANDBOX_MAX_OUTPUT_CHARS` (20000 by
        # default) of output, and providers truncate captured output by
        # keeping the HEAD (see opensandbox_provider.run_code) — so echoing
        # the rc-marker last, straight into the same unbounded stream (the
        # round-1 shape), let a verbose-but-successful bootstrap get its own
        # rc-marker truncated away and misreported as failed/degraded.
        # Redirecting the script's own stdout/stderr to a sandbox-side log
        # file and only echoing a bounded tail of it (well under the output
        # cap) keeps the rc-marker line always present and always last.
        # Wrapped in a subshell so `cd` never leaks into later reused
        # execution contexts on providers that pool them; the exit-code
        # sentinel is what lets us tell a failed/timed-out script apart from
        # a successful one (run_code returns a string either way — C2).
        cmd = (
            f"( cd {shlex.quote(target_dir)} && bash {shlex.quote(payload.bootstrap_script_path)} ) "
            f"> {quoted_log_path} 2>&1; rc=$?; "
            f"tail -c 4000 {quoted_log_path}; "
            f'echo "{rc_marker}=$rc"; '
            f"rm -f {quoted_log_path}"
        )
        try:
            output = self.run_code(
                handle,
                cmd,
                language="bash",
                timeout=settings.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S,
                max_output_chars=settings.SANDBOX_MAX_OUTPUT_CHARS,
            )
        except SandboxExpiredError:
            raise
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "ensure_skill: bootstrap script failed for skill %r: %s", name, exc
            )
            return SkillPhaseResult(
                phase="bootstrap",
                status="failed",
                detail=truncate_detail(f"bootstrap script failed: {exc}"),
                duration_ms=duration_ms,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        exit_code = self._extract_marker_exit_code(output, rc_marker)
        is_provider_error = isinstance(output, str) and output.lstrip().startswith("[Error]")
        if is_provider_error or exit_code is None or exit_code != 0:
            detail = (
                f"bootstrap script failed (exit_code={exit_code}): {output}"
                if exit_code is not None
                else f"bootstrap script did not confirm success: {output}"
            )
            logger.warning("ensure_skill: bootstrap script failed for skill %r: %s", name, truncate_detail(detail))
            return SkillPhaseResult(
                phase="bootstrap",
                status="failed",
                detail=truncate_detail(detail),
                duration_ms=duration_ms,
            )

        return SkillPhaseResult(
            phase="bootstrap",
            status="ok",
            detail=truncate_detail(output or "bootstrap completed"),
            duration_ms=duration_ms,
        )

    def _log_skill_activation(self, handle: SandboxHandle, result: SkillActivationResult) -> None:
        """Log once per ``ensure_skill`` call at INFO (NFR-7) — no file contents."""
        logger.info(
            "ensure_skill: sandbox=%s skill=%r status=%s phases=%s",
            handle.sandbox_id,
            result.skill_name,
            result.status,
            [(p.phase, p.status, p.duration_ms) for p in result.phases],
        )
