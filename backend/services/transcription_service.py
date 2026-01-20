import whisper
import os
from typing import List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)

class TranscriptionService:
    # Load model once at class level (singleton pattern)
    _model = None
    MODEL_SIZE = os.getenv('WHISPER_MODEL_SIZE', 'base')  # tiny, base, small, medium, large
    
    @classmethod
    def _get_model(cls):
        """Lazy load Whisper model"""
        if cls._model is None:
            logger.info(f"Loading Whisper model: {cls.MODEL_SIZE}")
            cls._model = whisper.load_model(cls.MODEL_SIZE)
        return cls._model
    
    @staticmethod
    def transcribe_audio(audio_path: str) -> dict:
        """
        Transcribe audio file using Whisper
        
        Args:
            audio_path: Path to audio file (preferably WAV, 16kHz, mono)
        
        Returns:
            {
                'segments': [{'start': float, 'end': float, 'text': str}],
                'language': str,
                'duration': float,
                'text': str  # Full transcription
            }
        """
        try:
            model = TranscriptionService._get_model()
            
            logger.info(f"Transcribing audio: {audio_path}")
            
            # Transcribe with word-level timestamps
            result = model.transcribe(
                audio_path,
                task='transcribe',
                verbose=False,
                word_timestamps=True
            )
            
            # Extract segments with timestamps
            segments = []
            for segment in result.get('segments', []):
                segments.append({
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                })
            
            # Get duration from last segment or audio file
            duration = segments[-1]['end'] if segments else 0.0
            
            transcription_data = {
                'segments': segments,
                'language': result.get('language', 'unknown'),
                'duration': duration,
                'text': result.get('text', '').strip()
            }
            
            logger.info(f"Transcription complete: {len(segments)} segments, {duration:.2f}s, language: {transcription_data['language']}")
            return transcription_data
            
        except Exception as e:
            logger.error(f"Error transcribing audio {audio_path}: {str(e)}")
            raise
    
    @staticmethod
    def create_chunks(segments: List[dict], min_window: int = 30, max_window: int = 120) -> List[dict]:
        """
        Group segments into chunks based on time windows
        
        Args:
            segments: List of segments from transcription
            min_window: Minimum chunk duration in seconds (default 30s)
            max_window: Maximum chunk duration in seconds (default 120s)
        
        Returns:
            List of chunks: [{'text': str, 'start_time': float, 'end_time': float}]
        """
        if not segments:
            return []
        
        chunks = []
        current_chunk = {
            'text': '',
            'start_time': segments[0]['start'],
            'end_time': segments[0]['start']
        }
        
        for segment in segments:
            segment_text = segment['text'].strip()
            if not segment_text:
                continue
            
            # Calculate duration if we add this segment
            potential_duration = segment['end'] - current_chunk['start_time']
            
            # If adding this segment would exceed max_window, save current chunk and start new one
            if potential_duration > max_window and current_chunk['text']:
                chunks.append(current_chunk.copy())
                current_chunk = {
                    'text': segment_text,
                    'start_time': segment['start'],
                    'end_time': segment['end']
                }
            else:
                # Add segment to current chunk
                if current_chunk['text']:
                    current_chunk['text'] += ' ' + segment_text
                else:
                    current_chunk['text'] = segment_text
                current_chunk['end_time'] = segment['end']
                
                # If we've reached min_window, we could potentially end chunk at natural break
                chunk_duration = current_chunk['end_time'] - current_chunk['start_time']
                
                # End chunk if we hit a natural break (sentence ending) and min duration met
                if chunk_duration >= min_window and segment_text.rstrip().endswith(('.', '!', '?')):
                    chunks.append(current_chunk.copy())
                    current_chunk = {
                        'text': '',
                        'start_time': segment['end'],
                        'end_time': segment['end']
                    }
        
        # Add final chunk if it has content
        if current_chunk['text']:
            chunks.append(current_chunk)
        
        logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments")
        return chunks