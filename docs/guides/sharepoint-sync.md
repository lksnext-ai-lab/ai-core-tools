# SharePoint Sync

> Part of [Mattin AI Documentation](../README.md)

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
- [Architecture](#architecture)

---

## Prerequisites

- A Microsoft Azure tenant with an **App Registration** (service principal) that has the `Files.Read.All` Microsoft Graph application permission (see below).

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
| `PUT` | `/internal/apps/{app_id}/sharepoint-sources/{id}` | Update source |
| `DELETE` | `/internal/apps/{app_id}/sharepoint-sources/{id}` | Delete source and its silo |
| `POST` | `/internal/apps/{app_id}/sharepoint-sources/{id}/sync` | Trigger manual sync |
| `GET` | `/internal/microsoft/sites` | Search SharePoint sites by keyword |
| `GET` | `/internal/microsoft/resolve-site` | Resolve a SharePoint site by URL |
| `GET` | `/internal/microsoft/drives` | List drives for a resolved site |
| `POST` | `/internal/microsoft/test-connection` | Test Azure credentials |

---

## Architecture

### Backend

```
backend/
├── routers/internal/sharepoint.py      # Sources CRUD + sync trigger + Microsoft Graph helpers (/internal/...)
├── schemas/sharepoint_schemas.py       # Pydantic request/response models
├── services/sharepoint/
│   ├── graph_client.py                 # Microsoft Graph API client (token, delta, download, site resolution)
│   ├── service.py                      # SharePointSourceService (CRUD) + SharePointSyncService (delta sync loop)
│   └── worker.py                       # asyncio.Queue-based background sync worker
├── repositories/sharepoint_source_repository.py
├── repositories/sharepoint_file_repository.py
└── models/sharepoint_source.py, models/sharepoint_file.py
```

The router is mounted inside the internal router, so it gets the same CSRF check and viewer write block as every other internal endpoint. The sync worker starts and stops with the other background workers in the `backend/main.py` lifespan.

### Frontend

`SharePointSourcesPage`, `SharePointWizardPage` and `SharePointSourceDetailPage` are regular app pages, reachable from the **SharePoint** entry in the app sidebar. API calls go through `frontend/src/services/sharepoint.ts`.
