# Step 002: Add reusable ownership validation and apply to internal silo endpoints

> **Target Agent**: @backend-expert
> **Status**: pending
> **FR**: FR-4, FR-5, FR-6
> **AC**: AC-5, AC-6, AC-7, AC-8, AC-10
> **Depends On**: step_001

## Task

Implement app ownership validation hardening in internal silo router by introducing and applying a reusable helper.

Scope is limited to:
- `backend/routers/internal/silos.py`
- only supporting files if strictly required by imports/types.

Required changes:
1. Add helper `_validate_silo_app_ownership(silo_id: int, app_id: int, db: Session) -> Silo` at module scope.
2. Helper behavior must be:
   - fetch silo by `silo_id`
   - raise `HTTPException(status_code=404, ...)` if not found
   - if `silo.app_id != app_id`, log warning-level security event and raise `HTTPException(status_code=403, detail="Silo does not belong to this app")`
   - return silo on success
3. Apply validation behavior in these internal endpoints:
   - `GET /` (`list_silos`) app-level access validation consistent with existing auth/decorator model
   - `GET /{silo_id}`
   - `POST /{silo_id}` (update path; keep create behavior compatible, including any `silo_id=0` convention)
   - `DELETE /{silo_id}`
   - `GET /{silo_id}/playground`
   - `POST /{silo_id}/search`
4. Remove all `# TODO: Add app access validation` comments in internal router after implementation.
5. Keep current role-based auth and endpoint contracts unchanged.

## Context

From plan `silo-api-completion`:
- `delete_silo_documents` already contains the target validation pattern and can be reused as reference style.
- Security requirement mandates consistent 404/403 behavior and warning logs for forbidden cross-app access.
- No endpoint signature changes are allowed.

## Expected Outcome

- Reusable helper exists and is used where needed.
- Internal endpoints enforce app/silo ownership constraints and return consistent 403/404 outcomes.
- All related TODO comments in internal router are removed.

---

## Result

- Status: done
- Summary of what changed: Added `_validate_silo_app_ownership(silo_id, app_id, db) -> Silo` in the internal silos router, enforcing consistent `404` for missing silo and `403` with warning-level security logging for cross-app access. Applied ownership validation to `GET /`, `GET /{silo_id}` (except `silo_id=0`), `POST /{silo_id}` update path (`silo_id != 0`), `DELETE /{silo_id}`, `GET /{silo_id}/playground`, and `POST /{silo_id}/search`. Removed all `# TODO: Add app access validation` comments from the internal silos router.
- Files changed:
   - `backend/routers/internal/silos.py`
   - `plans/silo-api-completion/execution/step_002.md`
- Notes about validation/build checks run (if any): Ran targeted checks with workspace diagnostics (`get_errors`) and a text search confirming no remaining `# TODO: Add app access validation` comments in the updated router.
