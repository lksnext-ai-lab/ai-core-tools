from models.media import Media
from db.database import SessionLocal
from services.transcription_service import TranscriptionService
from services.silo_service import SiloService
from services.video_analysis_service import VideoAnalysisService
from services.storage_service import get_storage_backend
from utils.logger import get_logger
import asyncio
import os
import tempfile
import yt_dlp
from pydub import AudioSegment
from datetime import datetime

logger = get_logger(__name__)


async def _collect_stream(storage_key: str) -> bytes:
    """Collect all chunks from a storage stream into bytes."""
    backend = get_storage_backend()
    chunks = []
    async for chunk in backend.stream(storage_key):
        chunks.append(chunk)
    return b"".join(chunks)


def _upload_to_storage(key: str, data: bytes, content_type: str | None = None) -> None:
    asyncio.run(get_storage_backend().upload(key, data, content_type))


def _delete_from_storage(key: str) -> None:
    asyncio.run(get_storage_backend().delete(key))

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
        
        # Resolve service IDs from repository configuration
        effective_transcription_id = (
            media.repository.transcription_service_id if media.repository else None
        )
        effective_video_service_id = (
            media.repository.video_ai_service_id if media.repository else None
        )
        
        if not effective_transcription_id:
            raise ValueError(
                f"No transcription service configured on repository {media.repository_id}. "
                f"Please configure a transcription service in the repository settings."
            )
        
        logger.info(
            f"Media {media_id} effective services — "
            f"transcription: {effective_transcription_id}, video: {effective_video_service_id}"
        )

        # Step 1: Download if YouTube
        if media.source_type == 'youtube':
            media.status = 'downloading'
            db.commit()
            
            storage_key = _download_youtube(media.source_url, media_id, media.repository_id)
            media.storage_key = storage_key
            db.commit()
            
            logger.info(f"Downloaded YouTube video for media {media_id}")
        
        # Step 2: Extract audio
        media.status = 'processing'
        db.commit()
        
        audio_storage_key = _extract_audio(media.storage_key)
        logger.info(f"Extracted audio for media {media_id}: {audio_storage_key}")
        
        # Step 3: Transcribe
        media.status = 'transcribing'
        db.commit()

        # Download audio to a local temp file for transcription
        audio_bytes = asyncio.run(_collect_stream(audio_storage_key))
        with tempfile.NamedTemporaryFile(suffix='_audio.wav', delete=False) as tmp_audio:
            tmp_audio.write(audio_bytes)
            tmp_audio_path = tmp_audio.name

        try:
            transcription = TranscriptionService.transcribe_audio(
                tmp_audio_path,
                language=media.forced_language,  # Use forced language if specified
                ai_service_id=effective_transcription_id,
                db=db
            )
        finally:
            os.unlink(tmp_audio_path)
        
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

        logger.info(f"Created {len(chunks_data)} chunks (in-memory) for media {media_id}")
        logger.info(f"First chunk sample: {chunks_data[0] if chunks_data else 'NO CHUNKS'}")

        # Step 4b: Multimodal video analysis (if repository has a video service configured)
        if effective_video_service_id:
            try:
                media.status = 'analyzing_video'
                db.commit()
                
                logger.info(f"Starting chunk-aligned multimodal video analysis for media {media_id}")
                # Download video to a local temp file for analysis
                video_ext = os.path.splitext(media.storage_key)[1] or '.mp4'
                video_bytes = asyncio.run(_collect_stream(media.storage_key))
                tmp_video_path = None
                with tempfile.NamedTemporaryFile(suffix=video_ext, delete=False) as tmp_video_f:
                    tmp_video_f.write(video_bytes)
                    tmp_video_path = tmp_video_f.name
                try:
                    visual_segments = VideoAnalysisService.analyze_video(
                        video_path=tmp_video_path,
                        ai_service_id=effective_video_service_id,
                        db=db,
                        chunks=chunks_data
                    )
                finally:
                    if tmp_video_path and os.path.exists(tmp_video_path):
                        os.unlink(tmp_video_path)
                
                logger.info(f"Video analysis returned {len(visual_segments)} visual segments for media {media_id}")
                
                # Split into separate audio and visual chunks with matching time ranges
                chunks_data = VideoAnalysisService.split_audio_visual_chunks(
                    chunks_data, visual_segments
                )

                media.processing_mode = 'multimodal'
                db.commit()
                logger.info(f"Split into {len(chunks_data)} audio+visual chunks for media {media_id}")
                
            except Exception as e:
                logger.warning(f"Video analysis failed for media {media_id}, continuing with audio-only chunks: {str(e)}")
                media.processing_mode = 'basic'
                db.commit()
                # Don't fail the entire pipeline — continue with audio-only chunks

        # Step 5: Index chunks directly without creating DB rows
        media.status = 'indexing'
        db.commit()

        for idx, chunk_data in enumerate(chunks_data):
            # Preserve chunk_index set by split_audio_visual_chunks so audio/visual
            # pairs from the same time window share the same index for retrieval correlation.
            chunk_data.setdefault('chunk_index', idx)
            SiloService.index_media_chunk(chunk_data, media, db)

        logger.info(f"Indexed {len(chunks_data)} chunks for media {media_id}")
        
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
        
    finally:
        db.close()

