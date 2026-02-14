# Export/Import Inconsistencies Report

> **Date**: 2026-02-12
> **Tested by**: Automated Playwright browser testing
> **Source app**: `test1` (app_id=2) — 5 agents, 1 repo, 3 domains,
> 5 silos, 8 AI services, 4 embedding services, 8 output parsers,
> 1 MCP config
> **Target app**: `test` (app_id=17), clean app (app_id=21)

---

## Summary

All 8 component types were tested for both export and import.
All exports work correctly. Import has several bugs and
behavioral inconsistencies across component types.

| Category | Count |
|----------|-------|
| **Bugs (code defects)** | 3 |
| **Behavioral inconsistencies** | 7 |

---

## Bugs (Code Defects)

### BUG-1: Repository/Domain Import — Missing `session.commit()`

**Status**: FIXED during this testing session

**Affected files**:
- `backend/services/repository_import_service.py`
- `backend/services/domain_import_service.py`

**Description**: Both new import services only called
`session.flush()` (sends SQL within the transaction) but never
called `session.commit()`. Since `SessionLocal` is configured
with `autocommit=False`, all imported data was silently rolled
back when the DB session closed.

**Symptoms**:
- Import returns 201 with success response and valid IDs
- Imported repositories/domains are NOT persisted to DB
- Subsequent GET returns 404
- Conflict detection (FAIL mode) never triggers because
  prior imports were rolled back

**Fix**: Replaced `flush()` with `commit()` in both override
and create paths, matching the pattern used by all existing
import services (`silo_import_service.py`,
`ai_service_import_service.py`, etc.).

---

### BUG-2: Agent Import — Wrong Schema Passed to MCP Config Import

**Status**: FIXED

**File**: `backend/services/agent_import_service.py`, line ~446

**Code**:
```python
# BROKEN: passes AgentExportFileSchema to import_mcp_config
mcp_import_result = self.mcp_import.import_mcp_config(
    export_data,    # <-- Full AgentExportFileSchema
    app_id,
    ConflictMode.RENAME,
)
```

**Expected**: Should wrap each MCP config in a
`MCPConfigExportFileSchema`:
```python
mcp_file = MCPConfigExportFileSchema(
    metadata=export_data.metadata,
    mcp_config=mcp_config,  # Individual item from loop
)
mcp_import_result = self.mcp_import.import_mcp_config(
    mcp_file, app_id, ConflictMode.RENAME,
)
```

**Root cause**: `import_mcp_config()` expects
`MCPConfigExportFileSchema` (with singular `mcp_config`
attribute) but receives `AgentExportFileSchema` (with plural
`mcp_configs` attribute).

**Error message**:
```
Failed to import MCP config: 'AgentExportFileSchema'
object has no attribute 'mcp_config'
```

**Impact**: When importing an agent individually, its bundled
MCP configs are silently skipped with a warning. The agent is
created but without MCP associations.

---

### BUG-3: Agent Import — Incomplete `ImportSummarySchema`

**Status**: FIXED

**File**: `backend/services/agent_import_service.py`,
lines ~560 and ~665

**Description**: The agent import returns `ImportSummarySchema`
without setting `component_id`, `mode`, or `created` fields:
```python
return ImportSummarySchema(
    component_type=ComponentType.AGENT,
    component_name=agent_name,
    warnings=warnings,
    # Missing: component_id, mode, created, next_steps
)
```

**Observed response**:
```json
{
  "component_type": "agent",
  "component_id": null,
  "component_name": "export-test (1)",
  "mode": null,
  "created": false,
  "warnings": ["Failed to import MCP config: ..."]
}
```

**Expected**: Should populate all fields like other services:
```json
{
  "component_id": 42,
  "mode": "rename",
  "created": true
}
```

**All other import services** (silo, AI service, embedding,
output parser, repository, domain) correctly set these fields.

---

## Behavioral Inconsistencies

### INC-1: FAIL Mode Returns HTTP 409 Conflict

**Affected**: All import services

**Status**: FIXED — All import routers now return
HTTP 409 Conflict when `conflict_mode=fail` detects
a name conflict.

---

### INC-2: All Import Endpoints Now Return HTTP 201

**Status**: FIXED — Full app import endpoint now also returns
HTTP 201 Created, consistent with individual imports.

---

### INC-3: Full App Import Creates New App vs Individual Imports Target Existing App

**URL structure**:
- Full app import: `POST /internal/apps/import` (no app_id,
  always creates a new app)
- Individual imports: `POST /internal/apps/{app_id}/{type}/import`
  (targets existing app)

