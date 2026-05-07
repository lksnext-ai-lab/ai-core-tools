# SharePoint Sync

> Part of [Mattin AI Documentation](../README.md) · Enterprise Edition module

SharePoint Sync lets you index content from Microsoft SharePoint and OneDrive drives directly into a Mattin AI silo, keeping it up to date via Microsoft Graph API **delta queries** (incremental sync — only changed files are re-processed after the first run).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Azure App Registration](#azure-app-registration)
- [Creating a SharePoint Source](#creating-a-sharepoint-source)
- [Sync Behaviour](#sync-behaviour)
- [File Extension Filters](#file-extension-filters)
- [Supported File Types](#supported-file-types)
- [Chunk Metadata](#chunk-metadata)
- [API Endpoints](#api-endpoints)
- [Plugin Installation](#plugin-installation)
- [Architecture](#architecture)

---

## Prerequisites

- A Microsoft Azure tenant with an **App Registration** (service principal) that has the `Files.Read.All` Microsoft Graph application permission (see below).
- The `mattin-sharepoint` backend plugin installed (Enterprise Edition — see [Plugin Installation](#plugin-installation)).

---

## Azure App Registration

Create a dedicated App Registration in [Azure Portal](https://portal.azure.com) → **Entra ID → App registrations → New registration**.

### Required API Permission

| API | Permission | Type |
|-----|-----------|------|
| Microsoft Graph | `Files.Read.All` | Application |

After adding the permission, click **Grant admin consent** for your tenant.

### Credentials you will need

| Field | Where to find it |
|-------|-----------------|
| **Tenant ID** | Entra ID → Overview → Tenant ID |
| **Client ID** | App Registration → Overview → Application (client) ID |
| **Client Secret** | App Registration → Certificates & secrets → New client secret |

> No delegated permissions or user interaction is required. The connector uses the **client credentials** (app-only) OAuth 2.0 flow.

---

## Creating a SharePoint Source

Navigate to your app → **Data → SharePoint** → **Add SharePoint Source**.

The wizard has three steps:

### Step 1 — Credentials

Enter the **Tenant ID**, **Client ID**, and **Client Secret**. The wizard validates connectivity before proceeding.

### Step 2 — Site & Drive

Enter the full SharePoint site URL (e.g. `https://contoso.sharepoint.com/sites/MyTeam`). Click **Load** to resolve the site and list its available drives. Select the drive to index.

> Site resolution uses `GET /sites/{hostname}:{path}` — no tenant-wide admin consent required.

### Step 3 — Silo & Filters

| Field | Description |
|-------|-------------|
| **Name** | Display name for this source |
| **Silo name** | A new dedicated silo is created and linked to this source |
| **Embedding service** | Embedding model used to vectorise content |
| **Vector DB** | PGVector or Qdrant |
| **File extension filters** | Optional whitelist (e.g. `pdf`, `docx`). Leave empty to index all supported types |

---

## Sync Behaviour

Sync is driven by the **Microsoft Graph delta API** (`GET /drives/{id}/root/delta`).

| Run | What happens |
|-----|-------------|
| **First sync** | Full scan of the drive — every file is downloaded and indexed |
| **Subsequent syncs** | Only items changed since the last run are processed (delta token) |
| **Deleted file** | Vectors are removed from the silo and the file record is deleted |
| **Delta token expired** | Graph returns `410 Gone` — the connector automatically falls back to a full re-scan |

### Sync Statuses

| Status | Meaning |
|--------|---------|
| `IDLE` | No sync has run yet, or last sync finished cleanly |
| `RUNNING` | Sync is currently in progress |
| `SUCCESS` | Last sync completed with no file-level errors |
| `PARTIAL` | Sync finished but one or more individual files failed |
| `ERROR` | Sync itself failed (auth error, network error, etc.) |

Manual sync can be triggered from the source detail page or via `POST /internal/apps/{app_id}/sharepoint-sources/{id}/sync`.

---

## File Extension Filters

Filters are stored as a list of extensions **without** the leading dot (e.g. `["pdf", "docx"]`).

- **Empty list** — all supported file types are indexed.
- **Non-empty list** — only matching extensions are indexed; files previously indexed under a removed extension are de-indexed automatically.
- **Adding a new extension** to the filter resets the delta token on save, so the next sync does a full re-scan and picks up pre-existing files that match the new extension.

---

## Supported File Types

The connector can only vectorise file types the extraction pipeline handles:

| Extension | Format |
|-----------|--------|
| `pdf` | PDF documents |
| `docx` | Microsoft Word |
| `txt` | Plain text |
| `md` | Markdown |

Files with other extensions (`.xlsx`, `.png`, `.aspx`, etc.) are silently skipped — they are never downloaded or stored.

---

## Chunk Metadata

Every vector chunk produced by a sync run carries enough metadata to reconstruct the original SharePoint URL:

```json
{
  "source": "sharepoint",
  "source_id": 1,
  "drive_item_id": "01ABC...",
  "file_name": "report.pdf",
  "file_path": "Marketing/Q1/report.pdf",
  "web_url": "https://contoso.sharepoint.com/sites/MyTeam/Shared%20Documents/Marketing/Q1/report.pdf",
  "site_url": "https://contoso.sharepoint.com/sites/MyTeam",
  "drive_id": "b!abc..."
}
```

---

## API Endpoints

All endpoints require session or OIDC authentication and are scoped to an app.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/internal/apps/{app_id}/sharepoint-sources` | List sources |
| `POST` | `/internal/apps/{app_id}/sharepoint-sources` | Create source (validates credentials) |
| `GET` | `/internal/apps/{app_id}/sharepoint-sources/{id}` | Get source detail with file list |
| `PATCH` | `/internal/apps/{app_id}/sharepoint-sources/{id}` | Update source |
| `DELETE` | `/internal/apps/{app_id}/sharepoint-sources/{id}` | Delete source and its silo |
| `POST` | `/internal/apps/{app_id}/sharepoint-sources/{id}/sync` | Trigger manual sync |
| `GET` | `/internal/microsoft/resolve-site` | Resolve a SharePoint site by URL |
| `GET` | `/internal/microsoft/drives` | List drives for a resolved site |
| `POST` | `/internal/microsoft/test-connection` | Test Azure credentials |

---

## Plugin Installation

The SharePoint connector is an **Enterprise Edition** module. It ships as a separate Python package (`mattin-sharepoint`) that lives in the private `mattin-ai-plugins` repository, side-by-side with `ai-core-tools`:

```
LKS/IA-Core-Tools/
├── ai-core-tools/        ← this repo
└── mattin-ai-plugins/    ← private EE plugins repo (clone separately)
```

If you do not have access to `mattin-ai-plugins`, simply skip these steps — the backend runs fine without the plugin. The capabilities endpoint will omit `sharepoint` and the sidebar will show **SharePoint [EE]**.

---

### First-time setup

**Step 1 — Clone the plugins repo** (side-by-side, same parent directory):

```bash
git clone <mattin-ai-plugins-url> ../mattin-ai-plugins
```

**Step 2 — Install via Poetry:**

```bash
# From the ai-core-tools root
poetry install --with sharepoint
```

**Step 3 — Switch to editable (in-place) install:**

```bash
poetry run pip install -e ../mattin-ai-plugins/
```

> `poetry install --with sharepoint` copies the plugin into `.venv/site-packages/`. Step 3 replaces that static copy with a direct link to the source tree. **Without step 3, code changes in `mattin-ai-plugins/` are invisible to the backend.**

**Step 4 — Verify:**

```bash
# Should print the path inside mattin-ai-plugins/, not site-packages/
poetry run python -c "import mattin_sharepoint; print(mattin_sharepoint.__file__)"
# ✓ .../mattin-ai-plugins/mattin_sharepoint/__init__.py   ← editable (correct)
# ✗ .../site-packages/mattin_sharepoint/__init__.py        ← static copy (redo step 3)

# Capability visible in API
curl http://localhost:8000/internal/capabilities
# → {"sharepoint": true, ...}
```

In the frontend sidebar the entry shows as **SharePoint** (without a badge).

---

### Development workflow

Once the editable install is active:

- **Editing plugin source** (`mattin-ai-plugins/mattin_sharepoint/*.py`) — changes take effect on the **next backend restart**. No reinstall needed.
- **After `poetry install`** (e.g. pulling new dependencies) — Poetry re-copies the static version, overwriting the editable link. Re-run step 3:
  ```bash
  poetry run pip install -e ../mattin-ai-plugins/
  ```
- **After `git pull` in `mattin-ai-plugins/`** — no action needed; the editable install already points to the live source.

---

### Uninstall

```bash
poetry remove mattin-sharepoint --group sharepoint
```

Restart the backend. The plugin is no longer loaded — the capabilities endpoint no longer includes `sharepoint`, and the sidebar entry changes to **SharePoint [EE]** which redirects users to the Enterprise Edition info page.

### Reinstall after removal

```bash
poetry install --with sharepoint
poetry run pip install -e ../mattin-ai-plugins/
```

---

### Client / production install

For clients who have purchased the EE plugin, swap the dependency in `pyproject.toml` from the local path to the private Git URL before deploying:

```toml
[tool.poetry.group.sharepoint.dependencies]
# mattin-sharepoint = {path = "../mattin-ai-plugins", develop = true}  # local dev
mattin-sharepoint = {git = "https://github.com/lks/mattin-ai-plugins.git"}  # production
```

The client provides a read-only **deploy key** or **fine-grained PAT** scoped to `mattin-ai-plugins`. Once authentication is configured, the install is the same single command — no editable install step needed:

```bash
poetry install --with sharepoint
```

---

## Architecture

### Backend

```
mattin-ai-plugins/          # side-by-side with ai-core-tools (separate private repo)
└── mattin_sharepoint/
    ├── plugin.py          # Entry point: register(app, registry) — mounts router, starts worker
    ├── graph_client.py    # Microsoft Graph API client (token, delta, download, site resolution)
    ├── service.py         # SharePointSourceService (CRUD) + SharePointSyncService (delta sync loop)
    ├── router.py          # FastAPI router mounted at /internal/apps/{app_id}/sharepoint-sources
    ├── repository.py      # Data access for SharePointSource and SharePointFile
    ├── schemas.py         # Pydantic request/response models
    └── worker.py          # asyncio.Queue-based background sync worker
```

**Plugin discovery** uses Python entry points (`importlib.metadata`). The `pyproject.toml` inside `mattin-ai-plugins/` declares:

```toml
[project.entry-points."mattin.plugins"]
sharepoint = "mattin_sharepoint.plugin:register"
```

`backend/main.py` iterates `importlib.metadata.entry_points(group="mattin.plugins")` at startup and calls each `register(app, registry)` function — zero core changes needed to add a new plugin.

**Database models** (`SharePointSource`, `SharePointFile`) live in the core `backend/models/` directory and are always migrated, regardless of whether the plugin is installed. This means the schema is stable across installs/uninstalls.

### Frontend

The SharePoint EE pattern is built into the base navigation system:

- `NavigationItem.enterpriseFeature` — capability key to check against `GET /internal/capabilities`
- When the capability is absent, the sidebar renders the item with an `[EE]` suffix and links to `/apps/:appId/enterprise?feature=<name>`
- `EnterpriseFeaturePage` is a generic contact/upgrade page — reusable for any future EE module

To add a new Enterprise Edition feature, set `enterpriseFeature: 'your-key'` on its navigation item in `defaultNavigation.tsx`. No other frontend changes are needed.
