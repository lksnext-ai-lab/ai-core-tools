"""SharePoint plugin service layer: CRUD for sources and sync execution."""
from __future__ import annotations

import tempfile
import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from mattin_sharepoint.graph_client import GraphClient, GraphAuthError, GraphAccessError, GraphDeltaExpiredError
from mattin_sharepoint.repository import SharePointSourceRepository, SharePointFileRepository
from mattin_sharepoint.schemas import (
    SharePointSourceResponse,
    SharePointSourceDetailResponse,
    SharePointFileResponse,
)


class SharePointSourceService:
    """CRUD + connection-test operations for SharePointSource objects."""

    @staticmethod
    def list_sources(app_id: int, db: Session) -> list[SharePointSourceResponse]:
        """Return all sources for an app with file counts."""
        sources = SharePointSourceRepository.list_by_app(app_id, db)
        result = []
        for source in sources:
            file_count = SharePointSourceRepository.get_file_count(source.id, db)
            resp = SharePointSourceResponse.model_validate(source)
            resp.file_count = file_count
            result.append(resp)
        return result

    @staticmethod
    def get_source(
        source_id: int,
        app_id: int,
        db: Session,
    ) -> SharePointSourceDetailResponse:
        """Return a single source with its files list. Raises 404 if not found."""
        source = SharePointSourceRepository.get_by_id_and_app(source_id, app_id, db)
        if not source:
            raise HTTPException(status_code=404, detail="SharePoint source not found")
        files = SharePointFileRepository.list_by_source(source_id, db)
        file_count = len(files)
        resp = SharePointSourceDetailResponse.model_validate(source)
        resp.file_count = file_count
        resp.files = [SharePointFileResponse.model_validate(f) for f in files]
        return resp

    @staticmethod
    async def create_source(
        app_id: int,
        data,  # SharePointSourceCreateRequest
        db: Session,
    ) -> SharePointSourceResponse:
        """Validate connection, create silo, persist source. Returns response schema."""
        # 1. Test connection
        try:
            await SharePointSourceService._test_connection(
                data.tenant_id, data.client_id, data.client_secret,
                site_id=None, drive_id=data.drive_id,
            )
        except (GraphAuthError, GraphAccessError) as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

        # 2. Create linked silo
        from services.silo_service import SiloService
        from services.output_parser_service import OutputParserService
        from models.silo import SiloType
        from repositories.silo_repository import SiloRepository
        silo = SiloService.create_or_update_silo(
            {
                'silo_id': 0,
                'name': data.silo_name,
                'description': f'SharePoint silo for {data.name}',
                'status': 'active',
                'app_id': app_id,
                'fixed_metadata': False,
                'embedding_service_id': data.embedding_service_id,
                'vector_db_type': data.vector_db_type,
            },
            SiloType.SHAREPOINT,
            db,
        )

        # 2b. Create default data structure and link to silo
        parser_id = OutputParserService().create_default_filter_for_sharepoint(
            db=db,
            silo_id=silo.silo_id,
            source_name=data.name,
            app_id=app_id,
        )
        silo.metadata_definition_id = parser_id
        SiloRepository.update(silo, db)

        # 3. Create source ORM object
        from models.sharepoint_source import SharePointSource
        source = SharePointSource(
            app_id=app_id,
            silo_id=silo.silo_id,
            name=data.name,
            description=data.description,
            tenant_id=data.tenant_id,
            client_id=data.client_id,
            client_secret=data.client_secret,
            site_id=data.site_id,
            site_name=data.site_name,
            site_url=data.site_url,
            drive_id=data.drive_id,
            drive_name=data.drive_name,
            file_extension_filters=data.file_extension_filters,
        )
        source = SharePointSourceRepository.create(source, db)

        # 4. Build response
        resp = SharePointSourceResponse.model_validate(source)
        resp.file_count = 0
        return resp

    @staticmethod
    async def update_source(
        source_id: int,
        app_id: int,
        data,  # SharePointSourceUpdateRequest
        db: Session,
    ) -> SharePointSourceResponse:
        """Update allowed fields on an existing source. Validates credentials if provided."""
        source = SharePointSourceRepository.get_by_id_and_app(source_id, app_id, db)
        if not source:
            raise HTTPException(status_code=404, detail="SharePoint source not found")

        # Merge credential fields for validation
        new_tenant_id = data.tenant_id if data.tenant_id is not None else source.tenant_id
        new_client_id = data.client_id if data.client_id is not None else source.client_id
        new_client_secret = data.client_secret if data.client_secret is not None else source.client_secret

        credential_changed = any(
            f is not None for f in [data.tenant_id, data.client_id, data.client_secret]
        )
        if credential_changed:
            try:
                await SharePointSourceService._test_connection(
                    new_tenant_id, new_client_id, new_client_secret,
                    site_id=None, drive_id=source.drive_id,
                )
            except (GraphAuthError, GraphAccessError) as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)})
            except Exception as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)})

        # Apply updates (only non-None fields)
        if data.name is not None:
            source.name = data.name
        if data.description is not None:
            source.description = data.description
        if data.file_extension_filters is not None:
            old_filters = set(e.lower().lstrip(".") for e in (source.file_extension_filters or []))
            new_filters = set(e.lower().lstrip(".") for e in data.file_extension_filters)
            # If new extensions were added (filter expanded), reset delta token so the
            # next sync does a full re-scan and picks up pre-existing files.
            if new_filters - old_filters:
                source.last_delta_token = None
            source.file_extension_filters = data.file_extension_filters
        if data.tenant_id is not None:
            source.tenant_id = data.tenant_id
        if data.client_id is not None:
            source.client_id = data.client_id
        if data.client_secret is not None:
            source.client_secret = data.client_secret

        source = SharePointSourceRepository.update(source, db)
        file_count = SharePointSourceRepository.get_file_count(source_id, db)
        resp = SharePointSourceResponse.model_validate(source)
        resp.file_count = file_count
        return resp

    @staticmethod
    def delete_source(source_id: int, app_id: int, db: Session) -> None:
        """Delete a source, its files, and its associated silo. Raises 404/409 as needed."""
        source = SharePointSourceRepository.get_by_id_and_app(source_id, app_id, db)
        if not source:
            raise HTTPException(status_code=404, detail="SharePoint source not found")

        from models.enums.sharepoint_sync_status import SharePointSyncStatus
        if source.last_sync_status == SharePointSyncStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Sync in progress — cannot delete while running")

        silo_id = source.silo_id
        SharePointSourceRepository.delete(source_id, db)  # cascades SharePointFile rows

        if silo_id:
            from services.silo_service import SiloService
            SiloService.delete_silo(silo_id, db)

    @staticmethod
    async def _test_connection(
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_id: Optional[str],
        drive_id: Optional[str],
    ) -> None:
        """Acquire a Graph token and optionally verify drive/site access.

        Raises GraphAuthError or GraphAccessError on failure.
        """
        token = await GraphClient.get_token(tenant_id, client_id, client_secret)
        if drive_id:
            await GraphClient.verify_drive_access(token, drive_id)


