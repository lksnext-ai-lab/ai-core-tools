# Implementation Plan: System Embedding Services

**Spec**: develop/features/system-embedding-services/spec.md
**Created**: 2026-03-26
**Status**: pending

---

## Overview

This feature makes `EmbeddingService.app_id` nullable (mirroring the existing `AIService` pattern) and wires up the full stack: Alembic migration, model change, repository method, service helper, admin CRUD endpoints, silo form enrichment, and a new frontend admin page with deletion impact check.

The reference implementation to follow throughout is:
- Backend: `admin.py` endpoints `list/create/update/delete_system_ai_service`, `AIServiceService._to_list_item`, `AIServiceRepository.get_system_services`
- Frontend: `SystemAIServicesPage.tsx`, `api.ts` system AI service methods

---

## Steps

### Step 01 — Add Alembic migration to make `embedding_service.app_id` nullable

- **Layer**: database
- **Files**:
  - `alembic/versions/saas003_system_embedding_services.py` — create
- **What**: Create a new Alembic revision with:
  - `revision = 'saas003'`
  - `down_revision = 'saas002'`
  - `branch_labels = None`
  - `depends_on = None`
  - **upgrade**: Call `op.alter_column('embedding_service', 'app_id', existing_type=sa.Integer(), nullable=True)`. No data migration needed — all existing rows already have an `app_id`.
  - **downgrade**: Before restoring `NOT NULL`, check whether any rows have `app_id IS NULL`. Use an inline SQL check: if the count is > 0, raise an `Exception` with a clear message ("Cannot downgrade: system embedding services exist with app_id IS NULL. Delete them first."). Then call `op.alter_column('embedding_service', 'app_id', existing_type=sa.Integer(), nullable=False)`.
  - Follow the exact header format and comment style of `saas002_system_ai_services_refactor.py`.
- **Acceptance**: `alembic upgrade head` succeeds on a fresh dev DB. `alembic downgrade -1` succeeds when no `app_id IS NULL` rows exist; raises a clear Python exception when they do.
- **Status**: [x]

---

### Step 02 — Make `EmbeddingService.app_id` nullable in the SQLAlchemy model

- **Layer**: model
- **Files**:
  - `backend/models/embedding_service.py` — modify
- **What**: Change line 17 from `nullable=False` to `nullable=True` and add an inline comment identical to the `AIService` model:
  ```python
  app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform service
  ```
  No other changes to this file.
- **Acceptance**: `python -c "from models.embedding_service import EmbeddingService; print(EmbeddingService.__table__.c.app_id.nullable)"` prints `True`.
- **Status**: [x]

---

### Step 03 — Add `is_system` field to `EmbeddingServiceListItemSchema` and new `EmbeddingServiceOptionSchema`

- **Layer**: model (Pydantic schemas)
- **Files**:
  - `backend/schemas/embedding_service_schemas.py` — modify
- **What**: Two changes:
  1. Add `is_system: bool = False` field to `EmbeddingServiceListItemSchema` (after `needs_api_key`), mirroring `AIServiceListItemSchema`.
  2. Add a new schema class at the bottom of the file:
     ```python
     class EmbeddingServiceOptionSchema(BaseModel):
         """Lightweight schema for embedding service dropdown options (includes is_system flag)."""
         service_id: int
         name: str
         provider: Optional[str] = None
         is_system: bool = False

         model_config = ConfigDict(from_attributes=True)
     ```
  `EmbeddingServiceOptionSchema` will be used in `SiloDetailSchema` to replace the current untyped `Dict[str, Any]` for the `embedding_services` list.
- **Acceptance**: `python -c "from schemas.embedding_service_schemas import EmbeddingServiceListItemSchema, EmbeddingServiceOptionSchema; print(EmbeddingServiceListItemSchema.model_fields)"` shows `is_system` field.
- **Status**: [x]

---

### Step 04 — Update `SiloDetailSchema` to use `EmbeddingServiceOptionSchema`

- **Layer**: model (Pydantic schemas)
- **Files**:
  - `backend/schemas/silo_schemas.py` — modify
- **What**: Change the type of the `embedding_services` field in `SiloDetailSchema` from `List[Dict[str, Any]]` to `List[EmbeddingServiceOptionSchema]`. Add the import at the top of the file:
  ```python
  from schemas.embedding_service_schemas import EmbeddingServiceOptionSchema
  ```
  The field declaration becomes:
  ```python
  embedding_services: List[EmbeddingServiceOptionSchema]
  ```
  No other changes to this file.
