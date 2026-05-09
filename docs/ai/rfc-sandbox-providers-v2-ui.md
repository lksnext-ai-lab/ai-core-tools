# RFC: Sandbox Providers v2 UI Definition

> Part of [Mattin AI Documentation](../index.md)  
> **Status**: Draft - May 10, 2026  
> **Related**: [RFC v2: Sandbox Providers, Skills Runtime, and Lifecycle Recovery](rfc-sandbox-providers-v2.md)  
> **Branch context reviewed**: `exp/sandbox`

## 1. Purpose

This RFC defines the user interface for the sandbox and Skill functionality described in
`rfc-sandbox-providers-v2.md`.

The backend RFC defines runtime behavior: sandbox providers, lifecycle recovery, Skill package
activation, progressive disclosure, and Skill router semantics. This RFC defines how administrators
and agent users should see and manage those capabilities in Mattin's UI.

The UI target is:

1. Let administrators create, import, validate, inspect, and export portable Agent Skills packages.
2. Remove the misleading "runtime + pip dependencies" mental model from the Skill editor.
3. Show sandbox provider configuration without letting a Skill override the conversation image.
4. Surface Skill activation and sandbox execution status in the playground.
5. Keep advanced runtime failures visible, actionable, and bounded.

## 2. Current UI Audit

| Area | Current UI | Gap against sandbox v2 |
|---|---|---|
| Skills list | `frontend/src/pages/settings/SkillsPage.tsx` lists name, description, type, created date, and actions. | Type is based on `runtime == "python-sandbox"`, which v2 retires. No package/resource visibility. No import/export/validation entry points. |
| Skill editor | `frontend/src/components/forms/SkillForm.tsx` edits name, display name, runtime, pip dependencies, description, and instructions. | Runtime and dependencies reinforce the old dependency registry. No `SKILL.md` frontmatter view. No resource tree. No bootstrap path selection. |
| App settings | `frontend/src/pages/settings/AppSettingsPage.tsx` exposes sandbox provider override. | Good base, but labels should distinguish provider policy from per-Skill setup and show inherited/default provider. |
| Playground code output | `frontend/src/components/playground/CodeExecutionPanel.tsx` shows combined output lines. | Does not distinguish stdout/stderr, truncation, execution budget, sandbox recovery, or Skill activation phases. |
| Tool history | `ToolHistoryPanel` and streaming hooks show tool activity. | Skill router decisions and automatic Skill activation are not first-class events. |

## 3. Product Principles

1. Preserve progressive disclosure.
   The UI should mirror the runtime: metadata first, `SKILL.md` body on activation, resources on
   demand. The Skills list must not load large resource bodies.

2. Treat Skills as portable packages.
   The UI should describe Skills as `SKILL.md` plus bundled resources, not as Mattin-only prompt
   records.

3. Keep sandbox configuration at app/provider level.
   A Skill may describe requirements, but the UI must not imply that a Skill can choose Docker
   images or install arbitrary dependencies through a registry.

4. Prefer status over silence.
   File-copy failures, bootstrap failures, expired sandboxes, output truncation, and execution
   budgets should be visible in the UI.

5. Keep operational UI dense and scannable.
   These screens are settings and debugging tools. Use tables, tabs, compact status badges,
   drawers, and panels rather than marketing-style pages.

## 4. Information Architecture

### 4.1 Settings - Skills

Replace the current single modal editor with a Skill package management surface:

```text
Settings
+-- Skills
    +-- Skills table
    +-- Create Skill
    +-- Import Skill Package
    +-- Skill detail drawer/page
        +-- Overview
        +-- SKILL.md
        +-- Resources
        +-- Validation
        +-- Agents
```

The first iteration may keep a modal for simple edits, but package resources and validation should
move into a detail drawer or full page once implemented.

### 4.2 Settings - App Settings

Keep sandbox provider configuration in app settings:

```text
Settings
+-- General Settings
    +-- Code Interpreter Sandbox
```

This control selects an app-level provider override or inherits the system default. It must not
expose per-Skill images.

### 4.3 Agent Builder

The agent form should continue assigning Skills to agents, but the Skill picker should show router
metadata:

- name;
- description;
- package status;
- resource count;
- bootstrap presence;
- whether `disable-model-invocation` prevents automatic router selection.

### 4.4 Playground

The playground should show runtime events during a turn:

```text
Message stream
+-- Thinking/tool activity
+-- Skill activity
|   +-- router selected skill
|   +-- SKILL.md loaded
|   +-- files copied
|   +-- bootstrap skipped/ok/failed
+-- Code output
    +-- stdout
    +-- stderr
    +-- truncation marker
    +-- execution budget status
```