# ---------------------------------------------------------------------------
# Sync service (added in Step 15)
# ---------------------------------------------------------------------------

class SharePointSyncService:
    """Executes full/incremental sync runs for a SharePointSource."""

    @staticmethod
    async def run_sync(source_id: int) -> None:
        """Main sync coroutine. Opens its own DB session."""
        from db.database import SessionLocal
        from models.enums.sharepoint_sync_status import SharePointSyncStatus
        from models.enums.sharepoint_file_status import SharePointFileStatus

        db: Session = SessionLocal()
        try:
            source = SharePointSourceRepository.get_by_id(source_id, db)
            if not source:
                return

            # Mark as running
            source.last_sync_status = SharePointSyncStatus.RUNNING
            source.last_sync_error = None
            SharePointSourceRepository.update(source, db)

            # Acquire token
            token = await GraphClient.get_token(
                source.tenant_id, source.client_id, source.client_secret
            )

            # Delta query
            try:
                items, new_delta_token = await GraphClient.delta_query(
                    token, source.drive_id, source.last_delta_token
                )
            except GraphDeltaExpiredError:
                # Token expired — reset and do a full re-sync
                import logging
                logging.getLogger(__name__).warning(
                    f"Delta token expired for source {source_id}; performing full re-sync"
                )
                source.last_delta_token = None
                items, new_delta_token = await GraphClient.delta_query(
                    token, source.drive_id, None
                )

            per_file_errors = False
            allowed_extensions: list[str] = source.file_extension_filters or []

            for item in items:
                item_id = item.get("id", "")

                # Deleted items
                if item.get("deleted") is not None:
                    existing = SharePointFileRepository.get_by_drive_item(source_id, item_id, db)
                    if existing:
                        SharePointSyncService._delete_file_vectors(source.silo_id, existing, db)
                        SharePointFileRepository.delete_file(existing.id, db)
                    continue

                # Folder items — skip
                if item.get("folder") is not None:
                    continue

                # File items
                if item.get("file") is not None:
                    name = item.get("name", "")
                    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    ext_with_dot = f".{ext}" if ext else ""

                    # Extension filter enforcement (filters stored without dot, e.g. ["pdf","docx"])
                    if allowed_extensions:
                        normalised = {e.lower().lstrip(".") for e in allowed_extensions}
                        if ext not in normalised:
                            # Delete any previously indexed version
                            existing = SharePointFileRepository.get_by_drive_item(source_id, item_id, db)
                            if existing:
                                SharePointSyncService._delete_file_vectors(source.silo_id, existing, db)
                                SharePointFileRepository.delete_file(existing.id, db)
                            continue

                    # Skip file types the extraction pipeline cannot handle
                    SUPPORTED_EXTENSIONS = {"pdf", "docx", "txt", "md"}
                    if ext not in SUPPORTED_EXTENSIONS:
                        logger.debug(f"Skipping unsupported file type '{ext}': {name}")
                        continue

                    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext_with_dot)
                    os.close(tmp_fd)
                    try:
                        await GraphClient.download_file(token, source.drive_id, item_id, tmp_path)

                        web_url = item.get("webUrl", "")
                        parent_path = item.get("parentReference", {}).get("path", "")
                        # parentReference.path is like "/drives/{driveId}/root:/Folder/Sub"
                        # Strip the "/drives/{id}/root:" prefix to get the folder path
                        folder_path = parent_path.split("root:", 1)[-1] if "root:" in parent_path else parent_path
                        file_path = f"{folder_path}/{name}".lstrip("/")

                        base_metadata = {
                            "source": "sharepoint",
                            "source_id": source_id,
                            "drive_item_id": item_id,
                            "file_name": name,
                            "file_path": file_path,
                            "web_url": web_url,
                            "site_url": source.site_url or "",
                            "drive_id": source.drive_id,
                        }

                        from services.silo_service import SiloService
                        docs = SiloService.extract_documents_from_file(tmp_path, ext_with_dot, base_metadata)

                        # Convert Document objects to dict format expected by index_multiple_content
                        doc_dicts = []
                        for doc in docs:
                            doc_dicts.append({
                                "content": doc.page_content,
                                "metadata": doc.metadata,
                            })

                        vector_ids = SiloService.index_multiple_content(source.silo_id, doc_dicts, db)

                        SharePointFileRepository.upsert_by_drive_item(
                            source_id=source_id,
                            drive_item_id=item_id,
                            data={
                                "name": name,
                                "path": item.get("parentReference", {}).get("path"),
                                "web_url": item.get("webUrl"),
                                "mime_type": item.get("file", {}).get("mimeType"),
                                "size_bytes": item.get("size"),
                                "last_modified_at": _parse_dt(item.get("lastModifiedDateTime")),
                                "status": SharePointFileStatus.INDEXED,
                                "last_synced_at": datetime.utcnow(),
                                "error_message": None,
                                "vector_doc_ids": vector_ids or [],
                            },
                            db=db,
                        )
                    except Exception as exc:
                        per_file_errors = True
                        SharePointFileRepository.upsert_by_drive_item(
                            source_id=source_id,
                            drive_item_id=item_id,
                            data={
                                "name": name,
                                "status": SharePointFileStatus.ERROR,
                                "error_message": str(exc),
                                "last_synced_at": datetime.utcnow(),
                            },
                            db=db,
                        )
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

            # Filter enforcement pass — remove any files whose extension is no longer allowed
            if allowed_extensions:
                stale_files = SharePointFileRepository.get_files_with_extension_not_in(
                    source_id, allowed_extensions, db
                )
                for stale in stale_files:
                    SharePointSyncService._delete_file_vectors(source.silo_id, stale, db)
                    SharePointFileRepository.delete_file(stale.id, db)

            # Persist state
            source.last_delta_token = new_delta_token
            source.last_synced_at = datetime.utcnow()
            source.last_sync_status = (
                SharePointSyncStatus.PARTIAL if per_file_errors else SharePointSyncStatus.SUCCESS
            )
            source.last_sync_error = None
            SharePointSourceRepository.update(source, db)

        except Exception as exc:
            try:
                from models.enums.sharepoint_sync_status import SharePointSyncStatus
                source = SharePointSourceRepository.get_by_id(source_id, db)
                if source:
                    source.last_sync_status = SharePointSyncStatus.ERROR
                    source.last_sync_error = str(exc)
                    SharePointSourceRepository.update(source, db)
            except Exception:
                pass
            raise
        finally:
            db.close()

    @staticmethod
    def _delete_file_vectors(silo_id: int, file, db: Session) -> None:
        """Remove indexed vectors for a single SharePointFile from the silo."""
        if not file.vector_doc_ids:
            return
        try:
            from repositories.silo_repository import SiloRepository
            from tools.vector_store_factory import VectorStoreFactory
            silo = SiloRepository.get_by_id(silo_id, db)
            if not silo or not silo.embedding_service:
                return
            collection_name = f"silo_{silo_id}"
            store = VectorStoreFactory.get_vector_store(db, silo.vector_db_type or 'PGVECTOR')
            store.delete_documents(
                collection_name,
                ids=file.vector_doc_ids,
                embedding_service=silo.embedding_service,
            )
        except Exception:
            pass  # Best-effort; log at caller level


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string from the Graph API."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