- **Acceptance**: `python -c "from schemas.silo_schemas import SiloDetailSchema; import inspect; print(SiloDetailSchema.model_fields['embedding_services'])"` shows `EmbeddingServiceOptionSchema` as the item type.
- **Status**: [x]

---

### Step 05 — Add `get_system_services` to `EmbeddingServiceRepository`

- **Layer**: repository
- **Files**:
  - `backend/repositories/embedding_service_repository.py` — modify
- **What**: Add one new static method after `get_all`, mirroring `AIServiceRepository.get_system_services`:
  ```python
  @staticmethod
  def get_system_services(db: Session) -> List[EmbeddingService]:
      """Return all EmbeddingService records with app_id IS NULL (system/platform services)."""
      return db.query(EmbeddingService).filter(EmbeddingService.app_id.is_(None)).all()
  ```
  No other changes to this file.
- **Acceptance**: The method can be imported and called against the test DB without error.
- **Status**: [x]

---

### Step 06 — Add `_to_list_item` helper to `EmbeddingServiceService`

- **Layer**: service
- **Files**:
  - `backend/services/embedding_service_service.py` — modify
- **What**: Add a new static method `_to_list_item` at the top of the class (before `get_embedding_services_list`), mirroring `AIServiceService._to_list_item`. It converts an `EmbeddingService` ORM instance to an `EmbeddingServiceListItemSchema`:
  ```python
  @staticmethod
  def _to_list_item(service: "EmbeddingService", is_system: bool = False) -> EmbeddingServiceListItemSchema:
      """Convert an EmbeddingService ORM instance to a list item schema."""
      needs_api_key = (
          not service.api_key
          or service.api_key == PLACEHOLDER_API_KEY
      )
      return EmbeddingServiceListItemSchema(
          service_id=service.service_id,
          name=service.name,
          provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
          model_name=service.description or "",
          created_at=service.create_date,
          needs_api_key=needs_api_key,
          is_system=is_system,
      )
  ```
  Also update `get_embedding_services_list` to use `_to_list_item` instead of the inline dict construction (refactor only — no behavior change for app-scoped services, `is_system=False`).
- **Acceptance**: `EmbeddingServiceService._to_list_item` exists and the existing `get_embedding_services_list` still returns the same schema type.
- **Status**: [x]

---

### Step 07 — Include system embedding services in silo form data

- **Layer**: repository + service
- **Files**:
  - `backend/repositories/silo_repository.py` — modify
  - `backend/services/silo_service.py` — modify
- **What**:
  **In `silo_repository.py`**: In `get_form_data_for_silo`, after fetching `embedding_services = SiloRepository.get_embedding_services_by_app_id(app_id, db)`, also fetch system services:
  ```python
  from repositories.embedding_service_repository import EmbeddingServiceRepository  # already imported via get_embedding_services_by_app_id
  system_embedding_services = EmbeddingServiceRepository.get_system_services(db)
  ```
  Return a new key in the dict:
  ```python
  return {
      'output_parsers': output_parsers,
      'silo': silo,
      'embedding_services': embedding_services,
      'system_embedding_services': system_embedding_services,
  }
  ```

  **In `silo_service.py`**, in `get_silo_detail`, replace the current line that builds `embedding_services`:
  ```python
  # OLD (line ~1151):
  embedding_services = [{"service_id": s.service_id, "name": s.name} for s in form_data['embedding_services']]

  # NEW:
  from schemas.embedding_service_schemas import EmbeddingServiceOptionSchema
  embedding_services = (
      [EmbeddingServiceOptionSchema(service_id=s.service_id, name=s.name, provider=s.provider.value if hasattr(s.provider, 'value') else s.provider, is_system=False) for s in form_data['embedding_services']]
      + [EmbeddingServiceOptionSchema(service_id=s.service_id, name=s.name, provider=s.provider.value if hasattr(s.provider, 'value') else s.provider, is_system=True) for s in form_data.get('system_embedding_services', [])]
  )
  ```
  The new silo path (`silo_id == 0`) also returns `embedding_services=[]` — leave that unchanged for now (it fetches services separately in `loadFormData()` on the frontend via `getEmbeddingServices`; that path is handled in Step 08 below by modifying the `get_embedding_services_list` endpoint instead).

  **Note**: `EmbeddingServicesPage` calls `apiService.getEmbeddingServices(appId)` which hits the existing `GET /internal/apps/{app_id}/settings/embedding-services` endpoint. That endpoint calls `EmbeddingServiceService.get_embedding_services_list` which only returns app-scoped services. The `SiloForm` also calls `apiService.getEmbeddingServices`. These two paths must be kept consistent — both must include system services. The existing embedding services list endpoint must also be updated (see Step 08).
