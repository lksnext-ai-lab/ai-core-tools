# RFC: Sandbox Provider Integration

> Part of [Mattin AI Documentation](../index.md)
> **Status**: Draft — May 1, 2026 · Architecture Analysis added May 6, 2026
> **Branch**: `exp/sandbox`

## Overview

This RFC proposes replacing the current unprotected subprocess-based code interpreter with a
**provider-abstracted sandbox layer**. A `SandboxProvider` protocol defines a common interface;
multiple backend implementations plug in — subprocess (backward-compatible default), OpenSandbox
(primary self-hosted target), E2B (cloud-managed alternative), and future adapters such as Modal,
Daytona, CodeSandbox SDK, or Microsandbox. Sandboxes are scoped to a conversation, persist state
across turns, and support **Skills** — Mattin skills stored as portable packages centered on a
`SKILL.md` file with YAML frontmatter, Markdown instructions, and optional supporting resources
such as scripts, references, templates, and assets. Agents attach skills from one place; some
skills only provide instructions, some include executable resources and dependency metadata that
bootstrap sandbox capabilities, and some do both to unlock advanced operations such as document
generation, data visualisation, spreadsheet processing, presentation building, and report
assembly.

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Design Goals](#2-design-goals)
3. [Non-Goals](#3-non-goals)
4. [Current State](#4-current-state)
5. [Proposed Architecture](#5-proposed-architecture)
   - 5.1 [Provider Abstraction](#51-provider-abstraction)
   - 5.2 [Provider Implementations](#52-provider-implementations)
   - 5.3 [SandboxSessionService](#53-sandboxsessionservice)
   - 5.4 [Skills](#54-skills)
   - 5.5 [Integration with AgentTools](#55-integration-with-agenttools)
   - 5.6 [File Synchronisation](#56-file-synchronisation)
   - 5.7 [Fit for Mattin Content Generation](#57-fit-for-mattin-content-generation)
6. [Data Model Changes](#6-data-model-changes)
7. [Configuration](#7-configuration)
8. [Provider Comparison](#8-provider-comparison)
9. [Self-Hosted Deployment](#9-self-hosted-deployment)
10. [Security Considerations](#10-security-considerations)
11. [Migration Path](#11-migration-path)
12. [Open Questions](#12-open-questions)
13. [Architecture Analysis](#13-architecture-analysis)
    - 13.1 [Impact Map](#131-impact-map)
    - 13.2 [Integration Flow](#132-integration-flow)
    - 13.3 [New Artefacts Layout](#133-new-artefacts-layout)
    - 13.4 [Implementation Plan](#134-implementation-plan)
    - 13.5 [Iteration Dependencies](#135-iteration-dependencies)
    - 13.6 [Open Questions — Prioritised](#136-open-questions--prioritised)
    - 13.7 [Security Contracts per Iteration](#137-security-contracts-per-iteration)
14. [References](#14-references)

---

## 1. Motivation

### Current security exposure

When `enable_code_interpreter = true` on an Agent, LangGraph calls `python_repl` — a LangChain
tool backed by `python_sandbox_tools.py`. That implementation spawns a subprocess with:

```python
result = subprocess.run(
    [sys.executable, script_path],
    capture_output=True,
    cwd=working_dir,
    env=os.environ.copy(),   # ← all secrets exposed
)
```

Any code the LLM generates runs **on the backend host** with:

- Full access to `SQLALCHEMY_DATABASE_URI`, `OPENAI_API_KEY`, `SECRET_KEY`, and every other
  environment variable.
- The ability to read and write any file the backend process can access.
- No CPU, memory, or network egress controls.

This is acceptable only in fully trusted, single-tenant development environments. It must not
reach production multi-tenant deployments.

### Capability gap

The current interpreter only provides a bare Python environment plus the packages installed in
the backend virtual environment. There is no mechanism to pre-load domain-specific libraries
(e.g., `python-docx`, `reportlab`, `matplotlib`) per-agent without polluting the global
backend environment.

---

## 2. Design Goals

| # | Goal |
|---|------|
| G1 | Eliminate host exposure — agent code must not reach backend secrets or filesystem |
| G2 | Preserve backward compatibility — existing agents with `enable_code_interpreter = true` must work unchanged using the subprocess provider |
| G3 | Single abstraction seam — swapping providers requires no changes outside `SandboxProvider` implementations and one routing call in `agentTools.py` |
| G4 | Conversation-scoped state persistence — a sandbox survives across turns of the same conversation so that variables, files, and installed packages remain available |
| G5 | Skills — agents declare skills from the existing skill library; skills with dependency metadata and executable resources bootstrap the sandbox before the first turn |
| G6 | File round-trip — files written inside the sandbox surface in the existing `working_dir` files panel |
| G7 | Support OpenSandbox as primary self-hosted provider and E2B as managed-cloud alternative |
| G8 | Make the boundary between Mattin-managed sandbox generation and provider-native hosted tools explicit |

---

## 3. Non-Goals

- Creating a parallel skill catalogue — the existing `Skill` system evolves from prompt-only
  instructions into a single catalogue that can also describe sandbox runtime requirements.
- Providing a general-purpose remote development environment — sandboxes are ephemeral and
  conversation-scoped.
- Supporting languages other than Python in the initial release (multi-language is possible via
  OpenSandbox's `SupportedLanguage` enum but deferred).
- Frontend execution — sandboxes run server-side.
- Replacing provider-native hosted tools such as OpenAI `image_generation`, OpenAI hosted
  `code_interpreter`, Anthropic code execution, or Gemini code execution. Those remain
  `server_tools`; this RFC governs Mattin-managed execution environments and file round-trip.

---

## 4. Current State

### Relevant files

| File | Role |
|------|------|
| `backend/tools/python_sandbox_tools.py` | Subprocess-based `python_repl` tool factory |
| `backend/tools/agentTools.py` | Calls `create_python_repl_tool` when `agent.enable_code_interpreter` is true |
| `backend/models/agent.py` | `enable_code_interpreter: bool` and `server_tools: JSON` columns |
| `backend/services/agent_execution_service.py` | Allocates `working_dir` per conversation; syncs output files |
| `backend/models/skill.py` | Existing app-scoped skill catalogue (`Skill.content` markdown instructions) |
| `backend/tools/skill_tools.py` | Adds the `load_skill` tool and available-skills system prompt section |

### Current skill system

Mattin already has a single skill management surface:

- `Skill` stores reusable markdown instructions with `name`, `description`, `content`, and
  `app_id`.
- `agent_skills` attaches skills to agents and supports a per-agent `description`.
- `agentTools.py` advertises attached skills in the system prompt and adds a `load_skill` tool
  so the model can load detailed instructions on demand.

The current implementation is prompt-only, but the catalogue, permissions, tier limits,
repository/service/API layers, and frontend management flow already exist. Creating a separate
`SandboxPackage` catalogue would duplicate that management surface and force users to decide
whether a reusable capability is a "skill" or a "code skill". This RFC therefore evolves
`Skill` to store portable skill packages.

The package format should match Claude's Agent Skills definition for portability, but the
application should continue to refer to these capabilities simply as **Skills**:

- A skill is a directory whose name matches the skill `name`.
- The directory contains a required `SKILL.md`.
- `SKILL.md` starts with YAML frontmatter containing required `name` and `description` fields.
- The Markdown body contains the instructions loaded when the skill is triggered.
- Optional supporting files live beside `SKILL.md`, commonly under `scripts/`, `references/`,
  `templates/`, or `assets/`.
- The `description` is activation metadata: it must describe what the skill does and when the
  model should use it.

Mattin should therefore treat skills as portable packages that can be imported from, exported to,
and eventually executed as `SKILL.md`-based skill directories.

### Provider-side tools already exist

Mattin also has a separate `agent.server_tools` path for model-provider hosted tools:

| Provider | Current mapped tools |
|----------|----------------------|
| OpenAI / Azure | `web_search`, `image_generation`, `code_interpreter`, `file_search` |
| Anthropic | `web_search`, `code_interpreter` |
| Google | `web_search`, `code_interpreter` |
| MistralAI / Custom | none |

This path is complementary to `enable_code_interpreter`. Hosted tools execute inside the model
provider's infrastructure and return provider-specific content blocks. Mattin already decodes
OpenAI `image_generation_call` blocks and Gemini `image_url` data URIs into `working_dir`, so
those generated images are registered by `FileManagementService.sync_output_files()`.

### How `create_agent()` wires the tool today

```python
# backend/tools/agentTools.py  (simplified, line ~246)
if agent.enable_code_interpreter and working_dir:
    os.makedirs(working_dir, exist_ok=True)
    python_tool = create_python_repl_tool(working_dir=working_dir)
    tools.append(python_tool)
```

### What `create_python_repl_tool` does

1. Writes the LLM-generated code to a temp `.py` file inside `working_dir`.
2. Calls `subprocess.run([sys.executable, script_path], cwd=working_dir, env=os.environ.copy())`.
3. Returns truncated stdout/stderr.
4. Deletes the temp file.

No sandbox isolation, no resource limits, no secret stripping.

---

## 5. Proposed Architecture

### 5.1 Provider Abstraction

A `SandboxProvider` abstract base class (or `typing.Protocol`) defines the interface every
implementation must satisfy. The goal is that `agentTools.py` only ever talks to this interface.

```
backend/tools/sandbox/
    __init__.py
    provider.py          ← SandboxProvider ABC + SandboxHandle dataclass
    subprocess_provider.py   ← current behaviour (default/backward-compat)
    opensandbox_provider.py  ← OpenSandbox (Alibaba)
    e2b_provider.py          ← E2B (e2b.dev)
    modal_provider.py        ← optional future adapter
    daytona_provider.py      ← optional future adapter
    factory.py           ← resolve_provider(agent) → SandboxProvider
```

#### `SandboxHandle`

A lightweight opaque object returned by `create_sandbox()` and passed back to all subsequent
calls within the same conversation.

```python
# backend/tools/sandbox/provider.py

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SandboxHandle:
    """Opaque reference to an active sandbox session."""
    provider: str           # "subprocess" | "opensandbox" | "e2b" | ...
    session_key: str        # unique key: f"{agent_id}_{conversation_id}"
    raw: Any = None         # provider-specific object (Sandbox, None, …)
    interpreter: Any = None # provider-specific interpreter object (CodeInterpreter, …)
    runtime_ready: bool = False
```

#### `SandboxProvider` ABC

```python
# backend/tools/sandbox/provider.py  (continued)

import abc
from typing import List, Optional


class SandboxProvider(abc.ABC):

    @abc.abstractmethod
    async def create_sandbox(
        self,
        session_key: str,
        runtime_skills: List["Skill"] | None = None,
    ) -> SandboxHandle:
        """Create (or reconnect to) an isolated execution environment.

        If ``runtime_skills`` are provided, each skill's sandbox requirements
        are installed and its setup script is executed before the handle is returned.
        """

    @abc.abstractmethod
    async def run_code(
        self,
        handle: SandboxHandle,
        code: str,
        timeout: int = 30,
    ) -> str:
        """Execute ``code`` inside the sandbox and return stdout/stderr."""

    @abc.abstractmethod
    async def write_file(
        self,
        handle: SandboxHandle,
        remote_path: str,
        data: bytes | str,
    ) -> None:
        """Write a file into the sandbox filesystem."""

    @abc.abstractmethod
    async def read_file(
        self,
        handle: SandboxHandle,
        remote_path: str,
    ) -> bytes:
        """Read a file from the sandbox filesystem."""

    @abc.abstractmethod
    async def list_files(
        self,
        handle: SandboxHandle,
        remote_dir: str = "/workspace",
    ) -> List[str]:
        """List files in ``remote_dir`` (non-recursive)."""

    @abc.abstractmethod
    async def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Terminate the sandbox and release all resources."""
```

#### `SandboxFactory`

```python
# backend/tools/sandbox/factory.py

from models.agent import Agent
from tools.sandbox.provider import SandboxProvider


def resolve_provider(agent: Agent) -> SandboxProvider:
    """Return the correct SandboxProvider for the given agent.

    Selection priority:
      1. agent.sandbox_provider  (explicit per-agent config)
      2. SANDBOX_DEFAULT_PROVIDER env var (app-level default)
      3. "subprocess"  (backward-compatible fallback)
    """
    from utils.config import get_app_config
    from tools.sandbox.subprocess_provider import SubprocessProvider
    from tools.sandbox.opensandbox_provider import OpenSandboxProvider
    from tools.sandbox.e2b_provider import E2BProvider

    provider_name = (
        getattr(agent, "sandbox_provider", None)
        or get_app_config().get("SANDBOX_DEFAULT_PROVIDER", "subprocess")
    )

    match provider_name:
        case "opensandbox":
            return OpenSandboxProvider()
        case "e2b":
            return E2BProvider()
        case _:
            return SubprocessProvider()
```

---

### 5.2 Provider Implementations

#### SubprocessProvider (backward-compatible default)

Wraps the current `python_sandbox_tools.py` logic so existing behaviour is fully preserved.
`create_sandbox` is a no-op; `run_code` spawns the subprocess exactly as today.

```python
# backend/tools/sandbox/subprocess_provider.py

import os, subprocess, sys, tempfile
from tools.sandbox.provider import SandboxProvider, SandboxHandle


class SubprocessProvider(SandboxProvider):
    """Backward-compatible provider — runs code in a subprocess on the backend host.

    WARNING: No isolation. Do not use in multi-tenant or production environments.
    """

    async def create_sandbox(self, session_key, runtime_skills=None):
        return SandboxHandle(provider="subprocess", session_key=session_key)

    async def run_code(self, handle, code, timeout=30):
        working_dir = _working_dir_from_key(handle.session_key)
        os.makedirs(working_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", dir=working_dir, delete=False
        ) as f:
            f.write(code)
            path = f.name
        try:
            r = subprocess.run(
                [sys.executable, path],
                capture_output=True, text=True,
                timeout=timeout, cwd=working_dir,
                env=os.environ.copy(),
            )
            return (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else ""))[:20_000]
        except subprocess.TimeoutExpired:
            return f"[Error] Timed out after {timeout}s"
        finally:
            os.unlink(path)

    async def write_file(self, handle, remote_path, data):
        path = os.path.join(_working_dir_from_key(handle.session_key), remote_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(path, mode) as f:
            f.write(data)

    async def read_file(self, handle, remote_path):
        path = os.path.join(_working_dir_from_key(handle.session_key), remote_path)
        with open(path, "rb") as f:
            return f.read()

    async def list_files(self, handle, remote_dir="/workspace"):
        d = _working_dir_from_key(handle.session_key)
        return os.listdir(d) if os.path.isdir(d) else []

    async def destroy_sandbox(self, handle):
        pass  # subprocess leaves nothing to clean up
```

#### OpenSandboxProvider (primary)

Uses the `opensandbox` Python SDK (Alibaba, Apache-2.0). Each sandbox runs the
`opensandbox/code-interpreter:v1.0.2` Docker image. State (variables, installed packages)
persists across `run_code` calls via a `CodeInterpreter` context.

```python
# backend/tools/sandbox/opensandbox_provider.py  (sketch)

import json
from datetime import timedelta
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig
from code_interpreter import CodeInterpreter, SupportedLanguage
from tools.sandbox.provider import SandboxProvider, SandboxHandle


class OpenSandboxProvider(SandboxProvider):

    def _config(self):
        from utils.config import get_app_config
        cfg = get_app_config()
        return ConnectionConfig(
            domain=cfg["OPENSANDBOX_DOMAIN"],   # e.g. "localhost:8080" for self-hosted
            api_key=cfg["OPENSANDBOX_API_KEY"],
        )

    async def create_sandbox(self, session_key, runtime_skills=None):
        sandbox = await Sandbox.create(
            "opensandbox/code-interpreter:v1.0.2",
            connection_config=self._config(),
            entrypoint=["/opt/opensandbox/code-interpreter.sh"],
            env={"PYTHON_VERSION": "3.11"},
            timeout=timedelta(hours=2),
        )
        interpreter = await CodeInterpreter.create(sandbox)
        handle = SandboxHandle(
            provider="opensandbox",
            session_key=session_key,
            raw=sandbox,
            interpreter=interpreter,
        )
        if runtime_skills:
            await self._bootstrap_runtime_skills(handle, runtime_skills)
        return handle

    async def run_code(self, handle, code, timeout=30):
        result = await handle.interpreter.codes.run(
            code, language=SupportedLanguage.PYTHON
        )
        stdout = "\n".join(l.text for l in (result.logs.stdout or []))
        text   = result.result[0].text if result.result else stdout
        return text[:20_000]

    async def _bootstrap_runtime_skills(self, handle, runtime_skills):
        reqs = []
        for skill in runtime_skills:
            reqs.extend(_python_requirements_from_dependencies(skill.dependencies or []))
        if reqs:
            reqs_json = json.dumps(reqs)
            await self.run_code(
                handle,
                "import json, subprocess\n"
                f"reqs = json.loads({reqs_json!r})\n"
                "subprocess.run(['pip', 'install', '-q', *reqs], check=True)",
                timeout=120,
            )
        for skill in runtime_skills:
            if skill.bootstrap_script_path:
                script = _read_skill_file_text(skill, skill.bootstrap_script_path)
                await self.run_code(handle, script, timeout=60)
        handle.runtime_ready = True

    async def write_file(self, handle, remote_path, data):
        from opensandbox.models import WriteEntry
        await handle.raw.files.write_files(
            [WriteEntry(path=remote_path, data=data, mode=644)]
        )

    async def read_file(self, handle, remote_path):
        return await handle.raw.files.read_file(remote_path)

    async def list_files(self, handle, remote_dir="/workspace"):
        entries = await handle.raw.files.list(remote_dir)
        return [e.path for e in entries]

    async def destroy_sandbox(self, handle):
        await handle.raw.kill()
```

#### E2BProvider (cloud-managed alternative)

Uses the `e2b-code-interpreter` SDK. Suited for SaaS deployments where self-hosting
infrastructure is undesirable.

```python
# backend/tools/sandbox/e2b_provider.py  (sketch)

import json
from e2b_code_interpreter import Sandbox
from tools.sandbox.provider import SandboxProvider, SandboxHandle


class E2BProvider(SandboxProvider):

    async def create_sandbox(self, session_key, runtime_skills=None):
        sandbox = await Sandbox.create()
        handle = SandboxHandle(
            provider="e2b",
            session_key=session_key,
            raw=sandbox,
        )
        if runtime_skills:
            await self._bootstrap_runtime_skills(handle, runtime_skills)
        return handle

    async def run_code(self, handle, code, timeout=30):
        execution = await handle.raw.run_code(code)
        return (execution.text or "")[:20_000]

    async def _bootstrap_runtime_skills(self, handle, runtime_skills):
        reqs = []
        for skill in runtime_skills:
            reqs.extend(_python_requirements_from_dependencies(skill.dependencies or []))
        if reqs:
            reqs_json = json.dumps(reqs)
            await self.run_code(
                handle,
                "import json, subprocess\n"
                f"reqs = json.loads({reqs_json!r})\n"
                "subprocess.run(['pip', 'install', '-q', *reqs], check=True)",
                timeout=120,
            )
        for skill in runtime_skills:
            if skill.bootstrap_script_path:
                script = _read_skill_file_text(skill, skill.bootstrap_script_path)
                await self.run_code(handle, script, timeout=60)
        handle.runtime_ready = True

    async def write_file(self, handle, remote_path, data):
        await handle.raw.files.write(remote_path, data)

    async def read_file(self, handle, remote_path):
        return await handle.raw.files.read(remote_path)

    async def list_files(self, handle, remote_dir="/workspace"):
        entries = await handle.raw.files.list(remote_dir)
        return [e.path for e in entries]

    async def destroy_sandbox(self, handle):
        await handle.raw.kill()
```

#### Additional provider candidates researched on May 1, 2026

These providers fit the same `SandboxProvider` protocol but are not recommended for Phase 1
implementation unless product requirements change.

| Provider | Why consider it | Fit / caveats |
|----------|-----------------|---------------|
| Modal Sandboxes | Managed secure containers for untrusted user or agent code; supports arbitrary commands, custom images, volumes, filesystem APIs, timeouts up to 24h, and `Sandbox.from_id` reconnects | Strong fit for cloud deployments that already use Modal; not self-hosted and the file API has recently changed, so it is a Phase 5+ adapter candidate |
| Daytona Sandboxes | Managed isolated "full computer" environments with SDKs for Python/TypeScript/Ruby/Go/Java, Python/TypeScript/JavaScript direct execution, snapshots, resources, regions, and per-sandbox firewall settings | Good managed alternative for longer-running coding-agent workflows; broader dev-environment surface than Mattin needs for initial content generation |
| CodeSandbox SDK | Together/CodeSandbox microVM sandboxes with Python/JS/shell execution, filesystem API, fork/clone, hibernation, snapshots, Docker-based templates, and regional infrastructure | Interesting for agent development environments and A/B cloning; JavaScript-first SDK and commercial hosted dependency make it a later candidate |
| Microsandbox | Self-hosted VM-level isolation with Python/Node SDKs, MCP integration, OCI images, filesystem operations, persistent state, package installation, and very fast startup claims | Promising self-hosted alternative if OpenSandbox proves too heavy; currently a younger ecosystem, so validate operational maturity before selecting |

Not selected for this RFC:

- **Provider-native hosted code tools** (OpenAI, Anthropic, Gemini): useful `server_tools`,
  but the execution environment, package set, file persistence, and network policy are owned by
  the LLM provider rather than Mattin.
- **Raw Kubernetes Jobs / Docker containers**: viable primitives, but using them directly would
  push lifecycle, egress, file APIs, and isolation policy into Mattin instead of behind a
  maintained sandbox provider.

---

### 5.3 SandboxSessionService

Manages the mapping from conversation session keys to `SandboxHandle` objects, ensuring one
sandbox per conversation and proper cleanup on reset or expiry.

```
backend/services/sandbox_session_service.py
```

```python
# Sketch

import asyncio
from typing import Dict, List, Optional
from tools.sandbox.provider import SandboxHandle, SandboxProvider


class SandboxSessionService:
    """Singleton service that manages sandbox lifecycle per conversation."""

    _handles: Dict[str, SandboxHandle] = {}
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    def session_key(cls, agent_id: int, conversation_id: int | str) -> str:
        return f"sandbox_{agent_id}_{conversation_id}"

    @classmethod
    async def get_or_create(
        cls,
        key: str,
        provider: SandboxProvider,
        runtime_skills: Optional[List] = None,
    ) -> SandboxHandle:
        async with cls._lock:
            if key not in cls._handles:
                cls._handles[key] = await provider.create_sandbox(
                    key, runtime_skills=runtime_skills
                )
            return cls._handles[key]

    @classmethod
    async def destroy(cls, key: str) -> None:
        async with cls._lock:
            handle = cls._handles.pop(key, None)
            if handle:
                provider = _provider_from_handle(handle)
                await provider.destroy_sandbox(handle)

    @classmethod
    async def destroy_all_for_agent(cls, agent_id: int) -> None:
        prefix = f"sandbox_{agent_id}_"
        keys = [k for k in list(cls._handles) if k.startswith(prefix)]
        for key in keys:
            await cls.destroy(key)
```

**Lifecycle hooks:**

| Event | Action |
|-------|--------|
| First turn of a conversation | `get_or_create()` — sandbox created lazily |
| Subsequent turns | `get_or_create()` returns existing handle |
| `reset_agent_conversation()` | `destroy(key)` — sandbox killed |
| Agent deleted | `destroy_all_for_agent(agent_id)` |
| App startup | No auto-resume (sandboxes are ephemeral) |

---

### 5.4 Skills

Mattin should not introduce a second "code skill" or `SandboxPackage` catalogue. The existing
`Skill` entity is already the place where users create reusable agent capabilities and attach
them to agents through `agent_skills`. This RFC evolves `Skill` from **prompt-only instructions**
into a single capability package. The internal package shape follows Claude's Agent Skills
definition for portability, but the application UI and API should continue to call them
**Skills**.

This gives Mattin three skill shapes without fragmenting the UI or API:

| Skill shape | `SKILL.md` body | Supporting files / metadata | Example |
|-------------|-----------------|-----------------------------|---------|
| Instruction skill | Required | Optional references | Brand voice, legal review checklist, support triage process |
| Runtime skill | Short usage guidance | `dependencies` metadata plus `scripts/` and templates | `word-generation`, `charts`, `data-analysis` |
| Hybrid skill | Required | Dependencies, scripts, references, templates, assets | "Board report writer" instructions plus document, spreadsheet, and charting helpers |

The current `load_skill` tool remains responsible for prompt instructions. The sandbox bootstrap
path reads the same attached skills and extracts dependency metadata and executable resources, so
agents still attach skills from one library.

#### Skill package shape

Each Mattin skill should be importable/exportable as this filesystem layout:

```text
word-generation/
  SKILL.md
  scripts/
    create_docx.py
  templates/
    report-template.docx
  references/
    formatting.md
  assets/
    logo.png
```

`SKILL.md` is the source of truth for model-facing metadata and instructions:

```markdown
---
name: word-generation
description: Create and edit Word documents. Use when the user asks for DOCX reports, letters, proposals, or formatted editable documents.
dependencies:
  - python>=3.11
  - python-docx>=1.1
---

# Word Generation

## Instructions
Use `python-docx` for editable `.docx` files. Save final documents in `/workspace`.

## Resources
- Use `templates/report-template.docx` when the user asks for a report.
- Use scripts in `scripts/` for deterministic document operations.
```

Compatibility rules:

- `name` is the canonical skill id: lowercase letters, numbers, and hyphens only, maximum
  64 characters, no XML tags, no reserved `anthropic` or `claude` names, and it must match the
  package directory name.
- `description` is required and should explain both what the skill does and when to use it.
  It must not contain XML tags. Mattin should store up to 1024 characters, while export flows
  may warn when targeting surfaces with shorter limits.
- `dependencies` is optional metadata. Mattin uses Python package entries to bootstrap its
  sandbox; non-Python entries are preserved for export and future runtimes.
- `allowed-tools` may be preserved for Claude Code compatibility, but Mattin should enforce tool
  policy through its own agent/tool permissions.
- Supporting files are loaded progressively: `SKILL.md` metadata is always visible, the body is
  loaded when the skill is relevant, and referenced resources/scripts/templates are read or run
  only as needed.

#### Skill model evolution

```python
# backend/models/skill.py  (additions)

class Skill(Base):
    __tablename__ = 'Skill'

    skill_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)
    name = Column(String(64), nullable=False)
    # Portable canonical name, e.g. "word-generation".
    display_name = Column(String(100), nullable=True)
    description = Column(String(1024), nullable=False)

    # Markdown body of SKILL.md after YAML frontmatter.
    content = Column(Text, nullable=False)

    # Parsed YAML frontmatter beyond name/description. Preserve unknown fields
    # so import/export remains compatible as Claude's format evolves.
    frontmatter = Column(JSON, nullable=False, default=dict)
    dependencies = Column(JSON, nullable=False, default=list)
    allowed_tools = Column(JSON, nullable=False, default=list)

    # Mattin execution metadata derived from the package, not exposed as a
    # separate skill type.
    runtime = Column(String(30), nullable=True)
    # Initial value: 'python-sandbox' when dependencies/scripts require it.
    bootstrap_script_path = Column(String(255), nullable=True)
    runtime_options = Column(JSON, nullable=False, default=dict)

    is_builtin = Column(Boolean, default=False, nullable=False)
```

Supporting files are stored separately so the database can round-trip a portable skill package:

```python
class SkillFile(Base):
    __tablename__ = 'SkillFile'

    file_id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey('Skill.skill_id'), nullable=False)
    path = Column(String(512), nullable=False)
    media_type = Column(String(100), nullable=True)
    content_text = Column(Text, nullable=True)
    content_bytes = Column(LargeBinary, nullable=True)
    checksum_sha256 = Column(String(64), nullable=False)
```

Design notes:

- `app_id = NULL` represents platform-built-in skills available to every app; app-scoped skills
  continue to use the existing `app_id`.
- `content` is still the agent-facing usage guide and is loaded through the existing `load_skill`
  tool.
- `dependencies`, `bootstrap_script_path`, selected `SkillFile` entries, and `runtime_options`
  are consumed by the sandbox service.
- Mattin should generate `SKILL.md` from `name`, `description`, `frontmatter`, and `content` on
  export, and parse those same fields on import.
- No new agent association table is needed. `agent_skills` remains the single attachment model,
  including the existing per-agent association `description`.

#### Built-in Skills

The platform ships a catalogue of curated built-in `Skill` records with `app_id = NULL` and
`is_builtin = true`. They appear in the same skill picker as app skills, with badges that show
whether they add instructions, runtime dependencies, or both.

| Name | `dependencies` entries | Purpose |
|------|------------------------|---------|
| `word-generation` | `python-docx>=1.1` | `.docx` creation and editing |
| `pdf-generation` | `reportlab>=4.1`, `weasyprint>=62` | PDF rendering from HTML/templates |
| `presentation-generation` | `python-pptx>=0.6.23` | `.pptx` creation and editing |
| `data-analysis` | `pandas>=2.2`, `openpyxl>=3.1`, `numpy>=2.0` | Spreadsheet and tabular data |
| `charts` | `matplotlib>=3.9`, `seaborn>=0.13` | Visualisation, PNG/SVG output |
| `image-processing` | `pillow>=10.4`, `opencv-python-headless>=4.10` | Image resizing, annotation, compositing, and format conversion |
| `web-scraping` | `httpx>=0.27`, `beautifulsoup4>=4.12`, `lxml>=5.2` | HTTP + HTML parsing |
| `email-html` | `jinja2>=3.1`, `premailer>=3.10` | HTML email template rendering |
| `markdown-publishing` | `markdown>=3.6`, `pyyaml>=6.0`, `python-frontmatter>=1.1` | Markdown/HTML publishing workflows |

#### Bootstrap flow

```
Agent turn 1
  └─ attached_skills = agent.skill_associations[*].skill
  └─ runtime_skills = [skill for skill in attached_skills if skill.runtime == "python-sandbox"]
  └─ SandboxSessionService.get_or_create(key, provider, runtime_skills=runtime_skills)
       └─ provider.create_sandbox(key, runtime_skills)
            └─ for each runtime skill:
                 write referenced SkillFile resources into /workspace/.skills/<skill.name>/
                 pip install Python entries from <skill.dependencies>
                 exec <skill.bootstrap_script_path> when present
            └─ handle.runtime_ready = True
  └─ tool registered: python_repl(handle, provider)
  └─ load_skill remains available for the same attached skills

Agent turn 2+
  └─ SandboxSessionService.get_or_create(key, ...) → cached handle
  └─ runtime dependencies already installed — state persists
```

#### Example: Word document generation agent

A content-writing agent configured with:
- `sandbox_provider = "opensandbox"`
- `skill_associations = [word-generation]`

The attached skill exposes concise usage guidance through `load_skill` and installs `python-docx`
in the sandbox before the first turn runs. The agent can then:

```python
# Code generated by LLM, executed in sandbox
from docx import Document

doc = Document()
doc.add_heading("Quarterly Report", 0)
doc.add_paragraph("This document was generated by Mattin AI.")
doc.save("quarterly_report.docx")
print("quarterly_report.docx")
```

The file `quarterly_report.docx` is synced to `working_dir` and surfaced in the files panel.

---

### 5.5 Integration with AgentTools

The single integration point is the `create_agent()` function in `agentTools.py`. The current
conditional block:

```python
# BEFORE
if agent.enable_code_interpreter and working_dir:
    os.makedirs(working_dir, exist_ok=True)
    python_tool = create_python_repl_tool(working_dir=working_dir)
    tools.append(python_tool)
```

becomes:

```python
# AFTER
if agent.enable_code_interpreter:
    sandbox_handle = await _get_or_create_sandbox_handle(agent, session_id)
    if sandbox_handle:
        tools.append(create_sandbox_repl_tool(sandbox_handle, provider))
```

where `create_sandbox_repl_tool` returns a LangChain `@tool` that delegates `run_code` calls
to the provider through the handle. The tool signature and docstring remain identical to the
current `python_repl` tool so existing agents require no system-prompt changes.

`_get_or_create_sandbox_handle()` uses `agent.skill_associations` to collect attached skills with
`runtime = "python-sandbox"` and passes them to
`SandboxSessionService.get_or_create(..., runtime_skills=...)`. The existing skill prompt section
and `load_skill` tool continue to use the same associations.

```python
# backend/tools/sandbox/tool_factory.py

from langchain_core.tools import tool
from tools.sandbox.provider import SandboxHandle, SandboxProvider


def create_sandbox_repl_tool(handle: SandboxHandle, provider: SandboxProvider):

    @tool
    async def python_repl(code: str) -> str:
        """Execute Python code and return stdout + stderr.

        Use this tool to read, analyse, transform, and create files.
        Files saved to /workspace are automatically available for download.

        State persists across calls within the same conversation — variables,
        imports, and installed packages remain available.

        Example:
            import pandas as pd
            df = pd.read_csv('data.csv')
            print(df.describe())
        """
        return await provider.run_code(handle, code)

    return python_repl
```

---

### 5.6 File Synchronisation

The existing `FileManagementService.sync_output_files()` is called by `_finalize_turn()` after
each agent response. It reads files from `working_dir` and makes them available in the files
panel.

For real sandboxes the flow adds a pull step:

```
_finalize_turn()
  └─ if ctx.sandbox_handle is not None:
       remote_files = provider.list_files(handle, "/workspace")
       for path in remote_files:
           if path not in pre_existing_remote_files:
               data = provider.read_file(handle, path)
               write to working_dir/basename(path)
  └─ existing sync_output_files() runs as normal
```

Uploads (files sent by the user in a conversation turn) are pushed into the sandbox at the
start of `_prepare_turn()`:

```
_prepare_turn()
  └─ after sandbox handle is obtained:
       for ref in file_references:
           provider.write_file(handle, f"/workspace/{ref.filename}", ref.bytes)
```

### 5.7 Fit for Mattin Content Generation

The proposal covers the "extend Mattin with new content generation capabilities" direction
when the generated artifact can be produced by Python libraries or shell tools inside a
Mattin-managed workspace.

| Capability | Covered by this RFC? | Notes |
|------------|----------------------|-------|
| Word documents | Yes | `word-generation` installs `python-docx`; files are written to `/workspace` and synced to the files panel |
| PDFs and printable reports | Yes | `pdf-generation` supports `reportlab` and HTML-to-PDF workflows; generated files round-trip through `working_dir` |
| Spreadsheets and CSV exports | Yes | `data-analysis` covers `pandas`, `openpyxl`, and `numpy` |
| Charts and data visualisations | Yes | `charts` emits PNG/SVG assets; `sync_output_files()` registers the generated files |
| Presentations | Yes, add package | `presentation-generation` should be included in the built-in catalogue before exposing this as a first-class capability |
| HTML/email/content publishing | Yes | `email-html` and `markdown-publishing` cover templated HTML/Markdown outputs |
| Image editing/compositing | Partial | `image-processing` can resize, annotate, crop, compose, and convert images; it does not generate novel images by itself |
| Generative images | Covered by existing provider/model output paths, not this RFC | Use `agent.server_tools=["image_generation"]` for OpenAI/Azure, or Gemini image-capable model output where configured; Mattin already saves returned base64/data-URI images into `working_dir` |
| Provider-hosted code execution | Complementary | OpenAI/Anthropic/Gemini code tools can remain available through `server_tools`, but they do not satisfy Mattin-managed package, egress, or lifecycle requirements |
| Audio/video generation | Not covered | Requires separate provider integrations, artifact handling, quotas, and likely async job semantics |

Recommended product model:

- Keep `enable_code_interpreter` for Mattin-managed deterministic artifact generation.
- Keep `server_tools` for provider-native tools (`image_generation`, provider-hosted
  `code_interpreter`, `web_search`, `file_search`).
- Add an optional higher-level `content_capabilities` view in the UI that maps user-facing
  capabilities to the underlying switches:
  - "Documents and reports" → `enable_code_interpreter=true` + Skills.
  - "Images" → provider-native `image_generation` where supported, or Gemini native image output where configured.
  - "Data analysis" → Mattin Skills, optionally plus provider-hosted code execution
    for models where that is explicitly desired.

This means the sandbox RFC is sufficient for document/report/spreadsheet/chart/presentation
generation, but it should not be treated as the complete design for all media generation.

---

## 6. Data Model Changes

### Agent table

```sql
ALTER TABLE "Agent"
  ADD COLUMN sandbox_provider VARCHAR(50)
    NOT NULL DEFAULT 'subprocess';
```

Values: `'subprocess'` (default, backward-compat), `'opensandbox'`, `'e2b'`.

```python
# backend/models/agent.py (addition)
sandbox_provider = Column(
    String(50),
    nullable=False,
    default='subprocess',
    server_default='subprocess',
)
```

### Skill table evolution

The current `Skill` table remains the single catalogue for reusable agent capabilities. Align its
stored shape with `SKILL.md`-based packages instead of creating `SandboxPackage`.

```sql
ALTER TABLE "Skill"
  ALTER COLUMN name TYPE VARCHAR(64),
  ALTER COLUMN description TYPE VARCHAR(1024),
  ADD COLUMN display_name VARCHAR(100),
  ADD COLUMN frontmatter JSON NOT NULL DEFAULT '{}',
  ADD COLUMN dependencies JSON NOT NULL DEFAULT '[]',
  ADD COLUMN allowed_tools JSON NOT NULL DEFAULT '[]',
  ADD COLUMN runtime VARCHAR(30),
  ADD COLUMN bootstrap_script_path VARCHAR(255),
  ADD COLUMN runtime_options JSON NOT NULL DEFAULT '{}',
  ADD COLUMN is_builtin BOOLEAN NOT NULL DEFAULT false;
```

```sql
CREATE TABLE "SkillFile" (
  file_id INTEGER PRIMARY KEY,
  skill_id INTEGER NOT NULL REFERENCES "Skill"(skill_id),
  path VARCHAR(512) NOT NULL,
  media_type VARCHAR(100),
  content_text TEXT,
  content_bytes BYTEA,
  checksum_sha256 VARCHAR(64) NOT NULL
);
```

No new agent association table is required. `agent_skills` continues to attach all skill types
to agents.

### Alembic migration

One migration file covering the `Agent` column and `Skill` table additions, following the
project's [Alembic conventions](./.alembic.instructions.md). Seed data should create the
platform built-in Skills with `app_id = NULL`.

For existing skills, the migration should derive a portable `name` slug from the current
display name when needed, preserve the original value in `display_name`, and fail validation only
for unresolved collisions.

---

## 7. Configuration

### Environment variables (backend `.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_DEFAULT_PROVIDER` | `subprocess` | Platform-wide default when agent has no explicit `sandbox_provider` |
| `OPENSANDBOX_DOMAIN` | — | OpenSandbox server host:port (e.g. `opensandbox:8080` in Docker) |
| `OPENSANDBOX_API_KEY` | — | API key for OpenSandbox server |
| `E2B_API_KEY` | — | API key for E2B cloud service |
| `SANDBOX_DEFAULT_TIMEOUT_S` | `30` | Default per-execution timeout (seconds) |
| `SANDBOX_SESSION_TTL_H` | `2` | Max sandbox lifetime in hours |
| `SANDBOX_PACKAGE_INSTALL_TIMEOUT_S` | `120` | Timeout for `pip install` during bootstrap |

---

## 8. Provider Comparison

### Phase 1 provider shortlist

| Dimension | `subprocess` | OpenSandbox | E2B |
|-----------|-------------|-------------|-----|
| **Isolation** | None — host process | Container runtime, with optional gVisor/Kata/Firecracker hardening | Cloud sandbox / microVM-oriented isolation |
| **Self-hosting** | N/A | Docker or Kubernetes | Possible via E2B infra, but not the simple path |
| **Managed service** | N/A | Available | Primary path |
| **Session persistence** | Per process only; no interpreter state | Default language context persists across runs | Code contexts, pause/resume, lifecycle options |
| **Multi-language** | Python only | Python, Java, Node.js/TypeScript, Go, Bash via Code Interpreter SDK/runtime | Python code interpreter plus shell/command APIs |
| **Package install** | Backend venv | `pip` or prebuilt sandbox image | `pip` or custom template |
| **File I/O** | Local `working_dir` | Sandbox files API | Sandbox files API |
| **Network control** | None | Runtime egress policy / secure runtime configuration | Provider network configuration, internet access toggle |
| **Best fit** | Local dev only | Self-hosted production and Docker/Kubernetes-first deployments | SaaS / managed cloud deployments |

**Primary recommendation**: OpenSandbox for self-hosted deployments (matches existing Docker
Compose stack). E2B for SaaS deployments or when infrastructure management is undesirable.

### Adapter watchlist

| Provider | Deployment model | Strengths | Main reason to defer |
|----------|------------------|-----------|----------------------|
| Modal Sandboxes | Managed cloud | Mature Python SDK, custom images, volumes, arbitrary commands, reconnect by ID | Not self-hosted; file APIs are still evolving |
| Daytona | Managed cloud / open-source platform | Full computer environments, snapshots, resource sizing, firewall settings, multiple SDKs | More dev-environment oriented than needed for first content-generation release |
| CodeSandbox SDK | Managed microVMs | Fast clone/hibernate/fork, Docker templates, JS/Python/shell execution | JavaScript-first integration and commercial hosted dependency |
| Microsandbox | Self-hosted microVMs | VM-level isolation, OCI images, Python/Node SDKs, filesystem APIs, MCP | Younger ecosystem; needs operational validation |

### Hosted model tools

| Tool family | Fit | Limitation for this RFC |
|-------------|-----|-------------------------|
| OpenAI/Azure `image_generation` | Best path for generative images; Mattin already persists returned image blocks | Not a general-purpose Mattin sandbox and cannot install arbitrary packages |
| OpenAI hosted `code_interpreter` | Good provider-native file/code reasoning tool | Package set, lifecycle, and network controls are provider-owned |
| Anthropic code execution | Strong for Claude-native bash/file workflows | Beta/provider-owned; not portable across LLM providers |
| Gemini code execution | Useful for Python reasoning, CSV/text/image analysis, and graph output | 30s runtime and fixed library set; no arbitrary package install |

---

## 9. Self-Hosted Deployment

OpenSandbox is added to `docker/docker-compose.yaml` as a new service. All communication
between the backend and the sandbox server remains on the internal Docker network — no port
is exposed to the host.

```yaml
# docker/docker-compose.yaml  (addition)

  opensandbox:
    image: opensandbox/server:latest
    restart: unless-stopped
    environment:
      - OPENSANDBOX_API_KEY=${OPENSANDBOX_API_KEY}
    volumes:
      - ${OPENSANDBOX_CONFIG_PATH:-~/.sandbox.toml}:/root/.sandbox.toml:ro
    networks:
      - internal
    # No ports exposed — only reachable from backend on the internal network
```

Backend configuration for this setup:

```env
SANDBOX_DEFAULT_PROVIDER=opensandbox
OPENSANDBOX_DOMAIN=opensandbox:8080
OPENSANDBOX_API_KEY=<shared-local-secret>
```

### Optional secure runtime (`~/.sandbox.toml`)

For production hardening, operators can configure gVisor on the Docker host:

```toml
# ~/.sandbox.toml
[runtime]
type = "docker"
execd_image = "opensandbox/execd:v1.0.5"

[secure_runtime]
type = "gvisor"
docker_runtime = "runsc"
```

Without this file, OpenSandbox defaults to standard `runc` — still fully isolated from the
backend but without kernel-level syscall filtering.

---

## 10. Security Considerations

| Risk | Mitigation |
|------|-----------|
| LLM-generated code reads host secrets | Sandbox process has no access to host env vars — eliminated for `opensandbox` and `e2b` providers |
| Unbounded resource consumption | `resourceLimits` (CPU, memory) set at sandbox creation; `timeout` per execution |
| Network egress from sandbox | OpenSandbox: configure egress controls in `~/.sandbox.toml`; E2B: managed at infrastructure level |
| Sandbox escape via kernel vulnerability | gVisor/Kata/Firecracker provide defence-in-depth; `subprocess` provider remains unsafe |
| Malicious packages in `Skill.dependencies` | Dependency metadata is set by ADMINISTRATOR users or trusted built-in seed data, not by the LLM at runtime |
| Secrets in skill scripts | Scripts are stored as `SkillFile` records; treat executable files in skill packages as sensitive configuration — require ADMINISTRATOR role to create/edit runtime-capable skills |
| `subprocess` provider in production | Block via `SANDBOX_DEFAULT_PROVIDER != subprocess` policy check at app startup (warn, not hard-block, for backward compat) |

> **Important**: The `subprocess` provider must never be the default in any deployment that
> serves multiple tenants or exposes the Public API. Set `SANDBOX_DEFAULT_PROVIDER=opensandbox`
> or `SANDBOX_DEFAULT_PROVIDER=e2b` in all production `.env` files.

---

## 11. Migration Path

### Phase 0 — Abstraction (no behaviour change)
- Create `backend/tools/sandbox/` package.
- Implement `SubprocessProvider` wrapping existing `python_sandbox_tools.py`.
- Replace the direct call in `agentTools.py` with `resolve_provider` + `create_sandbox_repl_tool`.
- All agents with `sandbox_provider = 'subprocess'` behave identically to today.

### Phase 1 — Data model
- Add `sandbox_provider` column to `Agent` (default `'subprocess'`).
- Add runtime capability fields to `Skill`; keep `agent_skills` as the single association table.
- Alembic migration + downgrade tested.
- `SandboxSessionService` service created.

### Phase 2 — OpenSandbox provider
- Implement `OpenSandboxProvider`.
- Add `opensandbox` + `opensandbox-code-interpreter` to `requirements.txt` (optional dependency group).
- Add `opensandbox` service to `docker-compose.yaml`.
- Integration test: create sandbox → install pandas → run code → destroy.

### Phase 3 — Skills
- Extend `Skill` CRUD, service, repository, schemas, and internal API responses with portable
  package fields and `SkillFile` resources.
- Add import/export for skill directories and zip files containing `SKILL.md`.
- Keep one skill assignment flow: attach skills to agents through `agent_skills`.
- Bootstrap flow in `SandboxSessionService.get_or_create`.
- Seed built-in Skills catalogue.

### Phase 4 — File round-trip
- `_prepare_turn`: push user-uploaded files into sandbox via `write_file`.
- `_finalize_turn`: pull new sandbox files into `working_dir`.
- Existing `sync_output_files` flow unchanged.

### Phase 5 — E2B provider
- Implement `E2BProvider`.
- Add `e2b-code-interpreter` to optional dependencies.
- Document SaaS deployment variant.

### Phase 6 — Frontend
- Agent configuration form: `sandbox_provider` selector + unified skill picker with capability badges.
- Skills management page: `SKILL.md` editor, metadata validation, and supporting-file manager.
- Content capabilities view that maps friendly options to `enable_code_interpreter`,
  Skills, and supported `server_tools`.

### Phase 7 — Optional provider adapters
- Re-evaluate Modal, Daytona, CodeSandbox SDK, and Microsandbox after OpenSandbox/E2B are
  implemented.
- Add adapters only when a concrete deployment or product requirement justifies them.

---

## 12. Open Questions

| # | Question | Options |
|---|----------|---------|
| Q1 | How should built-in Skills be overridden by apps? | Built-in `Skill.app_id = NULL` is globally reusable; app-scoped skills can copy and customize them |
| Q2 | Should sandbox files be **scoped to the conversation** (deleted on reset) or survive across conversations? | Per-conversation is safer; cross-conversation adds value for long-running workflows |
| Q3 | Should the `subprocess` provider emit a **deprecation warning** when used with `enable_code_interpreter = true`? | Opt-in warning via env flag |
| Q4 | Should Skills support **pre-built Docker images** as a Mattin extension to `dependencies`? | Images give faster cold starts; pip install is more flexible for user-defined skills |
| Q5 | How should the `SandboxSessionService` handle backend **restarts**? Sandboxes are destroyed; conversations appear to resume but without sandbox state. | Surface a "sandbox unavailable, state lost" message; or reconnect by ID (E2B supports `Sandbox.connect(id)`) |
| Q6 | Should Mattin expose a higher-level **content capabilities** UI instead of raw `server_tools` and individual skills? | Higher-level UI is easier for users; raw config remains useful for administrators |
| Q7 | Should generated images from provider-native tools be editable inside the Mattin sandbox by default? | Auto-push generated images into `/workspace` for image-processing agents; otherwise leave them in `working_dir` only |

---

## 13. Architecture Analysis

> Added May 6, 2026. Based on inspection of the actual codebase on branch `develop`.

### 13.1 Impact Map

#### Files directly impacted

| Layer | Current file | Change type |
|-------|-------------|-------------|
| Tool | `backend/tools/python_sandbox_tools.py` | Wrapped by `SubprocessProvider`; no longer called directly |
| Tool | `backend/tools/agentTools.py` (lines 244–248) | Single integration point: replace direct `create_python_repl_tool` call with `resolve_provider` + `create_sandbox_repl_tool` |
| Tool | `backend/tools/skill_tools.py` | Extended to read `skill.dependencies` and `skill.runtime` for bootstrap |
| Model | `backend/models/agent.py` | +1 column: `sandbox_provider VARCHAR(50) DEFAULT 'subprocess'` |
| Model | `backend/models/skill.py` | +8 columns; `name` widened to 64; `description` widened to 1024; new `SkillFile` table |
| Service | `backend/services/agent_execution_service.py` | `_prepare_turn` → push user files into sandbox; `_finalize_turn` → pull new sandbox files before `sync_output_files()` |
| Service | `backend/services/sandbox_session_service.py` | **New** — manages `SandboxHandle` lifecycle per conversation |
| Infrastructure | `docker/docker-compose.yaml` | +`opensandbox` service on internal network (no host port) |
| Config | `.env` / `backend/config.py` | 7 new environment variables (see §7) |
| Migrations | `alembic/versions/` | 1 new migration: `Agent` column + `Skill` columns + `SkillFile` table + seed data |

#### Files **not** impacted

- `agent_skills` association table — remains the single Agent↔Skill join
- `FileManagementService.sync_output_files()` — called unchanged from `_finalize_turn`
- All internal and public router files — no API surface changes
- Frontend (deferred to IT-6)

---

### 13.2 Integration Flow

The diagram below reflects the **actual call chain** in the codebase after the full implementation:

```
┌──────────────────────────────────────────────────────────┐
│                  AgentExecutionService                    │
│                                                           │
│  _prepare_turn()                                          │
│    └─ [new] SandboxSessionService.get_or_create(          │
│              key, provider, runtime_skills)               │
│    └─ [new] for each user file:                           │
│              provider.write_file(handle, name, bytes)     │
│                                                           │
│  _execute_agent_async()                                   │
│    └─ create_agent(agent, ..., working_dir)               │
│         └─ agentTools.create_agent()                      │
│              └─ resolve_provider(agent)                   │
│              └─ create_sandbox_repl_tool(handle, prov)    │
│                   (same tool name: python_repl)           │
│                                                           │
│  _finalize_turn()                                         │
│    └─ [new] remote_files = provider.list_files(handle)    │
│    └─ [new] pull new files → working_dir                  │
│    └─ sync_output_files()  [unchanged]                    │
└──────────────────────────────────────────────────────────┘

         SandboxProvider (ABC)
         ┌─────────────────────────┐
         │  create_sandbox()       │
         │  run_code()             │
         │  write_file()           │
         │  read_file()            │
         │  list_files()           │
         │  destroy_sandbox()      │
         └─────────────────────────┘
                  ▲         ▲         ▲
     SubprocessProvider  OpenSandbox  E2BProvider
     (default / dev)     (self-hosted) (SaaS)
```

Key observations from the real code:

- `agentTools.create_agent()` already receives `working_dir` as a parameter — the sandbox
  handle only needs to be threaded through alongside it.
- `_prepare_turn()` already snapshots `pre_existing_files` in `working_dir`; the same pattern
  applies to sandbox files before each turn.
- `skill_associations` are already loaded eagerly via `get_agent_with_relationships()`, so
  runtime skill filtering requires no extra DB query.
- The `server_tools` path (OpenAI `image_generation`, Anthropic `code_interpreter`, etc.) is
  a separate conditional block in `agentTools.py` and is not touched by this RFC.

---

### 13.3 New Artefacts Layout

```
backend/
├── tools/
│   └── sandbox/                     ← new package
│       ├── __init__.py
│       ├── provider.py              ← SandboxProvider ABC + SandboxHandle dataclass
│       ├── factory.py               ← resolve_provider(agent) → SandboxProvider
│       ├── tool_factory.py          ← create_sandbox_repl_tool(handle, provider)
│       ├── subprocess_provider.py   ← wraps existing python_sandbox_tools.py logic
│       ├── opensandbox_provider.py  ← primary self-hosted provider
│       └── e2b_provider.py          ← managed cloud alternative
└── services/
    └── sandbox_session_service.py   ← new: SandboxHandle lifecycle per conversation
```

---

### 13.4 Implementation Plan

Each iteration is self-contained, testable, and non-breaking.

#### IT-0 — Abstraction without behaviour change

**Goal**: New code, identical runtime behaviour. `subprocess` remains the only active provider.

| Task | Detail |
|------|--------|
| Create `backend/tools/sandbox/` | `provider.py`, `factory.py`, `tool_factory.py`, `subprocess_provider.py` |
| Wrap existing logic | `SubprocessProvider.run_code()` replicates `python_sandbox_tools.py` exactly |
| Replace call site | Lines 244–248 of `agentTools.py`: `create_python_repl_tool(working_dir)` → `resolve_provider(agent)` + `create_sandbox_repl_tool(handle, provider)` |
| Keep legacy file | `python_sandbox_tools.py` retained but no longer imported by `agentTools.py` |

**Verification**: All existing tests pass without modification. Runtime behaviour is identical.

---

#### IT-1 — Data model + SandboxSessionService

**Goal**: Conversation-scoped sandbox lifecycle; Agent knows its provider.

| Task | Detail |
|------|--------|
| `Agent.sandbox_provider` | `VARCHAR(50) NOT NULL DEFAULT 'subprocess'` |
| `Skill` column additions | `display_name`, `frontmatter`, `dependencies`, `allowed_tools`, `runtime`, `bootstrap_script_path`, `runtime_options`, `is_builtin`; widen `name` to 64, `description` to 1024 |
| `SkillFile` table | `file_id`, `skill_id`, `path`, `media_type`, `content_text`, `content_bytes`, `checksum_sha256` |
| Alembic migration | Upgrade + downgrade tested; data migration derives slug from current `name` into `display_name` where needed |
| `SandboxSessionService` | `get_or_create()`, `destroy()`, `destroy_all_for_agent()` |
| Lifecycle hooks | `reset_agent_conversation()` calls `destroy(key)`; agent deletion calls `destroy_all_for_agent(agent_id)` |

**Verification**:
- `alembic upgrade head` + `alembic downgrade -1` clean
- Unit test: `SandboxSessionService.get_or_create()` with mocked `SubprocessProvider`
- Existing agents unchanged (`sandbox_provider='subprocess'` by default)

---

#### IT-2 — OpenSandbox provider

**Goal**: First truly isolated provider for self-hosted deployments.

| Task | Detail |
|------|--------|
| `OpenSandboxProvider` | Implement all six abstract methods; state persists via `CodeInterpreter` context |
| Dependencies | `opensandbox` + `opensandbox-code-interpreter` as optional group in `requirements.txt` |
| Docker Compose | Add `opensandbox` service on internal network; no host port exposed |
| Config | Document `SANDBOX_DEFAULT_PROVIDER`, `OPENSANDBOX_DOMAIN`, `OPENSANDBOX_API_KEY` in `.env.example` |
| Startup warning | Log `WARNING` if `SANDBOX_DEFAULT_PROVIDER=subprocess` and `AICT_LOGIN != FAKE` |

**Verification**:
- Integration test: `create_sandbox → pip install pandas → run code → list_files → destroy`
- Agent with `sandbox_provider='opensandbox'` cannot read `os.environ` of the backend process
- Agent with `sandbox_provider='subprocess'` still works unchanged

---

#### IT-3 — Skills with runtime capabilities

**Goal**: Skills evolve from prompt-only to portable packages; sandbox bootstraps from attached skills.

| Task | Detail |
|------|--------|
| Extend `SkillRepository`, `SkillService` | CRUD for new columns and `SkillFile` records |
| Update Pydantic schemas | Request/response schemas include `dependencies`, `runtime`, `is_builtin`, `files` |
| Import/export | Round-trip a skill as a ZIP or directory with `SKILL.md` and supporting files |
| Bootstrap flow | `agentTools.py` filters `runtime_skills`; passes to `SandboxSessionService.get_or_create()` |
| `skill_tools.py` | `load_skill` continues unchanged; `generate_skills_system_prompt_section` unchanged |
| Built-in Skills seed | Data migration creates `word-generation`, `data-analysis`, `charts`, `pdf-generation`, `presentation-generation` with `app_id=NULL`, `is_builtin=True` |
| Access control | Create/edit of runtime-capable skills (non-null `runtime`) requires role ≥ `ADMINISTRATOR` |

**Verification**:
- Agent with `word-generation` skill attached can execute `from docx import Document` without manual install
- Agent without runtime skills is unaffected
- Import → export → re-import of a skill package is lossless

---

#### IT-4 — Complete file round-trip

**Goal**: User files reach the sandbox; sandbox-generated files reach the file panel.

| Task | Detail |
|------|--------|
| `_prepare_turn()` | After sandbox handle obtained, push each `processed_file` via `provider.write_file(handle, filename, bytes)` |
| `_finalize_turn()` | Before `sync_output_files()`: call `provider.list_files()`, diff against pre-turn snapshot, pull new files into `working_dir` |
| `SubprocessProvider` exception | Uses `working_dir` directly — no push/pull needed; the existing snapshot diff in `_finalize_turn` is sufficient |

**Verification**:
- User uploads `data.xlsx`; LLM code reads it with `open('data.xlsx')` inside the sandbox
- LLM writes `report.docx` to `/workspace`; file appears in the file panel as downloadable
- `SubprocessProvider` path produces the same outcome as today

---

#### IT-5 — E2B provider

**Goal**: Cloud-managed alternative for SaaS deployments.

| Task | Detail |
|------|--------|
| `E2BProvider` | Implement all six methods using `e2b-code-interpreter` SDK |
| Dependencies | `e2b-code-interpreter` as optional group |
| Config | Document `E2B_API_KEY` in `.env.example` |

**Verification**: End-to-end test identical to IT-2 using E2B sandbox, no local infrastructure required.

---

#### IT-6 — Frontend

**Goal**: Expose sandbox capabilities in the UI without requiring technical knowledge.

| Task | Detail |
|------|--------|
| Agent config form | `sandbox_provider` selector (subprocess / opensandbox / e2b) |
| Skill picker | Badges per skill: `instructions`, `runtime`, or `hybrid` |
| Content capabilities view | Friendly switches map to `enable_code_interpreter` + Skills + `server_tools` |
| Skill management page | `SKILL.md` editor, metadata validation, `SkillFile` manager, import/export UI |

**Verification**: A non-technical user can enable Word document generation in ≤ 3 steps.

---

### 13.5 Iteration Dependencies

```
IT-0 (abstraction layer)
  └─► IT-1 (data model + session service)
         └─► IT-2 (OpenSandbox provider)
               └─► IT-3 (Skills runtime)
                     └─► IT-4 (file round-trip)
                           └─► IT-5 (E2B provider)

IT-1 ──────────────────────────────────────────────► IT-6 (frontend)
```

IT-5 and IT-6 are independent of each other once IT-4 is complete.

---

### 13.6 Open Questions — Prioritised

The questions from §12 are re-ordered by implementation risk:

| Priority | # | Question | Recommended resolution |
|----------|---|----------|------------------------|
| **High** | Q5 | Backend restart destroys active sandboxes; conversation appears to resume but sandbox state is lost | Store `sandbox_session_id` on `Conversation`; reconnect via `Sandbox.connect(id)` where supported (E2B). Otherwise surface a clear "sandbox state reset" message to the user. |
| **High** | Q3 | Should `subprocess` emit a deprecation warning in production? | Log `WARNING` at app startup if `SANDBOX_DEFAULT_PROVIDER=subprocess` and `AICT_LOGIN != FAKE`. Hard block is not required. |
| **Medium** | Q1 | How do apps override built-in Skills? | `app_id=NULL` + `is_builtin=True` → globally readable. App can clone a built-in into its own scope and customise it. |
| **Medium** | Q2 | Should sandbox files persist across conversations? | Scope to conversation (per-conversation `working_dir` pattern already in place). Cross-conversation persistence is a later opt-in. |
| **Low** | Q6 | Should Mattin expose a higher-level "content capabilities" UI? | Implement as a presentation layer in IT-6 over the existing fields — no data model changes needed. |
| **Low** | Q4 | Should Skills support pre-built Docker images in `dependencies`? | Defer. `pip` covers initial built-in catalogue. Docker image support is a future `runtime_options` extension. |
| **Low** | Q7 | Should provider-native generated images be auto-pushed into the sandbox? | Only push when agent has both `server_tools` with `image_generation` and a runtime skill like `image-processing`. Gate behind a flag. |

---

### 13.7 Security Contracts per Iteration

| Iteration | Security posture change |
|-----------|------------------------|
| IT-0 | No change. Establishes the seam that later iterations make secure. |
| IT-1 | No change. Data model ready for secure providers. |
| IT-2 | **Primary fix**: LLM-generated code no longer has access to `os.environ` of the backend process (eliminates OWASP A02:2021 — Cryptographic Failures / secret exposure). CPU and memory bounded by sandbox resource limits. |
| IT-3 | Skill dependency metadata is set only by `ADMINISTRATOR`+ users or trusted built-in seed data, never by the LLM at runtime (prevents supply-chain package injection). |
| IT-4 | Files transit through `working_dir` under controlled paths; sandbox cannot write to arbitrary backend filesystem locations. |
| IT-5 | Network egress policy delegated to E2B infrastructure; same isolation guarantees as IT-2 without self-hosted overhead. |

> The `subprocess` provider **must not** be set as `SANDBOX_DEFAULT_PROVIDER` in any deployment
> that exposes the Public API or serves multiple tenants. See §10 for the full risk table.

---

## 14. References

- [OpenSandbox (Alibaba) — GitHub](https://github.com/alibaba/opensandbox)
- [OpenSandbox — Secure Container Runtime guide](https://github.com/alibaba/opensandbox/blob/main/docs/secure-container.md)
- [OpenSandbox — LangGraph integration example](https://github.com/alibaba/opensandbox/blob/main/examples/langgraph/README.md)
- [E2B — GitHub](https://github.com/e2b-dev/E2B)
- [E2B — LangChain integration docs](https://e2b.dev/docs/quickstart/connect-llms)
- [E2B — Self-hosting guide](https://github.com/e2b-dev/infra/blob/main/self-host.md)
- [Modal — Sandboxes guide](https://modal.com/docs/guide/sandboxes)
- [Modal — Sandbox reference](https://modal.com/docs/reference/modal.Sandbox)
- [Daytona — Sandboxes docs](https://www.daytona.io/docs/en/sandboxes/)
- [CodeSandbox SDK](https://codesandbox.io/sdk)
- [Microsandbox docs](https://docs.microsandbox.dev/)
- [OpenAI — Code Interpreter tool](https://platform.openai.com/docs/guides/tools-code-interpreter/)
- [OpenAI — Image generation tool](https://platform.openai.com/docs/guides/tools-image-generation/)
- [Anthropic — Agent Skills overview](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
- [Anthropic — Agent Skills in Claude Code](https://docs.claude.com/en/docs/claude-code/skills)
- [Anthropic — Skill authoring best practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Anthropic — Code execution tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/code-execution-tool)
- [Google Gemini API — Code execution](https://ai.google.dev/gemini-api/docs/code-execution)
- [Google Gemini API — Image generation](https://ai.google.dev/gemini-api/docs/image-generation)
- [MattinAI — Agent System](agent-system.md)
- [MattinAI — Backend Architecture](../architecture/backend.md)
- `backend/tools/python_sandbox_tools.py` — current subprocess implementation
- `backend/tools/agentTools.py` — `create_agent()` tool assembly
- `backend/models/agent.py` — `enable_code_interpreter`, `server_tools` columns
