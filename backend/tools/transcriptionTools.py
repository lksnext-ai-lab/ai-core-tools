"""
Transcription tools for handling audio-to-text conversion
Supports OpenAI Whisper API
"""

from openai import OpenAI
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


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
        
        # Open the audio file
        with open(audio_path, 'rb') as audio_file:
            # Call Whisper API with verbose response format
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language if language and language != '' else None,
                response_format="verbose_json",  # Get detailed response with segments
                timestamp_granularities=["segment"]
            )
        
        # Parse response
        segments = []
        if hasattr(transcript, 'segments') and transcript.segments:
            for segment in transcript.segments:
                segments.append({
                    'start': segment.start, 
                    'end': segment.end,      
                    'text': segment.text.strip() 
                })
        
        duration = segments[-1]['end'] if segments else 0.0

        transcription_data = {
            'segments': segments,
            'language': transcript.language if hasattr(transcript, 'language') else 'unknown',
            'duration': duration,
            'text': transcript.text.strip() if hasattr(transcript, 'text') else ''
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