- **Acceptance**: `GET /internal/apps/{app_id}/silos/{silo_id}` response's `embedding_services` array contains both app-scoped (no `is_system`) and system services (with `is_system: true`).
- **Status**: [x]

---

### Step 08 — Update `EmbeddingServiceService.get_embedding_services_list` to include system services

- **Layer**: service
- **Files**:
  - `backend/services/embedding_service_service.py` — modify
- **What**: Update `get_embedding_services_list` to also fetch and append system services, mirroring the identical pattern in `AIServiceService.get_ai_services_by_app_id`:
  ```python
  @staticmethod
  def get_embedding_services_list(db: Session, app_id: int) -> List[EmbeddingServiceListItemSchema]:
      """Get list of embedding services for an app, plus platform-level system services."""
      app_services = EmbeddingServiceRepository.get_by_app_id(db, app_id)
      system_services = EmbeddingServiceRepository.get_system_services(db)

      result = [EmbeddingServiceService._to_list_item(svc, is_system=False) for svc in app_services]
      result += [EmbeddingServiceService._to_list_item(svc, is_system=True) for svc in system_services]
      return result
  ```
  This is the method called by `GET /internal/apps/{app_id}/settings/embedding-services` (used by both `EmbeddingServicesPage` and `SiloForm.loadFormData()`). After this change, system services will appear in both places. The `EmbeddingServicesPage` must show system services as read-only (handled in Step 15).
- **Acceptance**: `GET /internal/apps/{app_id}/settings/embedding-services` returns both app-scoped and system embedding services, each with an `is_system` flag.
- **Status**: [x]

---

### Step 09 — Add admin schemas for system embedding service impact response

- **Layer**: model (Pydantic schemas)
- **Files**:
  - `backend/schemas/embedding_service_schemas.py` — modify
- **What**: Add two new schema classes at the bottom of the file:
  ```python
  class AffectedSiloSchema(BaseModel):
      """A silo affected by deletion of a system embedding service."""
      silo_id: int
      silo_name: str
      app_id: int
      app_name: str

  class SystemEmbeddingServiceImpactSchema(BaseModel):
      """Response schema for system embedding service deletion impact check."""
      service_id: int
      service_name: str
      affected_silos_count: int
      affected_apps_count: int
      affected_silos: List[AffectedSiloSchema]
  ```
- **Acceptance**: The classes can be imported from `schemas.embedding_service_schemas` without error.
- **Status**: [x]

---

### Step 10 — Add system embedding service admin CRUD endpoints to `admin.py`

- **Layer**: router
- **Files**:
  - `backend/routers/internal/admin.py` — modify
