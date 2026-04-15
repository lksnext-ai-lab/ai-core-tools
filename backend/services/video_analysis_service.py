"""
Video Analysis Service

Sends video files to Gemini models (Google / GoogleCloud) for temporal visual analysis.
Returns timestamped visual descriptions that can be merged with transcript chunks.
"""

import os
import json
import base64
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from repositories.ai_service_repository import AIServiceRepository

logger = logging.getLogger(__name__)


# Maximum video size in bytes for supported providers
PROVIDER_MAX_SIZE = {
    'Google': 2 * 1024 * 1024 * 1024,       # 2GB
    'GoogleCloud': 2 * 1024 * 1024 * 1024,  # 2GB (Vertex AI)
}

SUPPORTED_VIDEO_PROVIDERS = ('Google', 'GoogleCloud')

VIDEO_ANALYSIS_PROMPT = """Analyze this video and describe what happens visually in chronological segments.

For each distinct visual segment or scene, provide:
- start_time: approximate start time in seconds
- end_time: approximate end time in seconds  
- visual_description: what is shown visually (diagrams, slides, code, UI, actions, people, etc.)

Focus on visual information that would NOT be captured by audio transcription alone:
- Text shown on screen (slides, code, terminal output)
- Diagrams, charts, or visual elements
- UI interactions or demonstrations
- Scene transitions and visual context

Return your response as a JSON array:
[
  {"start_time": 0.0, "end_time": 30.0, "visual_description": "..."},
  {"start_time": 30.0, "end_time": 60.0, "visual_description": "..."}
]

IMPORTANT: Return ONLY the JSON array, no additional text or markdown formatting."""


def _build_chunk_aligned_prompt(chunks: List[Dict]) -> str:
    """Build a prompt that asks the Video-LLM to describe exactly the given chunk time ranges."""
    segments_desc = "\n".join(
        f'  {{"chunk_index": {i}, "start_time": {c["start_time"]}, "end_time": {c["end_time"]}, "visual_description": "..."}}'
        for i, c in enumerate(chunks)
    )
    return f"""Analyze this video and describe what is shown visually for each of the following time segments.

For each segment, describe ONLY visual information that would NOT be captured by audio transcription:
- Text shown on screen (slides, code, terminal output)
- Diagrams, charts, or visual elements
- UI interactions or demonstrations
- Scene transitions and visual context
- People, objects, and actions visible

Return your response as a JSON array with EXACTLY {len(chunks)} items, one per segment, in this format:
[
{segments_desc}
]

Fill in the "visual_description" field for each segment. Keep each description concise but informative.
IMPORTANT: Return ONLY the JSON array, no additional text or markdown formatting."""


