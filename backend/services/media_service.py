import os
from typing import List, Tuple, Optional
from fastapi import UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.media import Media
from utils.logger import get_logger

from repositories.media_repository import MediaRepository
from services.silo_service import SiloService
from services.storage_service import get_storage_backend

logger = get_logger(__name__)

class MediaService:
    # Supported file extensions
    SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.mpeg', '.mpg'}
    SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma'}

    @staticmethod
    def list_media(
        repository_id: int,
        folder_id: Optional[int],
        db: Session,
    ) -> List[Media]:
        """List media for a repository with optional folder filtering."""
        return MediaRepository.list_by_repository_and_folder(
            repository_id=repository_id,
            folder_id=folder_id,
            db=db,
        )
    
    @staticmethod
    async def upload_media_files(
        repository_id: int,
        files: List[UploadFile],
        folder_id: Optional[int],
        db: Session,
        background_tasks: BackgroundTasks, 
        user_context,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Tuple[List[Media], List[dict]]:
        """
        Upload multiple media files
        
        Returns:
            Tuple of (created_media_list, failed_files_list)
        """
        # Convert 0 to None for root folder
        if folder_id == 0:
            folder_id = None
        
        created_media = []
        failed_files = []
        
        for file in files:
            try:
                media = await MediaService.create_media_from_file(
                    file=file,
                    repository_id=repository_id,
                    folder_id=folder_id,
                    db=db,
                    background_tasks=background_tasks, 
                    forced_language=forced_language,
                    chunk_min_duration=chunk_min_duration,
                    chunk_max_duration=chunk_max_duration,
                    chunk_overlap=chunk_overlap,
                )
                created_media.append(media)
            except Exception as e:
                logger.error(f"Failed to upload {file.filename}: {str(e)}")
                failed_files.append({
                    'filename': file.filename,
                    'error': str(e)
                })
        
        return created_media, failed_files
    
    @staticmethod
    def move_media_to_folder(
    app_id: int,
    media_id: int,
    repository_id: int,
    new_folder_id: Optional[int],
    db: Session
    ) -> dict:
        """
        Move a media item to a different folder within the same repository.
        Updates the folder metadata in the database and re-indexes in vector DB.
        The storage key is unchanged — folder is a DB/metadata concept only.
        """
        try:
            # Convert 0 to None for root folder
            if new_folder_id == 0:
                new_folder_id = None

            # Get the media
            media = db.query(Media).filter(Media.media_id == media_id).one_or_none()
            if not media:
                raise ValueError(f"Media {media_id} not found")

            # Validate repository ownership
            if media.repository_id != repository_id:
                raise ValueError(f"Media {media_id} does not belong to repository {repository_id}")

            # Validate target folder if provided
            if new_folder_id is not None:
                from services.folder_service import FolderService
                if not FolderService.validate_folder_access(new_folder_id, repository_id, db):
                    raise ValueError(f"Folder {new_folder_id} does not belong to repository {repository_id}")

            # Update database — storage key stays the same (folder is metadata only)
            media.folder_id = new_folder_id
            db.add(media)
            db.commit()
            logger.info(f"Updated media {media_id} folder_id to {new_folder_id}")

            # Update metadata in vector database
            from services.silo_service import SiloService
            SiloService.update_media_metadata(media, db)
            logger.info(f"Updated metadata for media {media_id} with new folder information")

            return {
                "success": True,
                "message": "Media moved successfully",
                "media_id": media_id,
                "new_folder_id": new_folder_id,
            }

        except Exception as e:
            logger.error(f"Error moving media {media_id}: {str(e)}")
            raise ValueError(f"Failed to move media: {str(e)}")

    @staticmethod
    async def delete_media(
        media_id: int,
        app_id: int,
        repository_id: int,
        db: Session
    ) -> bool:
        """Delete media by ID"""

        logger.info(f"Delete media service called - app_id: {app_id}, repository_id: {repository_id}, media_id: {media_id}")
        
        media = MediaRepository.get_by_id(media_id, db)
        if not media:
            logger.warning(f"Media {media_id} not found for deletion")
            return False
        
        try:
            # Delete from silo first
            SiloService.delete_media(media)
            logger.info(f"Media {media_id} deleted from silo")
            
            # Delete files from storage
            if media.storage_key:
                backend = get_storage_backend()
                await backend.delete(media.storage_key)
                logger.info(f"File {media.storage_key} deleted from storage")
                audio_key = os.path.splitext(media.storage_key)[0] + "_audio.wav"
                if await backend.exists(audio_key):
                    await backend.delete(audio_key)
                    logger.info(f"Audio file {audio_key} deleted from storage")
            
            # Delete from database
            MediaRepository.delete(media, db)
            MediaRepository.commit(db)
            logger.info(f"Media {media_id} deleted from database")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting media {media_id}: {str(e)}")
            MediaRepository.rollback(db)
            return False


    @staticmethod
    async def create_media_from_file(
        file: UploadFile,
        repository_id: int,
        folder_id: Optional[int],
        db: Session,
        background_tasks: BackgroundTasks,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        """Create media from uploaded file"""
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        # Validate extension
        if file_extension not in (MediaService.SUPPORTED_VIDEO_EXTENSIONS | MediaService.SUPPORTED_AUDIO_EXTENSIONS):
            raise ValueError(f"Unsupported file type: {file_extension}")
        
        # Create media record
        name = os.path.splitext(file.filename)[0]
        media = Media(
            name=name,
            repository_id=repository_id,
            folder_id=folder_id,
            source_type='upload',
            status='pending',
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )
        
        db.add(media)
        db.flush()  # Get media_id without committing
        
        # Upload file to storage
        content = await file.read()
        key = f"repositories/{repository_id}/{media.media_id}{file_extension}"
        await get_storage_backend().upload(key, content, content_type=file.content_type)

        media.storage_key = key
        db.commit()
        db.refresh(media)
        
        # Schedule background task
        from tasks.media_tasks import process_media_task_sync
        background_tasks.add_task(process_media_task_sync, media.media_id)
        
        logger.info(f"Created media {media.media_id} from file upload: {file.filename}")
        return media
    
    @staticmethod
    async def create_media_from_youtube(
        url: str,
        repository_id: int,
        folder_id: Optional[int],
        db: Session,
        background_tasks: BackgroundTasks,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        """Create media from YouTube URL"""
        import re
        
        # Validate YouTube URL
        youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'
        if not re.match(youtube_regex, url):
            raise ValueError("Invalid YouTube URL")
        
        # Convert 0 to None for root folder
        if folder_id == 0:
            folder_id = None
        
        # Check for duplicate URL in the same repository
        existing_media = db.query(Media).filter(
            and_(
                Media.repository_id == repository_id,
                Media.source_url == url,
                Media.source_type == 'youtube'
            )
        ).first()
        
        if existing_media:
            raise ValueError(f"This YouTube URL already exists in this repository (Media ID: {existing_media.media_id})")
        
        # Extract video title (basic extraction from URL)
        name = f"YouTube: {url.split('/')[-1][:30]}"
        
        media = Media(
            name=name,
            repository_id=repository_id,
            folder_id=folder_id,
            source_type='youtube',
            source_url=url,
            status='pending',
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )
        
        db.add(media)
        db.commit()
        db.refresh(media)
        
        # Schedule background task
        from tasks.media_tasks import process_media_task_sync
        background_tasks.add_task(process_media_task_sync, media.media_id)
        
        logger.info(f"Created media {media.media_id} from YouTube URL: {url}")
        return media