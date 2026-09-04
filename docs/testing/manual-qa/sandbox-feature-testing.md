# Manual QA — Sandbox (Code Interpreter) Feature

This is a manual test plan for the `feature/sandbox-v2-core` branch: the new
Sandbox subsystem (agents run LLM-directed code in OpenSandbox/E2B/Daytona),
plus the security/reliability fixes applied on top of it during review.

It has two parts:

1. **New feature test cases** — the Sandbox subsystem itself.
2. **Regression test cases** — previously-existing features whose code paths
   were touched by this branch, even if you're not touching the sandbox at
   all (conversation handling, memory, agent chat, file downloads, the
   generic Service UI/API).

An importable app fixture ([`sandbox-qa-app-export.json`](./sandbox-qa-app-export.json))
is included so you don't have to hand-build test agents — see **Step 0**.

Automated coverage for everything below already exists and passes
(`1606 unit + 13 integration tests` at the time of writing) — this manual
plan is for the things that genuinely need a human and/or live infra: Docker
networking, real provider accounts, and "does this feel right in the UI."

---

## Step 0 — Import the test app

The fixture creates a new App called **"Sandbox QA Test App"** with one
AI Service and four agents pre-wired to it, so you can start testing
immediately instead of configuring agents by hand.

1. Log in, go to the **Apps** (workspaces) list page.
2. Click **Import App**.
3. Upload `sandbox-qa-app-export.json`.
4. On the API-keys step, set a real key for **"QA OpenAI Service"** (or skip
   and add it later in **App Settings → AI Services** — the agents won't be
   usable until it's set).
5. Confirm the import. You should land on a new App with:

   | Agent | `has_memory` | Purpose |
   |---|---|---|
   | `QA - Memory Chat` | true | Regression baseline (memory/summarization) |
   | `QA - Stateless Chat` | false | Regression target for the conversation-ownership fix |
   | `QA - Sandbox Code Interpreter` | false | Primary sandbox feature agent |
   | `QA - Sandbox + Memory` | true | Sandbox + memory interaction |

> **Why isn't Code Interpreter already enabled on import?** The app-export
> format (`ExportAgentSchema`) doesn't carry `enable_code_interpreter` or
> `sandbox_service_id` yet — that's a real, pre-existing gap in the
> export/import feature (confirmed by reading `backend/schemas/export_schemas.py`;
> `SandboxService` itself has no export/import implementation at all yet —
> both of its import/export endpoints return `501 Not Implemented`). You'll
> enable it by hand in Step 2 below. If this friction is worth fixing, it's a
> good follow-up ticket: add `enable_code_interpreter`/`sandbox_service_name`
> to `ExportAgentSchema` and implement `SandboxServiceExportFileSchema`.

## Step 1 — Environment setup

1. In `docker/.env`, explicitly set `SANDBOX_DEFAULT_PROVIDER=opensandbox`
   (don't rely on the old compose default — it was broken and has since been
   fixed, but double-check your `.env` doesn't override it back to
   `subprocess`).
2. Bring up the base stack **and** the sandbox profile:
   ```bash
   cd docker
   docker compose --profile opensandbox up -d --build
   ```
   Plain `docker compose up` will **not** start the `opensandbox` /
   `mattin-code-interpreter` services.
3. Confirm it's healthy: `docker compose logs opensandbox` (no port is
   published to the host — it's internal-only).
4. Optional, only if testing the cloud providers: an E2B key
   (e2b.dev/dashboard) and/or a Daytona key (app.daytona.io) — both need a
   real external account.

## Step 2 — Configure a Sandbox Service and attach it

1. As an app ADMINISTRATOR+, go to **App Settings → Sandbox Services**.
2. Create an **OpenSandbox** service (base URL `opensandbox:8080`, no API
   key needed for local/insecure-mode testing). Click **Test Connection** —
   it should succeed.
   - If it fails with `"Invalid or disallowed endpoint"`: this is the new
     SSRF guard working as intended for a self-hosted internal hostname.
     Set `SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE=true` in `docker/.env` and
     restart the backend (see `docker/.env.example` for the explanation of
     this trade-off), then retry.
3. Open `QA - Sandbox Code Interpreter` and `QA - Sandbox + Memory` in the
   Agent form, check **Code Interpreter**, and pick the Sandbox Service you
   just created (or leave it on "Use app/system default" and instead set
   **App Settings → Code Interpreter Sandbox Service** to it once — either
   path is worth testing).

---

## Part A — New feature test cases (Sandbox)

### A1. Runtime code-execution flow

Using `QA - Sandbox Code Interpreter` in the playground:

- [ ] Ask it to compute something ("compute the 20th Fibonacci number in
      Python"). Confirm: the Active Tool Bar shows a running → complete
      pill, the Tool History panel streams stdout live, the final answer is
      correct.
- [ ] Ask it to write a file to `output/` (e.g. "write a CSV of the sequence
      to output/fib.csv"). Confirm it appears in the Attached Files panel
      with a "Generated" badge and downloads correctly.
- [ ] Upload a file, ask it to read/process it. Confirm it round-trips via
      `input/`.
- [ ] Ask it to run 6+ separate code executions in one turn. Confirm you see
      `"[Execution budget exceeded: 5 executions per turn]"` rather than a
      crash.
- [ ] Trigger a `Bash`/`Read`/`Write` builtin tool (ask it to "list files in
      the sandbox" or "read /workspace/input"), not just the Python REPL —
      these are the tools that previously had no expiry-recovery handling.
- [ ] Leave a conversation idle past the idle timeout
      (`SANDBOX_IDLE_TIMEOUT_S`, default 120s), then send another code-exec
      message. Confirm you get a clean "session expired and was reset"
      message and a fresh sandbox — not a raw error.
- [ ] Repeat the core round-trip against E2B/Daytona if you have credentials,
      to confirm parity across providers.

### A2. Sandbox + memory interaction

Using `QA - Sandbox + Memory`:

- [ ] Run code in one turn, then in a later turn (same conversation) ask it
      to reference something from the earlier code output. Confirm memory
      and sandbox state both persist correctly within one conversation.
- [ ] Reset the conversation (trash/reset button). Confirm the sandbox is
      torn down and a fresh one is created on the next code-exec message.

### A3. Cross-tenant / IDOR check (Critical fix — confirm it holds)

- [ ] As an EDITOR/ADMINISTRATOR of this app, try (via the API directly,
      since the UI dropdown only lists your own + system services) to set
      an agent's `sandbox_service_id` to an id belonging to a **different**
      App's Sandbox Service. This must now be **rejected with a 400/422**
      (previously it silently succeeded and ran that agent's code through
      the other tenant's credentials).

### A4. Session-hijack check (High fix — confirm it holds)

Using `QA - Stateless Chat` (a `has_memory=false` agent — this is exactly
where the bug lived):

- [ ] Create a conversation as User A (or via one API key), note its
      `conversation_id`.
- [ ] As User B (a different user/API key on the same or a different app),
      try to send a chat message using User A's `conversation_id`. This must
      now return **404 "Conversation not found or access denied"**, not
      silently proceed.
- [ ] Repeat via the **public reset endpoint**:
      `POST /public/v1/app/{app_id}/chat/{agent_id}/reset?conversation_id=<foreign_id>`
      with `X-API-KEY` header auth. This must also 404, and must NOT destroy
      the other user's live sandbox as a side effect (this was a second,
      related gap fixed in the same area — the sandbox was previously torn
      down *before* the ownership check ran, so even the request that got
      rejected still had already destroyed someone else's session). Note:
      the **internal playground's** reset button doesn't accept a
      client-supplied `conversation_id` at all (it resets your own current
      session), so this specific check needs the public API — an API key
      for the app under test (create one in **App Settings → API Keys**).

### A5. Sandbox Service configuration & SSRF checks

- [ ] Try to save a Sandbox Service with `base_url` pointing at an obviously
      internal target (e.g. `postgres:5432`, `169.254.169.254`). This must
      be rejected at **save time**, not just when clicking "Test
      Connection" (this was a gap: the endpoint was previously only
      validated on the optional diagnostic probe, not on save).
- [ ] Configure `SANDBOX_ALLOWED_PROVIDERS=opensandbox` in `.env` (restart
      backend), then try to create a Sandbox Service with
      `provider=daytona`. Must be rejected — both at save time and via the
      "Test Connection" probe.
- [ ] Delete a Sandbox Service that's referenced by an agent's
      `sandbox_service_id` or an App's default. Confirm the FK
      `ON DELETE SET NULL` behaves — the agent/app should fall back to the
      next resolution step, not error.

### A6. Concurrency / capacity (best-effort — hard to fully exercise manually)

- [ ] If you can script it: fire several concurrent chat requests for
      **different** conversations with code-interpreter agents, more than
      `SANDBOX_MAX_CONCURRENT_SESSIONS` (default 50 — lower it via env var
      for this test, e.g. to 2). Confirm the excess requests get a clean
      "Maximum concurrent sandbox sessions reached" error rather than all
      succeeding (this was a real race: the cap could previously be
      overshot by concurrent requests for different conversations, not just
      the same one).

### A7. Graceful degradation

- [ ] Temporarily set `SANDBOX_DEFAULT_PROVIDER` to an invalid value (e.g.
      `bogus`) with no agent/app-level Sandbox Service configured, restart
      the backend, and chat with a code-interpreter-enabled agent. Confirm
      the chat still completes (the LLM responds normally, just without
      code execution) instead of a hard 500.

---

## Part B — Regression test cases (previously-existing features)

These exercise code paths touched by this branch's changes even though
they're not "the sandbox feature" — the most important ones are the general
chat path (`agent_execution_service.py` had the largest diff in the whole
PR) and anything using `conversation_id`.

### B1. General agent chat (no sandbox at all)

Using `QA - Memory Chat`:

- [ ] Send several messages in one conversation. Confirm normal multi-turn
      behavior, correct responses, no regressions from the sandbox wiring
      added to this same code path.
- [ ] Have a long enough conversation to trigger summarization
      (`memory_summarize_threshold`). Confirm it still summarizes correctly.
- [ ] Reset the conversation. Confirm messages/session clear and a new
      conversation starts cleanly.
- [ ] Confirm conversation history loads correctly when reopening an
      existing conversation.

### B2. Memory-less agent chat (no sandbox)

Using `QA - Stateless Chat` with `enable_code_interpreter` left **off**:

- [ ] Send a message with no `conversation_id`. Confirm it works exactly as
      before (this is the common case for public/marketplace embeds).
- [ ] Send a message with a `conversation_id` you legitimately created via
      the dedicated "create conversation" endpoint for this agent (if your
      client does this — e.g. file-grouping use cases). Confirm it's
      accepted normally (the ownership fix must not have broken the
      legitimate case, only the unvalidated-foreign-id case tested in A4).

### B3. File attachments and the download-URL tool

- [ ] Attach a file to a chat message and confirm it processes normally
      (upload status, extraction, "Ready" pill) — unrelated to the sandbox,
      but `AttachedFilesPanel.tsx`/file handling were touched by the
      broader streaming UI changes in this branch.
- [ ] Ask any agent (sandbox or not) to fetch a normal public URL via the
      `download_url_to_workspace` tool (e.g. "download
      https://example.com/some-file.pdf to output/"). Confirm it still
      works — this tool's SSRF hardening must not have broken legitimate
      downloads.
- [ ] Ask it to fetch an obviously bad target (`file:///etc/hostname`, or an
      internal-looking URL). Confirm it's rejected with a clean
      `[Error] ...` message, not a raw exception.

### B4. Sandbox Services page vs. AI/Embedding Services pages

The generic "Service" UI/API was extended with a `sandbox` `ServiceKind` —
confirm the existing kinds weren't disturbed:

- [ ] Create/edit/delete an **AI Service** and an **Embedding Service**
      normally. Confirm the wizard, masked-key handling, and test-connection
      flow behave exactly as before.
- [ ] Confirm the **Sandbox Services** list/detail/wizard don't leak into or
      break the AI/Embedding Services pages (separate list, separate
      wizard steps).

### B5. Provider-side "Code Interpreter" (the *other* toggle — don't confuse it)

On an OpenAI/Anthropic/Azure-backed agent, there's a second, unrelated
"Provider-side Tools → Code Interpreter" toggle that runs on the LLM
provider's own infrastructure and has nothing to do with this Sandbox
feature:

- [ ] Enable it (with Sandbox's own "Code Interpreter" checkbox left off)
      and confirm it still works via the provider's native tool-calling —
      this must be unaffected by anything in this branch.

### B6. Migration rollback

- [ ] `alembic downgrade -1` from the sandbox migration
      (`sandbox001_add_sandbox_provider_and_conversation_state`), confirm it
      cleanly drops the new columns/table in reverse order, then
      `alembic upgrade head` again to confirm re-applying works cleanly.

### B7. Automated suite (sanity check before/after manual testing)

```bash
# Unit tests — no DB needed
poetry run python -m pytest tests/unit/ -q

# Sandbox-specific integration tests — needs the test DB running
docker compose -f docker/docker-compose.yaml --profile test up -d db_test
poetry run python -m pytest tests/integration/sandbox/ -v
```

Both should be fully green (1606 unit / 13 sandbox-integration passing as of
this writing). If either regresses while you're testing, treat it as a
signal something in your environment/config diverged from the fixture
assumptions above, not just a flaky test.

---

## Known residual risk (don't expect these to be airtight)

- **OpenSandbox server has no API key** by default — network isolation
  (sandboxes can no longer reach `backend`/`postgres`/`qdrant`) is the
  primary defense instead. Wiring a real `server.api_key` needs a
  Dockerfile change that wasn't safe to make blind without a live
  OpenSandbox instance to validate against.
- **DNS rebinding** on the SSRF guards (test-connection, save-time endpoint
  check, `download_url_to_workspace`): validation resolves a hostname once,
  then the actual connection resolves it again — a small window for a
  malicious DNS server to switch answers between the two. Loopback,
  RFC1918, link-local, CGNAT (100.64.0.0/10), reserved, and multicast
  ranges are all blocked; full protection would need pinning the validated
  IP at connect time.
- **Two broader, pre-existing IDORs unrelated to the sandbox feature
  itself** were found during review and are **not** fixed by this branch:
  `POST /internal/apps/{app_id}/agents/{agent_id}` doesn't scope the agent
  lookup by `app_id` (a cross-app agent takeover), and an agent's
  `service_id`/`silo_id`/`output_parser_id`/`mcp_config_ids`/`tool_ids`
  have no ownership validation at all (only `sandbox_service_id` got fixed
  in this branch). Worth a dedicated follow-up.
- **Unrelated pre-existing bug found while building this fixture**: the
  full-app import service (`agent_import_service.py`) passes
  `prompt_template` straight from the export file into the new `Agent` row
  with no fallback. Every agent created through the normal UI always has
  `prompt_template = "{question}"` (hardcoded default in
  `AgentFormPage.tsx`) — `build_human_message()` in `agentTools.py` does
  `agent.prompt_template.format(question=message)`, and if the template is
  empty/None, the user's actual message is silently dropped and the LLM
  receives an empty `HumanMessage` (symptom: the model replies something
  like "it seems your message didn't come through"). This fixture's
  `prompt_template` fields are set to `"{question}"` for exactly this
  reason — if you hand-build your own import JSON, don't set it to `null`.