class VideoAnalysisService:
    """Service for analyzing video content using Video-capable LLMs"""

    @staticmethod
    def analyze_video(
        video_path: str,
        ai_service_id: int,
        db: Session,
        chunks: Optional[List[Dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze a video file using a Video-LLM service.
        
        If chunks are provided, uses chunk-aligned prompting: the LLM is asked to describe
        exactly the time ranges of the given chunks, producing one visual description per chunk.
        
        If chunks are not provided, falls back to free-form analysis where the LLM decides
        its own time segments.
        
        Args:
            video_path: Path to the video file
            ai_service_id: ID of an AI service with video capabilities
            db: Database session
            chunks: Optional list of transcript chunks with start_time, end_time, text
        
        Returns:
            List of dicts with keys: start_time, end_time, visual_description
            (and chunk_index if chunk-aligned)
        """
        ai_service = AIServiceRepository.get_by_id(db, ai_service_id)
        if not ai_service:
            raise ValueError(f"AI Service with ID {ai_service_id} not found")
        
        if not ai_service.supports_video:
            raise ValueError(f"AI Service '{ai_service.name}' does not have video capabilities enabled")
        
        provider = ai_service.provider if isinstance(ai_service.provider, str) else ai_service.provider.value

        if provider not in SUPPORTED_VIDEO_PROVIDERS:
            raise ValueError(
                f"Video analysis is only supported for Google and GoogleCloud providers. "
                f"Got: {provider}"
            )

        # Check file size
        file_size = os.path.getsize(video_path)
        max_size = PROVIDER_MAX_SIZE[provider]
        
        if file_size > max_size:
            raise ValueError(
                f"Video file too large ({file_size / (1024*1024):.1f}MB). "
                f"Max for {provider}: {max_size / (1024*1024):.0f}MB"
            )
        
        # Build prompt: chunk-aligned if chunks provided, otherwise free-form
        prompt = _build_chunk_aligned_prompt(chunks) if chunks else VIDEO_ANALYSIS_PROMPT
        
        logger.info(f"Analyzing video with AI service {ai_service_id} ({provider}): {video_path}"
                     f"{f' [chunk-aligned, {len(chunks)} chunks]' if chunks else ' [free-form]'}")
        
        if provider == 'Google':
            return _analyze_with_gemini(ai_service, video_path, prompt)
        else:  # GoogleCloud
            return _analyze_with_vertex_ai(ai_service, video_path, prompt)

    @staticmethod
    def split_audio_visual_chunks(
        chunks: List[Dict],
        visual_segments: List[Dict]
    ) -> List[Dict]:
        """
        Split audio chunks and visual segments into separate chunks sharing the
        same time ranges.  For each temporal window the method produces up to two
        independent chunks:

        1. An **audio** chunk  (``chunk_type='audio'``) with the transcript text.
        2. A **visual** chunk (``chunk_type='visual'``) with the visual description.

        Both chunks carry identical ``start_time`` / ``end_time`` so they can be
        correlated later, but they are embedded independently in the vector store.

        If no visual description is available for a given time range only the
        audio chunk is emitted.

        Args:
            chunks: Transcript chunks with start_time, end_time, text.
            visual_segments: Visual segments returned by ``analyze_video``.

        Returns:
            Flat list of chunks, each with an added ``chunk_type`` field
            (``'audio'`` or ``'visual'``).
        """
        # Build a lookup: chunk_index → visual description
        has_chunk_index = any('chunk_index' in vs for vs in visual_segments) if visual_segments else False

        visual_by_index: Dict[int, str] = {}
        if visual_segments and has_chunk_index:
            for vs in visual_segments:
                idx = vs.get('chunk_index')
                if idx is not None:
                    desc = vs.get('visual_description', '')
                    if desc:
                        visual_by_index[int(idx)] = desc
        elif visual_segments:
            # Fallback: timestamp-overlap matching
            for i, chunk in enumerate(chunks):
                c_start = chunk.get('start_time', 0)
                c_end = chunk.get('end_time', 0)
                descs = [
                    vs.get('visual_description', '')
                    for vs in visual_segments
                    if vs.get('start_time', 0) < c_end and vs.get('end_time', 0) > c_start
                    and vs.get('visual_description')
                ]
                if descs:
                    visual_by_index[i] = ' | '.join(descs)

        result: List[Dict] = []
        for i, chunk in enumerate(chunks):
            # Audio chunk — always emitted
            audio_chunk = {
                **chunk,
                'chunk_type': 'audio',
            }
            # Remove any leftover visual_description from audio chunk
            audio_chunk.pop('visual_description', None)
            result.append(audio_chunk)

            # Visual chunk — only if description exists
            visual_desc = visual_by_index.get(i)
            if visual_desc:
                visual_chunk = {
                    'start_time': chunk.get('start_time', 0),
                    'end_time': chunk.get('end_time', 0),
                    'text': visual_desc,
                    'chunk_type': 'visual',
                    'chunk_index': i,
                }
                result.append(visual_chunk)

        return result


def _parse_llm_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse JSON response from LLM, handling potential formatting issues"""
    import re
    text = response_text.strip()
    
    # Try to extract JSON from markdown code block
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0].strip()
    elif '```' in text:
        text = text.split('```')[1].split('```')[0].strip()
    
    # Fix missing commas between JSON objects in arrays: }\n  { → },\n  {
    text = re.sub(r'\}\s*\n\s*\{', '},\n{', text)
    
    try:
        result = json.loads(text)
        if isinstance(result, list):
            # Validate structure
            validated = []
            for item in result:
                entry = {
                    'start_time': float(item.get('start_time', 0)),
                    'end_time': float(item.get('end_time', 0)),
                    'visual_description': str(item.get('visual_description', ''))
                }
                if 'chunk_index' in item:
                    entry['chunk_index'] = int(item['chunk_index'])
                validated.append(entry)
            return validated
        else:
            logger.warning(f"Video analysis response was not a list: {type(result)}")
            return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse video analysis response as JSON: {e}")
        logger.error(f"Response text: {text[:500]}")
        return []


def _analyze_with_gemini(ai_service, video_path: str, prompt: str = VIDEO_ANALYSIS_PROMPT) -> List[Dict[str, Any]]:
    """Analyze video using Google Gemini via LangChain ChatGoogleGenerativeAI.
    
    Uploads the video via the google-genai Files API, then uses LangChain to invoke
    the model with the file URI as multimodal input.
    """
    try:
        import time
        from google import genai
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        client = genai.Client(api_key=ai_service.api_key)

        logger.info(f"Uploading video to Gemini Files API: {video_path}")
        video_file = client.files.upload(file=video_path)

        while video_file.state.name == "PROCESSING":
            logger.info("Waiting for Gemini to process video...")
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise ValueError(f"Gemini video processing failed: {video_file.state.name}")

        logger.info("Gemini video processed, requesting analysis via LangChain...")

        llm = ChatGoogleGenerativeAI(
            model=ai_service.description,
            api_key=ai_service.api_key,
            temperature=0.1,
            max_output_tokens=8192,
        )

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "media", "file_uri": video_file.uri, "mime_type": video_file.mime_type},
        ])

        response = llm.invoke([message])

        # Cleanup uploaded file
        try:
            client.files.delete(name=video_file.name)
        except Exception:
            pass

        return _parse_llm_response(response.content)

    except ImportError:
        raise ValueError(
            "Required packages not installed. "
            "Install with: pip install langchain-google-genai google-genai"
        )
    except Exception as e:
        logger.error(f"Error analyzing video with Gemini: {str(e)}")
        raise


