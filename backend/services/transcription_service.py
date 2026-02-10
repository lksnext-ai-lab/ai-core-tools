from typing import List, Optional
from sqlalchemy.orm import Session
from utils.logger import get_logger
from tools.transcriptionTools import get_transcription_from_service
from repositories.ai_service_repository import AIServiceRepository

logger = get_logger(__name__)

class TranscriptionService:
    
    @staticmethod
    def transcribe_audio(
        audio_path: str, 
        language: Optional[str] = None,
        db: Session = None,
        ai_service_id: Optional[int] = None
    ) -> dict:
        """
        Transcribe audio file using configured AI Service (OpenAI Whisper API)
        
        Args:
            audio_path: Path to audio file
            language: Force language (e.g., 'es', 'en', 'fr'). None for auto-detect.
            db: Database session (required for service config lookup)
            ai_service_id: AI Service ID with Whisper configuration (required)
        
        Returns:
            {
                'segments': [{'start': float, 'end': float, 'text': str}],
                'language': str,
                'duration': float,
                'text': str  # Full transcription
            }
        
        Raises:
            ValueError: If db or ai_service_id is not provided, or AI service not found
        """
        try:
            if not db or not ai_service_id:
                raise ValueError("Database session and AI service ID are required for transcription")
            
            logger.info(f"Using AI Service {ai_service_id} for transcription")
            ai_service = AIServiceRepository.get_by_id(db, ai_service_id)
            
            if not ai_service:
                raise ValueError(f"AI Service with ID {ai_service_id} not found")
            
            return get_transcription_from_service(ai_service, audio_path, language)
            
        except Exception as e:
            logger.error(f"Error transcribing audio {audio_path}: {str(e)}")
            raise
    
    @staticmethod
    def create_chunks(segments: List[dict], min_window: int = 30, max_window: int = 120, overlap: int = 0) -> List[dict]:
        """
        Group segments into chunks based on time windows with optional overlap
        
        Args:
            segments: List of segments from transcription
            min_window: Minimum chunk duration in seconds (default 30s)
            max_window: Maximum chunk duration in seconds (default 120s)
            overlap: Overlap duration in seconds between chunks (default 0s, recommended 5-10s)
        
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
                chunks.append({
                    'text': current_chunk['text'],
                    'start_time': float(current_chunk['start_time']),
                    'end_time': float(current_chunk['end_time'])
                })
                
                # Start new chunk with overlap
                overlap_start = max(current_chunk['end_time'] - overlap, current_chunk['start_time'])
                
                # Find segments that fall within overlap period
                overlap_text = ''
                if overlap > 0:
                    for prev_seg in segments:
                        if prev_seg['start'] >= overlap_start and prev_seg['end'] <= current_chunk['end_time']:
                            overlap_text += ' ' + prev_seg['text'].strip()
                
                current_chunk = {
                    'text': overlap_text.strip() + (' ' + segment_text if overlap_text else segment_text),
                    'start_time': overlap_start if overlap > 0 else segment['start'],
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
                    chunks.append({
                        'text': current_chunk['text'],
                        'start_time': float(current_chunk['start_time']),
                        'end_time': float(current_chunk['end_time'])
                    })
                    
                    # Start new chunk with overlap
                    overlap_start = max(current_chunk['end_time'] - overlap, current_chunk['start_time'])
                    
                    # Find segments that fall within overlap period
                    overlap_text = ''
                    if overlap > 0:
                        for prev_seg in segments:
                            if prev_seg['start'] >= overlap_start and prev_seg['end'] <= current_chunk['end_time']:
                                overlap_text += ' ' + prev_seg['text'].strip()
                    
                    current_chunk = {
                        'text': overlap_text.strip(),
                        'start_time': overlap_start if overlap > 0 else segment['end'],
                        'end_time': segment['end']
                    }
        
        # Add final chunk if it has content
        if current_chunk['text']:
            chunks.append({
                'text': current_chunk['text'],
                'start_time': float(current_chunk['start_time']),
                'end_time': float(current_chunk['end_time'])
            })
        
        logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments (overlap: {overlap}s)")
        return chunks
    