def _download_youtube(url: str, media_id: int, repo_id: int) -> str:
    """
    Download YouTube video using yt-dlp, upload to storage, and return the storage key.

    Args:
        url: YouTube URL
        media_id: Media ID for filename
        repo_id: Repository ID for folder structure

    Returns:
        Storage key for the uploaded video
    """
    output_dir = tempfile.mkdtemp()
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

            logger.info(f"Downloaded YouTube video to temp: {actual_path}")

            # Upload to storage and return the storage key
            ext = os.path.splitext(actual_path)[1] or '.mp4'
            key = f"repositories/{repo_id}/{media_id}{ext}"
            with open(actual_path, 'rb') as f:
                _upload_to_storage(key, f.read(), "video/mp4")
            logger.info(f"Uploaded YouTube video to storage: {key}")

            return key

    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        raise
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)

def _extract_audio(storage_key: str) -> str:
    """
    Extract and normalize audio from a video stored in object storage.
    Downloads the video to a local temp file, extracts audio, uploads the result
    to storage, and cleans up both temp files.

    Args:
        storage_key: Storage key for the source video

    Returns:
        Storage key for the normalized audio file (WAV, 16kHz, mono)
    """
    video_ext = os.path.splitext(storage_key)[1] or '.mp4'
    tmp_video = None
    tmp_audio = None

    try:
        # Download video from storage to a local temp file
        video_data = asyncio.run(_collect_stream(storage_key))
        with tempfile.NamedTemporaryFile(suffix=video_ext, delete=False) as f:
            f.write(video_data)
            tmp_video = f.name

        # Extract and normalize audio to a local temp file
        with tempfile.NamedTemporaryFile(suffix='_audio.wav', delete=False) as f:
            tmp_audio = f.name

        audio = AudioSegment.from_file(tmp_video)
        audio = audio.set_channels(1)   # Mono
        audio = audio.set_frame_rate(16000)  # 16kHz
        audio.export(tmp_audio, format='wav')

        # Upload audio to storage
        audio_key = os.path.splitext(storage_key)[0] + "_audio.wav"
        with open(tmp_audio, 'rb') as f:
            _upload_to_storage(audio_key, f.read(), "audio/wav")

        logger.info(f"Extracted and normalized audio to storage: {audio_key}")
        return audio_key

    except Exception as e:
        logger.error(f"Error extracting audio: {str(e)}")
        raise
    finally:
        if tmp_video and os.path.exists(tmp_video):
            os.unlink(tmp_video)
        if tmp_audio and os.path.exists(tmp_audio):
            os.unlink(tmp_audio)