- **What**: Add five new endpoints to the admin router, directly after the `delete_system_ai_service` endpoint (around line 562). All endpoints use `Depends(require_admin)`. Follow the exact code style of the existing system AI service endpoints (inline imports inside handlers, no separate service class for admin logic).

  Add these imports at the top of the SAAS admin section (or inside each handler — use inline imports as the existing pattern does):
  ```python
  from schemas.embedding_service_schemas import (
      EmbeddingServiceListItemSchema,
      CreateUpdateEmbeddingServiceSchema,
      SystemEmbeddingServiceImpactSchema,
  )
  ```

  **5a. GET `/system-embedding-services`** — list all system embedding services:
  ```python
  @router.get("/system-embedding-services", response_model=List[EmbeddingServiceListItemSchema])
  async def list_system_embedding_services(
      auth_context: Annotated[AuthContext, Depends(require_admin)],
      db: Annotated[Session, Depends(get_db)],
  ):
      from repositories.embedding_service_repository import EmbeddingServiceRepository
      from services.embedding_service_service import EmbeddingServiceService
      services = EmbeddingServiceRepository.get_system_services(db)
      return [EmbeddingServiceService._to_list_item(svc, is_system=True) for svc in services]
  ```

  **5b. POST `/system-embedding-services`** — create (status 201):
  Create an `EmbeddingService()` with `app_id = None`, set `name`, `provider`, `description` (= `body.model_name`), `api_key`, `endpoint` (= `body.base_url or ""`), `create_date = datetime.now()`. Use `EmbeddingServiceRepository.create(db, svc)`. Return `EmbeddingServiceService._to_list_item(svc, is_system=True)`.

  **5c. PUT `/system-embedding-services/{service_id}`** — update:
  Fetch via `EmbeddingServiceRepository.get_by_id(db, service_id)`. If not found or `svc.app_id is not None`, raise `HTTPException(404, "System embedding service not found")`. Update fields: `name`, `provider`, `description`, `endpoint`. Only update `api_key` if `not is_masked_key(body.api_key)`. Use `EmbeddingServiceRepository.update(db, svc)`. Return `_to_list_item(svc, is_system=True)`.

  **5d. GET `/system-embedding-services/{service_id}/impact`** — deletion impact check:
  Fetch the service (same 404 guard as PUT). Then query:
  ```python
  from models.silo import Silo
  from models.app import App
  rows = db.query(Silo, App).join(App, Silo.app_id == App.app_id).filter(
      Silo.embedding_service_id == service_id
  ).all()
  ```
  Build `AffectedSiloSchema` items from the rows. Count unique `app_id` values for `affected_apps_count`. Return `SystemEmbeddingServiceImpactSchema(...)`.

  **5e. DELETE `/system-embedding-services/{service_id}`** — delete (status 204):
  Fetch the service (same 404 guard). Nullify references:
  ```python
  from models.silo import Silo
  db.query(Silo).filter(Silo.embedding_service_id == service_id).update(
      {Silo.embedding_service_id: None}, synchronize_session='fetch'
  )
  ```
  Then `EmbeddingServiceRepository.delete(db, svc)`.
- **Acceptance**: All 5 endpoints appear at `GET /internal/admin/system-embedding-services` (and sub-paths) in `http://localhost:8000/docs/internal`. Each returns the correct status code. A 404 is returned when trying to update/delete an app-scoped service via these endpoints.
- **Status**: [x]

---

### Step 11 — Unit tests: `EmbeddingServiceRepository.get_system_services`

- **Layer**: test (unit)
- **Files**:
  - `tests/unit/test_embedding_service_repository.py` — create
- **What**: Two unit tests using the `db` fixture (these are integration-style at the DB level but placed in `unit/` per spec; alternatively use `integration/` — follow the spec placement). Given the test description in the spec says "unit tests", place them in `tests/unit/` even though they require a DB session. Actually, re-reading: the spec says "unit tests" but the tests use a DB — place them in `tests/integration/` to match the project's convention (only tests with no DB go in `unit/`).

  **Correction**: Place in `tests/integration/test_embedding_service_repository.py`.

  **Test 1 — `test_get_system_services_returns_only_null_app_id`**:
  - Fixtures: `db`, `fake_app`
  - Setup: Create two `EmbeddingService` objects: one with `app_id=fake_app.app_id`, one with `app_id=None`. Flush both.
  - Assert: `EmbeddingServiceRepository.get_system_services(db)` returns exactly one service, and its `service_id` matches the one with `app_id=None`.

  **Test 2 — `test_get_by_app_id_excludes_system_services`**:
  - Fixtures: `db`, `fake_app`
  - Setup: Create one app-scoped and one system (`app_id=None`) `EmbeddingService`. Flush.
  - Assert: `EmbeddingServiceRepository.get_by_app_id(db, fake_app.app_id)` returns exactly one service (the app-scoped one), and the system service is not in the result.
- **Acceptance**: `pytest tests/integration/test_embedding_service_repository.py -v` passes (2/2 tests green).
- **Status**: [ ]

---

### Step 12 — Integration tests: admin system embedding service endpoints

- **Layer**: test (integration)
- **Files**:
  - `tests/integration/test_admin_system_embedding_services.py` — create
