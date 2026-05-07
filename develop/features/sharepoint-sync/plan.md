# Implementation Plan: SharePoint Sync

**Spec**: develop/features/sharepoint-sync/spec.md
**Created**: 2026-05-06
**Status**: pending

---

## Overview

This plan creates SharePoint Sync in two tightly coordinated tracks:

1. **Core changes** — DB schema, enum files, SQLAlchemy models, `AppService` cascade update, plugin discovery infrastructure, and the `/internal/capabilities` endpoint. These live in `backend/`.
2. **Plugin package** — `plugins/mattin_sharepoint/` at repo root. A self-contained, separately installable package that registers itself into the core via Python entry points.

The ordering follows strict dependency layering: schema → models → plugin scaffold → core registry → plugin repository/schemas → plugin service → plugin router → core wiring → tests → frontend types → frontend API client → frontend pages → frontend routes/nav wiring.

The `mattin-sharepoint` plugin directory lives at `plugins/mattin_sharepoint/` (repo root, parallel to `backend/` and `frontend/`). Its own `pyproject.toml` declares `mattin-sharepoint` as a package with the entry-point that loads it into core at startup.

---

## Steps

### Step 01 — Create enum files for SharePointSyncStatus and SharePointFileStatus

- **Layer**: model (enums)
- **Files**:
  - `backend/models/enums/sharepoint_sync_status.py` — create
  - `backend/models/enums/sharepoint_file_status.py` — create
- **What**:
  Create two Python `str, enum.Enum` classes following the exact pattern of `backend/models/enums/crawl_job_status.py`.

  `SharePointSyncStatus` values: `IDLE`, `RUNNING`, `SUCCESS`, `PARTIAL`, `ERROR`.
  `SharePointFileStatus` values: `PENDING`, `INDEXED`, `ERROR`.

  Each file must be a standalone module with only the enum class — no imports beyond `enum`. No `__init__.py` changes yet; the enums are imported directly by the model files in later steps.
- **Acceptance**: `python -c "from models.enums.sharepoint_sync_status import SharePointSyncStatus; print(SharePointSyncStatus.IDLE)"` executes without error (run from `backend/`).
- **Status**: [x]

---

### Step 02 — Write Alembic migration: sharepoint_source and sharepoint_file tables

- **Layer**: database
- **Files**:
  - `alembic/versions/spoint001_sharepoint_sync_tables.py` — create
