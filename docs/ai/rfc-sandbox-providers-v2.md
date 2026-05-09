# RFC v2: Sandbox Providers, Skills Runtime, and Lifecycle Recovery

> Part of [Mattin AI Documentation](../index.md)  
> **Status**: Draft v2 — May 8, 2026  
> **Supersedes**: [RFC: Sandbox Provider Integration](rfc-sandbox-providers.md) as the next-iteration design target  
> **Branch context reviewed**: `exp/sandbox`

## 1. Purpose

This RFC v2 updates the sandbox and Skills design after reviewing the current implementation and
the external review notes. The goal is to make Mattin's managed sandbox behavior closer to the
Skill lifecycle Anthropic documents for Claude:

1. Load only Skill metadata up front.
2. Activate a Skill when the task matches its description.
3. Load the full `SKILL.md` body only when relevant.
4. Load or execute supporting resources only when needed.

The current implementation has a useful provider seam, an OpenSandbox adapter, basic file
round-trip, and a `load_skill` tool that can prepare a Skill's runtime environment when needed.
The next iteration should focus on resilience and correctness: reconnecting to existing
sandboxes, recovering from expiry, tracking Skill activation phases, avoiding hidden failure
states, and adding an explicit metadata-only Skill router.

## 2. Current-Code Audit

The review covered these implementation files:

| Area | Files reviewed | Current state |
|---|---|---|
| Provider API | `backend/tools/sandbox/provider.py` | Synchronous ABC. `SandboxHandle` already has `sandbox_id`, `working_dir`, `provider_name`, and `metadata`, but no typed `active_skills` field. |
| OpenSandbox adapter | `backend/tools/sandbox/opensandbox_provider.py` | Creates new sandboxes with `SandboxSync.create`, supports persistent code contexts and stdout callbacks. It does not resume, renew, or implement `ensure_skill`. |
| Subprocess adapter | `backend/tools/sandbox/subprocess_provider.py` | Backward-compatible local execution. Still passes `env=os.environ.copy()` to subprocesses and uses a hard-coded `MAX_OUTPUT_CHARS = 20_000`. |
| Session lifecycle | `backend/services/sandbox_session_service.py` | In-memory `_sessions` cache with a reaper thread. `Conversation.sandbox_session_id` exists, but the service does not persist or resume by that ID. |
| Agent integration | `backend/services/agent_execution_service.py`, `backend/tools/agentTools.py` | Sandboxes are prepared before tool assembly and remote files are pushed/pulled. Reset currently computes a different key shape than turn preparation, so destroy can miss the active sandbox. |
| Skills | `backend/models/skill.py`, `backend/services/skill_service.py`, `backend/tools/skill_tools.py` | `Skill` has draft runtime fields and import/export support. `load_skill` auto-calls `ensure_skill` for Skills marked with `runtime == "python-sandbox"`, but this runtime behavior has not been released and can be redesigned cleanly. |
| Streaming | `backend/tools/sandbox/tool_factory.py`, `backend/tools/streaming_utils.py` | `run_code` already accepts an `on_stdout` callback and emits `code_output` through `get_stream_writer()`. Stderr streaming and structured execution status are not first-class. |

Key gaps:

- `sandbox_session_id` is stored on `Conversation` but not used to resume OpenSandbox sessions.
- `SandboxSessionService` is not multi-worker safe; each process has a separate `_sessions` dict.
- OpenSandbox `ensure_skill` is missing, so runtime environment preparation is only effective for
  `SubprocessProvider`, where it only records metadata.
- Active Skill state is split between `_Entry.active_skills` and provider handle metadata, and is
  not persisted.
- No phase status exists for Skill files or bootstrap.
- `load_skill` idempotency is based on a tool-instance closure, not the live sandbox id.
- Subprocess execution still exposes backend environment variables.
- `run_code` has no per-turn execution budget and output truncation is not configurable.
- Skill triggering still relies mostly on system-prompt guidance and tool choice; there is no
  explicit metadata-only router.

### 2.1 Delta Against Current Implementation

This RFC is not a description of the code as-is. It is the target for the next iteration. The
current implementation should be changed as follows:

| Area | Current implementation | RFC v2 target | Required change |
|---|---|---|---|
| `SandboxHandle` | `sandbox_id`, `working_dir`, `provider_name`, and untyped `metadata`. Active Skills are stored ad hoc in `metadata["active_skills"]` or `_Entry.active_skills`. | Add `session_key` and typed `active_skills: dict[str, dict]` to the handle. Keep `metadata` only for provider internals. | Extend the dataclass and migrate providers/tools to read/write `handle.active_skills`. |
| Provider lifecycle API | `create_sandbox(working_dir, **kwargs)` always creates. No `renew_sandbox`. No explicit expired-sandbox error type. | `create_sandbox(..., existing_sandbox_id=...)` resumes where possible; `renew_sandbox()` refreshes TTL; expiry maps to `SandboxExpiredError`. | Update `SandboxProvider`, `OpenSandboxProvider`, `SubprocessProvider`, and tests. |
| Provider execution API | `run_code(..., language, on_stdout)` only. Timeout and output size are hard-coded in providers. Stderr is not streamed. | `run_code(..., timeout, max_output_chars, on_stdout, on_stderr)` plus `run_code_streaming()` helper. | Add parameters and use `SANDBOX_MAX_OUTPUT_CHARS`; stream stderr through custom events. |
| OpenSandbox lifecycle | `SandboxSync.create()` only. Image is provider env config. No resume/renew or expiry recovery. | Resume by `Conversation.sandbox_session_id`; renew on every turn; create fresh only when resume fails. Image remains provider/app/deployment config, not Skill config. | Implement resume/renew capability detection and fallback behavior. |
| OpenSandbox Skill activation | `OpenSandboxProvider` does not implement `ensure_skill`; base class raises `NotImplementedError`. | `ensure_skill` writes Skill package files to `/workspace/.skills/{name}`, runs reviewed bootstrap when configured, and records phase status. | Implement file copy, bootstrap, phase state, and persistence hooks. Do not parse dependency manifests. |
| Subprocess provider | Uses `env=os.environ.copy()`, hard-coded timeout/output limit, and records Skill activation in metadata without phases. | Local-dev provider only, filtered env, configurable output limit, timeout parameter, phaseful Skill record. | Add safe env filtering, config-backed limits, and phaseful activation state. |
| Session persistence | `SandboxSessionService` stores `_sessions` in process memory only. `Conversation.sandbox_session_id` exists but is not populated/resumed by the service. | DB-backed lifecycle: `Conversation.sandbox_session_id` plus `sandbox_state`; in-memory registry is a cache. No Redis for this iteration. | Add `Conversation.sandbox_state`, load/persist state on create/resume/ensure/destroy, and coordinate concurrent creates through DB. |
| Session keys | Turn preparation uses `conv_{agent_id}_{conversation_id}`. Reset destroys `thread_{agent_id}_{session.id}`. `destroy_all_for_agent()` looks for `thread_{agent_id}_`, so it can miss `conv_...` keys. | A single helper derives keys for turn creation, reset, delete, and agent deletion. | Introduce and use `SandboxSessionService.session_key(...)` everywhere. |
| Expiry recovery | Cache hit returns the handle without renewal. Run failures return error strings, not typed expiry signals. | Renew on every turn; if renew/run indicates expiry, recreate and re-activate still-authorized Skills from current DB records. | Add provider error mapping and session-service recovery path. |
| Conversation cleanup | Reset attempts destroy with the wrong key shape. Delete endpoints/services do not consistently destroy persisted sandbox state. Reaper only touches in-memory sessions. | Reset/delete/agent-delete/reaper destroy provider sandbox and clear `sandbox_session_id` + `sandbox_state`. | Wire cleanup into reset/delete services and reaper persistence. |
| Skill model | `Skill.dependencies`, `runtime`, and `runtime_options` are draft runtime fields. Import/export serializes dependencies. Built-in seed data includes Python package deps. | No released dependency registry. Execution requirements live in `SKILL.md` body and reviewed bootstrap/supporting files. `runtime == "python-sandbox"` must be retired before release. | Remove dependency-based runtime contract from schemas, import/export, prompts, built-in seed data, and tool filtering. |
| Skill package repository | `SkillService.export_skill_zip()` writes `SKILL.md` plus supporting files under `files/<path>`. Import parses selected frontmatter fields and drops unknown fields. | Store and export a canonical Agent Skills package: `SKILL.md` at root, package-root-relative bundled resources such as `scripts/*`, `references/*`, and `assets/*`, raw frontmatter preserved, and metadata/body/resources available through progressive-disclosure repository methods. | Add package-aware validation/import/export APIs, migrate `files/<path>` archives as a compatibility input only, and make canonical export portable to Agent Skills-compatible clients. |
| `load_skill` | Uses closure `_loaded_skills` for idempotency, gates setup on `runtime == "python-sandbox"`, swallows setup errors, and returns no phase status. | Idempotency uses `handle.active_skills` and `sandbox_id`; setup happens for Skills with supporting/bootstrap files; errors are visible as phase status. | Replace closure-only cache, remove runtime marker gating, surface phase status in tool output. |
| Sandbox Skill tools | `create_sandbox_skill_tools` exposes activation only for `runtime == "python-sandbox"` and says it installs dependencies/assets. | Activation is an override/retry tool for attached Skills with package files/bootstrap. It must not promise dependency installation. | Filter by actual package/bootstrap availability and rewrite tool descriptions. |
| Skill triggering | Main LLM sees a prompt list and may call `load_skill`. No explicit router exists. | Metadata-only `skill_router` selects relevant attached Skills before the main LLM. Router sees no body, files, or execution requirements. | Add graph node or pre-model middleware with structured decision output. |
| File sync | Remote file push/pull exists. `OpenSandboxProvider.list_files()` returns basenames only, which loses nested paths. Finalizer skips `.skills/**` defensively. | Providers return workspace-relative paths so nested outputs can sync safely and `.skills/**` is reliably excluded. | Change `list_files()` to return relative paths and update tests/finalizer expectations. |
| Execution budget | No per-turn execution counter. | `SANDBOX_MAX_EXECUTIONS_PER_TURN` limits REPL calls per turn. | Add counter in agent/tool state and return clear budget errors. |
| Output budget | `MAX_OUTPUT_CHARS = 20_000` constants in providers. | `SANDBOX_MAX_OUTPUT_CHARS` config with truncation marker. | Replace constants and add tests. |
| Config | Current config has provider selection, OpenSandbox image, TTL, create timeout, execution timeout, and an install-timeout setting. | Keep provider/app image config. Remove dependency-install config from the target runtime design. Add renew, max executions, max output, and bootstrap timeout. | Update `backend/config.py`, env docs, and tests. |

## 3. Anthropic Alignment Principles

The design target is not to copy Claude Code internals, but to adopt the observable lifecycle:

