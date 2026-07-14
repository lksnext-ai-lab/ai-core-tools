"""
Playground Media Service

Manages temporary repositories for the agent playground.
Creates temp repo + silo on first upload (media or file), processes content
through the standard vectorization pipeline, and cleans everything up on
conversation reset or explicit deletion.

Media (video/audio) is transcribed and chunked via the MediaService pipeline.
Files (PDFs, text) are chunked and indexed directly into the same silo.
"""

import os
import logging
from typing import Optional, List, Dict, Any

from fastapi import UploadFile, BackgroundTasks
from sqlalchemy.orm import Session

from models.repository import Repository
from models.media import Media
from models.agent import Agent
from services.repository_service import RepositoryService
from services.media_service import MediaService
from services.silo_service import SiloService

logger = logging.getLogger(__name__)

TEMP_REPO_PREFIX = "_playground_"

# File types that should be vectorized instead of injected into context
VECTORIZABLE_FILE_TYPES = {"pdf", "text"}


def _temp_repo_name(agent_id: int, session_id: str) -> str:
    return f"{TEMP_REPO_PREFIX}{agent_id}_{session_id}"


class PlaygroundMediaService:
    """Manages temporary media repositories for the agent playground."""

    @staticmethod
    def _resolve_media_config(
        agent_id: int,
        db: Session,
        transcription_service_id: Optional[int],
        video_ai_service_id: Optional[int],
        forced_language: Optional[str],
        chunk_min_duration: Optional[int],
        chunk_max_duration: Optional[int],
        chunk_overlap: Optional[int],
    ) -> Dict[str, Any]:
        """Fill missing media-upload parameters with the agent-level config.

        Media processing is configured once on the agent, so the playground
        upload only needs the file/URL. Any value explicitly passed in the
        request still takes precedence over the agent defaults.
        """
        agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()

        return {
            "transcription_service_id": (
                transcription_service_id
                if transcription_service_id is not None
                else getattr(agent, "transcription_service_id", None)
            ),
            "video_ai_service_id": (
                video_ai_service_id
                if video_ai_service_id is not None
                else getattr(agent, "video_ai_service_id", None)
            ),
            "forced_language": (
                forced_language
                if forced_language is not None
                else getattr(agent, "media_forced_language", None)
            ),
            "chunk_min_duration": (
                chunk_min_duration
                if chunk_min_duration is not None
                else getattr(agent, "media_chunk_min_duration", None)
            ),
            "chunk_max_duration": (
                chunk_max_duration
                if chunk_max_duration is not None
                else getattr(agent, "media_chunk_max_duration", None)
            ),
            "chunk_overlap": (
                chunk_overlap
                if chunk_overlap is not None
                else getattr(agent, "media_chunk_overlap", None)
            ),
        }

    @staticmethod
    def get_temp_repository(
        app_id: int,
        agent_id: int,
        session_id: str,
        db: Session,
    ) -> Optional[Repository]:
        """Find the temp playground repository for a given agent + session."""
        name = _temp_repo_name(agent_id, session_id)
        return (
            db.query(Repository)
            .filter(Repository.app_id == app_id, Repository.name == name)
            .first()
        )

    @staticmethod
    def get_or_create_temp_repository(
        app_id: int,
        agent_id: int,
        session_id: str,
        db: Session,
        transcription_service_id: Optional[int] = None,
        video_ai_service_id: Optional[int] = None,
        embedding_service_id: Optional[int] = None,
    ) -> Repository:
        """Get or create a temporary repository for playground media.

        The temp repo name follows the convention ``_playground_{agent_id}_{session_id}``.
        A new silo is automatically created with the repo (standard flow).
        """
        existing = PlaygroundMediaService.get_temp_repository(
            app_id, agent_id, session_id, db
        )
        if existing:
            # Keep the temp repo in sync with the latest resolved media config
            # (e.g. the agent's transcription/video services were configured
            # after the repo was first created in this session). Only explicit
            # (non-None) values overwrite existing config — callers that don't
            # resolve media services (e.g. file vectorization) pass None and
            # must not wipe an in-flight transcription's service configuration.
            updated = False
            if (
                transcription_service_id is not None
                and existing.transcription_service_id != transcription_service_id
            ):
                existing.transcription_service_id = transcription_service_id
                updated = True
            if (
                video_ai_service_id is not None
                and existing.video_ai_service_id != video_ai_service_id
            ):
                existing.video_ai_service_id = video_ai_service_id
                updated = True
            if updated:
                db.commit()
                logger.info(
                    "Updated temp playground repo %s media config "
                    "(transcription=%s, video=%s)",
                    existing.repository_id,
                    transcription_service_id,
                    video_ai_service_id,
                )
            return existing

        # Resolve embedding service: explicit request value > the agent's
        # configured media embedding service. There is NO arbitrary app/system
        # fallback — the embedding service is required on the agent so media is
        # never vectorized with a wrong/misconfigured model.
        if not embedding_service_id:
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            embedding_service_id = getattr(agent, "media_embedding_service_id", None)
        if not embedding_service_id:
            raise ValueError(
                "No media embedding service configured for this agent. Set it in "
                "the agent's Media Processing configuration before uploading media."
            )

        repo = Repository(
            name=_temp_repo_name(agent_id, session_id),
            type="playground_media",
            status="active",
            app_id=app_id,
            transcription_service_id=transcription_service_id,
            video_ai_service_id=video_ai_service_id,
        )

        created = RepositoryService.create_repository(
            repository=repo,
            embedding_service_id=embedding_service_id,
            db=db,
        )
        logger.info(
            "Created temp playground repo %s (silo %s) for agent %s session %s",
            created.repository_id,
            created.silo_id,
            agent_id,
            session_id,
        )
        return created

    @staticmethod
    async def upload_media_files(
        app_id: int,
        agent_id: int,
        session_id: str,
        files: List[UploadFile],
        db: Session,
        background_tasks: BackgroundTasks,
        transcription_service_id: Optional[int] = None,
        video_ai_service_id: Optional[int] = None,
        embedding_service_id: Optional[int] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        
        cfg = PlaygroundMediaService._resolve_media_config(
            agent_id,
            db,
            transcription_service_id,
            video_ai_service_id,
            forced_language,
            chunk_min_duration,
            chunk_max_duration,
            chunk_overlap,
        )

        repo = PlaygroundMediaService.get_or_create_temp_repository(
            app_id,
            agent_id,
            session_id,
            db,
            transcription_service_id=cfg["transcription_service_id"],
            video_ai_service_id=cfg["video_ai_service_id"],
            embedding_service_id=embedding_service_id,
        )

        created_media, failed_files = await MediaService.upload_media_files(
            repository_id=repo.repository_id,
            files=files,
            folder_id=None,
            db=db,
            background_tasks=background_tasks,
            user_context=None,
            forced_language=cfg["forced_language"],
            chunk_min_duration=cfg["chunk_min_duration"],
            chunk_max_duration=cfg["chunk_max_duration"],
            chunk_overlap=cfg["chunk_overlap"],
        )

        return {
            "repository_id": repo.repository_id,
            "silo_id": repo.silo_id,
            "created_media": created_media,
            "failed_files": failed_files,
        }

    @staticmethod
    async def upload_youtube(
        app_id: int,
        agent_id: int,
        session_id: str,
        url: str,
        db: Session,
        background_tasks: BackgroundTasks,
        transcription_service_id: Optional[int] = None,
        video_ai_service_id: Optional[int] = None,
        embedding_service_id: Optional[int] = None,
        forced_language: Optional[str] = None,
        chunk_min_duration: Optional[int] = None,
        chunk_max_duration: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Add a YouTube URL to a temp playground repository."""
        cfg = PlaygroundMediaService._resolve_media_config(
            agent_id,
            db,
            transcription_service_id,
            video_ai_service_id,
            forced_language,
            chunk_min_duration,
            chunk_max_duration,
            chunk_overlap,
        )

        repo = PlaygroundMediaService.get_or_create_temp_repository(
            app_id,
            agent_id,
            session_id,
            db,
            transcription_service_id=cfg["transcription_service_id"],
            video_ai_service_id=cfg["video_ai_service_id"],
            embedding_service_id=embedding_service_id,
        )

        media = await MediaService.create_media_from_youtube(
            url=url,
            repository_id=repo.repository_id,
            folder_id=None,
            db=db,
            background_tasks=background_tasks,
            forced_language=cfg["forced_language"],
            chunk_min_duration=cfg["chunk_min_duration"],
            chunk_max_duration=cfg["chunk_max_duration"],
            chunk_overlap=cfg["chunk_overlap"],
        )

        return {
            "repository_id": repo.repository_id,
            "silo_id": repo.silo_id,
            "media": media,
        }

    @staticmethod
    def list_media(
        app_id: int,
        agent_id: int,
        session_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """List media items in the temp playground repository."""
        repo = PlaygroundMediaService.get_temp_repository(
            app_id, agent_id, session_id, db
        )
        if not repo:
            return []

        media_items = db.query(Media).filter(
            Media.repository_id == repo.repository_id
        ).all()

        AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma'}

        def _media_type(media: Media) -> str:
            """Return 'audio' or 'video' based on file name or source type."""
            if media.source_type == 'youtube':
                return 'video'
            name = (media.name or media.file_path or '').lower()
            ext = name[name.rfind('.'):] if '.' in name else ''
            return 'audio' if ext in AUDIO_EXTENSIONS else 'video'

        return [
            {
                "media_id": m.media_id,
                "name": m.name,
                "status": m.status,
                "source_type": m.source_type,
                "media_type": _media_type(m),
                "duration": m.duration,
                "error_message": m.error_message,
            }
            for m in media_items
        ]

    @staticmethod
    def cleanup(
        app_id: int,
        agent_id: int,
        session_id: str,
        db: Session,
    ) -> bool:
        """Delete the temp playground repository, its silo, and all vector data."""
        repo = PlaygroundMediaService.get_temp_repository(
            app_id, agent_id, session_id, db
        )
        if not repo:
            return False

        logger.info(
            "Cleaning up playground media: repo %s, silo %s (agent %s, session %s)",
            repo.repository_id,
            repo.silo_id,
            agent_id,
            session_id,
        )
        RepositoryService.delete_repository(repo, db)

        return True

    @staticmethod
    def get_temp_silo_ids_for_agent(
        app_id: int,
        agent_id: int,
        session_id: Optional[str],
        db: Session,
    ) -> List[int]:
        """Return silo IDs from any temp playground repos for this agent/session.

        Used by agent execution to include temp media silos in retrieval.
        """
        if not session_id:
            return []

        repo = PlaygroundMediaService.get_temp_repository(
            app_id, agent_id, session_id, db
        )
        if repo and repo.silo_id:
            return [repo.silo_id]
        return []

    @staticmethod
    def vectorize_uploaded_file(
        app_id: int,
        agent_id: int,
        session_id: str,
        file_id: str,
        filename: str,
        file_path: Optional[str],
        content: str,
        db: Session,
        embedding_service_id: Optional[int] = None,
    ) -> bool:
        """Vectorize a single file at upload time into the shared temp silo.

        Called immediately after a file is uploaded to the playground, so that
        vectorization happens once and the message hot path never re-processes it.

        Args:
            app_id: App ID.
            agent_id: Agent ID.
            session_id: Conversation session ID (e.g. ``conv_5_abc123``).
            file_id: Unique file identifier.
            filename: Original filename.
            file_path: Relative path to TMP_BASE_FOLDER (may be None).
            content: Pre-extracted text content (fallback if file_path unavailable).
            db: Database session.
            embedding_service_id: Optional explicit embedding service ID.

        Returns:
            True if file was successfully vectorized.
        """
        repo = PlaygroundMediaService.get_or_create_temp_repository(
            app_id, agent_id, session_id, db,
            embedding_service_id=embedding_service_id,
        )

        if not repo or not repo.silo_id:
            logger.warning("Could not create temp repository/silo for file vectorization")
            return False

        from utils.config import get_app_config
        app_config = get_app_config()
        tmp_base = app_config['TMP_BASE_FOLDER']

        base_metadata = {
            "file_id": file_id,
            "filename": filename,
            "source": "playground_upload",
        }

        docs_indexed = False

        # Try file-based extraction with proper loaders/chunking
        if file_path:
            abs_path = os.path.join(tmp_base, file_path)
            if os.path.exists(abs_path):
                ext = os.path.splitext(filename)[1].lower()
                try:
                    docs = SiloService.extract_documents_from_file(
                        abs_path, ext, base_metadata
                    )
                    if docs:
                        SiloService.index_multiple_content(
                            repo.silo_id,
                            [{"content": d.page_content, "metadata": d.metadata} for d in docs],
                            db,
                        )
                        docs_indexed = True
                except Exception as exc:
                    logger.warning(
                        "File-based extraction failed for %s, falling back to content: %s",
                        filename, exc,
                    )

        # Fallback: use pre-extracted text content
        if not docs_indexed and content:
            SiloService.index_multiple_content(
                repo.silo_id,
                [{"content": content, "metadata": base_metadata}],
                db,
            )
            docs_indexed = True

        if docs_indexed:
            logger.info(
                "Vectorized file %s (%s) into silo %s at upload time",
                file_id, filename, repo.silo_id,
            )

        return docs_indexed
