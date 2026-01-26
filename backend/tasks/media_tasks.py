from celery import shared_task
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.media import Media
from models.media_chunk import MediaChunk
from db.database import SessionLocal
from services.transcription_service import TranscriptionService
from services.silo_service import SiloService
from utils.logger import get_logger
import os
import yt_dlp
from pydub import AudioSegment
from datetime import datetime

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

# @shared_task(bind=True, max_retries=3)
# def process_media_task(self, media_id: int):
#     """
#     Process media: download (if YouTube), extract audio, transcribe, chunk, index
    
#     Flow:
#     1. Download video if YouTube source
#     2. Extract and normalize audio
#     3. Transcribe using Whisper
#     4. Create chunks from transcription
#     5. Index chunks in vector database
#     6. Update media status
#     """
#     db = SessionLocal()
    
#     try:
#         # Fetch media
#         media = db.query(Media).filter(Media.media_id == media_id).first()
#         if not media:
#             logger.error(f"Media {media_id} not found")
#             return
        
#         logger.info(f"Starting processing for media {media_id} ({media.source_type})")
        
#         # Step 1: Download if YouTube
#         if media.source_type == 'youtube':
#             media.status = 'downloading'
#             db.commit()
            
#             file_path = _download_youtube(media.source_url, media_id, media.repository_id)
#             media.file_path = file_path
#             db.commit()
            
#             logger.info(f"Downloaded YouTube video for media {media_id}")
        
#         # Step 2: Extract audio
#         media.status = 'processing'
#         db.commit()
        
#         audio_path = _extract_audio(media.file_path, media_id, media.repository_id)
#         logger.info(f"Extracted audio for media {media_id}: {audio_path}")
        
#         # Step 3: Transcribe
#         media.status = 'transcribing'
#         db.commit()
        
#         transcription = TranscriptionService.transcribe_audio(
#             audio_path,
#             language=media.forced_language,  # Use forced language if specified
#             ai_service_id=media.transcription_service_id,
#             db=db
#         )
        
#         # Update media with transcription metadata
#         media.language = transcription['language']
#         media.duration = float(transcription['duration'])
#         db.commit()
        
#         logger.info(f"Transcribed media {media_id}: {len(transcription['segments'])} segments, language: {transcription['language']}")
        
#         # Step 4: Create chunks with custom configuration
#         chunks_data = TranscriptionService.create_chunks(
#             transcription['segments'],
#             min_window=media.chunk_min_duration or 30,
#             max_window=media.chunk_max_duration or 120,
#             overlap=media.chunk_overlap or 0
#         )
        
#         for idx, chunk_data in enumerate(chunks_data):
#             chunk = MediaChunk(
#                 media_id=media_id,
#                 text=chunk_data['text'],
#                 start_time=chunk_data['start_time'],
#                 end_time=chunk_data['end_time'],
#                 chunk_index=idx
#             )
#             db.add(chunk)
        
#         db.commit()
#         logger.info(f"Created {len(chunks_data)} chunks for media {media_id}")
        
#         # Step 5: Index chunks
#         media.status = 'indexing'
#         db.commit()
        
#         chunks = db.query(MediaChunk).filter(MediaChunk.media_id == media_id).all()
#         for chunk in chunks:
#             SiloService.index_media_chunk(chunk, db)
        
#         logger.info(f"Indexed {len(chunks)} chunks for media {media_id}")
        
#         # Step 6: Mark as ready
#         media.status = 'ready'
#         media.processed_at = datetime.utcnow()
#         db.commit()
        
#         logger.info(f"✅ Media {media_id} processed successfully")
        
#     except Exception as e:
#         logger.error(f"❌ Error processing media {media_id}: {str(e)}")
        
#         # Update status to error
#         try:
#             media = db.query(Media).filter(Media.media_id == media_id).first()
#             if media:
#                 media.status = 'error'
#                 media.error_message = str(e)[:500]  # Limit error message length
#                 db.commit()
#         except Exception as update_error:
#             logger.error(f"Failed to update error status: {str(update_error)}")
        
#         # Retry logic for transient errors
#         if self.request.retries < self.max_retries:
#             raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        
#     finally:
#         db.close()