- **What**:
  Manually write (do not autogenerate) a migration with `revision = 'spoint001'`. Check `alembic heads` first to find the current tip and set `down_revision` to the current head revision ID (which is `multimodal001` as of the branch start — confirm with `alembic heads` before writing).

  **`upgrade()`**:

  1. Create PostgreSQL enum type `sharepoint_sync_status` with values `IDLE`, `RUNNING`, `SUCCESS`, `PARTIAL`, `ERROR` using `postgresql.ENUM(..., name='sharepoint_sync_status', create_type=True)`.create(op.get_bind(), checkfirst=True)`.
  2. Create PostgreSQL enum type `sharepoint_file_status` with values `PENDING`, `INDEXED`, `ERROR` the same way.
  3. Create table `sharepoint_source`:
     - `id` INTEGER PK autoincrement
     - `app_id` INTEGER NOT NULL FK → `App.app_id` ON DELETE CASCADE
     - `silo_id` INTEGER NOT NULL FK → `Silo.silo_id`
     - `name` VARCHAR(255) NOT NULL
     - `description` TEXT NULL
     - `tenant_id` VARCHAR(255) NOT NULL
     - `client_id` VARCHAR(255) NOT NULL
     - `client_secret` TEXT NOT NULL
     - `site_id` VARCHAR(255) NOT NULL
     - `site_name` VARCHAR(255) NULL
     - `site_url` TEXT NULL
     - `drive_id` VARCHAR(255) NOT NULL
     - `drive_name` VARCHAR(255) NULL
     - `file_extension_filters` JSON NULL
     - `last_delta_token` TEXT NULL
     - `last_synced_at` DATETIME NULL
     - `last_sync_status` `sharepoint_sync_status` NOT NULL default `IDLE` server_default `'IDLE'`
     - `last_sync_error` TEXT NULL
     - `refresh_interval_minutes` INTEGER NULL
     - `next_run_at` DATETIME NULL
     - `created_at` DATETIME NOT NULL default utcnow
     - `updated_at` DATETIME NOT NULL default utcnow
     - UniqueConstraint: none additional
  4. Create table `sharepoint_file`:
     - `id` INTEGER PK autoincrement
     - `source_id` INTEGER NOT NULL FK → `sharepoint_source.id` ON DELETE CASCADE
     - `drive_item_id` VARCHAR(512) NOT NULL
     - `name` VARCHAR(512) NULL
     - `path` TEXT NULL
     - `web_url` TEXT NULL
     - `mime_type` VARCHAR(255) NULL
     - `size_bytes` BIGINT NULL
     - `last_modified_at` DATETIME NULL
     - `status` `sharepoint_file_status` NOT NULL default `PENDING` server_default `'PENDING'`
     - `last_synced_at` DATETIME NULL
     - `error_message` TEXT NULL
     - `vector_doc_ids` JSON NULL
     - `created_at` DATETIME NOT NULL default utcnow
     - `updated_at` DATETIME NOT NULL default utcnow
     - UniqueConstraint on (`source_id`, `drive_item_id`) named `uq_spfile_source_item`

  **`downgrade()`**:

  1. `op.drop_table('sharepoint_file')`
  2. `op.drop_table('sharepoint_source')`
  3. Drop enum `sharepoint_file_status` via `postgresql.ENUM(...).drop(op.get_bind(), checkfirst=True)`
  4. Drop enum `sharepoint_sync_status` same way

  Use `create_type=False` in all column definitions (the type is pre-created in step 1 of upgrade).
- **Acceptance**: `alembic upgrade head` succeeds, then `alembic downgrade -1` succeeds (both tables and enums dropped), then `alembic upgrade head` again succeeds.
- **Status**: [x]

---

### Step 03 — Create SharePointSource SQLAlchemy model

- **Layer**: model
- **Files**:
  - `backend/models/sharepoint_source.py` — create
- **What**:
  Model class `SharePointSource(Base)` with `__tablename__ = 'sharepoint_source'`. Use `sa.Enum(SharePointSyncStatus, name='sharepoint_sync_status', create_type=False)` for the status column (follow `CrawlJob` pattern exactly).

  All columns map 1:1 to the migration in Step 02. Relationships:
  - `app = relationship('App', back_populates='sharepoint_sources')` — not yet bidirectional (the back-population is added in Step 05)
  - `silo = relationship('Silo', lazy=False, uselist=False)` — read-only, no cascade (silo is managed externally)
  - `files = relationship('SharePointFile', back_populates='source', cascade='all, delete-orphan', lazy=True)`

  Use `default=list` (not `default=[]`) for `file_extension_filters` and `vector_doc_ids` JSON columns.
  `created_at` default `datetime.utcnow`, `updated_at` default `datetime.utcnow`, `onupdate=datetime.utcnow`.

  Import `SharePointSyncStatus` from `models.enums.sharepoint_sync_status`.
- **Acceptance**: `python -c "from models.sharepoint_source import SharePointSource"` from `backend/` with no import errors.
- **Status**: [x]

---

### Step 04 — Create SharePointFile SQLAlchemy model

- **Layer**: model
- **Files**:
  - `backend/models/sharepoint_file.py` — create
- **What**:
  Model class `SharePointFile(Base)` with `__tablename__ = 'sharepoint_file'`. Use `sa.Enum(SharePointFileStatus, name='sharepoint_file_status', create_type=False)` for the status column.

  All columns map 1:1 to the migration. The `__table_args__` must include `UniqueConstraint('source_id', 'drive_item_id', name='uq_spfile_source_item')`.

  Relationship: `source = relationship('SharePointSource', back_populates='files')`.
  Use `default=list` for `vector_doc_ids`.
  Import `SharePointFileStatus` from `models.enums.sharepoint_file_status`.
- **Acceptance**: `python -c "from models.sharepoint_file import SharePointFile"` from `backend/` with no import errors.
- **Status**: [x]

---

### Step 05 — Register models in backend/models/__init__.py

- **Layer**: model
- **Files**:
  - `backend/models/__init__.py` — modify
- **What**:
  Add two import lines after the existing `CrawlJob` line (before `Media`):

  ```python
  from .sharepoint_source import SharePointSource
  from .sharepoint_file import SharePointFile
  ```

  Add both to the `__all__` list.

  Also add `sharepoint_source` relationship to the `Silo` model is NOT needed (silo does not back-reference SharePointSource). However, the `App` model needs `sharepoint_sources = relationship('SharePointSource', back_populates='app', cascade='all, delete-orphan', lazy=True)` — add this in `backend/models/app.py` so that `SharePointSource.app` back-population works. Check `backend/models/app.py` to confirm current relationships before adding.
- **Acceptance**: `python -c "import models"` from `backend/` with no import errors. Test that `SharePointSource` and `SharePointFile` are importable from `models`.
- **Status**: [x]

---

### Step 06 — Create the plugin registry (core infrastructure)

- **Layer**: service
- **Files**:
  - `backend/plugins/__init__.py` — create (empty)
  - `backend/plugins/registry.py` — create
- **What**:
  `backend/plugins/__init__.py`: empty file to make `plugins` a Python package.

  `backend/plugins/registry.py`: define class `PluginRegistry` with:
  - `_plugins: dict[str, dict]` — internal store, initialized to `{}`
  - `register(name: str, descriptor: dict) -> None` — stores `{name: descriptor}` in `_plugins`
  - `get(name: str) -> dict | None` — returns plugin descriptor or None
  - `all() -> dict` — returns shallow copy of `_plugins`
  - `is_enabled(name: str) -> bool` — returns `True` if `name` in `_plugins` and `_plugins[name].get("enabled", False)`

  Instantiate a module-level singleton: `plugin_registry = PluginRegistry()`.

  This class is deliberately simple — it is a dict wrapper with no persistence. The registry is rebuilt each process startup.
- **Acceptance**: `python -c "from plugins.registry import plugin_registry; plugin_registry.register('test', {'enabled': True}); assert plugin_registry.is_enabled('test')"` from `backend/`.
- **Status**: [x]

---

### Step 07 — Wire plugin discovery into FastAPI lifespan and add /internal/capabilities endpoint

- **Layer**: router + service
- **Files**:
  - `backend/main.py` — modify
  - `backend/routers/internal/capabilities.py` — create
  - `backend/routers/internal/__init__.py` — modify
- **What**:
  **`backend/main.py`** — in the lifespan startup block, after `AuthConfig.load_config()`, add:

  ```python
  # Load plugins via entry points
  from plugins.registry import plugin_registry
  app.state.plugin_registry = plugin_registry
  import importlib.metadata
  for ep in importlib.metadata.entry_points(group="mattin.plugins"):
      try:
          ep.load()(app, plugin_registry)
          logger.info(f"Plugin loaded: {ep.name}")
      except Exception as e:
          logger.error(f"Failed to load plugin '{ep.name}': {e}", exc_info=True)
  ```

  The plugin loading happens before crawl workers start so that plugins can register their own workers.

  **`backend/routers/internal/capabilities.py`** — new file:

  ```python
  from fastapi import APIRouter, Depends
  from lks_idprovider import AuthContext
  from routers.internal.auth_utils import get_current_user_oauth
  from plugins.registry import plugin_registry

  router = APIRouter(tags=["Capabilities"])

  @router.get("/capabilities")
  async def get_capabilities(
      auth_context: AuthContext = Depends(get_current_user_oauth),
  ):
      """Return installed plugin capabilities. Requires authentication."""
      return plugin_registry.all()
  ```

  **`backend/routers/internal/__init__.py`** — add:

  ```python
  from .capabilities import router as capabilities_router
  ```
  and:
  ```python
  internal_router.include_router(capabilities_router)
  ```
  (no prefix — the route is `/capabilities` relative to `/internal`, so the final path is `/internal/capabilities`)
- **Acceptance**: Start the app (`uvicorn backend.main:app`). `GET /internal/capabilities` with a valid token returns `{}` (empty dict — no plugins installed yet). Without a token returns 401.
- **Status**: [x]

---

### Step 08 — Update AppService.delete_app() to cascade SharePointSource deletion

- **Layer**: service
- **Files**:
  - `backend/services/app_service.py` — modify
- **What**:
  In `AppService.delete_app()`, before step 6 ("Delete repositories"), insert a new step that deletes SharePoint sources for the app. This must happen before silo deletion because sources hold a reference to silos.

  Add between step 5 (fetching domains) and step 6 (delete repositories):

  ```python
  # 5b. Delete SharePoint sources (before silo deletion; each source owns a silo)
  # Import inline to avoid circular dependency
  from repositories.sharepoint_source_repository import SharePointSourceRepository
  from services.sharepoint_source_service import SharePointSourceService
  sp_sources = SharePointSourceRepository.list_by_app(app_id, self.db)
  for sp_source in sp_sources:
      logger.info(f"Deleting SharePoint source {sp_source.id}: {sp_source.name}")
      SharePointSourceService.delete_source(sp_source.id, self.db)
  ```

  Note: `SharePointSourceService` is not yet implemented (Step 16); however this step establishes the correct ordering. If the plugin is not installed, `SharePointSourceRepository` will still be importable from core (it lives in `backend/repositories/`). The delete is idempotent — if no sources exist, the loop is a no-op.

  Actually: because the repository is a core module (Step 09) but the service is a plugin module, use only the repository here to avoid requiring the plugin at core startup. Call `SiloService.delete_silo(sp_source.silo_id, self.db)` directly from the cascade, and let the DB cascade handle the `SharePointFile` rows:

  ```python
  # 5b. Delete SharePoint sources and their silos (before main silo deletion)
  from repositories.sharepoint_source_repository import SharePointSourceRepository
  sp_sources = SharePointSourceRepository.list_by_app(app_id, self.db)
  for sp_source in sp_sources:
      logger.info(f"Deleting SharePoint source {sp_source.id}: {sp_source.name}")
      silo_id = sp_source.silo_id
      # SharePointFile rows cascade-delete via FK; vectors are orphaned (acceptable for app deletion)
      self.db.delete(sp_source)
      self.db.flush()
      if silo_id:
          silo_service.delete_silo(silo_id, self.db)
  ```

  `silo_service` is already instantiated earlier in the method.
- **Acceptance**: Run `pytest tests/integration/routers/internal/test_apps.py -v` — existing app deletion test must still pass. The new cascade is exercised by the integration test in Step 22.
- **Status**: [x]

---

### Step 09 — Create SharePointSourceRepository (core)

- **Layer**: repository
- **Files**:
  - `backend/repositories/sharepoint_source_repository.py` — create
- **What**:
  Class `SharePointSourceRepository` with static methods only (matches the pattern of `DomainRepository`):

  - `list_by_app(app_id: int, db: Session) -> List[SharePointSource]` — filter by `app_id`, order by `created_at` desc.
  - `get_by_id(source_id: int, db: Session) -> Optional[SharePointSource]` — fetch single row with `joinedload(SharePointSource.silo)`.
  - `get_by_id_and_app(source_id: int, app_id: int, db: Session) -> Optional[SharePointSource]` — filter by both; returns None if not found (used by router for 404 checks).
  - `create(source: SharePointSource, db: Session) -> SharePointSource` — `db.add(source); db.commit(); db.refresh(source); return source`.
  - `update(source: SharePointSource, db: Session) -> SharePointSource` — same pattern as create.
  - `delete(source_id: int, db: Session) -> None` — `db.query(SharePointSource).filter(...).delete(); db.commit()`.
  - `get_file_count(source_id: int, db: Session) -> int` — `db.query(SharePointFile).filter(SharePointFile.source_id == source_id).count()`.
- **Acceptance**: `python -c "from repositories.sharepoint_source_repository import SharePointSourceRepository"` from `backend/`.
- **Status**: [x]

---

### Step 10 — Create SharePointFileRepository (core)

- **Layer**: repository
- **Files**:
  - `backend/repositories/sharepoint_file_repository.py` — create
- **What**:
  Class `SharePointFileRepository` with static methods:

  - `list_by_source(source_id: int, db: Session) -> List[SharePointFile]` — ordered by `created_at` desc.
  - `get_by_drive_item(source_id: int, drive_item_id: str, db: Session) -> Optional[SharePointFile]` — filter both columns.
  - `upsert_by_drive_item(source_id: int, drive_item_id: str, data: dict, db: Session) -> SharePointFile` — fetch existing via `get_by_drive_item`; if found, update fields from `data` dict (name, path, web_url, mime_type, size_bytes, last_modified_at, status, last_synced_at, error_message, vector_doc_ids); if not found, create new `SharePointFile(**{source_id, drive_item_id, **data})`; commit and refresh.
  - `delete_file(file_id: int, db: Session) -> None`.
  - `delete_by_source(source_id: int, db: Session) -> None` — bulk delete all files for a source.
  - `get_files_with_extension_not_in(source_id: int, allowed_extensions: List[str], db: Session) -> List[SharePointFile]` — returns files whose `name` extension (case-insensitive) is not in `allowed_extensions`. Use Python-level filtering after fetching all source files (acceptable for MVP given typical file counts). Extensions are compared without the leading dot where stored in `file_extension_filters` (normalise both sides).
- **Acceptance**: `python -c "from repositories.sharepoint_file_repository import SharePointFileRepository"` from `backend/`.
- **Status**: [x]

---

### Step 11 — Scaffold the mattin-sharepoint plugin package

- **Layer**: (new package)
- **Files**:
  - `plugins/mattin_sharepoint/__init__.py` — create (empty)
  - `plugins/mattin_sharepoint/plugin.py` — create (stub)
  - `plugins/mattin_sharepoint/schemas.py` — create (all Pydantic schemas)
  - `plugins/pyproject.toml` — create (package descriptor with entry point)
  - `plugins/README.md` — create (minimal install instructions)
- **What**:
  **Directory layout**:
  ```
  plugins/
  └── mattin_sharepoint/
      ├── __init__.py
      ├── plugin.py
      ├── schemas.py
      ├── graph_client.py    (Step 12)
      ├── repository.py      (re-exports from core — Step 13)
      ├── service.py         (Steps 15-16)
      ├── worker.py          (Step 17)
      └── router.py          (Steps 18-19)
  ```

  **`plugins/pyproject.toml`**:
  ```toml
  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.backends.legacy:build"

  [project]
  name = "mattin-sharepoint"
  version = "0.1.0"
  description = "SharePoint Sync plugin for Mattin AI"
  requires-python = ">=3.11"
  dependencies = [
      "fastapi",
      "sqlalchemy",
      "httpx>=0.28",
  ]

  [project.entry-points."mattin.plugins"]
  sharepoint = "mattin_sharepoint.plugin:register"

  [tool.setuptools.packages.find]
  where = ["."]
  ```

  **`plugins/mattin_sharepoint/__init__.py`**: empty.

  **`plugins/mattin_sharepoint/plugin.py`** (stub — replaced in Step 17 once worker/router exist):
  ```python
  """Plugin entry point. Called by core during FastAPI lifespan."""

  def register(app, registry):
      """Register the SharePoint plugin with the Mattin AI core."""
      import importlib.metadata
      version = importlib.metadata.version("mattin-sharepoint")
      # Router and worker wired in later steps
      registry.register("sharepoint", {"enabled": True, "version": version})
  ```

  **`plugins/mattin_sharepoint/schemas.py`**: implement all Pydantic request/response schemas (Pydantic v2 style with `model_config = ConfigDict(from_attributes=True)`):

  - `SharePointSourceCreateRequest`: fields `name: str`, `description: str | None = None`, `tenant_id: str`, `client_id: str`, `client_secret: str`, `site_id: str`, `site_name: str | None = None`, `site_url: str | None = None`, `drive_id: str`, `drive_name: str | None = None`, `file_extension_filters: list[str] | None = None`, `embedding_service_id: int | None = None`, `vector_db_type: str = "PGVECTOR"`, `silo_name: str`.
  - `SharePointSourceUpdateRequest`: all fields optional — `name: str | None`, `description: str | None`, `file_extension_filters: list[str] | None`, `tenant_id: str | None`, `client_id: str | None`, `client_secret: str | None`.
  - `SharePointFileResponse`: `id`, `drive_item_id`, `name`, `path`, `web_url`, `mime_type`, `size_bytes`, `last_modified_at`, `status`, `last_synced_at`, `error_message`.
  - `SharePointSourceResponse`: `id`, `app_id`, `silo_id`, `name`, `description`, `tenant_id`, `client_id` (client_secret is NEVER returned), `site_id`, `site_name`, `site_url`, `drive_id`, `drive_name`, `file_extension_filters`, `last_delta_token` (omit — never return), `last_synced_at`, `last_sync_status`, `last_sync_error`, `refresh_interval_minutes`, `next_run_at`, `created_at`, `updated_at`, `file_count: int = 0`.
  - `SharePointSourceDetailResponse`: extends `SharePointSourceResponse` with `files: list[SharePointFileResponse] = []`.
  - `MicrosoftSiteResponse`: `id: str`, `name: str`, `web_url: str`.
  - `MicrosoftDriveResponse`: `id: str`, `name: str`, `drive_type: str | None = None`.
  - `TestConnectionRequest`: `tenant_id: str`, `client_id: str`, `client_secret: str`, `site_id: str | None = None`, `drive_id: str | None = None`.
  - `TestConnectionResponse`: `ok: bool`, `error: str | None = None`.
  - `SyncTriggerResponse`: `message: str`, `source_id: int`, `status: str`.

  Mark `last_delta_token` as excluded from `SharePointSourceResponse` by simply not including it in the schema fields.
- **Acceptance**: `python -c "from mattin_sharepoint.schemas import SharePointSourceCreateRequest"` from `plugins/`.
- **Status**: [x]

---

### Step 12 — Implement GraphClient

- **Layer**: service (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/graph_client.py` — create
- **What**:
  Class `GraphClient` — stateless, all methods are `@staticmethod` or `@classmethod`. Uses `httpx` (already a core dependency).

  Methods:

  - `async get_token(tenant_id: str, client_id: str, client_secret: str) -> str`
    — POST to `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`.
    — Returns access_token string.
    — On non-200, raise `GraphAuthError(message)`.

  - `async search_sites(token: str, query: str) -> list[dict]`
    — GET `https://graph.microsoft.com/v1.0/sites?search={query}` with Bearer token.
    — Returns list of dicts `{id, displayName, webUrl}`.

  - `async list_drives(token: str, site_id: str) -> list[dict]`
    — GET `https://graph.microsoft.com/v1.0/sites/{site_id}/drives`.
    — Returns list of dicts `{id, name, driveType}`.

  - `async verify_drive_access(token: str, drive_id: str) -> dict`
    — GET `https://graph.microsoft.com/v1.0/drives/{drive_id}`.
    — On non-200 raises `GraphAccessError(status_code, message)`.

  - `async delta_query(token: str, drive_id: str, delta_token: str | None, select_fields: str | None = None) -> tuple[list[dict], str | None]`
    — If `delta_token` is None: initial request to `/drives/{drive_id}/root/delta?$select=id,name,file,folder,lastModifiedDateTime,deleted,webUrl,parentReference,size,mimeType`.
    — If `delta_token` provided: request to the stored delta URL directly.
    — Paginate via `@odata.nextLink` until exhausted.
    — Collect all items into one list.
    — Extract `@odata.deltaLink` from the final page and parse the token out of it.
    — Returns `(items, delta_token_or_none)`.
    — On HTTP 410: raise `GraphDeltaExpiredError()`.

  - `async download_file(token: str, drive_id: str, item_id: str, dest_path: str) -> None`
    — GET `https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content` (follow redirects).
    — Stream response body to `dest_path` using `httpx.AsyncClient` with `stream()`.

  Custom exceptions at module level:
  ```python
  class GraphAuthError(Exception): pass
  class GraphAccessError(Exception):
      def __init__(self, status_code: int, message: str):
          self.status_code = status_code
          super().__init__(message)
  class GraphDeltaExpiredError(Exception): pass
  ```