- **What**: Eight integration tests using `client`, `db`, `fake_user`, `fake_app` fixtures. To authenticate as OMNIADMIN, use `monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)` in a module-level or per-test fixture, then call `dev-login` to get a token. Create a `admin_headers` fixture local to this module.

  Helper fixture `system_embedding_svc(db)`: creates and flushes an `EmbeddingService` with `app_id=None`, `name="Platform OpenAI Embeddings"`, `provider="OpenAI"`, `api_key="sk-sys"`, `description="text-embedding-3-small"`.

  **Test 1 — `test_list_system_embedding_services_requires_admin`**: Call `GET /internal/admin/system-embedding-services` with non-admin `auth_headers`. Assert HTTP 403.

  **Test 2 — `test_create_system_embedding_service`**: POST with valid body `{name, provider, model_name, api_key}` using `admin_headers`. Assert 201, response has `service_id`, `is_system=True`.

  **Test 3 — `test_update_system_embedding_service`**: PUT to `/internal/admin/system-embedding-services/{id}` with updated `name`. Assert 200, response has new name.

  **Test 4 — `test_update_app_scoped_service_via_admin_returns_404`**: Create an app-scoped embedding service. PUT to admin endpoint with its ID. Assert 404.

  **Test 5 — `test_delete_system_embedding_service_no_silos`**: DELETE system service with no silos referencing it. Assert 204. Verify the service no longer exists via `EmbeddingServiceRepository.get_by_id`.

  **Test 6 — `test_delete_system_embedding_service_with_silos_nullifies_references`**: Create a `Silo` referencing the system embedding service. DELETE the service. Assert 204. Fetch the silo from DB and assert `silo.embedding_service_id is None`.

  **Test 7 — `test_impact_endpoint_returns_correct_counts`**: Create a `Silo` in `fake_app` referencing the system embedding service. GET `/impact`. Assert `affected_silos_count=1`, `affected_apps_count=1`, `affected_silos[0].silo_name` matches.

  **Test 8 — `test_silo_form_includes_system_embedding_services`**: Create a system embedding service and an app-scoped one. GET `/internal/apps/{fake_app.app_id}/silos/0` (new silo form) — note the silo detail endpoint for `silo_id=0` returns empty embedding_services (the form fetches them separately). Instead GET a real silo's detail. Create a silo with `app_id=fake_app.app_id`, then GET `/internal/apps/{fake_app.app_id}/silos/{silo_id}`. Assert `embedding_services` contains both, with correct `is_system` flags.
- **Acceptance**: `pytest tests/integration/test_admin_system_embedding_services.py -v` passes (8/8 green).
- **Status**: [ ]

---

### Step 13 — Add system embedding service API methods to `api.ts`

- **Layer**: frontend (API client)
- **Files**:
  - `frontend/src/services/api.ts` — modify
- **What**: Add five new methods immediately before the `// ==================== UTILITY METHODS ====================` comment (after `deleteSystemAIService`):
  ```typescript
  async getSystemEmbeddingServices() {
    return this.request('/internal/admin/system-embedding-services');
  }

  async createSystemEmbeddingService(data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request('/internal/admin/system-embedding-services', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSystemEmbeddingService(serviceId: number, data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getSystemEmbeddingServiceImpact(serviceId: number) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}/impact`);
  }

  async deleteSystemEmbeddingService(serviceId: number) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}`, {
      method: 'DELETE',
    });
  }
  ```
  Follow the exact parameter and return type style of the existing `getSystemAIServices` / `deleteSystemAIService` methods above them.
- **Acceptance**: TypeScript compilation (`npm run build:lib`) succeeds without errors. The five methods are callable from other frontend files.
- **Status**: [ ]

---

### Step 14 — Create `SystemEmbeddingServicesPage.tsx`

- **Layer**: frontend (component/page)
- **Files**:
  - `frontend/src/pages/admin/SystemEmbeddingServicesPage.tsx` — create