**Inconsistency**: Full app import cannot target an existing
app. Individual imports cannot create a new app. There is no
way to do a "full app import into existing app".

**Note**: This may be by design, but should be documented.

---

### INC-4: Response Now Includes `conflict_detected` Field

**Status**: FIXED — Added `conflict_detected: bool` field to
`ImportSummarySchema`. Set to `true` only when an existing
resource with the same name was found during import.
The `mode` field still shows the requested mode, but
`conflict_detected` clarifies whether a conflict actually
occurred.

---

### INC-5: Agent Export Schema Significantly More Complex

**Key counts by export type**:

| Component | Export Keys |
|-----------|------------|
| AI Service | 2 (metadata, ai_service) |
| Embedding | 2 (metadata, embedding_service) |
| Output Parser | 2 (metadata, output_parser) |
| MCP Config | 2 (metadata, mcp_config) |
| Silo | 4 (+ embedding_service, output_parser) |
| Repository | 5 (+ silo, embedding_service, output_parser) |
| Domain | 5 (+ silo, embedding_service, output_parser) |
| **Agent** | **9** (+ ai_service, silo, silo_embedding_service, silo_output_parser, output_parser, mcp_configs, agent_tools) |

Agent exports bundle significantly more dependencies. This is
necessary for self-contained imports but increases complexity
and file size.

---

### INC-6: Bundled Silo Now Respects Outer `conflict_mode`

**Status**: FIXED — `_resolve_silo()` in both
`repository_import_service.py` and `domain_import_service.py`
now accepts and propagates the outer `conflict_mode`
parameter to bundled silo imports.

---

### INC-7: MCP Config Auth Token Warning Now Conditional

**Status**: FIXED — The warning "Authentication tokens must
be reconfigured" is now only shown when the MCP config's
JSON contains authentication-related keys (e.g., `auth_type`,
`api_key`, `token`, `credentials`).

---

## Test Results Summary

### Individual Exports (All Pass ✅)

| Component | Status | Keys |
|-----------|--------|------|
| AI Service | 200 ✅ | metadata, ai_service |
| Embedding Service | 200 ✅ | metadata, embedding_service |
| Output Parser | 200 ✅ | metadata, output_parser |
| MCP Config | 200 ✅ | metadata, mcp_config |
| Silo | 200 ✅ | metadata, silo, embedding, parser |
| Repository | 200 ✅ | metadata, repository, silo, emb, parser |
| Domain | 200 ✅ | metadata, domain, silo, emb, parser |
| Agent | 200 ✅ | metadata, agent + 7 dependency keys |

### Individual Imports — RENAME Mode (All Pass ✅)

| Component | Status | Notes |
|-----------|--------|-------|
| AI Service | 201 ✅ | Renamed with date suffix |
| Embedding Service | 201 ✅ | Renamed with date suffix |
| Output Parser | 201 ✅ | Renamed with date suffix |
| MCP Config | 201 ✅ | Auth token warning |
| Silo | 201 ✅ | Renamed with date suffix |
| Repository | 201 ✅ | Created with bundled silo |
| Domain | 201 ✅ | Created with 1 URL (pending) |
| Agent | 201 ⚠️ | MCP import fails (BUG-2), incomplete response (BUG-3) |

### Conflict Modes — FAIL Mode

| Component | Status | Notes |
|-----------|--------|-------|
| Silo | 400 ✅ | Correctly blocks |
| AI Service | 400 ✅ | Correctly blocks |
| Repository | 400 ✅ | Correctly blocks (after BUG-1 fix) |
| Domain | 400 ✅ | Correctly blocks (after BUG-1 fix) |

### Conflict Modes — OVERRIDE Mode

| Component | Status | Notes |
|-----------|--------|-------|
| Silo | 201 ✅ | `created: false`, updated in-place |
| Repository | 201 ✅ | `created: false`, updated in-place |
| Domain | 201 ✅ | `created: false`, updated in-place |

### Full App Import

| Test | Status | Notes |
|------|--------|-------|
| Export app (10 keys) | 200 ✅ | All components included |
| Import → new app | 200 ✅ | 35 components, 0.84s |
| Verify imported app | ✅ | All counts match source |

---

## Recommendations

1. ~~**Fix BUG-2**~~ ✅ DONE
2. ~~**Fix BUG-3**~~ ✅ DONE
3. ~~**Standardize HTTP status codes**~~ ✅ DONE — 409 for conflicts
4. ~~**Add `conflict_detected` field**~~ ✅ DONE
5. ~~**Propagate conflict_mode**~~ ✅ DONE
6. ~~**Conditional auth token warning**~~ ✅ DONE