## 5. Skills UI

### 5.1 Skills Table

Columns:

| Column | Purpose |
|---|---|
| Name | Package `name`; clickable. |
| Description | Router metadata; truncated but expandable in detail. |
| Package | Status badge: `valid`, `warnings`, `invalid`, `builtin`, `frozen`. |
| Resources | Count by role: `scripts`, `references`, `assets`, `other`. |
| Activation | Compact metadata: bootstrap present, manual-only, or auto-selectable. |
| Updated | Last update date. |
| Actions | Edit, validate, export, duplicate, delete where allowed. |

Remove the old `prompt-only` and `sandbox` type badges. They are no longer the core model.

### 5.2 Create Skill

The create flow should offer two options:

```text
Create Skill
+-- Blank Skill
+-- Import ZIP
```

Blank Skill creates a minimal package:

```text
SKILL.md
```

The blank editor should ask for:

- `name`;
- `description`;
- optional `display_name`;
- `SKILL.md` body.

Do not ask for `runtime` or `pip dependencies`.

### 5.3 Import Skill Package

Import flow:

1. Upload ZIP.
2. Client sends ZIP to validation endpoint.
3. UI shows validation results before commit.
4. Administrator confirms import.
5. UI opens the imported Skill detail view.

Validation display:

```text
Errors
- Missing SKILL.md at archive root.
- Path traversal detected: ../secret.txt.

Warnings
- Deprecated runtime field will be ignored.
- allowed-tools is present but enforced through Mattin policy.
```

Hard errors block import. Warnings allow import after confirmation.

### 5.4 Skill Detail

Use tabs:

| Tab | Contents |
|---|---|
| Overview | Name, description, display name, builtin/frozen state, attached agents, package status. |
| `SKILL.md` | Frontmatter editor and Markdown body editor. Optionally support raw full-file mode. |
| Resources | Package tree with `scripts/`, `references/`, `assets/`, `agents/`, and other files. |
| Validation | Latest validation errors/warnings and revalidate action. |
| Agents | Agents using this Skill and whether each allows code interpreter. |

### 5.5 `SKILL.md` Editor

The default editor should separate high-signal fields from raw YAML:

```text
Name
Description
Display name
When to use
Disable automatic invocation
Bootstrap script path
Allowed tools (read-only compatibility metadata or advanced field)
Markdown instructions
```

Advanced users may switch to raw `SKILL.md` mode. Raw mode must preserve unknown frontmatter.

Validation hints:

- Description should be self-contained and router-friendly.
- Description should mention trigger words and file extensions.
- Body should move long references into `references/`.
- Deprecated `runtime` and `dependencies` fields are ignored.

### 5.6 Resources Tab

Resource tree requirements:

- Show package-root-relative paths.
- Group by prefix: `scripts`, `references`, `assets`, `agents`, `other`.
- Show file size, media type, checksum, and last update where available.
- Support upload, replace, rename, download, and delete for administrators.
- Support preview for text resources.
- Support binary metadata and download for binary resources.

Path safety must be visible in errors:

```text
Path must be relative to the Skill package root and cannot contain `..`.
```

The UI stores text files in `content_text` and binary files in `content_bytes` through the API.
This is not shown as database terminology to users; the UI should call them "text resource" and
"binary resource".

### 5.7 Bootstrap Selection

Bootstrap is a reviewed package script, not a dependency manifest. The UI should show:

- bootstrap path selector populated from `scripts/*`;
- current status: not configured, configured, last activation ok, or last activation failed;
- warning that bootstrap runs only during sandbox Skill activation;
- no package install form.

Suggested copy:

```text
Bootstrap script
Runs during sandbox activation after package files are copied. Use this for deterministic setup
owned by the Skill package. Do not use this as a general dependency registry.
```

## 6. Sandbox Provider UI

### 6.1 App Settings Control

Current app setting can remain, with updated labels:

```text
Code Interpreter Sandbox
[ Inherit system default v ]

Options:
- Inherit system default
- OpenSandbox (isolated container)
- Subprocess (local development only)
```

Display:

- effective provider;
- system default provider;
- warning when `subprocess` is selected outside development;
- disabled state if deployment policy allows only one provider.

### 6.2 Image Policy

Do not expose image selection in the Skill editor. If image selection becomes configurable later,
place it at provider/deployment/app level only.

UI rule:

```text
Skills may document prerequisites, but they do not choose the sandbox image.
```

## 7. Playground Runtime UI

### 7.1 Skill Activity Panel

Add a compact panel inside the streamed assistant turn or tool history:

```text
Skills
- charts: selected by router, files=ok, bootstrap=skipped
- pdf-processing: manually loaded, files=ok, bootstrap=failed
```

Each item should show:

- skill name;
- activation source: router, manual `load_skill`, retry tool;
- phase status: instructions, files, bootstrap;
- failure message with retry affordance when allowed.

### 7.2 Code Output Panel

Update `CodeExecutionPanel` to understand structured events:

```ts
type CodeOutputLine = {
  stream: "stdout" | "stderr" | "status";
  line: string;
  truncated?: boolean;
};
```

UI behavior:

- stdout and stderr are visually distinct.
- stderr does not automatically mean the whole turn failed.
- truncation marker is shown as a status line.
- running state expands the panel.
- completed state collapses by default but keeps summary.

Summary examples:

```text
Code output - running
Code output - 12 stdout, 2 stderr
Code output - truncated at 20000 chars
```

### 7.3 Sandbox Lifecycle Events

Show lifecycle events in tool history or a runtime drawer:

- sandbox resumed;
- sandbox renewed;
- sandbox expired, recreating;
- sandbox recreated, restoring active Skills;
- reset destroyed sandbox.

Only show these by default when they affect latency, output, or recovery. A detailed debug view can
show all lifecycle events.

### 7.4 Execution Budget

When the per-turn budget is exhausted, show a clear assistant/tool message:

```text
Code execution limit reached for this turn.
```

The UI should not present this as a crash. It is a policy limit.

## 8. API Requirements

### 8.1 Skills Package API

Frontend needs these operations:

```text
GET    /internal/apps/{app_id}/skills/
GET    /internal/apps/{app_id}/skills/{skill_id}
POST   /internal/apps/{app_id}/skills/{skill_id}
DELETE /internal/apps/{app_id}/skills/{skill_id}

POST   /internal/apps/{app_id}/skills/validate
POST   /internal/apps/{app_id}/skills/import
GET    /internal/apps/{app_id}/skills/{skill_id}/export

GET    /internal/apps/{app_id}/skills/{skill_id}/files
GET    /internal/apps/{app_id}/skills/{skill_id}/files/content?path=references/foo.md
PUT    /internal/apps/{app_id}/skills/{skill_id}/files/content?path=scripts/foo.py
DELETE /internal/apps/{app_id}/skills/{skill_id}/files?path=assets/foo.png
```

### 8.2 Suggested Frontend Types

```ts
type SkillPackageStatus = "valid" | "warnings" | "invalid" | "unknown";

type SkillListItem = {
  skill_id: number;
  name: string;
  display_name?: string | null;
  description: string;
  is_builtin: boolean;
  is_frozen: boolean;
  package_status: SkillPackageStatus;
  resource_counts: {
    scripts: number;
    references: number;
    assets: number;
    other: number;
  };
  bootstrap_script_path?: string | null;
  disable_model_invocation?: boolean;
  updated_at?: string | null;
};

type SkillPackageValidation = {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
};

type SkillFileSummary = {
  path: string;
  media_type?: string | null;
  size_bytes: number;
  checksum_sha256?: string | null;
  kind: "script" | "reference" | "asset" | "agent_metadata" | "other";
};

type SkillActivationEvent = {
  skill_name: string;
  source: "router" | "manual" | "retry";
  phases: {
    instructions?: "ok" | "skipped" | "failed";
    files?: "ok" | "skipped" | "failed";
    bootstrap?: "ok" | "skipped" | "failed";
  };
  message?: string;
};
```

### 8.3 Streaming Events

The frontend should support these event categories:

| Event | Purpose |
|---|---|
| `skill_route` | Router selected zero or more Skills and why. |
| `skill_activation` | File/bootstrap phase status for one Skill. |
| `code_output` | Structured stdout/stderr/status lines. |
| `sandbox_lifecycle` | Resume, renew, expiry recovery, recreation, destroy. |
| `sandbox_budget` | Execution budget or output budget status. |

Existing consumers should keep treating missing `stream` on `code_output` as stdout for backward
compatibility.

## 9. Permissions

| Capability | Viewer | Editor | Administrator |
|---|---:|---:|---:|
| List Skills | yes | yes | yes |
| View Skill detail | yes | yes | yes |
| Download/export Skill | yes | yes | yes |
| Create/import Skill | no | no | yes |
| Edit `SKILL.md` | no | no | yes |
| Upload/delete resources | no | no | yes |
| Delete Skill | no | no | yes |
| Configure sandbox provider | no | no | yes |
| Retry Skill activation in playground | no | yes, if agent access permits | yes |