| Anthropic behavior | Mattin target |
|---|---|
| Skill names and descriptions are available up front; bodies stay lazy. | Agent state and the Skill router see only `name`, `description`, and optional `when_to_use`. |
| A matching task causes automatic Skill activation. | A `skill_router` node selects zero or more attached Skills before the main LLM turn. |
| Full `SKILL.md` content is loaded only when invoked. | `load_skill` remains the body loader; the router may call the loader internally. |
| Supporting files/scripts load only as needed. | `ensure_skill` writes files and prepares runtime only after a Skill is selected, not when attached. |
| Descriptions drive activation quality. | Mattin validates and surfaces authoring guidance for descriptions; router never reads the full body for selection. |
| Tool permissions are controlled by the host environment. | Mattin preserves `allowed-tools` for import/export compatibility but enforces real permissions through Mattin tool policy. |

## 4. Decisions

1. Keep one Skill catalogue.
   Do not introduce `SandboxPackage`, `PromptSkill`, or `RuntimeSkill` as separate product
   concepts. `Skill` remains the single reusable capability unit. Execution setup is described
   by the Skill package, not by a different Skill type or dependency registry.

2. Store sandbox lifecycle state outside process memory.
   The in-memory registry becomes a cache only. `Conversation` is the source of truth for this
   iteration. Redis is explicitly out of scope for now.

3. Resume before create.
   Providers that support reconnecting must try `existing_sandbox_id` first. If resume fails,
   create a new sandbox, clear active runtime state, and re-activate recoverable Skills.

4. Treat Skill activation as phaseful.
   File copy and bootstrap each get independent status. Runtime requirements are described by
   the Skill document; Mattin should not maintain a separate dependency registry.

5. Make automatic Skill triggering explicit.
   Add a metadata-only `skill_router` before the main LLM call. Prompt hints and `load_skill`
   remain fallback/override paths.

6. Prefer structured status over swallowed errors.
   `load_skill` can still return instructions when runtime setup fails, but it must return an
   explicit warning and must not cache the Skill as healthy.

## 5. Data Model Changes

### 5.1 `SandboxHandle`

Current code already has `sandbox_id`, so the new target should extend the existing shape rather
than reverting to the older RFC sketch:

```python
@dataclass
class SandboxHandle:
    sandbox_id: str
    working_dir: str
    provider_name: str
    session_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Runtime Skill state for this concrete sandbox id.
    active_skills: dict[str, dict[str, Any]] = field(default_factory=dict)
```

Compatibility note: `active_skills` may initially be mirrored into `metadata["active_skills"]`
until all tests and call sites are migrated.

### 5.2 `Conversation` Sandbox State

`Conversation.sandbox_session_id` exists and should continue to store the provider sandbox id.
Add one JSON/Text column for state that cannot fit in a scalar id:

```python
sandbox_state = Column(Text, nullable=True)
```

Serialized shape:

```json
{
  "provider": "opensandbox",
  "session_key": "conv_12_456",
  "sandbox_id": "sbx_abc",
  "sandbox_image": "opensandbox/code-interpreter:v1.0.2",
  "active_skills": {
    "word-generation": {
      "skill_id": 10,
      "sandbox_id": "sbx_abc",
      "files_dir": "/workspace/.skills/word-generation",
      "phases": {
        "files": "ok",
        "bootstrap": "skipped"
      }
    }
  },
  "updated_at": "2026-05-08T10:00:00Z"
}
```

If a JSON column type becomes available for all supported databases, use it. Until then, mirror
the existing JSON-text pattern and store serialized state.

### 5.3 Skill Runtime Metadata

The Skill definition must not own the sandbox image. Sandbox image selection is a provider,
deployment, or app-level concern because the image defines the whole conversation environment,
not one isolated Skill. A Skill can declare requirements, but it cannot force Mattin to switch
the sandbox image mid-conversation.

Keep these fields or parse them from `SKILL.md`:

| Field | Storage | Purpose |
|---|---|---|
| `egress_policy` | `runtime_options["egress_policy"]` initially | Declarative network policy hint. Enforced only when the provider supports it. |
| `when_to_use` | `frontmatter` | Optional Anthropic-compatible trigger text appended to the router metadata. |
| `disable-model-invocation` | `frontmatter` | If true, `skill_router` must not auto-select this Skill. Manual `load_skill` may still work if authorized. |

Recommended implementation path:

1. Parse and preserve all frontmatter fields during import.
2. Remove the unreleased flat `Skill.dependencies` runtime contract from the release target.
3. Keep provider-specific and policy fields in `runtime_options` until semantics stabilize.

### 5.4 Execution Requirements in `SKILL.md`

The draft `Skill.dependencies` field is a flat list of Python package specs. Because the runtime
functionality has not been released, v2 does not need to preserve that shape as a public contract.
It should be removed from the target design rather than generalized into another registry.

The v2 model treats execution requirements as part of the Skill definition document:

- `description` answers "when should this Skill be used?"
- `content` answers "how should the model use this Skill?"
- the body of `SKILL.md` may describe libraries, expected tools, setup assumptions, fallback
  strategies, and language-specific examples;
- bootstrap files may perform deterministic setup when the Skill package owns that setup.

Mattin should not parse, store, or install package dependencies from a separate runtime dependency
field. If a Skill needs package setup, that setup must be expressed in the Skill document and, if
automation is required, in a reviewed bootstrap script that is part of the Skill package.
`description` remains activation metadata for the router and should not be used as a dependency
manifest.

### 5.5 Skill Package Repository

Mattin should treat the database as an indexed storage layer for a portable Agent Skills package,
not as a separate Mattin-only runtime package format. The canonical package layout is:

```text
skill-name/
+-- SKILL.md
+-- scripts/
+-- references/
+-- assets/
+-- LICENSE.txt
+-- agents/
|   +-- openai.yaml
+-- other optional files
```

