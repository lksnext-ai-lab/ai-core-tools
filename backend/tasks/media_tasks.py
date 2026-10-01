from models.media import Media
from db.database import SessionLocal
from services.transcription_service import TranscriptionService
from services.silo_service import SiloService
from services.video_analysis_service import VideoAnalysisService
from utils.logger import get_logger
import json
import os
import subprocess
import yt_dlp
from pydub import AudioSegment
from datetime import datetime

REPO_BASE_FOLDER = os.path.abspath(os.getenv('REPO_BASE_FOLDER'))
logger = get_logger(__name__)

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
                f"Please configure a transcription service on the agent's media settings."
            )
        
        logger.info(
            f"Media {media_id} effective services — "
            f"transcription: {effective_transcription_id}, video: {effective_video_service_id}"
        )

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

        if not _has_audio_stream(media.file_path):
            raise ValueError(
                "The uploaded file has no audio track. Upload a video or audio "
                "file that contains speech."
            )

        audio_path = _extract_audio(media.file_path, media_id, media.repository_id)
        logger.info(f"Extracted audio for media {media_id}: {audio_path}")
        
        # Step 3: Transcribe
        media.status = 'transcribing'
        db.commit()
        
        transcription = TranscriptionService.transcribe_audio(
            audio_path,
            language=media.forced_language,  # Use forced language if specified
            ai_service_id=effective_transcription_id,
            db=db
        )
        
        # Update media with transcription metadata
        media.language = transcription['language']
        media.duration = float(transcription['duration'])
        db.commit()
        
        segments = transcription.get('segments') or []
        logger.info(
            f"Transcribed media {media_id}: {len(segments)} segments, "
            f"language: {transcription['language']}"
        )
        if not segments:
            raise ValueError(
                "No speech was detected in the audio. Make sure the file "
                "contains spoken words."
            )

        # Step 4: Create chunks with custom configuration
        chunks_data = TranscriptionService.create_chunks(
            segments,
            min_window=media.chunk_min_duration or 30,
            max_window=media.chunk_max_duration or 120,
            overlap=media.chunk_overlap or 0
        )

        logger.info(f"Created {len(chunks_data)} chunks (in-memory) for media {media_id}")
        logger.info(f"First chunk sample: {chunks_data[0] if chunks_data else 'NO CHUNKS'}")

        # Step 4b: Multimodal video analysis — only when the media actually
        # carries a video stream. A video service configured on the agent must
        # not trigger analysis of an audio-only file: the model then invents
        # "visual" descriptions that pollute retrieval with fiction.
        if effective_video_service_id and _has_video_stream(media.file_path):
            try:
                media.status = 'analyzing_video'
                db.commit()
                
                logger.info(f"Starting chunk-aligned multimodal video analysis for media {media_id}")
                visual_segments = VideoAnalysisService.analyze_video(
                    video_path=media.file_path,
                    ai_service_id=effective_video_service_id,
                    db=db,
                    chunks=chunks_data
                )
                
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
    Download YouTube video using yt-dlp
    
    Args:
        url: YouTube URL
        media_id: Media ID for filename
        repo_id: Repository ID for folder structure
    
    Returns:
        Path to downloaded video file
    """
    output_dir = os.path.join(REPO_BASE_FOLDER, str(repo_id))
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
        raw = str(e)
        logger.error(f"Error downloading YouTube video: {raw}")
        raise ValueError(_youtube_download_error_message(raw)) from e


def _youtube_download_error_message(raw: str) -> str:
    """Map a raw yt-dlp failure to a concise, user-actionable message."""
    low = raw.lower()
    if "403" in raw or "forbidden" in low or "sign in to confirm" in low:
        return (
            "YouTube is blocking downloads from this server. Download the video "
            "yourself and upload the file directly."
        )
    if "private video" in low:
        return "This YouTube video is private and cannot be downloaded."
    if any(s in low for s in ("video unavailable", "not available", "has been removed", "age-restricted")):
        return (
            "This YouTube video is unavailable (removed, region-locked, or "
            "age-restricted)."
        )
    if any(s in low for s in ("unsupported url", "is not a valid url", "not a valid url")):
        return "The provided URL is not a valid YouTube video URL."
    return f"Could not download the YouTube video: {raw[:200]}"


def _has_audio_stream(path: str) -> bool:
    """Return True if the media file contains at least one audio stream.

    Uses ffprobe (already required by pydub). On any probe failure it returns
    True so extraction still runs and surfaces the real error instead of a
    false "no audio" verdict.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        streams = json.loads(result.stdout or "{}").get("streams", [])
        return len(streams) > 0
    except Exception as exc:
        logger.warning("Could not probe audio streams for %s: %s", path, exc)
        return True


def _has_video_stream(path: str) -> bool:
    """Return True if the file has a real video stream (not just cover art).

    Unlike the audio probe this fails closed: if ffprobe cannot confirm a
    video stream, skip video analysis rather than let the model invent
    "visual" descriptions for an audio-only file.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v",
                "-show_entries", "stream=codec_type,disposition",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        streams = json.loads(result.stdout or "{}").get("streams", [])
        for stream in streams:
            if stream.get("codec_type") != "video":
                continue
            # An MP3/M4A cover image is exposed as a video stream too — skip it.
            if (stream.get("disposition") or {}).get("attached_pic") == 1:
                continue
            return True
        return False
    except Exception as exc:
        logger.warning("Could not probe video streams for %s: %s", path, exc)
        return False

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
    output_dir = os.path.join(REPO_BASE_FOLDER, str(repo_id))
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

    except IndexError as e:
        # pydub raises a bare "list index out of range" when the container has
        # no decodable audio stream. Surface something actionable instead.
        logger.error(f"Error extracting audio (no readable audio stream): {e}")
        raise ValueError(
            "The file's audio track could not be read. It may be missing, "
            "empty, or in an unsupported codec."
        ) from e
    except Exception as e:
        logger.error(f"Error extracting audio: {str(e)}")
        raise