- **What**: Clone `SystemAIServicesPage.tsx`, replacing AI service specifics with embedding service equivalents. Key differences from the AI services page:
  - Import `EmbeddingServiceForm` instead of `AIServiceForm`. The `EmbeddingServiceForm` component takes `embeddingService` prop (not `aiService`).
  - Interface name: `SystemEmbeddingService` (same fields as `SystemAIService` but for embedding).
  - API calls: `apiService.getSystemEmbeddingServices()`, `apiService.createSystemEmbeddingService(data)`, `apiService.updateSystemEmbeddingService(id, data)`, `apiService.deleteSystemEmbeddingService(id)`.
  - **Deletion flow with impact check**: The `handleDelete` function must NOT use `confirm()` directly. Instead:
    1. Call `await apiService.getSystemEmbeddingServiceImpact(serviceId)` to get the impact.
    2. Store the impact in local state `deletionImpact`.
    3. Show a confirmation dialog (inline or using a simple modal) with either:
       - If `affected_silos_count > 0`: "This embedding service is used by **X silos** across **Y apps**. Deleting it will leave those silos without an embedding service. List of affected silos (if count < 20). Are you sure?"
       - If `affected_silos_count === 0`: "Delete this system embedding service?"
    4. On user confirmation, call `await apiService.deleteSystemEmbeddingService(serviceId)` and refresh.
    5. On cancel, close the dialog without deleting.
  - Implement the confirmation dialog as a local state-driven JSX block (no external modal library needed — a simple `div` overlay with Tailwind classes, similar to the existing pattern in the codebase). State: `showDeleteConfirm: boolean`, `deletionImpact: DeletionImpact | null`, `pendingDeleteId: number | null`.
  - Table columns: Name, Provider, Model, Actions (Edit / Delete).
  - Page title: "System Embedding Services". Loading and empty state messages adapted accordingly.
  - The `EmbeddingServiceForm` expects `embeddingService` prop of type matching `EmbeddingService` in that file. For the system page, when creating, pass `null`; when editing, build a compatible object from the `SystemEmbeddingService` state (set `api_key: ""`, `base_url: ""`, `created_at: ""`, `available_providers: []`).
- **Acceptance**: The page renders without TypeScript errors. `npm run build:lib` passes.
- **Status**: [ ]

---

### Step 15 — Update `EmbeddingServicesPage.tsx` to show system services as read-only

- **Layer**: frontend (component/page)
- **Files**:
  - `frontend/src/pages/settings/EmbeddingServicesPage.tsx` — modify
- **What**: The existing page renders services from `apiService.getEmbeddingServices(appId)`, which after Step 08 now includes system services (with `is_system: true`). The page must:
  1. Update the local `EmbeddingService` interface to add `is_system?: boolean`.
  2. In the table's "Name" column render: if `service.is_system`, render the name with a `(System)` badge or label — e.g., add `{service.is_system && <span className="ml-1 text-xs font-medium text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded">System</span>}` after the name.
  3. In the "Actions" column: if `service.is_system`, render a read-only indicator (e.g., `<span className="text-gray-400 text-sm">System</span>`) instead of the `ActionDropdown` with Edit/Delete/Export actions, regardless of `canEdit`.
  4. The "Add Embedding Service" button and import functionality remain unchanged — they only create app-scoped services.
  No other changes to business logic or the `useServicesManager` hook.
- **Acceptance**: System services appear in the list with the badge and without edit/delete actions. App-scoped services behave exactly as before.
- **Status**: [ ]

---

### Step 16 — Update `SiloForm.tsx` to show system services with visual distinction

- **Layer**: frontend (component/page)
- **Files**:
  - `frontend/src/components/forms/SiloForm.tsx` — modify
- **What**: The `SiloForm` fetches embedding services via `apiService.getEmbeddingServices(appId)` (which after Step 08 returns both app-scoped and system services). Two changes:

  1. **Update the inline `Silo` interface** to add `is_system?: boolean` to the embedding services items type:
     ```typescript
     embedding_services?: { service_id: number; name: string; provider?: string; is_system?: boolean }[];
     ```

  2. **Update the embedding service `<select>` dropdown** to display a `(System)` suffix for system services:
     ```tsx
     {embeddingServices.map((service) => (
       <option key={service.service_id} value={service.service_id}>
         {service.is_system ? `[System] ${service.name}` : service.name}{service.provider ? ` (${service.provider})` : ''}
       </option>
     ))}
     ```
     Using `[System]` prefix is simpler than grouping (plain HTML `<option>` elements cannot easily be styled, but `[System]` text prefix is clear and consistent with how other parts of the codebase use text prefixes for system-level items).

  3. **Update the `servicesResponse` type handling** in `loadFormData`: the response from `getEmbeddingServices` now includes `is_system`. Store this in the `embeddingServices` state (currently `any[]` — no type change needed, but the `is_system` field will be present on each item).

  4. **Auto-select logic**: The current code auto-selects the only service if `servicesResponse.length === 1`. After this change, system services are included. If there is only one service total (even if system), auto-select it. No change needed to this logic.
- **Acceptance**: In the silo form, system embedding services appear with `[System]` prefix in the dropdown. App-scoped services show without prefix. Selecting either type works normally.
- **Status**: [ ]

---

### Step 17 — Wire `SystemEmbeddingServicesPage` into navigation and routes

