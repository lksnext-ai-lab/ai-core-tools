# Step 001: Implement missing public silo API behaviors and delete-all service method

> **Target Agent**: @backend-expert
> **Status**: pending
> **FR**: FR-1, FR-2, FR-3
> **AC**: AC-1, AC-2, AC-3, AC-4, AC-9, AC-10
> **Depends On**: none

## Task

Implement the missing logic for stubbed public silo endpoints and add the required service method for collection-wide deletion.

Scope is limited to:
- `backend/services/silo_service.py`
- `backend/routers/public/v1/silos.py`
- any directly required vector-store interface/implementation files only if needed to support delete-all behavior through existing abstractions.

Required changes:
1. In `SiloService`, add `delete_all_docs_in_collection(silo_id, db)` that clears all documents for the silo collection and follows existing error handling/logging style used by other `SiloService` methods.
2. In public silo router, implement:
   - `GET /{app_id}/silos/{silo_id}/docs` using `SiloService.count_docs_in_silo()`
   - `POST /{app_id}/silos/{silo_id}/docs/multiple-index` using `SiloService.index_multiple_content()`
   - `DELETE /{app_id}/silos/{silo_id}/docs/delete/all` using the new `SiloService.delete_all_docs_in_collection()`
3. Preserve existing endpoint signatures and response schemas; delete-all must keep `MessageResponseSchema` response contract.
4. Remove related TODO comments for these public stub endpoints once logic is implemented.
5. Keep auth behavior unchanged (public API key auth still enforced).

## Context

From plan `silo-api-completion`:
- Current public endpoints return success without doing work.
- Plan requires backward compatibility and no API contract changes.
- Empty collection behavior must be safe (`count=0`, delete-all no-op success).
- Existing abstraction should be reused (no direct vector DB coupling in router).

## Expected Outcome

- Public endpoints execute real operations instead of stubs.
- `SiloService.delete_all_docs_in_collection` exists and is used by router.
- TODO comments for the three public stubs are removed.
- Changes are minimal, focused, and consistent with existing backend conventions.

---

## Result

- Status: done
- Summary of what changed: Added `SiloService.delete_all_docs_in_collection(silo_id, db)` to clear a silo collection through existing vector-store abstraction, and implemented real logic in public silo endpoints for docs count, multiple-index, and delete-all using `SiloService` methods. Removed the related TODO stubs from the public router while preserving auth behavior and response contracts.
- Files changed:
   - `backend/services/silo_service.py`
   - `backend/routers/public/v1/silos.py`
   - `plans/silo-api-completion/execution/step_001.md`
- Notes about validation/build checks run (if any): Not run in this step.
