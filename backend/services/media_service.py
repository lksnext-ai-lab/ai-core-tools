import os
from typing import List, Tuple, Optional
from fastapi import UploadFile
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
        db: Session,
        user_context
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
                    db=db
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
    async def create_media_from_file(
        file: UploadFile,
        repository_id: int,
        folder_id: Optional[int],
        db: Session
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
            status='pending'
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
        
        # Trigger async processing
        from tasks.media_tasks import process_media_task
        process_media_task.delay(media.media_id)
        
        logger.info(f"Created media {media.media_id} from file upload: {file.filename}")
        return media
    
    @staticmethod
    async def create_media_from_youtube(
        url: str,
        repository_id: int,
        folder_id: Optional[int],
        db: Session
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
            status='pending'
        )
        
        db.add(media)
        db.commit()
        db.refresh(media)
        
        # Trigger async processing
        from tasks.media_tasks import process_media_task
        process_media_task(media.media_id)
        
        logger.info(f"Created media {media.media_id} from YouTube URL: {url}")
        return media