def process_media_task_sync(media_id: int):
    """
    Process media: download (if YouTube), extract audio, transcribe, chunk, index
    
    Flow:
    1. Download video if YouTube source
    2. Extract and normalize audio
    3. Transcribe using Whisper
    4. Create chunks from transcription
    5. Index chunks in vector database
    6. Update media status
    """
    db = SessionLocal()
    
    try:
        # Fetch media
        media = db.query(Media).filter(Media.media_id == media_id).first()
        if not media:
            logger.error(f"Media {media_id} not found")
            return
        
        logger.info(f"Starting processing for media {media_id} ({media.source_type})")
        
        # Step 1: Download if YouTube
        if media.source_type == 'youtube':
            media.status = 'downloading'
            db.commit()
            
            file_path = _download_youtube(media.source_url, media_id, media.repository_id)
            media.file_path = file_path
            db.commit()
            
            logger.info(f"Downloaded YouTube video for media {media_id}")
        
        # Step 2: Extract audio
        media.status = 'processing'
        db.commit()
        
        audio_path = _extract_audio(media.file_path, media_id, media.repository_id)
        logger.info(f"Extracted audio for media {media_id}: {audio_path}")
        
        # Step 3: Transcribe
        media.status = 'transcribing'
        db.commit()
        
        transcription = TranscriptionService.transcribe_audio(
            audio_path,
            language=media.forced_language,  # Use forced language if specified
            ai_service_id=media.transcription_service_id,
            db=db
        )
        
        # Update media with transcription metadata
        media.language = transcription['language']
        media.duration = float(transcription['duration'])
        db.commit()
        
        logger.info(f"Transcribed media {media_id}: {len(transcription['segments'])} segments, language: {transcription['language']}")
        
        # Step 4: Create chunks with custom configuration
        chunks_data = TranscriptionService.create_chunks(
            transcription['segments'],
            min_window=media.chunk_min_duration or 30,
            max_window=media.chunk_max_duration or 120,
            overlap=media.chunk_overlap or 0
        )
        
        for idx, chunk_data in enumerate(chunks_data):
            chunk = MediaChunk(
                media_id=media_id,
                text=chunk_data['text'],
                start_time=chunk_data['start_time'],
                end_time=chunk_data['end_time'],
                chunk_index=idx
            )
            db.add(chunk)
        
        db.commit()
        logger.info(f"Created {len(chunks_data)} chunks for media {media_id}")
        
        # Step 5: Index chunks
        media.status = 'indexing'
        db.commit()
        
        chunks = db.query(MediaChunk).filter(MediaChunk.media_id == media_id).all()
        for chunk in chunks:
            SiloService.index_media_chunk(chunk, db)
        
        logger.info(f"Indexed {len(chunks)} chunks for media {media_id}")
        
        # Step 6: Mark as ready
        media.status = 'ready'
        media.processed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Media {media_id} processed successfully")
        
    except Exception as e:
        logger.error(f"❌ Error processing media {media_id}: {str(e)}")
        
        # Update status to error
        try:
            media = db.query(Media).filter(Media.media_id == media_id).first()
            if media:
                media.status = 'error'
                media.error_message = str(e)[:500]  # Limit error message length
                db.commit()
        except Exception as update_error:
            logger.error(f"Failed to update error status: {str(update_error)}")
        
        # Retry logic for transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        
    finally:
        db.close()

def _download_youtube(url: str, media_id: int, repo_id: int) -> str:
    """
    Download YouTube video using yt-dlp
    
    Args:
        url: YouTube URL
        media_id: Media ID for filename
        repo_id: Repository ID for folder structure
    
    Returns:
        Path to downloaded video file
    """
    output_dir = os.path.join(REPO_BASE_FOLDER, str(repo_id), 'media')
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, f"{media_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # yt-dlp may add .mp4 extension
            actual_path = filename
            if not os.path.exists(actual_path):
                # Try with .mp4 extension
                actual_path = os.path.join(output_dir, f"{media_id}.mp4")
            
            logger.info(f"Downloaded YouTube video to: {actual_path}")
            return actual_path
            
    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        raise

def _extract_audio(video_path: str, media_id: int, repo_id: int) -> str:
    """
    Extract and normalize audio from video
    
    Args:
        video_path: Path to video file
        media_id: Media ID for filename
        repo_id: Repository ID for folder structure
    
    Returns:
        Path to normalized audio file (WAV, 16kHz, mono)
    """
    output_dir = os.path.join(REPO_BASE_FOLDER, str(repo_id), 'media')
    audio_path = os.path.join(output_dir, f"{media_id}_audio.wav")
    
    try:
        # Load audio from video
        audio = AudioSegment.from_file(video_path)
        
        # Normalize to mono, 16kHz (optimal for Whisper)
        audio = audio.set_channels(1)  # Mono
        audio = audio.set_frame_rate(16000)  # 16kHz
        
        # Export as WAV
        audio.export(audio_path, format='wav')
        
        logger.info(f"Extracted and normalized audio to: {audio_path}")
        return audio_path
        
    except Exception as e:
        logger.error(f"Error extracting audio: {str(e)}")
        raise