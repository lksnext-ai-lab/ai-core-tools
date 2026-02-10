from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from typing import List, Optional
import os
import logging
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import services
from services.repository_service import RepositoryService
from services.resource_service import ResourceService
from services.media_service import MediaService

from schemas.repository_schemas import RepositoryListItemSchema, RepositoryDetailSchema, CreateUpdateRepositorySchema, RepositorySearchSchema
from schemas.media_schemas import MediaResponse, MediaUploadResponse
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls import enforce_file_size_limit
from routers.controls.role_authorization import require_min_role, AppRole
from repositories.media_repository import MediaRepository

# Import database dependency
from db.database import get_db

# Set up logging
logger = logging.getLogger(__name__)

repositories_router = APIRouter()

# Debug log when router is loaded
logger.info("Repositories router loaded successfully")


# ==================== REPOSITORY MANAGEMENT ====================

@repositories_router.get("/", 
                         summary="List repositories",
                         tags=["Repositories"],
                         response_model=List[RepositoryListItemSchema])
async def list_repositories(
    app_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer"))
):
    """
    List all repositories for a specific app.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"List repositories called for app_id: {app_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    return RepositoryService.get_repositories_list(app_id, db)


@repositories_router.get("/{repository_id}",
                        summary="Get repository details",
                        tags=["Repositories"],
                        response_model=RepositoryDetailSchema)
async def get_repository(
    app_id: int,
    repository_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer"))
):
    """
    Get detailed information about a specific repository including its resources.
    """
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    return RepositoryService.get_repository_detail(app_id, repository_id, db)


@repositories_router.post("/{repository_id}",
                         summary="Create or update repository",
                         tags=["Repositories"],
                         response_model=RepositoryDetailSchema)
async def create_or_update_repository(
    app_id: int,
    repository_id: int,
    repo_data: CreateUpdateRepositorySchema,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Create a new repository or update an existing one.
    """    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    repo = RepositoryService.create_or_update_repository_router(app_id, repository_id, repo_data, db)
    
    # Return updated repository (reuse the GET logic)
    return RepositoryService.get_repository_detail(app_id, repo.repository_id, db)


@repositories_router.delete("/{repository_id}",
                           summary="Delete repository",
                           tags=["Repositories"])
