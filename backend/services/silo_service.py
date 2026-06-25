from typing import Optional, List, Dict, Any
import os
import re
import uuid
from models.media import Media
from models.silo import Silo
from models.resource import Resource
from db.database import SessionLocal
from db.database import db as db_obj
from sqlalchemy import select
from sqlalchemy.orm import Session
from utils.logger import get_logger
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tools.vector_store_factory import VectorStoreFactory
from tools.vector_stores.vector_store_interface import VectorStoreInterface
from models.silo import SiloType
from services.output_parser_service import OutputParserService
from langchain_core.vectorstores.base import VectorStoreRetriever
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError,
    validate_required_fields
)
from utils.vector_db_immutability import assert_vector_db_type_immutable, assert_embedding_service_immutable
from schemas.silo_schemas import SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema
from repositories.silo_repository import SiloRepository
from services.folder_service import FolderService

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))
COLLECTION_PREFIX = 'silo_'
DEFAULT_SEARCH_LIMIT = 100
MAX_SEARCH_LIMIT = 200

# Per-chunk marker stamping each indexing run; lets reindex delete only stale chunks.
INDEX_BATCH_FIELD = 'index_batch'

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

logger = get_logger(__name__)

def _resolve_vector_db_type(silo: Optional[Silo] = None, override: Optional[str] = None) -> str:
    """Determine the vector DB type for a silo, falling back to PGVECTOR."""

    if override:
        return override.upper()

    if silo and getattr(silo, 'vector_db_type', None):
        return silo.vector_db_type.upper()

    return 'PGVECTOR'


def _get_vector_store(silo: Optional[Silo] = None, vector_db_type: Optional[str] = None) -> VectorStoreInterface:
    """Return the vector store implementation bound to the silo's backend."""

    resolved_type = _resolve_vector_db_type(silo, vector_db_type)
    return VectorStoreFactory.get_vector_store(db_obj, resolved_type)


# Patterns produced by PDF loaders when they encounter fonts with non-standard
# encodings (e.g. Type3 fonts where codepoint 64 maps to a drawn glyph):
#   PyPDFLoader  → outputs raw decimal codepoints:  "64/64/64/64/..."
#   PyMuPDFLoader → decodes codepoint 64 as ASCII @: "@@@@@@@@@..."
# Both represent the same underlying artifact and must be stripped.
_GARBAGE_PATTERNS = [
    re.compile(r'(\d+/){8,}'),  # raw decimal codepoint sequences
    re.compile(r'@{5,}'),       # decoded Type3 font artifacts
]

# Detects real words: 3+ consecutive Unicode letters (isalpha-equivalent via \w without digits/_)
# Used to distinguish OCR artifact lines from lines with actual text content.
_WORD_RE = re.compile(r'[^\W\d_]{3,}', re.UNICODE)

# Matches runs of single Unicode letters each separated by exactly one space:
# e.g. "V I T O R I A" or "p a s a d o". Used to detect and collapse
# spaced-out OCR output back into normal words.
_SPACED_WORD_RE = re.compile(r'[^\W\d_](?: [^\W\d_])+', re.UNICODE)


def _collapse_spaced_letters(line: str) -> str:
    """Collapse spaced-out single-letter OCR output into normal words.

    When > 60 % of the whitespace-delimited tokens on a line are single
    Unicode letters, the line is treated as spaced-out text (e.g. from
    low-resolution OCR) and consecutive single-letter runs are joined::

        "V I T O R I A .  E l  p a s a d o" → "VITORIA . El pasado"

    Lines that do not meet the threshold are returned unchanged.
    """
    tokens = line.split()
    if len(tokens) < 3:
        return line
    single_alpha = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
    if single_alpha / len(tokens) < 0.6:
        return line
    collapsed = _SPACED_WORD_RE.sub(lambda m: m.group(0).replace(' ', ''), line)
    # Normalize multiple spaces left after joining (e.g. between sections)
    collapsed = re.sub(r' {2,}', ' ', collapsed)
    return collapsed.strip()


def _clean_chunk_text(text: str) -> str:
    """Remove known PDF extraction artifacts from *text*.

    Two complementary strategies are applied:

    1. **Span-level:** Replace long runs of repeated glyph sequences in a single
       span (e.g. ``@@@@@`` or ``64/64/64/...``) with a space.
    2. **Line-level:** Drop entire lines that consist almost entirely of
       non-alphabetic characters and are very short (≤ 6 chars, < 2 alpha).
       This catches multi-line Type3 font artifacts such as ``@@h?``, ``@@g``,
       ``??``, ``?``, ``@@`` — which are Unicode codepoints decoded from glyphs
       that have no real text mapping (e.g. cp64→@, cp104→h, cp63→?).
    """
    # 1. Span-level: strip long repetitive sequences
    for pattern in _GARBAGE_PATTERNS:
        text = pattern.sub(' ', text)

    # 2. Per-line: collapse spaced-out single-letter OCR text BEFORE filtering
    #    so that "V I T O R I A" → "VITORIA" survives Rule B below.
    lines = text.split('\n')
    lines = [_collapse_spaced_letters(line) for line in lines]

    # 3. Line-level: drop lines that are clearly artifact/garbage
    #    Rule A — very short lines with minimal alpha (@@h?, @@g, ??, @@, …)
    #    Rule B — short-medium lines with no real word ≥ 3 letters; catches OCR
    #             image noise such as "r . * * * ! ? *", "^ i * * : * ;",
    #             "-'Jl", "i i ¥", etc.
    clean_lines = []
    for line in lines:
        s = line.strip()
        n = len(s)
        alpha = sum(c.isalpha() for c in s)
        if n <= 8 and alpha < 3:          # Rule A
            continue
        if n < 50 and not _WORD_RE.search(s):  # Rule B
            continue
        clean_lines.append(line)
    text = '\n'.join(clean_lines)

    # Collapse whitespace runs introduced by replacements
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _is_meaningful_chunk(text: str) -> bool:
    """Return True if *text* (already cleaned) contains real textual content.

    Rejects chunks that are too short or still dominated by non-alphabetic
    characters after ``_clean_chunk_text`` has been applied.
    """
    stripped = text.strip()
    if len(stripped) < 20:
        return False
    # Generic: fewer than 40 % of characters are letters or spaces → garbage
    alpha_space = sum(1 for c in stripped if c.isalpha() or c.isspace())
    if alpha_space / len(stripped) < 0.40:
        return False
    return True


