from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from .schemas import (
    RepositoriesResponseSchema,
    RepositoryResponseSchema,
    RepositorySchema,
    CreateRepositoryRequestSchema,
    UpdateRepositoryRequestSchema,
    SiloSearchSchema,
    DocsResponseSchema,
    MediaSchema,
    MediaListResponseSchema,
    MediaUploadResponseSchema,
    MediaResponseSchema,
    YouTubeRequestSchema,
    MessageResponseSchema,
)
from .auth import (
    get_api_key_auth,
    validate_api_key_for_app,
    validate_repository_ownership,
    validate_media_ownership,
)

from models.repository import Repository
from services.repository_service import RepositoryService
from services.silo_service import SiloService
from services.media_service import MediaService
from db.database import get_db

from utils.logger import get_logger

logger = get_logger(__name__)

repositories_router = APIRouter()


# ==================== REPOSITORY ENDPOINTS ====================


@repositories_router.get(
    "/",
    summary="Get all repositories in app",
    tags=["Repositories"],
    response_model=RepositoriesResponseSchema,
)
async def get_all_repos(
    app_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Get all repositories in the specified app."""
    validate_api_key_for_app(app_id, api_key, db)

    try:
        repos = RepositoryService.get_repositories_by_app_id(app_id, db)
        return RepositoriesResponseSchema(
            repositories=[RepositorySchema.model_validate(r) for r in repos]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing repositories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list repositories",
        )


@repositories_router.get(
    "/{repo_id}",
    summary="Get repository by id",
    tags=["Repositories"],
    response_model=RepositoryResponseSchema,
)
async def get_repo_by_id(
    app_id: int,
    repo_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Get a specific repository by ID."""
    validate_api_key_for_app(app_id, api_key, db)
    repo = validate_repository_ownership(db, repo_id, app_id)

    return RepositoryResponseSchema(
        repository=RepositorySchema.model_validate(repo)
    )


@repositories_router.post(
    "/",
    summary="Create repository",
    tags=["Repositories"],
    response_model=RepositoryResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_repo(
    app_id: int,
    request: CreateRepositoryRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Create a new repository."""
    validate_api_key_for_app(app_id, api_key, db)

    try:
        repo = Repository(
            name=request.name,
            app_id=app_id,
            type="default",
            status="active",
            create_date=datetime.now(),
        )
        created = RepositoryService.create_repository(repo, db=db)
        logger.info(f"Repository created via public API: {created.repository_id}")
        return RepositoryResponseSchema(
            repository=RepositorySchema.model_validate(created)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating repository: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create repository",
        )


@repositories_router.put(
    "/{repo_id}",
    summary="Update repository",
    tags=["Repositories"],
    response_model=RepositoryResponseSchema,
)
async def update_repo(
    app_id: int,
    repo_id: int,
    request: UpdateRepositoryRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Update an existing repository."""
    validate_api_key_for_app(app_id, api_key, db)
    repo = validate_repository_ownership(db, repo_id, app_id)

    try:
        updates = request.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(repo, field, value)

        updated = RepositoryService.update_repository(repo, db=db)
        logger.info(f"Repository updated via public API: {repo_id}")
        return RepositoryResponseSchema(
            repository=RepositorySchema.model_validate(updated)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating repository: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update repository",
        )


@repositories_router.delete(
    "/{repo_id}",
    summary="Delete repository",
    tags=["Repositories"],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_repo(
    app_id: int,
    repo_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Delete a repository and all its resources."""
    validate_api_key_for_app(app_id, api_key, db)
    repo = validate_repository_ownership(db, repo_id, app_id)

    try:
        RepositoryService.delete_repository(repo, db)
        logger.info(f"Repository deleted via public API: {repo_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting repository: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete repository",
        )


@repositories_router.post(
    "/{repo_id}/docs/find",
    summary="Find docs in repository",
    tags=["Repositories"],
    response_model=DocsResponseSchema,
)
async def find_docs_in_repository(
    app_id: int,
    repo_id: int,
    request: SiloSearchSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Find documents in a repository's silo collection."""
    validate_api_key_for_app(app_id, api_key, db)
    repository = validate_repository_ownership(db, repo_id, app_id)

    if not repository.silo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository does not have an associated silo",
        )

    try:
        query = request.query if request.query else " "
        docs = SiloService.find_docs_in_collection(
            silo_id=repository.silo_id,
            query=query,
            filter_metadata=request.filter_metadata,
            db=db,
        )

        doc_schemas = []
        for doc in docs:
            doc_id = (
                getattr(doc, "id", None)
                or doc.metadata.get("_id")
                or doc.metadata.get("id")
                or ""
            )
            doc_schemas.append(
                {
                    "page_content": doc.page_content,
                    "metadata": {
                        **doc.metadata,
                        "id": str(doc_id) if doc_id else "",
                    },
                }
            )

        return DocsResponseSchema(docs=doc_schemas)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding documents in repository: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error finding documents",
        )


# ==================== MEDIA ENDPOINTS ====================


@repositories_router.get(
    "/{repo_id}/media",
    summary="List media in repository",
    tags=["Media"],
    response_model=MediaListResponseSchema,
)
async def list_media(
    app_id: int,
    repo_id: int,
    folder_id: Optional[int] = Query(None),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """List all media (video/audio) in a repository, optionally filtered by folder."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)

    try:
        media_list = MediaService.list_media(
            repository_id=repo_id,
            folder_id=folder_id,
            db=db,
        )
        return MediaListResponseSchema(
            media=[MediaSchema.model_validate(m) for m in media_list]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list media",
        )


@repositories_router.post(
    "/{repo_id}/media",
    summary="Upload media files",
    tags=["Media"],
    response_model=MediaUploadResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    app_id: int,
    repo_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(None),
    transcription_service_id: int = Form(...),
    forced_language: Optional[str] = Form(None),
    chunk_min_duration: Optional[int] = Form(None),
    chunk_max_duration: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Upload video/audio files for transcription and indexing.

    Supported formats:
    - Video: mp4, mov, avi, mkv, webm, flv, wmv, mpeg, mpg
    - Audio: mp3, wav, m4a, aac, ogg, flac, wma
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)

    try:
        from .auth import create_api_key_user_context

        user_context = create_api_key_user_context(app_id, api_key)

        created_media, failed_files = await MediaService.upload_media_files(
            repository_id=repo_id,
            files=files,
            folder_id=folder_id,
            transcription_service_id=transcription_service_id,
            db=db,
            background_tasks=background_tasks,
            user_context=user_context,
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap,
        )

        return MediaUploadResponseSchema(
            message=f"Uploaded {len(created_media)} media file(s)",
            created_media=[MediaSchema.model_validate(m) for m in created_media],
            failed_files=failed_files,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload media",
        )


@repositories_router.post(
    "/{repo_id}/media/youtube",
    summary="Add YouTube video",
    tags=["Media"],
    response_model=MediaResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_youtube_video(
    app_id: int,
    repo_id: int,
    request: YouTubeRequestSchema,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """
    Add a YouTube video for transcription and indexing.

    The video will be downloaded, audio extracted, transcribed, chunked, and indexed for RAG queries.
    """
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)

    try:
        media = await MediaService.create_media_from_youtube(
            url=request.url,
            repository_id=repo_id,
            folder_id=request.folder_id,
            transcription_service_id=request.transcription_service_id,
            db=db,
            background_tasks=background_tasks,
            forced_language=request.forced_language,
            chunk_min_duration=request.chunk_min_duration,
            chunk_max_duration=request.chunk_max_duration,
            chunk_overlap=request.chunk_overlap,
        )

        return MediaResponseSchema(media=MediaSchema.model_validate(media))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding YouTube video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add YouTube video",
        )


@repositories_router.get(
    "/{repo_id}/media/{media_id}",
    summary="Get media status",
    tags=["Media"],
    response_model=MediaResponseSchema,
)
async def get_media_status(
    app_id: int,
    repo_id: int,
    media_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Get status and details of a specific media item."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)
    media = validate_media_ownership(db, media_id, repo_id)

    return MediaResponseSchema(media=MediaSchema.model_validate(media))


@repositories_router.post(
    "/{repo_id}/media/{media_id}/move",
    summary="Move media to folder",
    tags=["Media"],
    response_model=MessageResponseSchema,
)
async def move_media(
    app_id: int,
    repo_id: int,
    media_id: int,
    new_folder_id: Optional[int] = Form(default=None),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Move a media item to a different folder within the same repository."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)
    validate_media_ownership(db, media_id, repo_id)

    try:
        MediaService.move_media_to_folder(
            app_id=app_id,
            media_id=media_id,
            repository_id=repo_id,
            new_folder_id=new_folder_id,
            db=db,
        )
        logger.info(f"Media {media_id} moved via public API")
        return MessageResponseSchema(message="Media moved successfully")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move media",
        )


@repositories_router.delete(
    "/{repo_id}/media/{media_id}",
    summary="Delete media",
    tags=["Media"],
    response_model=MessageResponseSchema,
)
async def delete_media(
    app_id: int,
    repo_id: int,
    media_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Delete a media file and all derived data (chunks, transcripts, embeddings)."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)
    validate_media_ownership(db, media_id, repo_id)

    try:
        MediaService.delete_media(
            media_id=media_id,
            app_id=app_id,
            repository_id=repo_id,
            db=db,
        )
        logger.info(f"Media {media_id} deleted via public API")
        return MessageResponseSchema(message="Media deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete media",
        )