Built-in or frozen Skills are read-only unless cloned into the app.

## 10. Migration Plan

### Phase 1 - Remove Misleading Fields

- Remove `runtime` selector from `SkillForm`.
- Remove pip dependencies input.
- Replace "prompt-driven specializations" copy with package-oriented copy.
- Update list badges from `prompt-only/sandbox` to package/resource status.

### Phase 2 - Package Import/Export

- Add import ZIP action.
- Add validation result modal.
- Add export action.
- Add package warnings to list/detail views.

### Phase 3 - Skill Detail and Resources

- Add detail drawer or page.
- Add `SKILL.md` editor.
- Add resource tree with text preview and binary metadata.
- Add bootstrap script selector.

### Phase 4 - Runtime Observability

- Add Skill activity panel in playground.
- Update code output panel for stdout/stderr/status.
- Add sandbox lifecycle events to tool history.
- Show execution/output budget status.

### Phase 5 - Polish and Guardrails

- Add empty states and validation hints.
- Add read-only states for built-in/frozen Skills.
- Add docs links or inline guidance for Agent Skills package structure.
- Add telemetry for import, validation, activation failure, and retry.

## 11. Testing Strategy

### Unit Tests

- Skills table renders package status and resource counts.
- Skill form does not render runtime or dependency inputs.
- Validation modal blocks import on errors and permits import on warnings.
- Resource tree rejects unsafe paths client-side before submit.
- Code output panel renders stdout, stderr, status, running, collapsed, and truncated states.

### Integration Tests

- Import a canonical Skill ZIP, inspect resources, export it, and verify root-relative paths.
- Import a legacy `files/<path>` ZIP and verify the UI shows normalized package paths.
- Edit `SKILL.md` metadata and body without dropping unknown frontmatter.
- Select an app sandbox provider and verify effective provider text.
- Stream a turn with Skill activation and code output events.

### Accessibility Tests

- All tabs and resource-tree actions are keyboard reachable.
- Status badges have text labels, not color-only meaning.
- Code output uses sufficient contrast for stdout/stderr/status.
- Import errors are announced in the modal.

## 12. Open Questions

| Question | Proposed answer for v2 UI |
|---|---|
| Modal or full page for Skill detail? | Use a full page or large drawer once resources are editable. A modal is acceptable only for the first simple metadata/body edit pass. |
| Should viewers export Skills? | Yes, if they can view the Skill. Export does not mutate state. |
| Should users see router reasons? | Yes in tool history/debug surfaces; keep the main chat compact. |
| Should activation retry be exposed? | Yes for failed file/bootstrap phases when the user has agent access and code interpreter is enabled. |
| Should the UI show raw `frontmatter`? | Yes in advanced mode. Default mode should expose common fields directly. |
| Should the Skill editor support dependency installation UI? | No. Requirements belong in `SKILL.md`; deterministic setup belongs in reviewed bootstrap scripts. |

## 13. Implementation Checklist

| Priority | Change | Files |
|---|---|---|
| P0 | Remove runtime/dependencies UI | `SkillForm.tsx`, `SkillsPage.tsx`, frontend types |
| P0 | Add package import/export API methods | `frontend/src/services/api.ts` |
| P1 | Add validation modal and import flow | `SkillsPage.tsx`, new Skill import components |
| P1 | Add package status/resource count columns | `SkillsPage.tsx`, `core/types.ts` |
| P1 | Add Skill detail view with `SKILL.md` tab | new settings component/page |
| P1 | Add resources tree and file preview | new Skill resource components |
| P2 | Add bootstrap selector | Skill detail resources/overview |
| P2 | Update app sandbox provider labels/status | `AppSettingsPage.tsx` |
| P2 | Add Skill activity panel | playground streaming components |
| P2 | Structure stdout/stderr/status output | `CodeExecutionPanel.tsx`, `useStreamingChat.ts` |
| P3 | Add sandbox lifecycle/debug drawer | playground tool history/runtime panel |
| P3 | Add e2e coverage for import, activation, and streaming states | frontend tests |

## 14. References

- Runtime RFC: [RFC v2: Sandbox Providers, Skills Runtime, and Lifecycle Recovery](rfc-sandbox-providers-v2.md)
- Previous sandbox RFC: [RFC: Sandbox Provider Integration](rfc-sandbox-providers.md)
- Current Skills settings page: `frontend/src/pages/settings/SkillsPage.tsx`
- Current Skill form: `frontend/src/components/forms/SkillForm.tsx`
- Current code output panel: `frontend/src/components/playground/CodeExecutionPanel.tsx`
- Skill package repository: `backend/repositories/skill_package_repository.py`