def resolve_search_params(agent: Any, caller_search_params: Optional[dict]) -> tuple[dict, dict]:
    """Materialize RAG precedence: caller > agent > system.

    Returns ``(search_params, pinned_filter)`` where:
    - ``search_params``: tuning-only dict (no 'filter' key) — k, search_type,
      score_threshold, fetch_k, lambda_mult.
    - ``pinned_filter``: backend-ready ``{field: {op: value}}`` dict — the AND
      combination of caller flat filter and ``agent.rag_fixed_filters``. The
      agent's fixed filters WIN on (field, op) conflict: they are an
      admin-configured scoping floor a caller must not be able to loosen
      (security). Tuning params (k/search_type/...) keep caller > agent.

    Never raises: filter-building errors are caught and logged as WARNING.

    Args:
        agent: Agent ORM instance (or SimpleNamespace in tests).  Must expose
            ``rag_k``, ``rag_search_type``, ``rag_score_threshold``,
            ``rag_fixed_filters``, ``rag_max_retrieval_calls`` and
            optionally ``.silo`` (for metadata_definition + vector_db_type).
        caller_search_params: Optional search-param dict supplied by the call
            site (e.g. the public API chat endpoint).
    """
    caller: dict = caller_search_params or {}
    silo = getattr(agent, "silo", None)

    # ---- Tuning params (caller > agent > server_default) ----
    resolved: dict = {}

    # k: caller explicit value wins; otherwise use agent column (server_default 30)
    resolved["k"] = caller["k"] if "k" in caller else (getattr(agent, "rag_k", None) or 30)

    # search_type: caller wins; fall back to agent column (server_default 'similarity')
    resolved["search_type"] = (
        caller.get("search_type") or getattr(agent, "rag_search_type", None) or "similarity"
    )

    # score_threshold: caller wins (explicit None clears). Only concrete values are stored,
    # so absent key == no threshold; never forward None to as_retriever.
    if "score_threshold" in caller:
        if caller["score_threshold"] is not None:
            resolved["score_threshold"] = caller["score_threshold"]
    else:
        agent_threshold = getattr(agent, "rag_score_threshold", None)
        if agent_threshold is not None:
            resolved["score_threshold"] = agent_threshold

    # fetch_k / lambda_mult: caller pass-through only
    if "fetch_k" in caller:
        resolved["fetch_k"] = caller["fetch_k"]
    if "lambda_mult" in caller:
        resolved["lambda_mult"] = caller["lambda_mult"]

    # Threshold search without a threshold silently degrades to plain similarity — normalize
    # and warn instead of a silent no-op (legacy agents, or a caller that cleared the value).
    if resolved["search_type"] == "similarity_score_threshold" and "score_threshold" not in resolved:
        logger.warning(
            "resolve_search_params: 'similarity_score_threshold' requested without a "
            "score_threshold; falling back to plain similarity search"
        )
        resolved["search_type"] = "similarity"

    # ---- Pinned filters ----
    if silo is None:
        return resolved, {}

    metadata_definition = getattr(silo, "metadata_definition", None)

    def _build_backend_filter(clauses_input: list) -> dict:
        """Build backend filter from a list of MetadataFilterClause-like dicts/instances."""
        from tools.vector_stores.metadata_filters import (  # local import avoids cycles
            MetadataFilterClause,
            convert_clause_types,
            to_backend_filter,
        )
        clauses = []
        for item in clauses_input:
            try:
                if isinstance(item, MetadataFilterClause):
                    clauses.append(item)
                else:
                    clauses.append(MetadataFilterClause(**item))
            except Exception as exc:
                logger.warning(
                    "resolve_search_params: could not build filter clause from %r: %s",
                    {k: v for k, v in item.items() if k != "value"} if isinstance(item, dict) else "?",
                    exc,
                )
        if not clauses:
            return {}
        typed = convert_clause_types(clauses, metadata_definition)
        return to_backend_filter(typed)

    # Caller flat filter: {field: value} → convert to $eq clauses
    caller_backend: dict = {}
    raw_caller_filter = caller.get("filter") or {}
    if raw_caller_filter:
        try:
            caller_clauses = [{"field": f, "op": "$eq", "value": v} for f, v in raw_caller_filter.items()]
            caller_backend = _build_backend_filter(caller_clauses)
        except Exception as exc:
            logger.warning("resolve_search_params: failed to build caller filter: %s", exc)

    # Agent rag_fixed_filters: list of {field, op, value}
    agent_backend: dict = {}
    raw_agent_filters: Optional[list] = getattr(agent, "rag_fixed_filters", None)
    if raw_agent_filters:
        try:
            agent_backend = _build_backend_filter(raw_agent_filters)
        except Exception as exc:
            logger.warning("resolve_search_params: failed to build agent fixed filters: %s", exc)

    # AND merge. Agent fixed filters passed FIRST so they win on (field, op)
    # conflict — an admin scoping floor the caller cannot loosen (security).
    # merge_filters_and is first-wins per (field, op). Caller filters on other
    # fields still apply (AND).
    if caller_backend or agent_backend:
        from tools.vector_stores.metadata_filters import merge_filters_and  # local import
        pinned_filter = merge_filters_and(agent_backend, caller_backend)
    else:
        pinned_filter = {}

    return resolved, pinned_filter