- **Layer**: frontend (wiring)
- **Files**:
  - `frontend/src/core/defaultNavigation.tsx` — modify
  - `frontend/src/core/ExtensibleBaseApp.tsx` — modify
- **What**:
  **In `defaultNavigation.tsx`**: Add a new entry to the `admin` array, after the `system-ai-services` entry:
  ```typescript
  {
    path: '/admin/system-embedding-services',
    name: 'System Embedding Services',
    icon: <Brain size={16} />,
    section: 'admin',
    adminOnly: true,
  },
  ```
  `Brain` is already imported (used in `settingsNavigation` for Embedding Services).

  **In `ExtensibleBaseApp.tsx`**: Add import at the top (after `SystemAIServicesPage` import):
  ```typescript
  import SystemEmbeddingServicesPage from '../pages/admin/SystemEmbeddingServicesPage';
  ```
  Add route after the `/admin/system-ai-services` route block:
  ```tsx
  <Route path="/admin/system-embedding-services" element={
    <AdminLayoutRoute {...commonLayoutProps}>
      <SystemEmbeddingServicesPage />
    </AdminLayoutRoute>
  } />
  ```
- **Acceptance**: `npm run build:lib` succeeds. Navigating to `/admin/system-embedding-services` renders the new page. The nav link appears in the admin section for OMNIADMIN users.
- **Status**: [ ]

---

## Step Dependency Graph

```
Step 01 (migration)
  └─ Step 02 (model)
       └─ Step 03 (schemas: is_system + EmbeddingServiceOptionSchema)
            ├─ Step 04 (SiloDetailSchema uses EmbeddingServiceOptionSchema)
            ├─ Step 05 (repo: get_system_services)
            │    └─ Step 06 (service: _to_list_item)
            │         ├─ Step 07 (silo form data enrichment) ← needs 04
            │         │    └─ Step 08 (get_embedding_services_list includes system)
            │         └─ Step 09 (impact schemas)
            │              └─ Step 10 (admin CRUD endpoints) ← needs 05, 06, 09
            │                   ├─ Step 11 (repo unit tests) ← needs 05
            │                   └─ Step 12 (integration tests) ← needs 10
            └─ Step 13 (api.ts)
                 ├─ Step 14 (SystemEmbeddingServicesPage) ← needs 13
                 │    └─ Step 17 (routing + nav) ← needs 14
                 ├─ Step 15 (EmbeddingServicesPage read-only) ← needs 08
                 └─ Step 16 (SiloForm [System] prefix) ← needs 08
```

---

## Notes and Risks

1. **`silo_id=0` path in `get_silo_detail`** returns empty `embedding_services=[]`. The frontend `SiloForm` calls `apiService.getEmbeddingServices(appId)` independently for the dropdown, not from the silo detail response. This is the current design. Steps 07/08 handle the `SiloForm` path via `get_embedding_services_list`; the silo detail path (for existing silo editing) is handled in Step 07. Both paths must be addressed.

2. **`EmbeddingServicesPage` and system services**: After Step 08, system services appear in `EmbeddingServicesPage`. Step 15 must guard against attempting to edit/delete system services from that page. Do not skip Step 15 — without it, app admins could click "Edit" or "Delete" on system services and get a confusing error.

3. **Downgrade migration safety**: The downgrade in Step 01 uses a Python-level exception (not a DB assertion) to prevent silent data loss. This matches the guidance in the spec and the approach used in `saas002` for the same scenario with AI services.

4. **`SiloDetailSchema.embedding_services` type change** (Step 04): This is a breaking change to the silo detail response shape. The field changes from `List[Dict[str, Any]]` to `List[EmbeddingServiceOptionSchema]`. The frontend `SiloForm` accesses `service.service_id`, `service.name`, `service.provider`, and now `service.is_system`. The `Silo` interface in `SiloForm.tsx` already declares `embedding_services` as `{ service_id: number; name: string; provider?: string }[]`. Step 16 adds `is_system?: boolean` to this. Verify no other frontend code accesses the `embedding_services` field on the silo detail response and breaks.

5. **`factories.py`**: No `EmbeddingServiceFactory` exists yet. Tests in Steps 11 and 12 can create embedding services directly (like `fake_ai_service` does in `conftest.py`) rather than adding a factory, keeping the scope minimal. If a factory is preferred for cleanliness, add an `EmbeddingServiceFactory` to `tests/factories.py` and register it in `configure_factories`.
```
