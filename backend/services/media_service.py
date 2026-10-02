import os
from typing import List, Tuple, Optional
from fastapi import UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.media import Media
from utils.logger import get_logger

from repositories.media_repository import MediaRepository
from services.silo_service import SiloService

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
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
        Updates file system location (media + audio), database record, and re-indexes in vector DB.
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

            # Get old paths
            old_media_path = media.file_path
            if not old_media_path:
                raise ValueError(f"Could not determine current path for media {media_id}")
            
            base_path = os.path.splitext(old_media_path)[0]
            old_audio_path = f"{base_path}_audio.wav"

            # Build new paths
            repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
            media_filename = os.path.basename(old_media_path)
            audio_filename = os.path.basename(old_audio_path)
            
            if new_folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(new_folder_id, db)
                new_media_path = os.path.join(repository_path, folder_path, media_filename)
                new_audio_path = os.path.join(repository_path, folder_path, audio_filename)
            else:
                new_media_path = os.path.join(repository_path, media_filename)
                new_audio_path = os.path.join(repository_path, audio_filename)

            # Create target directory if needed
            os.makedirs(os.path.dirname(new_media_path), exist_ok=True)

            # Move files with rollback on failure
            media_moved = False
            audio_moved = False
            
            try:
                import shutil
                shutil.move(old_media_path, new_media_path)
                media_moved = True
                logger.info(f"Moved media file from {old_media_path} to {new_media_path}")

                if os.path.exists(old_audio_path):
                    shutil.move(old_audio_path, new_audio_path)
                    audio_moved = True
                    logger.info(f"Moved audio file from {old_audio_path} to {new_audio_path}")

            except Exception as e:
                # Rollback: move files back if partially completed
                if media_moved:
                    shutil.move(new_media_path, old_media_path)
                    logger.warning("Rolled back media file move")
                if audio_moved:
                    shutil.move(new_audio_path, old_audio_path)
                    logger.warning("Rolled back audio file move")
                raise ValueError(f"Failed to move files: {str(e)}")
        
            # Update database
            media.folder_id = new_folder_id
            media.file_path = new_media_path
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
                "new_path": new_media_path
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
    ) -> bool:
        """Delete media by ID"""

        logger.info(f"Delete media service called - app_id: {app_id}, repository_id: {repository_id}, media_id: {media_id}")
        
        media = MediaRepository.get_by_id(media_id, db)
        if not media:
            logger.warning(f"Media {media_id} not found for deletion")
            return False
        return MediaService.delete_media_item(media, db)

    @staticmethod
    def delete_media_item(media: Media, db: Session) -> bool:
        """Remove a media item's vectors, files and row."""
        media_id = media.media_id
        try:
            # Delete from silo first
            SiloService.delete_media(media)
            logger.info(f"Media {media_id} deleted from silo")
            
            # Delete file from disk
            if media.file_path and os.path.exists(media.file_path):
                audio_path = os.path.splitext(media.file_path)[0] + "_audio.wav"
                os.remove(media.file_path)
                logger.info(f"File {media.file_path} deleted from disk")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                    logger.info(f"Audio file {audio_path} deleted from disk")
            
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
        """Create media from a file uploaded to a repository."""
        return await MediaService._create_upload(
            file, db, background_tasks,
            silo_id=MediaService._repository_silo_id(repository_id, db),
            repository_id=repository_id, folder_id=folder_id,
            forced_language=forced_language, chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration, chunk_overlap=chunk_overlap,
        )

    @staticmethod
    async def create_silo_media_from_file(
        file: UploadFile,
        silo,
        db: Session,
        background_tasks: BackgroundTasks,
        metadata: Optional[dict] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        """Index a video/audio file straight into a silo (no repository), asynchronously."""
        MediaService.check_silo_accepts_media(silo)
        return await MediaService._create_upload(
            file, db, background_tasks,
            silo_id=silo.silo_id, repository_id=None, folder_id=None, custom_metadata=metadata or None,
            forced_language=forced_language, chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration, chunk_overlap=chunk_overlap,
        )

    @staticmethod
    def is_media_filename(filename: Optional[str]) -> bool:
        ext = os.path.splitext(filename or "")[1].lower()
        return ext in (MediaService.SUPPORTED_VIDEO_EXTENSIONS | MediaService.SUPPORTED_AUDIO_EXTENSIONS)

    @staticmethod
    def check_silo_accepts_media(silo) -> None:
        """Media needs an embedding service to index and a transcription service to transcribe."""
        if not silo.embedding_service_id:
            raise ValueError(f"Silo {silo.silo_id} has no embedding service configured")
        if not silo.transcription_service_id:
            raise ValueError(
                f"Silo {silo.silo_id} has no transcription service configured; "
                "set transcription_service_id on the silo to index video or audio"
            )

    @staticmethod
    def _repository_silo_id(repository_id: int, db: Session) -> int:
        from models.repository import Repository
        silo_id = db.query(Repository.silo_id).filter(Repository.repository_id == repository_id).scalar()
        if silo_id is None:
            raise ValueError(f"Repository {repository_id} not found")
        return silo_id

    @staticmethod
    async def _create_upload(
        file: UploadFile,
        db: Session,
        background_tasks: BackgroundTasks,
        *,
        silo_id: int,
        repository_id: Optional[int],
        folder_id: Optional[int],
        custom_metadata: Optional[dict] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        file_extension = os.path.splitext(file.filename)[1].lower()

        # Validate extension
        if not MediaService.is_media_filename(file.filename):
            raise ValueError(f"Unsupported file type: {file_extension}")

        # Create media record
        name = os.path.splitext(file.filename)[0]
        media = Media(
            name=name,
            silo_id=silo_id,
            repository_id=repository_id,
            folder_id=folder_id,
            source_type='upload',
            status='pending',
            custom_metadata=custom_metadata,
            forced_language=forced_language,
            chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration,
            chunk_overlap=chunk_overlap
        )

        db.add(media)
        db.flush()  # Get media_id without committing

        # Save file
        from tasks.media_tasks import media_storage_folder
        media_folder = media_storage_folder(media)
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
        db: Session,
        background_tasks: BackgroundTasks,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        """Create media from a YouTube URL in a repository."""
        # Convert 0 to None for root folder
        if folder_id == 0:
            folder_id = None
        return MediaService._create_youtube(
            url, db, background_tasks,
            silo_id=MediaService._repository_silo_id(repository_id, db),
            repository_id=repository_id, folder_id=folder_id,
            forced_language=forced_language, chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration, chunk_overlap=chunk_overlap,
        )

    @staticmethod
    async def create_silo_media_from_youtube(
        url: str,
        silo,
        db: Session,
        background_tasks: BackgroundTasks,
        metadata: Optional[dict] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        """Index a YouTube video straight into a silo (no repository), asynchronously."""
        MediaService.check_silo_accepts_media(silo)
        return MediaService._create_youtube(
            url, db, background_tasks,
            silo_id=silo.silo_id, repository_id=None, folder_id=None, custom_metadata=metadata or None,
            forced_language=forced_language, chunk_min_duration=chunk_min_duration,
            chunk_max_duration=chunk_max_duration, chunk_overlap=chunk_overlap,
        )

    @staticmethod
    def _create_youtube(
        url: str,
        db: Session,
        background_tasks: BackgroundTasks,
        *,
        silo_id: int,
        repository_id: Optional[int],
        folder_id: Optional[int],
        custom_metadata: Optional[dict] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Media:
        import re

        # Validate YouTube URL
        youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'
        if not re.match(youtube_regex, url):
            raise ValueError("Invalid YouTube URL")

        # Check for duplicate URL in the same repository (or, without one, the same silo)
        scope = (Media.repository_id == repository_id) if repository_id else (Media.silo_id == silo_id)
        existing_media = db.query(Media).filter(
            and_(scope, Media.source_url == url, Media.source_type == 'youtube')
        ).first()

        if existing_media:
            where = "repository" if repository_id else "silo"
            raise ValueError(f"This YouTube URL already exists in this {where} (Media ID: {existing_media.media_id})")

        # Extract video title (basic extraction from URL)
        name = f"YouTube: {url.split('/')[-1][:30]}"

        media = Media(
            name=name,
            silo_id=silo_id,
            repository_id=repository_id,
            folder_id=folder_id,
            source_type='youtube',
            source_url=url,
            status='pending',
            custom_metadata=custom_metadata,
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