Only `SKILL.md` is required. `scripts/`, `references/`, and `assets/` are optional bundled
resources. Mattin may preserve additional files such as `LICENSE.txt` and `agents/openai.yaml`,
but model-facing behavior must still follow progressive disclosure: metadata first, full
`SKILL.md` body on activation, bundled resources only when referenced or copied into a sandbox.

#### Repository Contract

Add a package-aware repository/service layer rather than spreading package semantics across
routers, providers, and tools:

```python
class SkillPackageRepository:
    def import_package(db, app_id, zip_bytes, *, source="upload") -> Skill: ...
    def export_package(db, app_id, skill_id) -> bytes: ...
    def validate_package(zip_bytes | directory) -> SkillPackageValidation: ...
    def get_catalog(db, app_id) -> list[SkillCatalogItem]: ...
    def get_activation_payload(db, app_id, skill_name) -> SkillActivationPayload: ...
    def list_files(db, skill_id) -> list[SkillFileSummary]: ...
    def read_file(db, skill_id, path) -> SkillFileContent: ...
```

The repository contract exists to support the three tiers:

| Method | Disclosure tier | Must return |
|---|---|---|
| `get_catalog` | Metadata | `name`, `description`, and router-safe frontmatter such as `when_to_use` and `disable-model-invocation`. No body or file content. |
| `get_activation_payload` | Instructions | Skill body, preserved frontmatter if needed, package-root path metadata, and a bounded resource listing. No eager resource reads. |
| `list_files` / `read_file` | Resources | Specific bundled resources requested by the model, tool, or provider after activation. |
| `export_package` | Portability | A canonical ZIP whose root contains `SKILL.md` and bundled files at package-root-relative paths. |

Current `files/<path>` export archives should remain importable as a migration compatibility input,
but all new exports must use the canonical root-relative layout:

```text
SKILL.md
scripts/bootstrap.py
references/schema.md
assets/template.docx
agents/openai.yaml
LICENSE.txt
```

#### Storage Mapping

The existing `Skill` and `SkillFile` tables remain the source of truth, with tighter semantics:

| Field | Target meaning |
|---|---|
| `Skill.name` | Required frontmatter `name`; normalized by Agent Skills naming rules for new packages. |
| `Skill.description` | Required frontmatter `description`; router metadata. |
| `Skill.content` | Markdown body after the frontmatter, loaded only on activation. |
| `Skill.frontmatter` | Raw or canonical serialized frontmatter. Preserve unknown fields for round-trip portability. |
| `Skill.allowed_tools` | Parsed compatibility metadata from `allowed-tools`; host enforcement still comes from Mattin policy. |
| `Skill.bootstrap_script_path` | Mattin runtime hint pointing to a package-root-relative file such as `scripts/bootstrap.py`. |
| `Skill.runtime_options` | Mattin/provider policy hints such as egress policy. Do not expose this as a dependency registry. |
| `SkillFile.path` | Package-root-relative path, for example `scripts/setup.py`, `references/api.md`, or `assets/logo.png`. |

`SkillFile.path` must never be absolute, contain `..`, or normalize outside the package root. A
derived role such as `script`, `reference`, `asset`, or `other` may be added for UI filtering, but
the path prefix remains the portable contract.

#### Validation Rules

Package validation should distinguish hard errors from warnings.

Hard errors:

- missing root `SKILL.md`;
- unparseable frontmatter when no compatibility fallback can recover it;
- missing or empty `name` or `description`;
- unsafe paths: absolute paths, path traversal, duplicate normalized paths, or paths under
  reserved sandbox internals;
- archive limits exceeded: total size, file count, per-file size, or decompressed size ratio.

Warnings:

- package directory or ZIP top-level folder does not match `name`;
- `SKILL.md` body is unusually large and should move details into `references/`;
- unknown frontmatter fields are present;
- deprecated draft fields such as `runtime` or `dependencies` are present;
- bundled resources are present but not referenced from `SKILL.md`;
- `allowed-tools` is present but cannot be directly enforced by Mattin's current tool policy.

The import path should be lenient enough to load existing Agent Skills packages, but the UI/API
should surface validation diagnostics so administrators can fix portability and activation issues.

#### API Shape

Keep existing CRUD endpoints, but add package-oriented operations:

```text
GET    /skills/                         # catalog/list
GET    /skills/{id}                     # detail
POST   /skills/{id}                     # edit metadata/body
POST   /skills/import                   # upload canonical skill zip
GET    /skills/{id}/export              # canonical zip
POST   /skills/validate                 # validate before import
GET    /skills/{id}/files               # package tree
GET    /skills/{id}/files/content?path=references/foo.md
PUT    /skills/{id}/files/content?path=scripts/foo.py
DELETE /skills/{id}/files?path=assets/foo.png
```

Activation tools and sandbox providers should consume the repository payloads rather than
reconstructing package state from ad hoc fields. In particular, `ensure_skill` copies the package
files from `SkillFile.path` into `/workspace/.skills/{skill.name}/...` with the same relative paths,
then optionally runs the reviewed `bootstrap_script_path`.

## 6. Provider API v2

The current implementation is synchronous, so this RFC defines a synchronous contract with
optional async wrappers later. The key is behavior, not `async` syntax.