def _analyze_with_vertex_ai(ai_service, video_path: str, prompt: str = VIDEO_ANALYSIS_PROMPT) -> List[Dict[str, Any]]:
    """Analyze video using Google Cloud Vertex AI via ChatGoogleGenerativeAI (vertexai=True).
    
    Reads the video as inline base64 data and passes it to the model
    using LangChain's HumanMessage multimodal content format.
    """
    try:
        from google.oauth2 import service_account
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        project_id = (ai_service.endpoint or "").strip()
        location = (getattr(ai_service, 'api_version', None) or "").strip() or "europe-west1"
        api_key_raw = (ai_service.api_key or "").strip()

        if not api_key_raw:
            raise ValueError("Service Account JSON is required for GoogleCloud provider.")
        if not project_id:
            raise ValueError("Project ID (endpoint field) is required for GoogleCloud provider.")

        sa_info = json.loads(api_key_raw)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

        ext = os.path.splitext(video_path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
        }
        mime_type = mime_map.get(ext, 'video/mp4')

        with open(video_path, 'rb') as f:
            video_b64 = base64.b64encode(f.read()).decode('utf-8')

        llm = ChatGoogleGenerativeAI(
            model=ai_service.description,
            credentials=credentials,
            project=project_id,
            location=location,
            temperature=0.1,
            max_output_tokens=8192,
            vertexai=True,
        )

        logger.info(f"Requesting video analysis from Vertex AI ({project_id}/{location})...")

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "media", "data": video_b64, "mime_type": mime_type},
        ])

        response = llm.invoke([message])
        return _parse_llm_response(response.content)

    except ImportError:
        raise ValueError(
            "Required packages not installed. "
            "Install with: pip install langchain-google-genai google-auth"
        )
    except Exception as e:
        logger.error(f"Error analyzing video with Vertex AI: {str(e)}")
        raise