class SiloService:

    '''SILO CRUD Operations'''
    @staticmethod
    def get_silo(silo_id: int, db: Session) -> Optional[Silo]:
        """
        Retrieve a silo by its ID
        """
        return SiloRepository.get_by_id(silo_id, db)
    
    @staticmethod
    def get_silo_retriever(silo_id: int, search_params=None, **kwargs) -> Optional[VectorStoreRetriever]:
        """
        Get retriever for a silo with its corresponding embedding service
        
        Args:
            silo_id: ID of the silo
            search_params: Optional search parameters for filtering
            
        Returns:
            VectorStoreRetriever if silo exists and has embedding service, None otherwise
            
        Raises:
            NotFoundError: If silo doesn't exist
            ValidationError: If silo has no embedding service
        """
        if not isinstance(silo_id, int) or silo_id <= 0:
            raise ValidationError(f"Invalid silo_id: {silo_id}")
        
        # For retriever operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            silo = SiloService.get_silo(silo_id, session)
            if not silo:
                raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")

            if not silo.embedding_service:
                raise ValidationError(f"Silo {silo_id} has no embedding service configured")

            logger.debug(f"Getting retriever for silo {silo_id} with embedding service: {silo.embedding_service.name}")
            
            collection_name = COLLECTION_PREFIX + str(silo_id)
            
            # Merge search_params with default k value
            # search_params typically contains 'filter' for metadata filtering
            merged_search_kwargs = {'k': 30}
            
            if search_params:
                # Known retriever parameters that should not be wrapped in 'filter'
                known_params = {'k', 'filter', 'score_threshold', 'fetch_k', 'lambda_mult', 'search_type'}
                
                # Separate known params from filter fields
                filter_fields = {}
                direct_params = {}
                
                for key, value in search_params.items():
                    if key in known_params:
                        direct_params[key] = value
                    else:
                        # Any unknown key is treated as a filter field
                        filter_fields[key] = value
                
                # Update merged_search_kwargs with direct params
                merged_search_kwargs.update(direct_params)
                
                # If there are filter fields, wrap them in 'filter' key
                if filter_fields:
                    if 'filter' in merged_search_kwargs:
                        # Merge with existing filter
                        merged_search_kwargs['filter'].update(filter_fields)
                    else:
                        # Create new filter with these fields
                        merged_search_kwargs['filter'] = filter_fields
                
                logger.debug(f"Merged search_kwargs: {merged_search_kwargs}")
            
            # Extract search_type before passing search_kwargs — it must be a top-level
            # kwarg to `as_retriever`, not nested inside search_kwargs.
            retriever_search_type = merged_search_kwargs.pop("search_type", "similarity")

            # Use async engine with psycopg (not asyncpg) for async operations
            # psycopg supports async natively and handles multiple SQL statements properly
            return _get_vector_store(silo).get_retriever(
                collection_name,
                silo.embedding_service,
                merged_search_kwargs,
                search_type=retriever_search_type,
                use_async=True  # Use async psycopg engine for LangGraph compatibility
            )
        except Exception as e:
            logger.error(f"Failed to create retriever for silo {silo_id}: {str(e)}", exc_info=True)
            raise
        finally:
            session.close()
    
    @staticmethod
    def get_silos_by_app_id(app_id: int, db: Session) -> List[Silo]:
        """
        Retrieve all silos by app_id
        """
        return SiloRepository.get_by_app_id(app_id, db)
    
    @staticmethod
    @handle_database_errors("create_or_update_silo")
    def create_or_update_silo(silo_data: dict, silo_type: Optional[SiloType] = None, db: Session = None) -> Silo:
        """
        Create a new silo or update an existing one
        
        Args:
            silo_data: Dictionary containing silo data
            silo_type: Optional silo type to set
            db: Database session to use
            
        Returns:
            Created or updated Silo instance
            
        Raises:
            ValidationError: If required fields are missing or invalid
            DatabaseError: If database operation fails
        """
        logger.info(f"Received silo data: {silo_data}")
        
        # Convert ImmutableMultiDict to regular dict if needed
        if hasattr(silo_data, 'to_dict'):
            silo_data = silo_data.to_dict()
        else:
            silo_data = dict(silo_data)
        
        requested_vector_db_type = silo_data.get('vector_db_type')
        if requested_vector_db_type is not None:
            if not isinstance(requested_vector_db_type, str):
                raise ValidationError("vector_db_type must be a string")
            requested_vector_db_type = requested_vector_db_type.strip().upper()
            if not requested_vector_db_type:
                requested_vector_db_type = None
            elif requested_vector_db_type not in VectorStoreFactory.IMPLEMENTED_TYPES:
                supported = ', '.join(VectorStoreFactory.IMPLEMENTED_TYPES)
                raise ValidationError(
                    f"Unsupported vector_db_type '{requested_vector_db_type}'. Supported types: {supported}"
                )

        # Validate required fields
        required_fields = ['name', 'app_id']
        validate_required_fields(silo_data, required_fields)
        
        # Validate field types
        field_types = {'app_id': int}
        if 'silo_id' in silo_data and silo_data['silo_id']:
            field_types['silo_id'] = int
        if 'embedding_service_id' in silo_data and silo_data['embedding_service_id']:
            field_types['embedding_service_id'] = int
        
        # Convert string values to int where needed
        for field in ['silo_id', 'app_id', 'embedding_service_id']:
            if field in silo_data and silo_data[field] and isinstance(silo_data[field], str):
                try:
                    silo_data[field] = int(silo_data[field])
                except ValueError:
                    raise ValidationError(f"Invalid integer value for {field}: {silo_data[field]}")
        
        silo_id = silo_data.get('silo_id')
        
        # Use provided session or create a new one
        session = db if db is not None else SessionLocal()
        should_close = db is None
        
        try:
            # Get existing silo or create new one
            if silo_id:
                silo = SiloService.get_silo(silo_id, session)
                if not silo:
                    raise NotFoundError(f"Silo with ID {silo_id} not found", "silo")
                logger.info(f"Updating existing silo {silo_id}")
                assert_vector_db_type_immutable(
                    silo.vector_db_type, requested_vector_db_type, "silo"
                )
                assert_embedding_service_immutable(
                    silo.embedding_service_id, silo_data.get('embedding_service_id'), "silo"
                )
            else:
                # Enforce per-app silo limit before creation (SaaS mode only)
                app_id = silo_data.get('app_id')
                if app_id:
                    from services.tier_enforcement_service import TierEnforcementService
                    TierEnforcementService.check_resource_limit(session, int(app_id), 'silos')

                silo = Silo()
                # Set default type to CUSTOM, but allow override from form data
                silo.silo_type = SiloType.CUSTOM.value
                logger.info("Creating new silo")

            silo.vector_db_type = _resolve_vector_db_type(silo, requested_vector_db_type)
            
            # Set silo type from form data if provided
            if silo_data.get('type') and silo_data['type'].strip():
                silo.silo_type = silo_data['type'].strip()
            # Set silo type if provided via parameter (for backward compatibility)
            elif silo_type:
                silo.silo_type = silo_type.value
                if silo_type == SiloType.REPO:
                    silo.metadata_definition_id = 0

            # Set embedding service on creation only — immutable after creation
            if not silo_id and silo_data.get('embedding_service_id'):
                silo.embedding_service_id = silo_data['embedding_service_id']
            
            # Handle metadata definition (output parser) - explicitly handle None to clear it
            if 'output_parser_id' in silo_data:
                # If output_parser_id is explicitly provided (even if None), use it
                logger.info(f"Setting metadata_definition_id to: {silo_data['output_parser_id']}")
                silo.metadata_definition_id = silo_data['output_parser_id']
            elif 'metadata_definition_id' in silo_data:
                # Fallback to metadata_definition_id for backward compatibility
                logger.info(f"Setting metadata_definition_id from fallback to: {silo_data['metadata_definition_id']}")
                silo.metadata_definition_id = silo_data['metadata_definition_id']
            
            # Update silo attributes
            SiloService._update_silo(silo, silo_data)
            
            # Save to database
            session.add(silo)
            session.commit()
            
            logger.info(f"Successfully {'updated' if silo_id else 'created'} silo {silo.silo_id}")
            return silo
        finally:
            if should_close:
                session.close()
    
    @staticmethod
    def _update_silo(silo: Silo, data: dict):
        """
        Update silo attributes from input data
        
        Args:
            silo: Silo instance to update
            data: Dictionary containing update data
            
        Raises:
            ValidationError: If data validation fails
        """
        # Validate silo name
        name = data['name'].strip() if data['name'] else None
        if not name:
            raise ValidationError("Silo name cannot be empty")
        
        silo.name = name
        silo.description = data.get('description', '').strip() or None
        silo.status = data.get('status')
        silo.app_id = data['app_id']
        silo.fixed_metadata = bool(data.get('fixed_metadata', False))
        # Don't override metadata_definition_id here as it's handled above
        # silo.metadata_definition_id = data.get('metadata_definition_id') or None
            
    @staticmethod
    def delete_silo(silo_id: int, db: Session):
        """
        Delete a silo by its ID
        """
        silo = SiloRepository.get_by_id(silo_id, db)
        if silo:
            # Store metadata_definition_id before deleting (avoid DetachedInstanceError)
            metadata_definition_id = silo.metadata_definition_id
            
            SiloService.delete_collection(silo.silo_id, db)
            
            silo.embedding_service_id = None
            db.add(silo)
            db.commit()
            
            # Now delete the silo using repository
            SiloRepository.delete(silo_id, db)

            # Finally delete the output parser if it exists
            if metadata_definition_id:
                output_parser_service = OutputParserService()
                output_parser_service.delete_parser(db, metadata_definition_id)



    '''SILO and DATA Operations'''

    @staticmethod
    def check_silo_collection_exists(silo_id: int, db: Session) -> bool:
        collection_name = COLLECTION_PREFIX + str(silo_id)
        try:
            silo = SiloRepository.get_by_id(silo_id, db)
            if not silo:
                logger.warning("Silo %s not found while checking collection existence", silo_id)
                return False
            return _get_vector_store(silo).collection_exists(collection_name)
        except Exception as exc:
            logger.error(f"Error checking collection for silo {silo_id}: {exc}")
            return False
    
    @staticmethod
    def count_docs_in_silo(silo_id: int, db: Session) -> int:
        collection_name = COLLECTION_PREFIX + str(silo_id)
        try:
            silo = SiloRepository.get_by_id(silo_id, db)
            if not silo:
                logger.warning("Silo %s not found while counting documents", silo_id)
                return 0
            return _get_vector_store(silo).count_documents(collection_name)
        except Exception as exc:
            logger.error(f"Error counting docs in silo {silo_id}: {exc}")
            return 0

    @staticmethod
    def count_docs_with_filter(
        silo_id: int,
        filter_metadata: Optional[dict] = None,
        db: Session = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
    ) -> int:
        """
        Count documents in a silo collection, optionally filtered by metadata
        and/or content length. Returns 0 gracefully if the silo or collection
        does not exist.
        """
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo or not SiloService.check_silo_collection_exists(silo_id, db):
            return 0

        collection_name = COLLECTION_PREFIX + str(silo_id)
        try:
            return _get_vector_store(silo).count_documents(
                collection_name,
                filter_metadata=filter_metadata,
                min_content_length=min_content_length,
                max_content_length=max_content_length,
            )
        except Exception as exc:
            logger.error("count_docs_with_filter error for silo %s: %s", silo_id, exc)
            return 0

    @staticmethod
    def _get_silo_for_indexing(silo_id: int, db: Session):
        """Helper method to get silo and validate it exists"""
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            raise ValueError(f"Silo with id {silo_id} does not exist")
        return silo

    @staticmethod
    def _create_documents_for_indexing(silo_id: int, contents: List[dict]) -> List[Document]:
        """Split each content item into chunks and attach metadata.

        File-upload callers pre-split via ``extract_documents_from_file`` before
        calling ``index_multiple_content``, so chunks already ≤ CHUNK_SIZE produce
        exactly one chunk per input item (idempotent).
        """
        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        documents: List[Document] = []
        for item in contents:
            # silo_id last — a caller-supplied key must not override the parameter.
            base_metadata = {**(item.get('metadata', {})), "silo_id": silo_id}
            chunks = splitter.split_text(item['content'])
            for chunk in chunks:
                documents.append(Document(page_content=chunk, metadata=dict(base_metadata)))
        return documents

    @staticmethod
    def index_single_content(silo_id: int, content: str, metadata: dict, db: Session):
        """Index single content in a silo"""
        SiloService.index_multiple_content(silo_id, [{'content': content, 'metadata': metadata}], db)

    @staticmethod
    def index_multiple_content(silo_id: int, documents: List[dict], db: Session):
        """Index multiple documents in a silo with the corresponding embedding service"""
        logger.info(f"Indexando documentos en silo {silo_id}")
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        # Get silo within this session to avoid detached instance
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo con id {silo_id} no existe")
            raise ValueError(f"Silo with id {silo_id} does not exist")
        
        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        logger.debug(f"Usando embedding service: {embedding_service.name if embedding_service else 'None'}")
        
        docs = SiloService._create_documents_for_indexing(silo_id, documents)
        _get_vector_store(silo).index_documents(
            collection_name,
            docs,
            embedding_service=embedding_service
        )
        logger.info(f"Documentos indexados correctamente en silo {silo_id}")
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService  # noqa: PLC0415
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after index_multiple_content for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def extract_documents_from_file(file_path: str, file_extension: str, base_metadata: dict = None):
        """
        Extracts and splits documents from a file, attaching base metadata to each chunk.
        Args:
            file_path: Path to the file to extract from
            file_extension: File extension (e.g., '.pdf', '.docx', '.txt')
            base_metadata: Metadata dict to attach to each document
        Returns:
            List[Document]: List of Document objects
        """
        from langchain_core.documents import Document
        from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader

        if base_metadata is None:
            base_metadata = {}

        # Determine file type and use appropriate loader
        if file_extension == '.pdf':
            loader = PyMuPDFLoader(file_path)
        elif file_extension == '.docx':
            loader = Docx2txtLoader(file_path)
        elif file_extension in ('.txt', '.md'):
            loader = TextLoader(file_path, encoding='utf-8')
        else:
            logger.error(f"Unsupported file type: {file_extension}")
            raise ValueError(f"Unsupported file type: {file_extension}")

        pages = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        docs = text_splitter.split_documents(pages)

        # Clean known PDF extraction artifacts (e.g. @@@@, 64/64/64/...) from
        # each chunk's content, then discard chunks that are empty or still
        # dominated by non-textual characters after cleaning.
        for doc in docs:
            doc.page_content = _clean_chunk_text(doc.page_content)

        original_count = len(docs)
        docs = [doc for doc in docs if _is_meaningful_chunk(doc.page_content)]
        filtered = original_count - len(docs)
        if filtered:
            logger.debug(f"Filtered {filtered} garbage chunk(s) from {file_path}")

        for doc in docs:
            doc.metadata.update(base_metadata)
            # Only add page number if it exists (PDFs have page metadata, DOCX/TXT don't)
            if "page" in doc.metadata:
                doc.metadata["page"] = doc.metadata["page"] + 1
        return docs

    @staticmethod
    def update_resource_metadata(resource: Resource, db_session: Session = None):
        """
        Update only the metadata of a resource in the vector database without re-indexing content.
        This is more efficient for operations like moving files between folders.

        Args:
            resource: Resource instance with updated folder information
            db_session: Optional database session to use (if None, creates new session)
        """
        session = db_session if db_session else SessionLocal()
        try:
            resource_with_relations = session.query(Resource).filter(
                Resource.resource_id == resource.resource_id
            ).first()

            if not resource_with_relations:
                logger.error(f"Resource {resource.resource_id} not found for metadata update")
                return

            silo = resource_with_relations.repository.silo
            collection_name = COLLECTION_PREFIX + str(silo.silo_id)

            file_extension = os.path.splitext(resource_with_relations.uri)[1].lower()
            base_metadata = {
                "repository_id": resource_with_relations.repository_id,
                "resource_id": resource_with_relations.resource_id,
                "silo_id": silo.silo_id,
                "name": resource_with_relations.uri,
                "file_type": file_extension,
            }

            if resource_with_relations.folder_id:
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                base_metadata["folder_id"] = resource_with_relations.folder_id
                base_metadata["folder_path"] = folder_path
                base_metadata["ref"] = os.path.join(
                    str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri
                )
            else:
                base_metadata["folder_id"] = None
                base_metadata["folder_path"] = ""
                base_metadata["ref"] = os.path.join(
                    str(resource_with_relations.repository_id), resource_with_relations.uri
                )

            updated = _get_vector_store(silo).update_documents_metadata(
                collection_name,
                filter_metadata={"resource_id": {"$eq": str(resource.resource_id)}},
                metadata_updates=base_metadata,
                replace=True,
            )

            logger.info(
                "Updated metadata for resource %s in collection %s (%s rows)",
                resource.resource_id, collection_name, updated,
            )

        except Exception as e:
            logger.error(f"Error updating resource metadata: {str(e)}")
            raise
        finally:
            if not db_session:
                session.close()

    @staticmethod
    def update_media_metadata(media: Media, db_session: Session = None):
        """
        Update only the metadata of media chunks in the vector database without re-indexing content.
        Updates folder information for all chunks belonging to this media.

        Args:
            media: Media instance with updated folder information
            db_session: Optional database session
        """
        session = db_session if db_session else SessionLocal()
        try:
            media_with_relations = session.query(Media).filter(
                Media.media_id == media.media_id
            ).first()

            if not media_with_relations:
                logger.error(f"Media {media.media_id} not found for metadata update")
                return

            silo = media_with_relations.repository.silo
            collection_name = COLLECTION_PREFIX + str(silo.silo_id)

            metadata_updates = {
                "source_type": media_with_relations.source_type,
                "source_url": media_with_relations.source_url,
                "language": media_with_relations.language,
                "name": media_with_relations.name,
            }

            if media_with_relations.folder_id:
                folder_path = FolderService.get_folder_path(media_with_relations.folder_id, session)
                metadata_updates["folder_id"] = media_with_relations.folder_id
                metadata_updates["folder_path"] = folder_path
            else:
                metadata_updates["folder_id"] = None
                metadata_updates["folder_path"] = ""

            updated = _get_vector_store(silo).update_documents_metadata(
                collection_name,
                filter_metadata={
                    "media_id": {"$eq": str(media.media_id)},
                    "content_type": {"$eq": "media_chunk"},
                },
                metadata_updates=metadata_updates,
                replace=False,
            )

            logger.info(
                "Updated metadata for media %s in collection %s (%s chunks)",
                media.media_id, collection_name, updated,
            )

        except Exception as e:
            logger.error(f"Error updating media metadata: {str(e)}")
            raise
        finally:
            if not db_session:
                session.close()

    @staticmethod
    def index_resource(resource: Resource, index_batch: Optional[str] = None) -> str:
        """Index a resource's file into its silo collection.

        Every chunk is stamped with ``index_batch`` (generated if not supplied) so a
        later reindex can delete only the stale chunks. Returns the batch used.
        """
        index_batch = index_batch or uuid.uuid4().hex
        # For resource operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            # Load resource with relationships within the session to avoid detached instance issues
            resource_with_relations = session.query(Resource).filter(Resource.resource_id == resource.resource_id).first()
            if not resource_with_relations:
                logger.error(f"Resource {resource.resource_id} not found for indexing")
                return index_batch

            collection_name = COLLECTION_PREFIX + str(resource_with_relations.repository.silo_id)
            
            # Build the correct file path including folder structure
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
            else:
                path = os.path.join(REPO_BASE_FOLDER, str(resource_with_relations.repository_id), resource_with_relations.uri)
            
            file_extension = os.path.splitext(resource_with_relations.uri)[1].lower()

            # Prepare base metadata
            base_metadata = {
                "repository_id": resource_with_relations.repository_id,
                "resource_id": resource_with_relations.resource_id,
                "silo_id": resource_with_relations.repository.silo_id,
                "name": resource_with_relations.uri,
                "file_type": file_extension,
                INDEX_BATCH_FIELD: index_batch,
            }
            
            # Add folder information if resource is in a folder
            if resource_with_relations.folder_id:
                from services.folder_service import FolderService
                folder_path = FolderService.get_folder_path(resource_with_relations.folder_id, session)
                base_metadata["folder_id"] = resource_with_relations.folder_id
                base_metadata["folder_path"] = folder_path
                # Store relative path including folder structure
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), folder_path, resource_with_relations.uri)
            else:
                # Resource is at root level
                base_metadata["folder_id"] = None
                base_metadata["folder_path"] = ""
                base_metadata["ref"] = os.path.join(str(resource_with_relations.repository_id), resource_with_relations.uri)

            docs = SiloService.extract_documents_from_file(path, file_extension, base_metadata)

            if not docs:
                logger.warning(f"No content extracted from resource {resource_with_relations.resource_id} ({resource_with_relations.uri}). The file may be empty or contain only images/scans without text.")
                return index_batch

            embedding_service = resource_with_relations.repository.silo.embedding_service

            if not embedding_service:
                logger.warning(f"Silo {resource_with_relations.repository.silo_id} has no embedding service, skipping indexing for resource {resource_with_relations.resource_id}")
                return index_batch

            _get_vector_store(resource_with_relations.repository.silo).index_documents(
                collection_name,
                docs,
                embedding_service
            )
            logger.info(f"Successfully indexed resource {resource_with_relations.resource_id} in silo {resource_with_relations.repository.silo_id}")
            try:
                from services.metadata_values_cache_service import MetadataValuesCacheService
                MetadataValuesCacheService.invalidate(resource_with_relations.repository.silo_id)
            except Exception as _cache_exc:
                logger.warning("metadata_values_cache: invalidation failed after index_resource for silo=%d: %s", resource_with_relations.repository.silo_id, _cache_exc)
        except Exception as e:
            logger.error(f"Error indexing resource {resource.resource_id}: {str(e)}")
            raise
        finally:
            session.close()

        return index_batch

    @staticmethod
    def _delete_resource_chunks(resource_id: int, collection_name: str, silo) -> None:
        """Delete all vector chunks for a resource. Propagates vector-store exceptions.

        Single authoritative point for the ``resource_id`` filter; both
        ``delete_resource`` (tolerant) and ``reindex_resource`` (fail-fast) delegate here.
        """
        embedding_service = silo.embedding_service
        _get_vector_store(silo).delete_documents(
            collection_name,
            ids={"resource_id": {"$eq": resource_id}},
            embedding_service=embedding_service,
        )

    @staticmethod
    def reindex_resource(resource: Resource) -> None:
        """Re-index a resource using index-then-swap (no empty-collection window).

        The fresh batch is written first; only after it succeeds are the resource's
        other chunks deleted. If indexing fails, the previous chunks are untouched
        (worst case: transient duplicates that the next successful reindex resolves —
        never zero chunks).

        Raises:
            ValueError: If the silo has no embedding service configured.
            Exception: If the vector-store delete/index fails.
        """
        session = SessionLocal()
        try:
            resource_with_relations = session.scalars(
                select(Resource).where(Resource.resource_id == resource.resource_id)
            ).first()

            if not resource_with_relations:
                logger.warning(
                    "reindex_resource: resource %s not found in database; aborting",
                    resource.resource_id,
                )
                return

            silo = resource_with_relations.repository.silo
            silo_id = resource_with_relations.repository.silo_id

            if not silo or not silo.embedding_service:
                raise ValueError(f"Silo {silo_id} has no embedding service configured")

            # Capture everything needed for the swap before the session closes.
            collection_name = COLLECTION_PREFIX + str(silo_id)
            embedding_service = silo.embedding_service
            vector_store = _get_vector_store(silo)
        finally:
            session.close()

        # 1) Write the fresh batch first — previous chunks remain searchable meanwhile.
        new_batch = SiloService.index_resource(resource)

        # 2) Swap: drop this resource's chunks that are not the fresh batch.
        logger.info(
            "reindex_resource: swapping stale chunks for resource %s in collection %s (batch %s)",
            resource.resource_id, collection_name, new_batch,
        )
        vector_store.delete_documents_excluding(
            collection_name,
            filter_metadata={"resource_id": {"$eq": resource.resource_id}},
            exclude={INDEX_BATCH_FIELD: new_batch},
            embedding_service=embedding_service,
        )

    @staticmethod
    def index_media_chunk(chunk: dict, media: Media, db: Session = None):
        """
        Index a single media chunk in the vector database using chunk data dict and the Media instance.

        `chunk` should be a dict with keys: `text`, `start_time`, `end_time`, `chunk_index` and optionally `chunk_id`.
        The chunk information will be stored inside the embedding metadata (no DB row required).
        """
        if not media:
            logger.error("Media not provided for chunk indexing")
            return

        collection_name = COLLECTION_PREFIX + str(media.repository.silo_id)

        # Build metadata from chunk dict and media
        chunk_type = chunk.get('chunk_type', 'audio')  # 'audio' or 'visual'
        metadata = {
            "repository_id": media.repository_id,
            "media_id": media.media_id,
            "silo_id": media.repository.silo_id,
            "content_type": "media_chunk",
            "chunk_type": chunk_type,
            
            # Chunk-specific data
            "chunk_index": chunk.get('chunk_index'),
            "start_time": chunk.get('start_time'),
            "end_time": chunk.get('end_time'),
            "duration": chunk.get('end_time', 0) - chunk.get('start_time', 0),
            
            # Media file information
            "name": media.name,
            "source_type": media.source_type,
            "source_url": media.source_url,
            "language": media.language,
            "file_type": os.path.splitext(media.file_path)[1].lower() if media.file_path else None,
            "source": media.file_path,
            "processing_mode": media.processing_mode or "basic",
            
            # Folder information
            "folder_id": media.folder_id,
            "folder_path": FolderService.get_folder_path(media.folder_id, db) if media.folder_id else "",
            
            # Reference path (similar to resource 'ref')
            "ref": os.path.join(
                str(media.repository_id),
                FolderService.get_folder_path(media.folder_id, db) if media.folder_id else "",
                f"{media.media_id}{os.path.splitext(media.file_path)[1]}" if media.file_path else ""
            ).replace("\\", "/"),
            
            # Media metadata
            "media_duration": media.duration
        }

        # Add folder information if media is in a folder
        if media.folder_id:
            folder_path = FolderService.get_folder_path(media.folder_id, db)
            metadata["folder_id"] = media.folder_id
            metadata["folder_path"] = folder_path
        else:
            metadata["folder_id"] = None
            metadata["folder_path"] = ""

        # Create Document and index
        page_content = chunk.get('text', '')
        
        doc = Document(
            page_content=page_content,
            metadata=metadata
        )

        embedding_service = media.repository.silo.embedding_service
        if not embedding_service:
            logger.warning(f"Silo {media.repository.silo_id} has no embedding service, skipping indexing for media {media.media_id}")
            return

        try:
            _get_vector_store(media.repository.silo).index_documents(
                collection_name,
                [doc],
                embedding_service
            )
            logger.info(f"Indexed media chunk (media {media.media_id}) in silo {media.repository.silo_id}")
            try:
                from services.metadata_values_cache_service import MetadataValuesCacheService
                MetadataValuesCacheService.invalidate(media.repository.silo_id)
            except Exception as _cache_exc:
                logger.warning("metadata_values_cache: invalidation failed after index_media_chunk for silo=%d: %s", media.repository.silo_id, _cache_exc)
        except Exception as e:
            logger.error(f"Error indexing media chunk for media {media.media_id}: {str(e)}")
            raise

    @staticmethod
    def delete_media(media: Media):
        """Delete all chunks for a media"""
        logger.info(f"Eliminando recurso {media.media_id} del silo {media.repository.silo_id}")
        collection_name = COLLECTION_PREFIX + str(media.repository.silo_id)
        
        # For resource operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            # Load silo within the session to avoid detached instance issues
            silo = SiloRepository.get_by_id(media.repository.silo_id, session)
            if not silo:
                logger.error(f"Silo no encontrado para la media {media.media_id}")
                return

            # Check if silo has embedding service
            if not silo.embedding_service:
                logger.warning(f"Silo {silo.silo_id} has no embedding service, skipping vector deletion for media {media.media_id}")
                return

            _get_vector_store(silo).delete_documents(
                collection_name,
                ids={"media_id": {"$eq": media.media_id}},
                embedding_service=silo.embedding_service
            )
        except Exception as e:
            logger.error(f"Error deleting media {media.media_id} from vector store: {str(e)}")
            # Don't raise the exception - allow the media to be deleted from database and disk
        finally:
            session.close()

    @staticmethod
    def delete_resource(resource: Resource):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando recurso {resource.resource_id} del silo {resource.repository.silo_id}")
        collection_name = COLLECTION_PREFIX + str(resource.repository.silo_id)
        
        # For resource operations, we need a fresh session since this might be called from other contexts
        session = SessionLocal()
        try:
            # Load silo within the session to avoid detached instance issues
            silo = SiloRepository.get_by_id(resource.repository.silo_id, session)
            if not silo:
                logger.error(f"Silo no encontrado para el recurso {resource.resource_id}")
                return

            # Check if silo has embedding service
            if not silo.embedding_service:
                logger.warning(f"Silo {silo.silo_id} has no embedding service, skipping vector deletion for resource {resource.resource_id}")
                return

            SiloService._delete_resource_chunks(resource.resource_id, collection_name, silo)
            # Only reached when _delete_resource_chunks succeeded — safe to invalidate.
            try:
                from services.metadata_values_cache_service import MetadataValuesCacheService
                MetadataValuesCacheService.invalidate(silo.silo_id)
            except Exception as _cache_exc:
                logger.warning("metadata_values_cache: invalidation failed after delete_resource for silo=%d: %s", silo.silo_id, _cache_exc)
        except Exception as e:
            logger.error(f"Error deleting resource {resource.resource_id} from vector store: {str(e)}")
            # Don't raise the exception - allow the resource to be deleted from database and disk
        finally:
            session.close()

    @staticmethod
    def delete_url(silo_id: int, url: str, db: Session):
        """
        Delete a resource using its silo's embedding service
        """
        logger.info(f"Eliminando URL {url} del silo {silo_id}")
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        # Get silo within this session to avoid detached instance
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo no encontrado para la url {url}")
            return

        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        _get_vector_store(silo).delete_documents(
            collection_name,
            ids={"url": {"$eq": url}},
            embedding_service=embedding_service
        )
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_url for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def delete_content(silo_id: int, content_id: str, db: Session):
        """
        Delete content from a silo using its embedding service
        """
        logger.info(f"Eliminando contenido {content_id} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        _get_vector_store(silo).delete_documents(
            collection_name,
            filter_metadata={"id": {"$eq": content_id}},
            embedding_service=silo.embedding_service
        )
        logger.info(f"Contenido {content_id} eliminado correctamente del silo {silo_id}")
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_content for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def delete_collection(silo_id: int, db: Session):
        """Delete a collection using its silo's embedding service"""
        if not SiloService.check_silo_collection_exists(silo_id, db):
            return

        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        _get_vector_store(silo).delete_collection(collection_name, silo.embedding_service)
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_collection for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def delete_docs_in_collection(silo_id: int, ids: List[str], db: Session):
        """
        Delete documents from a silo using its embedding service
        """
        logger.info(f"Eliminando documentos {ids} del silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"La colección para el silo {silo_id} no existe")
            return

        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} no encontrado")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        _get_vector_store(silo).delete_documents(
            collection_name,
            ids=ids,
            embedding_service=silo.embedding_service
        )
        logger.info(f"Documentos eliminados correctamente del silo {silo_id}")
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_docs_in_collection for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def delete_all_docs_in_collection(silo_id: int, db: Session):
        """
        Delete all documents from a silo collection.
        """
        logger.info(f"Deleting all documents from silo {silo_id}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"Collection for silo {silo_id} does not exist, nothing to delete")
            return

        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} not found")
            return

        collection_name = COLLECTION_PREFIX + str(silo_id)
        _get_vector_store(silo).delete_collection(collection_name, silo.embedding_service)
        logger.info(f"All documents deleted from silo {silo_id}")
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_all_docs_in_collection for silo=%d: %s", silo_id, _cache_exc)

    @staticmethod
    def delete_docs_by_metadata(silo_id: int, filter_metadata: Dict[str, Any], db: Session) -> int:
        """
        Delete documents from a silo using metadata filters.
        
        Args:
            silo_id: ID of the silo
            filter_metadata: Metadata filter dict (MongoDB-style, e.g., {"field": {"$eq": "value"}})
            db: Database session
            
        Returns:
            Number of documents deleted
        """
        logger.info(f"Deleting documents from silo {silo_id} with filter: {filter_metadata}")
        
        if not SiloService.check_silo_collection_exists(silo_id, db):
            logger.warning(f"Collection for silo {silo_id} does not exist")
            return 0

        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} not found")
            return 0

        if not silo.embedding_service:
            logger.warning(f"Silo {silo_id} has no embedding service configured")
            return 0

        collection_name = COLLECTION_PREFIX + str(silo_id)
        store = _get_vector_store(silo)

        # Count matches first via the vector store abstraction (faster than search).
        doc_count = store.count_documents(collection_name, filter_metadata=filter_metadata)

        if doc_count == 0:
            logger.info(f"No documents found matching the filter in silo {silo_id}")
            return 0

        # Delete the matched documents using metadata filter
        store.delete_documents(
            collection_name,
            ids=filter_metadata,  # Pass metadata filter as dict
            embedding_service=silo.embedding_service
        )
        logger.info(f"Successfully deleted {doc_count} document(s) from silo {silo_id}")
        try:
            from services.metadata_values_cache_service import MetadataValuesCacheService
            MetadataValuesCacheService.invalidate(silo_id)
        except Exception as _cache_exc:
            logger.warning("metadata_values_cache: invalidation failed after delete_docs_by_metadata for silo=%d: %s", silo_id, _cache_exc)
        return doc_count

    @staticmethod
    def find_docs_in_collection(
        silo_id: int,
        query: str,
        filter_metadata: Optional[dict] = None,
        limit: Optional[int] = None,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None,
        fetch_k: Optional[int] = None,
        lambda_mult: Optional[float] = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
        db: Session = None,
    ) -> List[Document]:
        # Get silo within the session to ensure relationships are loaded
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo or not SiloService.check_silo_collection_exists(silo_id, db):
            return []
        
        collection_name = COLLECTION_PREFIX + str(silo_id)
        
        # Get embedding service within the same session
        embedding_service = None
        if silo.embedding_service_id:
            embedding_service = SiloRepository.get_embedding_service_by_id(silo.embedding_service_id, db)
        
        results_limit = limit if limit and limit > 0 else DEFAULT_SEARCH_LIMIT
        if results_limit > MAX_SEARCH_LIMIT:
            results_limit = MAX_SEARCH_LIMIT

        docs = _get_vector_store(silo).search_similar_documents(
            collection_name,
            query,
            embedding_service=embedding_service,
            filter_metadata=filter_metadata or {},
            k=results_limit,
            search_type=search_type,
            score_threshold=score_threshold,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
        )
        if min_content_length is not None or max_content_length is not None:
            docs = [
                d for d in docs
                if (min_content_length is None or len(d.page_content) >= min_content_length)
                and (max_content_length is None or len(d.page_content) <= max_content_length)
            ]
        return docs

    @staticmethod
    def search_in_silo(
        silo_id: int,
        query: str,
        filter_metadata: Optional[dict] = None,
        limit: Optional[int] = None,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None,
        fetch_k: Optional[int] = None,
        lambda_mult: Optional[float] = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
        db: Session = None,
    ) -> List[Document]:
        """
        Search for documents in a silo using semantic search
        
        Args:
            silo_id: ID of the silo to search in
            query: Search query text
            filter_metadata: Optional metadata filters
            limit: Maximum number of results to return
            db: Database session
            
        Returns:
            List of Document objects with page_content and metadata
        """
        # Use find_docs_in_collection as the base implementation
        return SiloService.find_docs_in_collection(
            silo_id,
            query,
            filter_metadata,
            limit=limit,
            search_type=search_type,
            score_threshold=score_threshold,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            min_content_length=min_content_length,
            max_content_length=max_content_length,
            db=db,
        )

    @staticmethod
    def _get_filter_value_by_type(field_value: str, field_type: str) -> dict:
        """Helper method to convert field value to the appropriate type for filtering"""
        if field_type == 'int':
            return {"$eq": int(field_value)}
        elif field_type == 'float':
            return {"$eq": float(field_value)}
        elif field_type == 'bool':
            return {"$eq": field_value}
        elif field_type in ['str', 'date']:
            return {"$eq": field_value}
        return {"$eq": field_value}  # default case

    @staticmethod
    def get_metadata_filter_from_form(silo: Silo, form_data: dict) -> dict:
        filter_dict = {}
        if not silo.metadata_definition:
            return filter_dict

        field_definitions = {f['name']: f for f in silo.metadata_definition.fields}
        filter_prefix = 'filter_'
        
        for field_name, field_value in form_data.items():
            if not field_value or field_value == '':
                continue
                
            if not field_name.startswith(filter_prefix):
                continue
                
            name = field_name[len(filter_prefix):]
            if name not in field_definitions:
                continue
                
            field_definition = field_definitions[name]
            filter_dict[name] = SiloService._get_filter_value_by_type(
                field_value, 
                field_definition['type']
            )
        
        return filter_dict 

    # ==================== ROUTER SERVICE METHODS ====================
    
    @staticmethod
    def get_silos_list(app_id: int, db: Session) -> List[SiloListItemSchema]:
        """
        Get list of silos for a specific app with document counts
        """
        # Get silos using the existing service
        silos = SiloService.get_silos_by_app_id(app_id, db)
        
        result = []
        for silo in silos:
            # Get document count
            docs_count = SiloService.count_docs_in_silo(silo.silo_id, db)
            
            result.append(SiloListItemSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                description=silo.description,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count,
                vector_db_type=silo.vector_db_type
            ))
        
        return result
    
    @staticmethod
    def get_silo_detail(app_id: int, silo_id: int, db: Session) -> SiloDetailSchema:
        """
        Get detailed silo information including form data for editing
        """
        logger.info(f"Getting silo detail for app_id: {app_id}, silo_id: {silo_id}")
        
        if silo_id == 0:
            # New silo
            logger.info("Returning new silo template")
            vector_db_options = VectorStoreFactory.get_available_type_options()
            default_vector_db_type = _resolve_vector_db_type()
            return SiloDetailSchema(
                silo_id=0,
                name="",
                description=None,
                type=None,
                created_at=None,
                docs_count=0,
                vector_db_type=default_vector_db_type,
                # Form data
                output_parsers=[],
                embedding_services=[],
                vector_db_options=vector_db_options
            )
        
        # Existing silo
        logger.info(f"Getting existing silo {silo_id}")
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            logger.error(f"Silo {silo_id} not found")
            return None
        
        logger.info(f"Found silo: {silo.name}, app_id: {silo.app_id}")
        
        # Get document count
        try:
            logger.info(f"Counting docs in silo {silo_id}")
            docs_count = SiloService.count_docs_in_silo(silo_id, db)
            logger.info(f"Docs count: {docs_count}")
        except Exception as e:
            logger.error(f"Error counting docs in silo {silo_id}: {str(e)}")
            docs_count = 0
        
        # Get form data using repository consolidation
        try:
            logger.info(f"Getting form data for app_id: {app_id}")
            form_data = SiloRepository.get_form_data_for_silo(app_id, 0, db)  # We already have the silo
            output_parsers = [{"parser_id": p.parser_id, "name": p.name} for p in form_data['output_parsers']]
            from schemas.embedding_service_schemas import EmbeddingServiceOptionSchema
            embedding_services = (
                [EmbeddingServiceOptionSchema(service_id=s.service_id, name=s.name, provider=s.provider.value if hasattr(s.provider, 'value') else s.provider, is_system=False) for s in form_data['embedding_services']]
                + [EmbeddingServiceOptionSchema(service_id=s.service_id, name=s.name, provider=s.provider.value if hasattr(s.provider, 'value') else s.provider, is_system=True) for s in form_data.get('system_embedding_services', [])]
            )
            logger.info(f"Found {len(output_parsers)} parsers and {len(embedding_services)} embedding services")
        except Exception as e:
            logger.error(f"Error getting form data: {str(e)}")
            output_parsers = []
            embedding_services = []
        
        # Get metadata definition fields if silo has one
        metadata_fields = None
        try:
            if silo.metadata_definition_id:
                logger.info(f"Getting metadata parser {silo.metadata_definition_id}")
                metadata_parser = SiloRepository.get_output_parser_by_id(silo.metadata_definition_id, db)
                if metadata_parser and metadata_parser.fields:
                    metadata_fields = [
                        {
                            "name": field.get("name", ""),
                            "type": field.get("type", "str"),
                            "description": field.get("description", "")
                        }
                        for field in metadata_parser.fields
                    ]
        except Exception as e:
            logger.error(f"Error getting metadata fields: {str(e)}")
            metadata_fields = None
        
        try:
            logger.info(f"Creating SiloDetailSchema for silo {silo_id}")
            vector_db_type = _resolve_vector_db_type(silo)
            vector_db_options = VectorStoreFactory.get_available_type_options()
            return SiloDetailSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                description=silo.description,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count,
                vector_db_type=vector_db_type,
                # Current values for editing
                metadata_definition_id=silo.metadata_definition_id,
                embedding_service_id=silo.embedding_service_id,
                # Form data
                output_parsers=output_parsers,
                embedding_services=embedding_services,
                vector_db_options=vector_db_options,
                # Metadata definition fields for playground
                metadata_fields=metadata_fields
            )
        except Exception as e:
            logger.error(f"Error creating SiloDetailSchema: {str(e)}")
            raise
    
    @staticmethod
    def create_or_update_silo_router(
        app_id: int, 
        silo_id: int, 
        silo_data: CreateUpdateSiloSchema, 
        db: Session
    ) -> Silo:
        """
        Create or update silo using router data
        """
        # Prepare form data for the service
        # vector_db_type uses getattr so this method works with both CreateSiloSchema
        # (which has the field) and UpdateSiloSchema (which intentionally omits it).
        form_data = {
            'silo_id': silo_id,
            'name': silo_data.name,
            'description': silo_data.description,
            'app_id': app_id,
            'type': silo_data.type,
            'output_parser_id': silo_data.output_parser_id,
            'embedding_service_id': getattr(silo_data, 'embedding_service_id', None),
            'vector_db_type': getattr(silo_data, 'vector_db_type', None)
        }
        
        # Create or update using the existing service
        silo = SiloService.create_or_update_silo(form_data, db=db)
        return silo
    
    @staticmethod
    def delete_silo_router(silo_id: int, db: Session) -> bool:
        """
        Delete a silo and all its documents
        """
        return SiloRepository.delete(silo_id, db)
    
    @staticmethod
    def search_silo_documents_router(
        silo_id: int,
        query: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        search_type: str = "similarity",
        score_threshold: Optional[float] = None,
        fetch_k: Optional[int] = None,
        lambda_mult: Optional[float] = None,
        min_content_length: Optional[int] = None,
        max_content_length: Optional[int] = None,
        db: Session = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for documents in a silo using semantic search with optional metadata filtering
        """
        # Get silo to validate it exists
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            return None
        
        # Perform the search with metadata filtering
        results = SiloService.find_docs_in_collection(
            silo_id,
            query,
            filter_metadata=filter_metadata,
            limit=limit,
            search_type=search_type,
            score_threshold=score_threshold,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            min_content_length=min_content_length,
            max_content_length=max_content_length,
            db=db,
        )
        
        # Convert results to response format
        response_results = []
        for doc in results:
            # Extract score from metadata if available
            score = doc.metadata.pop('_score', None) if '_score' in doc.metadata else None
            response_results.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            })
        
        return {
            "query": query,
            "results": response_results,
            "total_results": len(response_results),
            "filter_metadata": filter_metadata
        }

    @staticmethod
    def get_neighboring_chunks(
        silo_id: int,
        source_type: str,
        source_id: str,
        db: Session = None,
    ) -> List[Dict[str, Any]]:
        """
        Return all chunks from the same source document, ordered by position.

        source_type: "media" or "resource"
        source_id:   str value of media_id or resource_id (as stored in metadata)

        Raises ValueError for unsupported source_type.
        """
        if source_type not in ("media", "resource"):
            raise ValueError(f"Unsupported source_type '{source_type}'. Must be 'media' or 'resource'.")

        if source_type == "media":
            filter_metadata = {
                "media_id": {"$eq": source_id},
                "content_type": {"$eq": "media_chunk"},
            }
        else:
            filter_metadata = {"resource_id": {"$eq": source_id}}

        docs = SiloService.find_docs_in_collection(
            silo_id,
            "",
            filter_metadata=filter_metadata,
            limit=MAX_SEARCH_LIMIT,
            db=db,
        )

        # Sort by position in the source document
        if source_type == "media":
            docs.sort(key=lambda d: d.metadata.get("chunk_index", 0))
        else:
            docs.sort(key=lambda d: d.metadata.get("page", d.metadata.get("chunk_index", 0)))

        return [
            {"page_content": doc.page_content, "metadata": doc.metadata, "score": None}
            for doc in docs
        ]

    @staticmethod
    def get_metadata_field_values(
        silo_id: int,
        field: str,
        prefix: Optional[str] = None,
        limit: int = 100,
        db: Session = None,
    ) -> List[str]:
        """
        Return distinct values for a metadata field in the silo's vector collection.
        Sorted alphabetically, filtered by optional case-insensitive prefix.
        limit is clamped to 1–500.
        Raises ValueError for invalid field names, NotFoundError for missing silo.
        """
        import re
        if not field or not re.match(r'^[\w.\-]+$', field):
            raise ValueError(f"Invalid metadata field name: '{field}'")

        limit = min(max(1, limit), 500)

        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            raise NotFoundError(f"Silo {silo_id} not found", "silo")

        collection_name = COLLECTION_PREFIX + str(silo_id)
        return _get_vector_store(silo).get_distinct_metadata_values(
            collection_name, field, prefix=prefix, limit=limit,
        )