- **Acceptance**: Unit test in Step 20 covers this. Manually: `python -c "from mattin_sharepoint.graph_client import GraphClient"`.
- **Status**: [x]

---

### Step 13 — Create plugin repository module (re-export pattern)

- **Layer**: repository (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/repository.py` — create
- **What**:
  The core repositories (`SharePointSourceRepository`, `SharePointFileRepository`) already live in `backend/repositories/`. The plugin needs to import them.

  Because `backend/` is on `sys.path` when the plugin is loaded (core adds it), the plugin can import directly:

  ```python
  """Re-exports core repositories for use within the plugin."""
  from repositories.sharepoint_source_repository import SharePointSourceRepository
  from repositories.sharepoint_file_repository import SharePointFileRepository

  __all__ = ["SharePointSourceRepository", "SharePointFileRepository"]
  ```

  This module is the single import point for repositories within the plugin — other plugin modules import from here.
- **Acceptance**: `python -c "from mattin_sharepoint.repository import SharePointSourceRepository"` (with `backend/` on `sys.path`) — no errors.
- **Status**: [x]

---

### Step 14 — Implement SharePointSourceService (CRUD + test-connection)

- **Layer**: service (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/service.py` — create (CRUD part only; sync service added in Step 15)
- **What**:
  Class `SharePointSourceService` in the same file. All methods are `@staticmethod`.

  - `list_sources(app_id: int, db: Session) -> list[SharePointSourceResponse]`
    — Calls `SharePointSourceRepository.list_by_app`. For each source, fetches file count. Returns list of `SharePointSourceResponse`.

  - `get_source(source_id: int, app_id: int, db: Session) -> SharePointSourceDetailResponse`
    — `SharePointSourceRepository.get_by_id_and_app`. If not found raise `HTTPException(404)`.
    — Fetches files via `SharePointFileRepository.list_by_source`.
    — Returns `SharePointSourceDetailResponse` (source fields + files list).

  - `create_source(app_id: int, data: SharePointSourceCreateRequest, db: Session) -> SharePointSourceResponse`
    1. Call `SharePointSourceService._test_connection(data.tenant_id, data.client_id, data.client_secret, None, data.drive_id)` — if it fails, raise `HTTPException(400, detail={"error": str(e)})`.
    2. Create the linked silo:
       ```python
       from services.silo_service import SiloService
       from models.silo import SiloType
       silo = SiloService.create_or_update_silo({
           'silo_id': 0,
           'name': data.silo_name,
           'description': f'SharePoint silo for {data.name}',
           'status': 'active',
           'app_id': app_id,
           'fixed_metadata': False,
           'embedding_service_id': data.embedding_service_id,
           'vector_db_type': data.vector_db_type,
       }, SiloType.CUSTOM)
       ```
    3. Create `SharePointSource` ORM object, call `SharePointSourceRepository.create(source, db)`.
    4. Return `SharePointSourceResponse` built from the new source.

  - `update_source(source_id: int, app_id: int, data: SharePointSourceUpdateRequest, db: Session) -> SharePointSourceResponse`
    1. Fetch source; 404 if not found.
    2. If any credential field (`tenant_id`, `client_id`, `client_secret`) is provided in the update, call `_test_connection` with the merged credentials (new value or existing). If test fails, raise `HTTPException(400)`.
    3. Update only provided fields (fields that are `None` in the request are skipped).
    4. `SharePointSourceRepository.update(source, db)`.
    5. Return updated response.

  - `delete_source(source_id: int, app_id: int, db: Session) -> None`
    — For MVP app-level cascade (Step 08) call this with `app_id=None` is not needed — the cascade in app_service calls repository directly. For router-level deletion:
    1. Fetch source; 404 if not found.
    2. Check `last_sync_status == RUNNING` → raise `HTTPException(409, "Sync in progress")`.
    3. Delete vector chunks from the silo. Use `SiloService.delete_collection(source.silo_id, db)` approach: iterate files with vector_doc_ids and call the vector store delete. For MVP simplicity: call `SiloService.delete_silo(source.silo_id, db)` (which calls `delete_collection` internally), then delete the source row:
       ```python
       silo_id = source.silo_id
       SharePointSourceRepository.delete(source_id, db)   # cascades SharePointFile rows
       if silo_id:
           SiloService.delete_silo(silo_id, db)
       ```

  - `async _test_connection(tenant_id: str, client_id: str, client_secret: str, site_id: str | None, drive_id: str | None) -> None`
    — Acquire token via `GraphClient.get_token`. If fails raise `GraphAuthError`.
    — If `drive_id`: call `GraphClient.verify_drive_access`. If fails raise `GraphAccessError`.
    — Else if `site_id`: call `GET /sites/{site_id}` (inline httpx call or add helper to GraphClient).
    — On any exception, re-raise so callers can map to HTTP 400.

  The `_test_connection` is the same logic used by both create and update endpoints, and by the `POST /internal/microsoft/test-connection` router endpoint.
- **Acceptance**: Module imports cleanly. Business logic verified by unit tests in Step 20.
- **Status**: [x]

---

### Step 15 — Implement SharePointSyncService

- **Layer**: service (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/service.py` — modify (add `SharePointSyncService` class at bottom)
- **What**:
  Add class `SharePointSyncService` to the same `service.py` file.

  - `async run_sync(source_id: int) -> None`
    This is the main sync coroutine. Opens its own DB session (like `CrawlExecutorService.run_job`). Full logic per spec Section "Sync flow":

    1. Open `db = SessionLocal()`.
    2. Fetch source. Set `last_sync_status = RUNNING`, `last_sync_error = None`; update.
    3. `token = await GraphClient.get_token(source.tenant_id, source.client_id, source.client_secret)`.
    4. Call `GraphClient.delta_query(token, source.drive_id, source.last_delta_token)`. Catch `GraphDeltaExpiredError` → clear `source.last_delta_token`, retry with `delta_token=None` (one retry only; log a warning).
    5. Iterate items:
       - `deleted` key present: look up file by `drive_item_id`, delete its vector chunks (using `source.silo_id`), delete the `SharePointFile` row.
       - `folder` key present: skip.
       - `file` key present:
         a. Check extension against `source.file_extension_filters`. If filter is non-empty and extension not in filter: check if a `SharePointFile` row exists for this item → if yes, delete vectors and row (treat as deletion). Skip.
         b. Download to temp file via `GraphClient.download_file(token, source.drive_id, item['id'], tmp_path)`.
         c. Extract text: `docs = SiloService.extract_documents_from_file(tmp_path, ext, base_metadata)`.
         d. Index: `SiloService.index_multiple_content(source.silo_id, [{...}], db)` — translate `Document` objects to the expected dict format.
         e. Upsert `SharePointFile` via `SharePointFileRepository.upsert_by_drive_item(...)` with `status=INDEXED`, `vector_doc_ids=[...]`, timestamps.
         f. Remove temp file.
         g. On per-file exception: set `SharePointFile.status = ERROR`, `error_message = str(e)`, note error for `PARTIAL` outcome.
    6. Filter enforcement pass: call `SharePointFileRepository.get_files_with_extension_not_in(source_id, allowed_extensions, db)`. For each: delete vectors, delete row.
    7. Persist new `last_delta_token`.
    8. Set `last_synced_at = utcnow()`. If any per-file errors → `last_sync_status = PARTIAL`, else → `SUCCESS`.
    9. Update source.
    10. Close `db`.
    11. On unhandled exception in steps 3–8: set `last_sync_status = ERROR`, `last_sync_error = str(e)`, update source, close db.

  Helper for deleting vector chunks by file:
  ```python
  def _delete_file_vectors(self, silo_id: int, file: SharePointFile, db: Session) -> None:
      """Remove indexed vectors for a single SharePointFile from the silo."""
      from tools.vector_store_factory import VectorStoreFactory
      from repositories.silo_repository import SiloRepository
      from db.database import db as db_obj
      silo = SiloRepository.get_by_id(silo_id, db)
      if not silo or not silo.embedding_service:
          return
      collection_name = f"silo_{silo_id}"
      store = VectorStoreFactory.get_vector_store(db_obj, silo.vector_db_type or 'PGVECTOR')
      if file.vector_doc_ids:
          store.delete_documents(
              collection_name,
              ids=file.vector_doc_ids,
              embedding_service=silo.embedding_service
          )
  ```

  Temp file path: use `tempfile.mkstemp(suffix=ext)` and always delete in a `finally` block.
- **Acceptance**: Module imports cleanly. Core sync logic verified by unit tests in Step 20.
- **Status**: [x]

---

### Step 16 — Implement the sync worker

- **Layer**: service (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/worker.py` — create
- **What**:
  Mirrors `backend/services/crawl/worker.py` exactly in structure.

  A simple queue-based worker: maintain an `asyncio.Queue` at module level (`_sync_queue: asyncio.Queue[int] = asyncio.Queue()`).

  Functions:

  - `async enqueue_sync(source_id: int) -> None` — puts `source_id` onto `_sync_queue`. Raises `ConflictError` (custom exception) if `source_id` is already in the queue (check `_sync_queue._queue` for presence).

  - `async _worker_loop() -> None`:
    ```python
    while True:
        try:
            source_id = await _sync_queue.get()
            logger.info(f"SharePoint worker: starting sync for source {source_id}")
            await SharePointSyncService.run_sync(source_id)
        except asyncio.CancelledError:
            logger.info("SharePoint worker shutting down")
            break
        except Exception as e:
            logger.error(f"SharePoint worker error for source {source_id}: {e}", exc_info=True)
        finally:
            _sync_queue.task_done()
    ```

  - `async start_sharepoint_worker() -> list[asyncio.Task]`:
    ```python
    tasks = [asyncio.create_task(_worker_loop(), name="sharepoint-worker")]
    return tasks
    ```

  - `async stop_sharepoint_worker(tasks: list[asyncio.Task]) -> None`:
    ```python
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    ```

  `ConflictError` — simple exception class at module top.
- **Acceptance**: `python -c "from mattin_sharepoint.worker import enqueue_sync, start_sharepoint_worker"`.
- **Status**: [x]

---

### Step 17 — Implement the plugin router

- **Layer**: router (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/router.py` — create
- **What**:
  Create a FastAPI `APIRouter()`. All routes use `Depends(get_current_user_oauth)` for auth and `Depends(require_min_role(...))` for RBAC. Import both from the same paths as other internal routers: `from routers.internal.auth_utils import get_current_user_oauth` and `from routers.controls.role_authorization import require_min_role, AppRole`.

  **SharePoint Sources CRUD** (all under `/apps/{app_id}/sharepoint-sources`):

  - `GET /apps/{app_id}/sharepoint-sources` → `VIEWER` → calls `SharePointSourceService.list_sources(app_id, db)` → returns `list[SharePointSourceResponse]`.
  - `POST /apps/{app_id}/sharepoint-sources` → `EDITOR` → body `SharePointSourceCreateRequest` → calls `SharePointSourceService.create_source(app_id, data, db)` → 201 + `SharePointSourceResponse`.
  - `GET /apps/{app_id}/sharepoint-sources/{source_id}` → `VIEWER` → returns `SharePointSourceDetailResponse`.
  - `PUT /apps/{app_id}/sharepoint-sources/{source_id}` → `EDITOR` → body `SharePointSourceUpdateRequest` → returns `SharePointSourceResponse`.
  - `DELETE /apps/{app_id}/sharepoint-sources/{source_id}` → `ADMINISTRATOR` → calls `SharePointSourceService.delete_source(source_id, app_id, db)` → 204.
  - `POST /apps/{app_id}/sharepoint-sources/{source_id}/sync` → `EDITOR`:
    1. Fetch source; 404 if not found.
    2. If `last_sync_status == RUNNING` → 409.
    3. `await enqueue_sync(source_id)` (from worker module).
    4. Return 202 + `SyncTriggerResponse`.

  **Microsoft Graph helpers** (no `app_id` path parameter — authenticated user only):

  - `GET /microsoft/sites` query params: `tenant_id`, `client_id`, `client_secret`, `q` → `EDITOR` (use a generic app RBAC check if possible, or just require authenticated user since credentials are in the request):
    — Since these endpoints do not have `app_id` we cannot use the `require_min_role` dependency that needs `app_id`. Use only `Depends(get_current_user_oauth)`.
    — Acquire token, call `GraphClient.search_sites(token, q)`, return `list[MicrosoftSiteResponse]`.

  - `GET /microsoft/drives` query params: `tenant_id`, `client_id`, `client_secret`, `site_id` → same pattern → calls `GraphClient.list_drives` → `list[MicrosoftDriveResponse]`.

  - `POST /microsoft/test-connection` body `TestConnectionRequest` → calls `SharePointSourceService._test_connection` → returns `TestConnectionResponse(ok=True)` or raises `HTTPException(400)`.

  Error mapping in all endpoints:
  - `GraphAuthError` → 400
  - `GraphAccessError` → 400 with `detail=str(e)`
  - `HTTPException` re-raised as-is
  - Other exceptions → 500

  Tag all routes with `["SharePoint"]`.
- **Acceptance**: `python -c "from mattin_sharepoint.router import router; print(len(router.routes))"` prints 9 (or more). No import errors.
- **Status**: [x]

---

### Step 18 — Complete plugin.py to mount router and start worker

- **Layer**: service (plugin)
- **Files**:
  - `plugins/mattin_sharepoint/plugin.py` — modify (replace stub)
- **What**:
  Replace the Step 11 stub with the full implementation:

  ```python
  """Plugin entry point. Called by core during FastAPI lifespan."""
  import asyncio
  import importlib.metadata
  from utils.logger import get_logger

  logger = get_logger(__name__)


  def register(app, registry) -> None:
      """Register the SharePoint plugin with the Mattin AI core.

      Called once during FastAPI lifespan startup by the entry-point loader in main.py.
      1. Mounts the SharePoint router under /internal.
      2. Registers a startup event to start the sync worker.
      3. Inserts a descriptor into PluginRegistry.
      """
      from mattin_sharepoint.router import router as sharepoint_router
      app.include_router(sharepoint_router, prefix="/internal", tags=["SharePoint"])

      # Register startup/shutdown worker lifecycle using app.on_event is deprecated;
      # instead, schedule a task via asyncio directly if the event loop is running,
      # or use the router's lifespan approach. For simplicity: store tasks on app.state.
      # The worker is started in the same async context as the plugin loader (lifespan).

      async def _start_worker():
          from mattin_sharepoint.worker import start_sharepoint_worker
          tasks = await start_sharepoint_worker()
          if not hasattr(app.state, 'sharepoint_tasks'):
              app.state.sharepoint_tasks = []
          app.state.sharepoint_tasks.extend(tasks)

      # Schedule the worker start. Since register() is called inside the lifespan
      # async context, we can use asyncio.ensure_future.
      asyncio.ensure_future(_start_worker())

      try:
          version = importlib.metadata.version("mattin-sharepoint")
      except importlib.metadata.PackageNotFoundError:
          version = "dev"

      registry.register("sharepoint", {"enabled": True, "version": version})
      logger.info(f"SharePoint plugin registered (version={version})")
  ```

  Add a shutdown hook: the lifespan in `main.py` already handles `crawl_tasks` — add analogous handling for `sharepoint_tasks` in `main.py` shutdown block (modify `main.py` to check `app.state.sharepoint_tasks` and cancel them):

  ```python
  # In shutdown block of lifespan:
  sharepoint_tasks = getattr(app.state, 'sharepoint_tasks', None)
  if sharepoint_tasks:
      from mattin_sharepoint.worker import stop_sharepoint_worker
      await stop_sharepoint_worker(sharepoint_tasks)
  ```

  Add this to `backend/main.py`.
- **Acceptance**: Install the plugin (`pip install -e plugins/`) and start the app — `GET /internal/capabilities` returns `{"sharepoint": {"enabled": true, "version": "0.1.0"}}`. SharePoint routes appear in `/docs/internal`.
- **Status**: [x]

---

### Step 19 — Install mattin-sharepoint as a dev dependency and verify end-to-end

- **Layer**: (infrastructure)
- **Files**:
  - `pyproject.toml` — modify (add dev dependency)
- **What**:
  Add to `[tool.poetry.dependencies]` (or a `[tool.poetry.group.dev.dependencies]` section — prefer dev group to keep it optional):

  ```toml
  [tool.poetry.group.sharepoint.dependencies]
  mattin-sharepoint = {path = "plugins", develop = true}
  ```

  Run `poetry install --with sharepoint` to make the entry point available to the Python environment.

  Verify:
  1. `python -c "import importlib.metadata; eps = list(importlib.metadata.entry_points(group='mattin.plugins')); print(eps)"` — shows one entry for `sharepoint`.
  2. Start the app and confirm `GET /internal/capabilities` returns the registry with `sharepoint.enabled = true`.
- **Acceptance**: Entry point loads cleanly and router mounts. No startup errors.
- **Status**: [x]

---

### Step 20 — Unit tests: plugin registry, GraphClient, and sync service

- **Layer**: test (unit)
- **Files**:
  - `tests/unit/plugins/__init__.py` — create (empty)
  - `tests/unit/plugins/test_plugin_registry.py` — create
  - `tests/unit/plugins/test_graph_client.py` — create
  - `tests/unit/plugins/test_sharepoint_sync_service.py` — create
- **What**:
  **`test_plugin_registry.py`**: Test `PluginRegistry` in isolation (no DB, no HTTP):
  - `test_register_and_get`: register a plugin, verify `get()` returns descriptor.
  - `test_is_enabled_true` / `test_is_enabled_false`: register with `enabled=True`/`False`, verify `is_enabled`.
  - `test_all_returns_copy`: verify `all()` returns a copy (mutating it doesn't affect registry).
  - `test_fake_entry_point_loading`: mock `importlib.metadata.entry_points` to return a fake entry point whose `load()` returns a function that calls `registry.register("fake", {"enabled": True})`. Instantiate a fresh `PluginRegistry`, run the loader loop from `main.py` inline. Assert `plugin_registry.is_enabled("fake")`.

  **`test_graph_client.py`**: All HTTP mocked via `respx` (or `unittest.mock.patch` on `httpx.AsyncClient`). Use `pytest-anyio` or `anyio` for async tests.
  - `test_get_token_success`: mock POST to token endpoint, verify token returned.
  - `test_get_token_failure`: mock 400 response, verify `GraphAuthError` raised.
  - `test_delta_query_initial`: mock delta endpoint with two pages (nextLink then deltaLink), verify all items collected, delta token extracted.
  - `test_delta_query_incremental`: mock delta URL call (with stored token in URL), verify correct URL used.
  - `test_delta_query_410`: mock 410 response, verify `GraphDeltaExpiredError` raised.
  - `test_search_sites`: mock Graph sites endpoint, verify list returned.
  - `test_list_drives`: mock Graph drives endpoint.

  **`test_sharepoint_sync_service.py`**: Mock `GraphClient`, `SiloService`, and the DB session (using `MagicMock`). No real DB.
  - `test_first_run_full_sync_indexes_files`: mock delta returning 2 file items, verify `SiloService.index_multiple_content` called twice, `SharePointFile` upserted.
  - `test_incremental_run_uses_delta_token`: source has existing `last_delta_token`, verify delta query called with that token.
  - `test_deleted_items_remove_rows_and_vectors`.
  - `test_filter_exclusion_removes_previously_indexed_files`.
  - `test_per_file_errors_mark_sync_partial`.
  - `test_410_gone_clears_delta_token_and_restarts`.
  - `test_test_connection_happy_path`.
  - `test_test_connection_auth_failure_maps_to_400`.

  Use `@pytest.mark.anyio` or `asyncio.run()` for async tests. All imports from `mattin_sharepoint` package.
- **Acceptance**: `pytest tests/unit/plugins/ -v` passes (all tests green).
- **Status**: [x]

---

### Step 21 — Integration tests: SharePoint sources CRUD and RBAC

- **Layer**: test (integration)
- **Files**:
  - `tests/integration/routers/internal/test_sharepoint_sources.py` — create
  - `tests/conftest.py` — modify (add `sharepoint_source_factory` and `sharepoint_file_factory` fixtures + `mock_graph_client`)
- **What**:
  **Conftest additions** (add to `tests/conftest.py`):

  - `fake_silo(db)` fixture: create a `Silo` linked to `fake_app`, flush. (Check if already exists; if not, add it.)
  - `fake_sharepoint_source(db, fake_app, fake_silo)` fixture:
    ```python
    from models.sharepoint_source import SharePointSource
    source = SharePointSource(
        app_id=fake_app.app_id,
        silo_id=fake_silo.silo_id,
        name="Test SP Source",
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
        site_id="test-site",
        drive_id="test-drive",
    )
    db.add(source)
    db.flush()
    return source
    ```
  - `fake_sharepoint_file(db, fake_sharepoint_source)` fixture: create a `SharePointFile` with `drive_item_id="item1"`, `status=PENDING`, linked to `fake_sharepoint_source`.
  - `mock_graph_client` fixture: use `unittest.mock.patch` to mock `mattin_sharepoint.service.GraphClient` with a `MagicMock`. Provide canned async returns for `get_token`, `verify_drive_access`.

  **Test class `TestSharePointSourcesCRUD`**:
  - `test_list_sources_empty`: GET list returns 200 + empty array.
  - `test_create_source_success`: POST with valid body (mock graph client for test-connection pass) → 201, response has expected fields, no `client_secret`.
  - `test_create_source_bad_credentials`: POST with creds that fail test-connection → 400.
  - `test_get_source_detail`: GET with `fake_sharepoint_source` → 200, `file_count` correct.
  - `test_update_source_name`: PUT changing name only → 200.
  - `test_update_source_credentials_fail`: PUT with bad new creds → 400, source unchanged.
  - `test_delete_source`: DELETE → 204, subsequent GET → 404.

  **Test class `TestSharePointSourcesRBAC`**:
  - `test_viewer_cannot_create`: POST with VIEWER-level headers → 403.
  - `test_editor_cannot_delete`: DELETE with EDITOR-level headers → 403.
  - `test_administrator_can_delete`.

  **Test class `TestSharePointSyncEndpoint`**:
  - `test_sync_trigger_returns_202`: POST `/sync` → 202.
  - `test_sync_while_running_returns_409`: set source `last_sync_status = RUNNING`, POST `/sync` → 409.

  **Test class `TestCapabilitiesEndpoint`**:
  - `test_capabilities_unauthenticated_returns_401`.
  - `test_capabilities_authenticated_without_plugin_returns_empty_dict`: use a test app with registry cleared.
  - `test_capabilities_with_plugin_registered_returns_sharepoint`: manually call `plugin_registry.register("sharepoint", {"enabled": True})` in test, GET → contains `sharepoint`.

  **Test class `TestAppCascadeDeleteWithSharePoint`**:
  - `test_delete_app_removes_sources_and_silo`: create source with silo, delete app, verify source and silo no longer exist.

  **Test class `TestMigrationSchemaState`** (add to existing or create `test_sharepoint_migration.py`):
  - `test_sharepoint_source_table_exists`.
  - `test_sharepoint_file_table_exists`.
  - `test_sharepoint_sync_status_enum_exists`: use `text("SELECT 1 FROM pg_type WHERE typname = 'sharepoint_sync_status'")`.
- **Acceptance**: `pytest tests/integration/routers/internal/test_sharepoint_sources.py -v` passes.
- **Status**: [x]

---

### Step 22 — Frontend: TypeScript types for SharePoint

- **Layer**: frontend
- **Files**:
  - `frontend/src/types/sharepoint.ts` — create
- **What**:
  Define TypeScript interfaces mirroring the Pydantic schemas from Step 11:

  ```typescript
  export type SharePointSyncStatus = 'IDLE' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'ERROR';
  export type SharePointFileStatus = 'PENDING' | 'INDEXED' | 'ERROR';

  export interface SharePointFile {
    id: number;
    drive_item_id: string;
    name: string | null;
    path: string | null;
    web_url: string | null;
    mime_type: string | null;
    size_bytes: number | null;
    last_modified_at: string | null;
    status: SharePointFileStatus;
    last_synced_at: string | null;
    error_message: string | null;
  }

  export interface SharePointSource {
    id: number;
    app_id: number;
    silo_id: number;
    name: string;
    description: string | null;
    tenant_id: string;
    client_id: string;
    site_id: string;
    site_name: string | null;
    site_url: string | null;
    drive_id: string;
    drive_name: string | null;
    file_extension_filters: string[] | null;
    last_synced_at: string | null;
    last_sync_status: SharePointSyncStatus;
    last_sync_error: string | null;
    refresh_interval_minutes: number | null;
    next_run_at: string | null;
    created_at: string;
    updated_at: string;
    file_count: number;
  }

  export interface SharePointSourceDetail extends SharePointSource {
    files: SharePointFile[];
  }

  export interface SharePointSourceCreateRequest {
    name: string;
    description?: string;
    tenant_id: string;
    client_id: string;
    client_secret: string;
    site_id: string;
    site_name?: string;
    site_url?: string;
    drive_id: string;
    drive_name?: string;
    file_extension_filters?: string[];
    embedding_service_id?: number;
    vector_db_type?: string;
    silo_name: string;
  }

  export interface SharePointSourceUpdateRequest {
    name?: string;
    description?: string;
    file_extension_filters?: string[];
    tenant_id?: string;
    client_id?: string;
    client_secret?: string;
  }

  export interface MicrosoftSite {
    id: string;
    name: string;
    web_url: string;
  }

  export interface MicrosoftDrive {
    id: string;
    name: string;
    drive_type: string | null;
  }

  export interface TestConnectionRequest {
    tenant_id: string;
    client_id: string;
    client_secret: string;
    site_id?: string;
    drive_id?: string;
  }

  export interface Capabilities {
    sharepoint?: { enabled: boolean; version?: string };
    [key: string]: { enabled: boolean; version?: string } | undefined;
  }
  ```
- **Acceptance**: `npm run build:lib` (or `npm run lint`) in `frontend/` succeeds with no TypeScript errors.
- **Status**: [x]

---

### Step 23 — Frontend: CapabilitiesContext


- **Layer**: frontend
- **Files**:
  - `frontend/src/contexts/CapabilitiesContext.tsx` — create
- **What**:
  Pattern: copy `DeploymentModeContext.tsx` structure.

  ```tsx
  import React, { createContext, useContext, useState, useEffect } from 'react';
  import type { ReactNode } from 'react';
  import type { Capabilities } from '../types/sharepoint';
  import { configService } from '../core/ConfigService';
  import { authService } from '../services/auth';

  interface CapabilitiesContextType {
    capabilities: Capabilities;
    isLoading: boolean;
    useCapability: (name: string) => boolean;
  }

  const CapabilitiesContext = createContext<CapabilitiesContextType>({
    capabilities: {},
    isLoading: true,
    useCapability: () => false,
  });

  export const useCapabilities = () => useContext(CapabilitiesContext);
  export const useCapability = (name: string): boolean => {
    const { capabilities } = useContext(CapabilitiesContext);
    return capabilities[name]?.enabled === true;
  };

  export const CapabilitiesProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [capabilities, setCapabilities] = useState<Capabilities>({});
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
      const fetchCapabilities = async () => {
        try {
          const token = localStorage.getItem('auth_token');
          if (!token) { setIsLoading(false); return; }
          const baseUrl = configService.getApiBaseUrl();
          const res = await fetch(`${baseUrl}/internal/capabilities`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) setCapabilities(await res.json());
        } catch {
          // Leave capabilities empty — feature gating defaults to hidden
        } finally {
          setIsLoading(false);
        }
      };
      fetchCapabilities();
    }, []);

    const useCapabilityFn = (name: string) => capabilities[name]?.enabled === true;

    return (
      <CapabilitiesContext.Provider value={{ capabilities, isLoading, useCapability: useCapabilityFn }}>
        {children}
      </CapabilitiesContext.Provider>
    );
  };
  ```
- **Acceptance**: No TypeScript errors, linter passes.
- **Status**: [x]

---

### Step 24 — Frontend: SharePoint API client module

- **Layer**: frontend
- **Files**:
  - `frontend/src/services/sharepoint.ts` — create
- **What**:
  All functions use `apiService.request(...)` (the singleton from `api.ts`) — never direct `fetch()`.

  ```typescript
  import { apiService } from './api';
  import type {
    SharePointSource, SharePointSourceDetail, SharePointSourceCreateRequest,
    SharePointSourceUpdateRequest, MicrosoftSite, MicrosoftDrive,
    TestConnectionRequest,
  } from '../types/sharepoint';

  const base = (appId: number) => `/internal/apps/${appId}/sharepoint-sources`;

  export const sharepointApi = {
    listSources: (appId: number): Promise<SharePointSource[]> =>
      apiService.request(base(appId)),

    getSource: (appId: number, sourceId: number): Promise<SharePointSourceDetail> =>
      apiService.request(`${base(appId)}/${sourceId}`),

    createSource: (appId: number, data: SharePointSourceCreateRequest): Promise<SharePointSource> =>
      apiService.request(base(appId), { method: 'POST', body: JSON.stringify(data) }),

    updateSource: (appId: number, sourceId: number, data: SharePointSourceUpdateRequest): Promise<SharePointSource> =>
      apiService.request(`${base(appId)}/${sourceId}`, { method: 'PUT', body: JSON.stringify(data) }),

    deleteSource: (appId: number, sourceId: number): Promise<null> =>
      apiService.request(`${base(appId)}/${sourceId}`, { method: 'DELETE' }),

    triggerSync: (appId: number, sourceId: number): Promise<{ message: string; source_id: number; status: string }> =>
      apiService.request(`${base(appId)}/${sourceId}/sync`, { method: 'POST' }),

    searchSites: (params: { tenant_id: string; client_id: string; client_secret: string; q: string }): Promise<MicrosoftSite[]> => {
      const qs = new URLSearchParams(params as Record<string, string>).toString();
      return apiService.request(`/internal/microsoft/sites?${qs}`);
    },

    listDrives: (params: { tenant_id: string; client_id: string; client_secret: string; site_id: string }): Promise<MicrosoftDrive[]> => {
      const qs = new URLSearchParams(params as Record<string, string>).toString();
      return apiService.request(`/internal/microsoft/drives?${qs}`);
    },

    testConnection: (data: TestConnectionRequest): Promise<{ ok: boolean; error?: string }> =>
      apiService.request('/internal/microsoft/test-connection', { method: 'POST', body: JSON.stringify(data) }),
  };
  ```
- **Acceptance**: `npm run lint` passes. TypeScript compilation succeeds.
- **Status**: [x]

---

### Step 25 — Frontend: SharePoint list page

- **Layer**: frontend
- **Files**:
  - `frontend/src/pages/SharePointSourcesPage.tsx` — create
- **What**:
  Functional component. Pattern: copy `DomainsPage.tsx` structure (useEffect to load, table with action dropdown, delete with confirm dialog).

  State: `sources: SharePointSource[]`, `loading: boolean`, `error: string | null`.

  Table columns:
  - **Name** — text
  - **Site / Drive** — `{source.site_name} / {source.drive_name}` (or IDs if names null)
  - **Status** — badge component with colour coding:
    - IDLE → grey, RUNNING → blue (spinner), SUCCESS → green, PARTIAL → amber, ERROR → red
  - **Last synced** — relative time (e.g. "2 hours ago") with absolute timestamp in tooltip. Use `Date` API for relative formatting.
  - **Files** — `source.file_count`
  - **Actions** — dropdown with: "Sync now" (POST `/sync`; disabled + spinner when RUNNING), "Edit" (navigate to detail page), "Delete" (confirm modal).

  "Add SharePoint Source" button → opens the 3-step wizard (Step 26). For now wire to `navigate('/apps/:appId/sharepoint/new')` — the route will be added in Step 28.

  Use `useParams<{ appId: string }>()`, `useNavigate()`, `useConfirm()`, `useApiMutation()`, `useAppRole()` — same hooks as `DomainsPage`.

  RBAC: show Add/Sync/Delete based on `hasMinRole(AppRole.EDITOR)` / `hasMinRole(AppRole.ADMINISTRATOR)`.
- **Acceptance**: Component renders (no runtime errors). Visible at `/apps/:appId/sharepoint` once route is wired in Step 28.
- **Status**: [x]

---

### Step 26 — Frontend: 3-step creation wizard

- **Layer**: frontend
- **Files**:
  - `frontend/src/pages/SharePointWizardPage.tsx` — create
- **What**:
  Three-step form component using local state `step: 1 | 2 | 3` and accumulated form data.

  **Step 1 — Connect**:
  - Fields: `name` (text), `description` (textarea optional), `tenant_id` (text), `client_id` (text), `client_secret` (password).
  - "Next" button: `onClick` → call `sharepointApi.testConnection({tenant_id, client_id, client_secret})` → if `ok=true`, advance to step 2; if error, show error alert and stay on step 1.
  - Show spinner while waiting.

  **Step 2 — Choose drive**:
  - Site autocomplete: debounced input (300ms) calls `sharepointApi.searchSites({...creds, q})`. Shows dropdown of `MicrosoftSite[]`. On select, set `site_id`, `site_name`, `site_url`, then call `sharepointApi.listDrives({...creds, site_id})` to populate drive list.
  - Drive selector: radio list or select of `MicrosoftDrive[]`. On select, set `drive_id`, `drive_name`.
  - "Next" disabled until both site and drive selected.

  **Step 3 — Configure indexing**:
  - `silo_name` (text, pre-filled with `name` from step 1).
  - Embedding service selector: fetch `/internal/apps/{appId}/embedding-services` (use `apiService.getEmbeddingServices(appId)`) → select dropdown.
  - Vector DB type selector: `PGVECTOR` / `QDRANT` (match pattern from `DomainFormPage`).
  - File extension filters: tag input — user types an extension (e.g., `pdf`) and presses Enter to add to a `string[]` list; shows tags with remove button. Optional — if empty, no filter applied.
  - "Create" button: calls `sharepointApi.createSource(appId, fullPayload)` → on success, navigate to list page; on error, show alert.

  Progress indicator at top showing step 1/2/3. "Back" button on steps 2 and 3. Entire wizard is a single page component.
- **Acceptance**: Component renders. Can navigate steps (mock API calls in dev mode).
- **Status**: [x]

---

### Step 27 — Frontend: SharePoint source detail/edit page

- **Layer**: frontend
- **Files**:
  - `frontend/src/pages/SharePointSourceDetailPage.tsx` — create
- **What**:
  Single-page detail + edit. Fetch source on load via `sharepointApi.getSource(appId, sourceId)`.

  Sections (collapsible or separate form groups):

  **General**: `name` (editable input), `description` (textarea). Save button → `sharepointApi.updateSource(appId, sourceId, {name, description})`.

  **SharePoint connection** (read-only + credential update):
  - Read-only: `site_name`, `site_url`, `drive_name`.
  - Editable (masked): `tenant_id`, `client_id`, `client_secret` (password field, placeholder "Leave blank to keep current"). If user types in any credential field, show "Credentials will be validated on save" notice.
  - Save → PUT with only changed credential fields. Server validates via test-connection. On 400 (credential validation failed), show inline error.

  **Indexing config**:
  - File extension filters: same tag input as wizard. Save → PUT with `file_extension_filters`.
  - Silo name + vector DB: read-only (display only).

  **Sync status** panel:
  - `last_sync_status` badge (same colour coding as list page).
  - `last_synced_at` relative + absolute.
  - `last_sync_error` (red text block, shown only if non-null).
  - `file_count`.
  - Auto-refresh: poll every 5 seconds while `last_sync_status == RUNNING` (use `useEffect` with `setInterval`; clear on unmount or when status leaves RUNNING).

  **"Sync now"** button (prominent, primary variant):
  - Disabled + spinner when `last_sync_status == RUNNING`.
  - On click: `sharepointApi.triggerSync(appId, sourceId)` → on 409 show "Already syncing" toast; on 202 show "Sync started" toast and set local status to RUNNING.

  **Danger zone** (bottom, red border):
  - "Delete source" button → confirm modal: "This will delete all indexed content from the silo. This action cannot be undone." → on confirm: `sharepointApi.deleteSource(appId, sourceId)` → navigate to list page.
- **Acceptance**: Component renders and loads data from the API. All save/sync/delete actions fire the correct API calls.
- **Status**: [x]

---

### Step 28 — Frontend: route registration, navigation, and CapabilitiesProvider wiring

- **Layer**: frontend
- **Files**:
  - `frontend/src/core/ExtensibleBaseApp.tsx` — modify
  - `frontend/src/core/defaultNavigation.tsx` — modify
  - `frontend/src/core/ExtensibleBaseApp.tsx` — modify (CapabilitiesProvider wrap)
- **What**:
  **`ExtensibleBaseApp.tsx`**:

  1. Import new pages:
     ```tsx
     import SharePointSourcesPage from '../pages/SharePointSourcesPage';
     import SharePointWizardPage from '../pages/SharePointWizardPage';
     import SharePointSourceDetailPage from '../pages/SharePointSourceDetailPage';
     ```
  2. Import `CapabilitiesProvider` and `useCapability`:
     ```tsx
     import { CapabilitiesProvider, useCapability } from '../contexts/CapabilitiesContext';
     ```
  3. Wrap the provider tree: add `<CapabilitiesProvider>` inside `<PlatformChatbotProvider>` (or at the same level as `DeploymentModeProvider`).
  4. Add capability-gated routes inside the app routes section. Use an inner component or inline condition:
     ```tsx
     {/* SharePoint routes — only rendered when plugin is installed */}
     <Route path="/apps/:appId/sharepoint" element={
       <CapabilityGate name="sharepoint" fallback={<Navigate to={`/apps/${appId}`} replace />}>
         <ProtectedLayoutRoute {...commonLayoutProps}>
           <SharePointSourcesPage />
         </ProtectedLayoutRoute>
       </CapabilityGate>
     } />
     <Route path="/apps/:appId/sharepoint/new" element={...} />
     <Route path="/apps/:appId/sharepoint/:sourceId" element={...} />
     ```
     Create a simple `CapabilityGate` component in `frontend/src/components/CapabilityGate.tsx`:
     ```tsx
     import { useCapability } from '../contexts/CapabilitiesContext';
     export const CapabilityGate: React.FC<{name: string; fallback?: ReactNode; children: ReactNode}> = ({name, fallback, children}) => {
       const enabled = useCapability(name);
       const { isLoading } = useCapabilities();
       if (isLoading) return null; // avoid flash
       return enabled ? <>{children}</> : <>{fallback}</>;
     };
     ```

  **`defaultNavigation.tsx`**:

  Add a SharePoint nav entry to `appNavigation` array. Because the nav is rendered unconditionally from `defaultNavigation`, and feature-gating is done by conditionally rendering the entry:

  The nav system may not support per-item capability checks today. Two options:
  1. Add the entry unconditionally and rely on the route-level gate (clicking nav goes to list, which redirects if not enabled).
  2. Add a `capabilityGate: 'sharepoint'` field to the nav item type and filter in the layout component.

  For MVP: use option 1 (simpler, avoids touching the nav type system). Add after Domains:

  ```tsx
  {
    path: '/apps/:appId/sharepoint',
    name: 'SharePoint',
    icon: <SharepointIcon />,  // use lucide `Cloud` or `Database` — pick an available icon
    section: 'appNavigation'
  }
  ```

  Import `Cloud` from `lucide-react` for the icon (not yet used in the nav, acceptable).
- **Acceptance**: `npm run build:lib` completes without errors. SharePoint nav item appears in the sidebar. Navigating to `/apps/:appId/sharepoint` shows the list page (or redirects to dashboard when plugin not installed due to empty capabilities).
- **Status**: [x]

---

## Dependency Graph (summary)

```
01 (enums) → 03 (SharePointSource model) → 05 (register models)
           → 04 (SharePointFile model)   ↗