async def delete_repository(
    app_id: int,
    repository_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Delete a repository and all its resources.
    """
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    RepositoryService.delete_repository_router(repository_id, db)
    
    return {"message": "Repository deleted successfully"}


# ==================== RESOURCE MANAGEMENT ====================

@repositories_router.post("/{repository_id}/resources",
                         summary="Upload resources",
                         tags=["Resources"])
async def upload_resources(
    app_id: int,
    repository_id: int,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Upload multiple resources to a repository.
    Optionally specify a folder_id to upload files to a specific folder.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Upload resources endpoint called - app_id: {app_id}, repository_id: {repository_id}, files_count: {len(files)}, folder_id: {folder_id} (type: {type(folder_id)}), user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.upload_resources_to_repository(
        app_id=app_id,
        repository_id=repository_id,
        files=files,
        db=db,
        folder_id=folder_id
    )
    
    return result


@repositories_router.post("/{repository_id}/resources/{resource_id}/move",
                         summary="Move resource to different folder",
                         tags=["Resources"])
async def move_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    new_folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Move a resource to a different folder within the same repository.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Move resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, new_folder_id: {new_folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.move_resource_to_folder(
        resource_id=resource_id,
        repository_id=repository_id,
        new_folder_id=new_folder_id,
        db=db
    )
    
    return result


@repositories_router.delete("/{repository_id}/resources/{resource_id}",
                           summary="Delete resource",
                           tags=["Resources"])
async def delete_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Delete a specific resource from a repository.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Delete resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.delete_resource_from_repository(
        app_id=app_id,
        repository_id=repository_id,
        resource_id=resource_id,
        db=db
    )
    
    return result


@repositories_router.get("/{repository_id}/resources/{resource_id}/download",
                        summary="Download resource",
                        tags=["Resources"])
async def download_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer"))
):
    """
    Download a specific resource from a repository.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Download resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    file_path, filename = ResourceService.download_resource_from_repository(
        app_id=app_id,
        repository_id=repository_id,
        resource_id=resource_id,
        user_id=user_id,
        db=db
    )
    
    # Return file for download
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


# ==================== MEDIA MANAGEMENT ====================
@repositories_router.post("/{repository_id}/media", response_model=MediaUploadResponse)
async def upload_media(
    app_id: int,
    repository_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(None),
    transcription_service_id: int = Form(...),
    forced_language: Optional[str] = Form(None),
    chunk_min_duration: Optional[int] = Form(None),
    chunk_max_duration: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
):
    """
    Upload video/audio files for transcription and indexing
    
    Supported formats:
    - Video: mp4, mov, avi, mkv, webm, flv, wmv, mpeg, mpg
    - Audio: mp3, wav, m4a, aac, ogg, flac, wma

    Configuration:
    - forced_language: Force transcription language (e.g., 'es', 'en', 'fr'). Leave empty for auto-detect.
    - chunk_min_duration: Minimum chunk duration in seconds (default: 30)
    - chunk_max_duration: Maximum chunk duration in seconds (default: 120)
    - chunk_overlap: Overlap between chunks in seconds (default: 0, recommended: 5-10)
    """
    user_id = auth_context.identity.id
    logger.info(f"Upload media - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}, files: {len(files)}")
    
    try:
        created_media, failed_files = await MediaService.upload_media_files(
            repository_id=repository_id,
            files=files,
            folder_id=folder_id,
            transcription_service_id=transcription_service_id,
            db=db,
            background_tasks=background_tasks,
            user_context=auth_context,
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )

        return MediaUploadResponse(
            message=f"Uploaded {len(created_media)} media file(s)",
            created_media=[MediaResponse(**m.__dict__) for m in created_media],
            failed_files=failed_files
        )
    except Exception as e:
        logger.error(f"Error uploading media: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@repositories_router.post("/{repository_id}/media/youtube", response_model=MediaResponse)
async def add_youtube_video(
    app_id: int,
    background_tasks: BackgroundTasks,
    repository_id: int,
    url: str = Form(...),
    folder_id: Optional[int] = Form(None),
    transcription_service_id: int = Form(...),
    forced_language: Optional[str] = Form(None),
    chunk_min_duration: Optional[int] = Form(None),
    chunk_max_duration: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Add YouTube video for transcription and indexing
    
    The video will be:
    1. Downloaded from YouTube
    2. Audio extracted and normalized
    3. Transcribed using Whisper
    4. Chunked into segments
    5. Indexed for RAG queries

    Configuration:
    - forced_language: Force transcription language (e.g., 'es', 'en', 'fr'). Leave empty for auto-detect.
    - chunk_min_duration: Minimum chunk duration in seconds (default: 30)
    - chunk_max_duration: Maximum chunk duration in seconds (default: 120)
    - chunk_overlap: Overlap between chunks in seconds (default: 0, recommended: 5-10)
    """
    user_id = auth_context.identity.id
    logger.info(f"Add YouTube video - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}, url: {url}")

    try:
        media = await MediaService.create_media_from_youtube(
            url=url,
            repository_id=repository_id,
            folder_id=folder_id,
            transcription_service_id=transcription_service_id,
            db=db,
            background_tasks=background_tasks,
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )

        return MediaResponse(**media.__dict__)
    except ValueError as e:
        # Handle validation errors (invalid URL, duplicate)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding YouTube video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@repositories_router.get("/{repository_id}/media", response_model=List[MediaResponse])
async def list_media(
    app_id: int,
    repository_id: int,
    folder_id: Optional[int] = None,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """List all media in repository"""
    from models.media import Media
    
    query = db.query(Media).filter(Media.repository_id == repository_id)
    
    if folder_id is not None:
        if folder_id == 0:
            query = query.filter(Media.folder_id.is_(None))
        else:
            query = query.filter(Media.folder_id == folder_id)
    
    media_list = query.order_by(Media.create_date.desc()).all()
    return [MediaResponse(**{k: v for k, v in m.__dict__.items() if not k.startswith('_')}) for m in media_list]

@repositories_router.post("/{repository_id}/media/{media_id}/move",
                         summary="Move media to different folder",
                         tags=["Media"])
async def move_media(
    app_id: int,
    repository_id: int,
    media_id: int,
    new_folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor"))
):
    """
    Move a resource to a different folder within the same repository.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Move media endpoint called - app_id: {app_id}, repository_id: {repository_id}, media_id: {media_id}, new_folder_id: {new_folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation

    # Use MediaService to handle the business logic
    result = MediaService.move_media_to_folder(
        app_id=app_id,
        media_id=media_id,
        repository_id=repository_id,
        new_folder_id=new_folder_id,
        db=db
    )
    
    return result

@repositories_router.get("/{repository_id}/media/{media_id}", response_model=MediaResponse)
async def get_media_status(
    app_id: int,
    repository_id: int,
    media_id: int,
    db: Session = Depends(get_db)
):
    media = MediaRepository.get_by_id(media_id, db)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media

@repositories_router.delete("/{repository_id}/media/{media_id}")
async def delete_media(
    app_id: int,
    repository_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Delete a media file and all derived data (chunks, transcripts, embeddings).
    """
    user_id = int(auth_context.identity.id)

    logger.info(f"Delete media endpoint called - app_id={app_id}, repository_id={repository_id}, media_id={media_id}, user_id={user_id}")

    result = MediaService.delete_media(
        app_id=app_id,
        repository_id=repository_id,
        media_id=media_id,
        db=db
    )

    return result

# ==================== REPOSITORY SEARCH ====================

@repositories_router.post("/{repository_id}/search",
                         summary="Search documents in repository",
                         tags=["Repositories", "Search"])
async def search_repository_documents(
    app_id: int,
    repository_id: int,
    search_query: RepositorySearchSchema,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Search for documents in a repository using semantic search with optional metadata filtering.
    This leverages the repository's associated silo for searching.
    """
    user_id = int(auth_context.identity.id)
    
    logger.info(f"Repository search request - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}")
    logger.info(f"Search query: {search_query.query}, limit: {search_query.limit}, filter_metadata: {search_query.filter_metadata}")
    
    # TODO: Add app access validation
    
    try:
        # Use RepositoryService to handle the search
        result = RepositoryService.search_repository_documents_router(
            repository_id=repository_id,
            query=search_query.query,
            filter_metadata=search_query.filter_metadata,
            limit=search_query.limit or 10,
            db=db
        )
        
        logger.info(f"Repository search completed - found {len(result.get('results', []))} results")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching repository {repository_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching repository: {str(e)}"
        ) 