```python
class SandboxExpiredError(RuntimeError):
    pass


class SandboxProvider(ABC):
    PROVIDER_NAME: str
    SUPPORTED_LANGUAGES: list[str] = ["python"]

    @abstractmethod
    def create_sandbox(
        self,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        """Resume existing_sandbox_id when possible; otherwise create a sandbox."""

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        """Extend provider TTL. Default no-op for providers without TTL support."""

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
        """Execute code and return truncated combined output."""

    def run_code_streaming(self, handle, code, stream_writer, **kwargs) -> str:
        """Bridge provider stdout/stderr callbacks to LangGraph custom stream."""

        def stdout(line: str) -> None:
            stream_writer({"type": "code_output", "stream": "stdout", "line": line})

        def stderr(line: str) -> None:
            stream_writer({"type": "code_output", "stream": "stderr", "line": line})

        return self.run_code(handle, code, on_stdout=stdout, on_stderr=stderr, **kwargs)

    @abstractmethod
    def ensure_skill(self, handle: SandboxHandle, skill: Skill) -> dict[str, Any]:
        """Activate one Skill and return phase status."""

    @abstractmethod
    def list_active_skills(self, handle: SandboxHandle) -> dict[str, dict[str, Any]]:
        """Return enriched Skill state, not just names."""
```

### 6.1 OpenSandboxProvider Changes

Required changes:

- Use `SandboxSync.resume(existing_sandbox_id, connection_config=...)` if available in the SDK.
- Call `sandbox.renew(duration)` on cache hits and after resume.
- Set `handle.sandbox_id = sandbox.id` and persist it to `Conversation`.
- Use the provider/app configured sandbox image. Skill definitions must not override the image.
- Raise `SandboxExpiredError` for resume/renew/run failures that indicate the remote sandbox no
  longer exists.
- Implement `ensure_skill`.
- Support `on_stderr` callbacks through `ExecutionHandlersSync`.

If the current OpenSandbox SDK version does not expose `resume` or `renew`, the provider should:

1. Detect the missing capability at startup.
2. Log one warning.
3. Fall back to create-only behavior.
4. Mark `provider_capabilities = {"resume": False, "renew": False}` in handle metadata so the
   session service can avoid pretending recovery is guaranteed.

### 6.2 SubprocessProvider Changes

`SubprocessProvider` remains local-dev only, but it must stop leaking secrets by default:

```python
BLOCKED_ENV_PATTERNS = (
    "API_KEY",
    "SECRET",
    "DATABASE_URI",
    "PASSWORD",
    "TOKEN",
    "PRIVATE_KEY",
)

safe_env = {
    k: v
    for k, v in os.environ.items()
    if not any(pattern in k.upper() for pattern in BLOCKED_ENV_PATTERNS)
}
```

Other required changes:

- Read `SANDBOX_MAX_OUTPUT_CHARS` instead of using a module constant.
- Honor the passed `timeout` parameter rather than only `DEFAULT_TIMEOUT`.
- Emit a startup warning if this provider is selected outside explicit development mode.
- Store phaseful Skill records with `"provider": "subprocess"` and skipped runtime setup phases.

## 7. SandboxSessionService v2

### 7.1 Responsibilities

`SandboxSessionService` must become the lifecycle authority:

- derive one stable `session_key`;
- resume existing provider sandboxes where possible;
- renew TTL on every turn;
- persist `sandbox_id` and `active_skills`;
- recover from expiry;
- destroy on reset, delete, and agent deletion;
- keep memory cache as an optimization only.

### 7.2 Stable Session Keys

Fix the current key mismatch:

- Turn preparation currently uses `conv_{agent_id}_{conversation_id}`.
- Reset currently destroys `thread_{agent_id}_{session.id}`.

The v2 contract is:

```python
def session_key(agent_id: int, conversation_id: int | str | None, session_id: str | None) -> str:
    if conversation_id is not None:
        return f"conv_{agent_id}_{conversation_id}"
    if session_id is not None:
        return f"thread_{agent_id}_{session_id}"
    return f"anon_{agent_id}"
```

Every create, reset, delete, and pull/push path must call this helper.

### 7.3 `get_or_create`

```python
def get_or_create(
    self,
    session_key: str,
    provider: SandboxProvider,
    working_dir: str,
    *,
    conversation: Conversation | None = None,
    skills_to_restore: Callable[[list[int]], list[Skill]] | None = None,
) -> SandboxHandle:
    with self._lock:
        entry = self._sessions.get(session_key)
        if entry is not None:
            try:
                provider.renew_sandbox(entry.handle, _renew_duration())
                entry.last_used = time.monotonic()
                return entry.handle
            except SandboxExpiredError:
                self._sessions.pop(session_key, None)
                persisted_state = entry.handle.active_skills

    saved = _load_sandbox_state(conversation)
    handle = provider.create_sandbox(
        working_dir,
        session_key=session_key,
        existing_sandbox_id=saved.sandbox_id if saved else None,
    )

    if saved and saved.sandbox_id != handle.sandbox_id:
        # Resume failed and provider created a fresh sandbox. Skill files/deps
        # must be reinstalled; old active state was for another filesystem.
        saved.active_skills = {}

    handle.active_skills = saved.active_skills if saved and saved.sandbox_id == handle.sandbox_id else {}
    _persist_sandbox_state(conversation, handle)

    with self._lock:
        self._sessions[session_key] = _Entry(handle=handle, provider=provider)
    return handle
```

Restoring Skills after recreation must be explicit and bounded:

- Restore only Skills that were previously active and still attached to the agent.
- Re-run `ensure_skill` because a new sandbox has a new filesystem.
- Preserve failed phases in state so the LLM and UI can see degraded setup.
- Do not restore setup behavior from stale serialized state without resolving the current `Skill`
  record from the database.

### 7.4 Persistence Backend