02 (migration) — independent, must precede 03/04 only for DB existence
05 → 09 (source repo) → 08 (app_service cascade)
   → 10 (file repo)
06 (registry) → 07 (capabilities endpoint + lifespan wiring)
11 (plugin scaffold + schemas) → 12 (GraphClient) → 14 (services) → 15 (sync service) → 16 (worker) → 17 (router) → 18 (plugin.py complete)
13 (plugin repo module) requires 09, 10
14 requires 12, 13
17 requires 14, 15, 16
18 requires 17
19 (install plugin) requires 11-18
20 (unit tests) requires 06, 12, 15
21 (integration tests) requires 07, 09, 10, 17, 18, 19 (plugin installed)
22 (TS types) — independent
23 (CapabilitiesContext) requires 22
24 (sharepoint.ts API) requires 22
25 (list page) requires 22, 24
26 (wizard page) requires 22, 24
27 (detail page) requires 22, 24
28 (routing + nav) requires 23, 25, 26, 27
```

---

## Notes on Plugin Installation in Tests

Integration tests (Step 21) require the `mattin-sharepoint` plugin to be installed. The plugin must be installed in editable mode (`pip install -e plugins/` or `poetry install --with sharepoint`) before running integration tests that exercise the SharePoint endpoints. Tests that test the registry in isolation (Step 20) do not require the plugin to be installed — they register directly via `plugin_registry.register(...)`.

The integration test conftest must patch or disable entry-point loading during test startup to avoid side effects from plugin worker threads. Suggested approach: in the test fixture that creates the TestClient, patch `importlib.metadata.entry_points` to return an empty list (preventing any plugin from auto-loading via lifespan), then manually register `sharepoint` into `plugin_registry` for capability tests.

---

## Files Changed / Created Summary

| Path | Change |
|---|---|
| `backend/models/enums/sharepoint_sync_status.py` | create |
| `backend/models/enums/sharepoint_file_status.py` | create |
| `alembic/versions/spoint001_sharepoint_sync_tables.py` | create |
| `backend/models/sharepoint_source.py` | create |
| `backend/models/sharepoint_file.py` | create |
| `backend/models/__init__.py` | modify |
| `backend/models/app.py` | modify (add relationship) |
| `backend/plugins/__init__.py` | create |
| `backend/plugins/registry.py` | create |
| `backend/main.py` | modify (plugin loading + shutdown) |
| `backend/routers/internal/capabilities.py` | create |
| `backend/routers/internal/__init__.py` | modify |
| `backend/services/app_service.py` | modify (cascade step 5b) |
| `backend/repositories/sharepoint_source_repository.py` | create |
| `backend/repositories/sharepoint_file_repository.py` | create |
| `plugins/pyproject.toml` | create |
| `plugins/mattin_sharepoint/__init__.py` | create |
| `plugins/mattin_sharepoint/plugin.py` | create |
| `plugins/mattin_sharepoint/schemas.py` | create |
| `plugins/mattin_sharepoint/graph_client.py` | create |
| `plugins/mattin_sharepoint/repository.py` | create |
| `plugins/mattin_sharepoint/service.py` | create |
| `plugins/mattin_sharepoint/worker.py` | create |
| `plugins/mattin_sharepoint/router.py` | create |
| `pyproject.toml` | modify (sharepoint group) |
| `tests/unit/plugins/__init__.py` | create |
| `tests/unit/plugins/test_plugin_registry.py` | create |
| `tests/unit/plugins/test_graph_client.py` | create |
| `tests/unit/plugins/test_sharepoint_sync_service.py` | create |
| `tests/integration/routers/internal/test_sharepoint_sources.py` | create |
| `tests/conftest.py` | modify (new fixtures) |
| `frontend/src/types/sharepoint.ts` | create |
| `frontend/src/contexts/CapabilitiesContext.tsx` | create |
| `frontend/src/components/CapabilityGate.tsx` | create |
| `frontend/src/services/sharepoint.ts` | create |
| `frontend/src/pages/SharePointSourcesPage.tsx` | create |
| `frontend/src/pages/SharePointWizardPage.tsx` | create |
| `frontend/src/pages/SharePointSourceDetailPage.tsx` | create |
| `frontend/src/core/ExtensibleBaseApp.tsx` | modify |
| `frontend/src/core/defaultNavigation.tsx` | modify |
