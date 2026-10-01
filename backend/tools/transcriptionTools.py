"""
Transcription tools for handling audio-to-text conversion
Supports OpenAI Whisper API
"""

from openai import OpenAI
import logging
import os
import tempfile
from typing import Optional, Dict, Any, List

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# OpenAI Whisper API rejects files larger than 25 MB. Keep a safety margin below
# that hard limit to account for container/header overhead when re-exporting chunks.
WHISPER_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
WHISPER_CHUNK_SIZE_LIMIT_BYTES = 24 * 1024 * 1024


def _transcribe_single_file(
    client: OpenAI,
    audio_path: str,
    language: Optional[str]
) -> Dict[str, Any]:
    """Transcribe one audio file that is already within the Whisper size limit."""
    with open(audio_path, 'rb') as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language if language and language != '' else None,
            response_format="verbose_json",  # Get detailed response with segments
            timestamp_granularities=["segment"]
        )

    segments = []
    if hasattr(transcript, 'segments') and transcript.segments:
        for segment in transcript.segments:
            segments.append({
                'start': segment.start,
                'end': segment.end,
                'text': segment.text.strip()
            })

    return {
        'segments': segments,
        'language': transcript.language if hasattr(transcript, 'language') else 'unknown',
        'text': transcript.text.strip() if hasattr(transcript, 'text') else ''
    }


def _transcribe_in_chunks(
    client: OpenAI,
    audio_path: str,
    language: Optional[str]
) -> Dict[str, Any]:
    """
    Split an oversized audio file into time-based chunks that each stay under the
    Whisper upload limit, transcribe them sequentially, and merge the results while
    offsetting timestamps so they stay aligned with the original timeline.
    """
    audio = AudioSegment.from_file(audio_path)
    total_ms = len(audio)
    file_size = os.path.getsize(audio_path)

    # Estimate a chunk duration whose exported size stays under the limit, based on
    # the average bytes-per-millisecond of the source file.
    bytes_per_ms = file_size / total_ms if total_ms > 0 else 0
    if bytes_per_ms <= 0:
        raise ValueError(f"Cannot determine audio size ratio for {audio_path}")

    chunk_ms = int(WHISPER_CHUNK_SIZE_LIMIT_BYTES / bytes_per_ms)
    # Guard against pathological values (e.g. very high bitrate) and cap chunks at 20 min.
    chunk_ms = max(30_000, min(chunk_ms, 20 * 60_000))

    num_chunks = (total_ms + chunk_ms - 1) // chunk_ms
    logger.info(
        f"Audio {audio_path} exceeds Whisper limit ({file_size} bytes); "
        f"splitting into {num_chunks} chunk(s) of ~{chunk_ms / 1000:.0f}s"
    )

    merged_segments: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    detected_language: Optional[str] = None

    for index in range(num_chunks):
        start_ms = index * chunk_ms
        end_ms = min(start_ms + chunk_ms, total_ms)
        offset_s = start_ms / 1000.0
        chunk_audio = audio[start_ms:end_ms]

        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            # Export as MP3 to keep chunk uploads small and safely under the limit.
            chunk_audio.export(tmp_path, format='mp3')
            logger.info(
                f"Transcribing chunk {index + 1}/{num_chunks} "
                f"({offset_s:.0f}s–{end_ms / 1000:.0f}s)"
            )
            chunk_result = _transcribe_single_file(client, tmp_path, language)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        if detected_language is None and chunk_result['language'] != 'unknown':
            detected_language = chunk_result['language']

        for segment in chunk_result['segments']:
            merged_segments.append({
                'start': segment['start'] + offset_s,
                'end': segment['end'] + offset_s,
                'text': segment['text']
            })

        if chunk_result['text']:
            text_parts.append(chunk_result['text'])

    return {
        'segments': merged_segments,
        'language': detected_language or 'unknown',
        'text': ' '.join(text_parts).strip()
    }


def transcribe_with_openai_whisper(
    audio_path: str,
    api_key: str,
    language: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transcribe audio using OpenAI's Whisper API
    
    Args:
        audio_path: Path to audio file (supports mp3, mp4, mpeg, mpga, m4a, wav, webm)
        api_key: OpenAI API key
        language: Optional language code (e.g., 'es', 'en', 'fr'). None for auto-detect.
    
    Returns:
        Dictionary with:
        - 'segments': List[{'start': float, 'end': float, 'text': str}]
        - 'language': str
        - 'duration': float
        - 'text': str (full transcription)
    """
    try:
        client = OpenAI(api_key=api_key)
        
        logger.info(f"Transcribing audio with OpenAI Whisper API: {audio_path}")

        # Whisper rejects uploads larger than 25 MB, so split oversized files into
        # smaller chunks and merge the transcriptions back together.
        if os.path.getsize(audio_path) > WHISPER_MAX_UPLOAD_BYTES:
            result = _transcribe_in_chunks(client, audio_path, language)
        else:
            result = _transcribe_single_file(client, audio_path, language)

        segments = result['segments']
        duration = segments[-1]['end'] if segments else 0.0

        transcription_data = {
            'segments': segments,
            'language': result['language'],
            'duration': duration,
            'text': result['text']
        }
        
        logger.info(f"OpenAI Whisper transcription complete: {len(segments)} segments, {duration:.2f}s, language: {transcription_data['language']}")
        return transcription_data
        
    except Exception as e:
        logger.error(f"Error transcribing audio with OpenAI Whisper: {str(e)}")
        raise


def get_transcription_from_service(ai_service, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Get transcription using an AIService configuration
    
    Args:
        ai_service: AIService model instance
        audio_path: Path to audio file
        language: Optional language code
    
    Returns:
        Dictionary with transcription data
    """
    if ai_service.provider == 'OpenAI':
        return transcribe_with_openai_whisper(
            audio_path,
            ai_service.api_key,
            language
        )
    else:
        raise ValueError(f"Unsupported transcription provider: {ai_service.provider}")