Recommended default: `Conversation.sandbox_session_id` + `Conversation.sandbox_state`.
No Redis will be used in this iteration. Horizontal workers must coordinate through the database
row, using normal transaction boundaries and a short lock or compare-and-swap update when two
requests try to create/resume the same conversation sandbox concurrently.

### 7.5 Destroy Hooks

Required call sites:

| Event | Call site | Required action |
|---|---|---|
| Conversation reset | `AgentExecutionService.reset_conversation` and public/internal reset endpoints | Destroy by stable `session_key`, clear `Conversation.sandbox_session_id`, clear `sandbox_state`. |
| Conversation delete | `ConversationService.delete_conversation` or the router before delete | Destroy before deleting or immediately after loading the conversation row. |
| Agent delete | `AgentService.delete_agent` | Destroy all in-memory sessions for the agent and query persisted conversations with sandbox ids. |
| Idle reaper | `SandboxSessionService._reap_stale` | Destroy provider sandbox and clear persisted state. |

## 8. Skill Activation v2

### 8.1 State Shape

Each activation writes this into `handle.active_skills[skill.name]`:

```python
{
    "skill_id": skill.skill_id,
    "skill_name": skill.name,
    "sandbox_id": handle.sandbox_id,
    "files_dir": f"/workspace/.skills/{skill.name}",
    "phases": {
        "files": "ok",
        "bootstrap": "skipped"
    },
    "updated_at": "2026-05-08T10:00:00Z"
}
```

`list_active_sandbox_skills` should summarize this enriched state, for example:

```text
word-generation: files=ok, bootstrap=skipped
charts: files=ok, bootstrap=failed: missing optional font package
```

### 8.2 Idempotency Rule

The idempotency key is `(handle.sandbox_id, skill.skill_id or skill.name)`.

Return early only when:

- the state exists for the same `sandbox_id`;
- `files == ok`;
- bootstrap is either `ok` or `skipped`;
- the caller did not request a retry.

If `bootstrap` failed, `load_skill` may return instructions, but the runtime status must remain
failed and `activate_sandbox_skill` must be able to retry.

### 8.3 OpenSandbox `ensure_skill`

```python
def ensure_skill(self, handle: SandboxHandle, skill: Skill, *, retry: bool = False) -> dict:
    existing = handle.active_skills.get(skill.name)
    if _healthy_for_same_sandbox(existing, handle.sandbox_id) and not retry:
        return existing

    state = {
        "skill_id": skill.skill_id,
        "skill_name": skill.name,
        "sandbox_id": handle.sandbox_id,
        "files_dir": f"/workspace/.skills/{skill.name}",
        "phases": {},
    }
    handle.active_skills[skill.name] = state

    try:
        _write_skill_files(handle, skill, state["files_dir"])
        state["phases"]["files"] = "ok"
    except Exception as exc:
        state["phases"]["files"] = f"failed: {exc}"
        return state

    if skill.bootstrap_script_path:
        try:
            script = _read_skill_file_text(skill, skill.bootstrap_script_path)
            self.run_code(handle, script, timeout=_bootstrap_timeout())
            state["phases"]["bootstrap"] = "ok"
        except Exception as exc:
            state["phases"]["bootstrap"] = f"failed: {exc}"
    else:
        state["phases"]["bootstrap"] = "skipped"

    return state
```

Important behavior:

- File-copy failure stops bootstrap because bootstrap may reference files.
- Bootstrap failure does not mark the Skill inactive; it marks a degraded active state.
- Every phase update should be persisted after the phase completes.

### 8.4 `load_skill`

`load_skill` must be adjusted:

- It should call `ensure_skill` when a Skill has supporting files or bootstrap files. The
  draft `runtime == "python-sandbox"` marker must be retired before release; package files and
  bootstrap metadata are the runtime contract.
- It should include phase status in the returned text.
- It should not add the Skill to the `_loaded_skills` closure if file setup failed.
- It may add the Skill as instruction-loaded even if bootstrap failed, but must tell the
  LLM which runtime capability is degraded.
- The closure cache should be replaced or backed by `handle.active_skills` so idempotency survives
  tool re-creation across turns.

Recommended response on partial failure:

```text
[SKILL ACTIVATED: charts]

Runtime status: files=ok, bootstrap=failed: missing optional font package.
Use the instructions below, but do not assume bootstrap-created assets are available unless you
retry activation successfully or choose a fallback implementation.

...
```

## 9. Skill Router

### 9.1 Why a Router

Anthropic's Skills behavior depends on automatic matching from description metadata. Mattin
currently relies on the main LLM to notice a system-prompt list and call `load_skill`. With many
Skills, that signal gets weak and competes with other tools.

Add an explicit `skill_router` before the main LLM call.

### 9.2 Router Inputs

The router may read only:

- `skill.name`;
- `skill.description`;
- optional `frontmatter.when_to_use`;
- optional `frontmatter.disable-model-invocation`;
- the last few user/assistant messages;
- agent/app policy such as attached Skill ids.

The router must not read `skill.content`, `SkillFile`, templates, references, or execution
requirements described in the Skill body.

### 9.3 Router Output

```python
class SkillRouteDecision(TypedDict):
    selected_skill_names: list[str]
    reason: str
```

Default limit: at most two auto-selected Skills per turn.

### 9.4 Graph Shape

Target LangGraph flow:

```text
request
  -> prepare_turn
  -> skill_router
  -> skill_loader        # internal, loads SKILL.md body and runtime status
  -> llm_with_tools
  -> tool_executor
  -> output_parser
  -> final_response
```

Routing rules:

- If `selected_skill_names` is empty, go directly to `llm_with_tools`.
- If a selected Skill has supporting files or bootstrap files, and code interpreter is enabled,
  call `ensure_skill` before the LLM receives the full instructions.
- Keep `load_skill` as a manual/LLM-callable tool for missed cases and direct user requests.
- Respect `disable-model-invocation: true`; those Skills can be invoked manually but not selected
  automatically.

If the current `create_langchain_agent` wrapper makes a custom node graph too large for one
iteration, implement the router first as pre-model middleware with the same input/output contract.

### 9.5 Description Authoring Contract

Because the router sees only metadata, `description` must be strong enough to trigger the Skill:

- Mention the task type.
- Include common trigger words and file extensions.
- Say when to use the Skill, not only what it contains.
- Be self-contained; do not rely on the body for activation.
- Recommended length: 2-4 sentences, maximum 100 words.

Example:

```yaml
description: Create and edit Word documents using python-docx. Use when the user asks for DOCX reports, letters, contracts, proposals, or any formatted editable document. Trigger on .docx, Word, report, template, letter, and contract requests.
```

## 10. Configuration

Add or normalize these settings:

| Setting | Default | Purpose |
|---|---|---|
| `SANDBOX_DEFAULT_PROVIDER` | `subprocess` | Backward-compatible default. Production should set `opensandbox`. |
| `SANDBOX_ALLOWED_PROVIDERS` | `subprocess,opensandbox` | Deployment allowlist. |
| `SANDBOX_DEFAULT_IMAGE` | `opensandbox/code-interpreter:v1.0.2` | Provider/app default image. Replaces or aliases `OPENSANDBOX_CODE_INTERPRETER_IMAGE`. |
| `SANDBOX_SESSION_TTL_H` | `2` | Provider sandbox TTL. |
| `SANDBOX_RENEW_MINUTES` | `30` | Renewal duration on each turn. |
| `SANDBOX_CREATE_TIMEOUT_S` | `60` | Create/resume timeout. |
| `SANDBOX_DEFAULT_TIMEOUT_S` | `30` | Per-execution timeout. |
| `SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S` | `60` | Bootstrap timeout. |
| `SANDBOX_MAX_EXECUTIONS_PER_TURN` | `5` | Tool-loop safety budget. |
| `SANDBOX_MAX_OUTPUT_CHARS` | `20000` | Output truncation limit. |
| `SANDBOX_SUBPROCESS_ALLOW_ENV` | empty | Optional comma-separated env allowlist for dev. |

Image policy:

- The sandbox image is configured at provider/deployment/app level, not in the Skill definition.
- A conversation has exactly one sandbox image for its lifetime.
- If a Skill needs binaries that are absent from the configured image, it should express that as
  human-readable prerequisites in `SKILL.md`, and bootstrap should report a clear failure rather
  than switching images.

## 11. Security

### 11.1 Subprocess Provider

Subprocess remains unsafe for production even with env filtering. Required changes:

- Filter secrets from env.
- Warn prominently at provider creation.
- Document it as local-dev only.
- Consider requiring `SANDBOX_ALLOW_UNSAFE_SUBPROCESS=true` when `APP_ENV=production`.

### 11.2 Execution Budget

Add a per-turn counter to agent state:

```python
if state["sandbox_execution_count"] >= SANDBOX_MAX_EXECUTIONS_PER_TURN:
    return "final_response"
```

Every call to `python_repl` or language-specific REPL increments the counter. The tool should
return a clear error when the budget is exhausted.

### 11.3 Output Budget

All providers use `SANDBOX_MAX_OUTPUT_CHARS`. Truncation should append a marker:

```text
[Output truncated at 20000 characters]
```

### 11.4 Network Egress

Initial policy:

- Default to the OpenSandbox deployment policy.
- Preserve Skill-level `egress_policy` but do not claim enforcement until the provider applies it.
- For future enforcement, prefer deployment-level allowlists over LLM-controlled runtime changes.

### 11.5 Skill-Document Execution Requirements

Execution requirements are part of the reviewed Skill definition document:

- Only administrators or trusted built-in migrations can create or update Skill documents that
  describe execution requirements.
- The LLM cannot alter `SKILL.md`, supporting files, or bootstrap scripts during a turn.
- Mattin does not parse or register runtime dependencies separately. The model learns setup
  assumptions from the loaded Skill instructions; deterministic setup lives in reviewed bootstrap
  scripts.

## 12. File Synchronization

Keep the `/workspace` convention.

Required fixes:

- `OpenSandboxProvider.list_files` should return relative paths, not only basenames, so nested
  outputs can be synced and `.skills/**` can be skipped reliably.
- Finalizer must ignore:
  - `.skills/**`;
  - hidden files;
  - paths escaping `/workspace`;
  - files that existed before the turn.
- `read_file` and `write_file` must accept only workspace-relative paths or validated
  `/workspace/...` paths.

## 13. Migration Plan

### Phase 1 — Lifecycle Foundation

- Add `session_key` and `active_skills` to `SandboxHandle`.
- Extend provider `create_sandbox` with `existing_sandbox_id`.
- Implement OpenSandbox resume/renew when SDK supports it.
- Persist `sandbox_id` and `sandbox_state` on `Conversation`.
- Fix stable session-key usage across turn preparation, reset, and delete.

### Phase 2 — Skill Activation Correctness

- Add canonical Skill package validation/import/export.
- Preserve raw frontmatter and package-root-relative bundled resource paths.
- Migrate `files/<path>` ZIP imports as compatibility input but export only canonical packages.
- Implement OpenSandbox `ensure_skill`.
- Add file/bootstrap phase state and enriched `list_active_skills`.
- Replace `load_skill` closure-only idempotency with sandbox-state idempotency.
- Return visible runtime warnings to the LLM.

