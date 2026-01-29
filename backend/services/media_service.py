import os
from typing import List, Tuple, Optional
from fastapi import UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.media import Media
from utils.logger import get_logger

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

class MediaService:
    # Supported file extensions
    SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.mpeg', '.mpg'}
    SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma'}
    
    @staticmethod
    async def upload_media_files(
        repository_id: int,
        files: List[UploadFile],
        folder_id: Optional[int],
        transcription_service_id: int,
        db: Session,
        background_tasks: BackgroundTasks, 
        user_context,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None
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
                    transcription_service_id=transcription_service_id,
                    db=db,
                    background_tasks=background_tasks, 
                    forced_language=forced_language,
                    chunk_min_duration=chunk_min_duration,
                    chunk_max_duration=chunk_max_duration,
                    chunk_overlap=chunk_overlap
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
        """

        try:
            logger.info(
                f"Move media service called - app_id: {app_id}, media_id: {media_id}, "
                f"repository_id: {repository_id}, new_folder_id: {new_folder_id}"
            )

            # Convert 0 to None for root folder
            if new_folder_id == 0:
                new_folder_id = None

            # Get the media
            media = (
                db.query(Media)
                .filter(Media.media_id == media_id)
                .one_or_none()
            )

            if not media:
                raise ValueError(f"Media {media_id} not found")

            # Validate repository ownership
            if media.repository_id != repository_id:
                raise ValueError(
                    f"Media {media_id} does not belong to repository {repository_id}"
                )

            # Validate target folder if provided
            if new_folder_id is not None:
                from services.folder_service import FolderService
                if not FolderService.validate_folder_access(
                    new_folder_id, repository_id, db
                ):
                    raise ValueError(
                        f"Folder {new_folder_id} does not belong to repository {repository_id}"
                    )

            # Update database record
            media.folder_id = new_folder_id
            db.add(media)
            db.commit()

            logger.info(
                f"Updated media {media_id} folder_id to {new_folder_id}"
            )

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
    def delete_media(
        media_id: int,
        app_id: int,
        repository_id: int,
        db: Session
    ) -> None:
        """Delete media by ID"""

        logger.info(f"Delete media service called - app_id: {app_id}, repository_id: {repository_id}, media_id: {media_id}")
        
        media = db.query(Media).filter(Media.media_id == media_id).first()
        if not media:
            raise ValueError(f"Media with ID {media_id} not found")
        
        # Delete associated file
        if media.file_path and os.path.exists(media.file_path):
            os.remove(media.file_path)
            logger.info(f"Deleted media file at {media.file_path}")
        
        # Delete media record
        db.delete(media)
        db.commit()
        logger.info(f"Deleted media record with ID {media_id}")

        logger.info(f"Media {media_id} deleted successfully")
        return {"message": "Media deleted successfully"}

    @staticmethod
    async def create_media_from_file(
        file: UploadFile,
        repository_id: int,
        folder_id: Optional[int],
        transcription_service_id: int,
        db: Session,
        background_tasks: BackgroundTasks,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None
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
            transcription_service_id=transcription_service_id,  
            source_type='upload',
            status='pending',
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )
        
        db.add(media)
        db.flush()  # Get media_id without committing
        
        # Save file
        media_folder = os.path.join(REPO_BASE_FOLDER, str(repository_id), 'media')
        os.makedirs(media_folder, exist_ok=True)
        
        file_path = os.path.join(media_folder, f"{media.media_id}{file_extension}")
        
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        media.file_path = file_path
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
        transcription_service_id: int,
        db: Session,
        background_tasks: BackgroundTasks,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None
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
            transcription_service_id=transcription_service_id,
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