### Phase 3 — Recovery

- Detect expired sandboxes on renew/run.
- Recreate sandboxes when resume fails.
- Re-activate previously active, still-authorized Skills from DB records.
- Clear active state when a new `sandbox_id` is created.

### Phase 4 — Router

- Add metadata-only `skill_router`.
- Respect `disable-model-invocation`.
- Add router telemetry: selected Skill, reason, and whether runtime setup succeeded.
- Keep `load_skill` and `activate_sandbox_skill` as fallback tools.

### Phase 5 — Security Hardening

- Filter subprocess env.
- Add execution and output budgets.
- Add configuration docs and production warnings.

### Phase 6 — Streaming Cleanup

- Add stderr streaming.
- Normalize `code_output` payloads with `{stream, line}`.
- Preserve current frontend compatibility by treating missing `stream` as stdout.

## 14. Testing Strategy

### Unit Tests

Add focused tests for:

- `SandboxSessionService.get_or_create` resumes from `Conversation.sandbox_session_id`.
- Renew failure recreates the sandbox and clears stale active state.
- Reset/delete use the same stable `session_key` as turn preparation.
- `OpenSandboxProvider.ensure_skill` records independent phase failures.
- Skill activation does not parse or register runtime dependency metadata.
- Skill package import/export round-trips root `SKILL.md`, `scripts/*`, `references/*`,
  `assets/*`, unknown frontmatter, text files, and binary files.
- Skill package validation rejects unsafe paths and warns on deprecated draft runtime fields.
- `load_skill` reports partial runtime failure and does not cache a failed setup as healthy.
- `SubprocessProvider` filters secret env vars.
- `SANDBOX_MAX_OUTPUT_CHARS` is honored by both providers.
- Execution budget blocks the sixth execution by default.
- `skill_router` reads metadata only.

### Provider Contract Tests

Parametrize common behavior across providers:

- create/destroy;
- write/read/list files;
- output truncation;
- unsupported language behavior;
- Skill activation state shape;
- idempotent activation for the same sandbox id.

### OpenSandbox Mock Tests

Mock SDK calls; do not require a real OpenSandbox server:

- create with configured default image;
- resume success;
- resume failure -> create fresh;
- renew success/failure;
- stdout/stderr callbacks;
- expired sandbox maps to `SandboxExpiredError`.

### Integration Tests

Mark real OpenSandbox tests with `@pytest.mark.integration`:

- create sandbox;
- push input file;
- auto-select `word-generation`;
- ensure supporting files/bootstrap are available where supported;
- generate output file;
- pull output file;
- reset conversation destroys sandbox and clears state.

## 15. Open Questions

| Question | Proposed answer for v2 |
|---|---|
| Redis or DB for sandbox state? | DB only for this iteration. Redis is explicitly out of scope. |
| Async provider API? | Keep sync for v2 because current providers and tools are sync. Add async wrappers only if the SDK and LangGraph graph move together. |
| Per-Skill Docker images? | No. Sandbox image is provider/deployment/app configuration, not Skill definition. |
| Are dependencies a Skill type or registry? | No. Skills are unified. Execution requirements live in the Skill document and reviewed bootstrap files; Mattin does not keep a separate runtime dependency registry. |
| Egress policy? | Preserve metadata now; enforce only when provider support is implemented and tested. |
| Should `allowed-tools` restrict Mattin tools? | Preserve for portability; enforce through Mattin's own tool permission model, not raw frontmatter. |
| Should Mattin export `files/<path>` archives? | No. Continue accepting them as migration input, but export canonical Agent Skills packages with root-relative bundled files. |
| Auto-activate multiple Skills? | Allow up to two by default; require router confidence/justification and attached Skill authorization. |

## 16. Implementation Checklist

| Priority | Change | Files |
|---|---|---|
| P0 | Fix session key mismatch for destroy/reset | `agent_execution_service.py`, `sandbox_session_service.py` |
| P0 | Filter subprocess env and configurable output limit | `subprocess_provider.py`, `config.py` |
| P1 | Provider resume/renew contract | `provider.py`, `opensandbox_provider.py` |
| P1 | Persist sandbox state | `models/conversation.py`, Alembic migration, `conversation_service.py`, `sandbox_session_service.py` |
| P1 | OpenSandbox `ensure_skill` with phases | `opensandbox_provider.py`, tests |
| P1 | `load_skill` runtime-status reporting | `skill_tools.py`, tests |
| P1 | Canonical Skill package repository/import/export | `skill_service.py`, `skill_repository.py`, `skill_schemas.py`, `routers/internal/skills.py`, tests |
| P2 | Expiry recovery and Skill restoration | `sandbox_session_service.py`, repository/service integration |
| P2 | Metadata-only `skill_router` | agent graph/middleware, tests |
| P2 | Per-turn execution budget | agent state/tool factory |
| P3 | Skill document execution requirements | `skill_service.py`, schemas, `opensandbox_provider.py`, tests |
| P3 | Stderr streaming normalization | provider/tool factory/frontend compatibility |

## 17. References

- Anthropic/Claude Skills overview: https://claude.com/docs/skills/overview
- Claude Code Skills guide: https://code.claude.com/docs/en/skills
- Claude Agent Skills API docs: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Claude Code SDK Skills docs: https://code.claude.com/docs/en/agent-sdk/skills
- Previous Mattin RFC: [RFC: Sandbox Provider Integration](rfc-sandbox-providers.md)
