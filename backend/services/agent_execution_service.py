import os
import asyncio
import ast
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ocr_agent import OCRAgent
from services.agent_execution_context import AgentExecutionContext
from tools.PDFTools import extract_text_from_pdf, convert_pdf_to_images, check_pdf_has_text
from tools.ocrAgentTools import (
    convert_image_to_base64,
    extract_text_from_image,
    format_data_with_text_llm,
    format_data_from_vision,
    get_data_from_extracted_text,
    get_document_data_from_pages
)
from tools.aiServiceTools import get_llm
from tools.outputParserTools import create_model_from_json_schema
from services.agent_service import AgentService
from services.file_management_service import FileManagementService
from services.session_management_service import SessionManagementService
from repositories.agent_execution_repository import AgentExecutionRepository
from utils.logger import get_logger
from utils.config import get_app_config

logger = get_logger(__name__)

_IMAGE_FILE_TYPES = {"image"}
_AGENT_NOT_FOUND = "Agent not found"


def _inject_file_markers(text: str, files: list) -> str:
    """Replace [Image saved: x] placeholders with file:// markdown markers.

    Files whose placeholder is not found in the text are appended at the end.
    Images become standard markdown images; other files become download links.
    """
    if not isinstance(text, str):
        return text

    remaining = []
    for f in files:
        if f.file_type in _IMAGE_FILE_TYPES:
            marker = f"![{f.filename}](file://{f.file_id})"
        else:
            marker = f"[📎 {f.filename}](file://{f.file_id})"

        placeholder = f"[Image saved: {f.filename}]"
        if placeholder in text:
            text = text.replace(placeholder, marker)
        else:
            remaining.append(marker)

    if remaining:
        text = text.rstrip() + "\n\n" + "\n\n".join(remaining)

    return text


class AgentExecutionService:
    """Unified service for agent execution - used by both public and internal APIs"""
    
    # Shared thread pool for blocking I/O operations (file processing, OCR, etc.)
    _executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="agent_exec")
    
    def __init__(self):
        self.agent_service = AgentService()
        self.session_service = SessionManagementService()
        self.agent_execution_repo = AgentExecutionRepository()
    
    async def execute_agent_chat_with_file_refs(
        self,
        agent_id: int,
        message: str,
        file_references: List = None,
        search_params: Dict = None,
        user_context: Dict = None,
        conversation_id: int = None,
        db: Session = None,
    ) -> Dict[str, Any]:
        """Execute agent chat with persistent file references.

        Returns:
            Dict containing agent response and metadata.
        """
        try:
            ctx = await self._prepare_turn(
                agent_id=agent_id,
                message=message,
                file_references=file_references,
                search_params=search_params,
                user_context=user_context,
                conversation_id=conversation_id,
                db=db,
            )

            response = await self._execute_agent_async(
                ctx.fresh_agent,
                ctx.enhanced_message,
                ctx.search_params,
                ctx.session_id_for_cache,
                ctx.user_context,
                ctx.image_files,
                working_dir=ctx.working_dir,
            )

            return await self._finalize_turn(ctx, response, db)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing agent chat: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    async def _prepare_turn(
        self,
        agent_id: int,
        message: str,
        file_references: List = None,
        search_params: Dict = None,
        user_context: Dict = None,
        conversation_id: int = None,
        db: Session = None,
    ) -> AgentExecutionContext:
        """Run all setup steps for one agent chat turn.

        Validates access, resolves the conversation / session, builds the
        enhanced message, and resolves the working directory.  Does NOT invoke
        the LangGraph chain — that is the caller's responsibility.

        Returns:
            A fully populated :class:`AgentExecutionContext`.
        """
        # 1. Fetch agent (lightweight — no relationships)
        agent = self.agent_service.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=_AGENT_NOT_FOUND)

        # 2. Access validation
        await self._validate_agent_access(agent, user_context)

        # 3. Frozen-state guard (SaaS mode)
        if getattr(agent, 'is_frozen', False):
            raise HTTPException(
                status_code=403,
                detail="This agent is frozen because your subscription tier has been downgraded. "
                       "Please upgrade your plan or delete other resources to unfreeze it.",
            )

        # 4. System LLM quota (SaaS mode, no-op in self-managed)
        if db and user_context and user_context.get('user_id'):
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_system_llm_quota(db, user_context['user_id'])

        # 5. Convert FileReference objects to plain dicts
        processed_files: List[Dict] = []
        if file_references:
            for file_ref in file_references:
                processed_files.append({
                    "filename": file_ref.filename,
                    "content": file_ref.content,
                    "type": file_ref.file_type,
                    "file_id": file_ref.file_id,
                    "file_path": file_ref.file_path,
                })

        # 6. Get / create conversation for memory-enabled agents
        session = None
        conversation = None
        if agent.has_memory:
            from services.conversation_service import ConversationService

            if conversation_id:
                conversation = ConversationService.get_conversation(
                    db=db,
                    conversation_id=conversation_id,
                    user_context=user_context,
                    agent_id=agent_id,
                )
                if not conversation:
                    raise HTTPException(
                        status_code=404, detail="Conversation not found or access denied"
                    )
                session_suffix = conversation.session_id.replace(f"conv_{agent_id}_", "")
                session = await self.session_service.get_user_session(
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=session_suffix,
                )
            else:
                conversation = ConversationService.create_conversation(
                    db=db,
                    agent_id=agent_id,
                    user_context=user_context,
                    title=None,
                )
                logger.info(
                    "Auto-created conversation %s for agent %s",
                    conversation.conversation_id,
                    agent_id,
                )
                session_suffix = conversation.session_id.replace(f"conv_{agent_id}_", "")
                session = await self.session_service.get_user_session(
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=session_suffix,
                )

        # 7. Re-query agent with all relationships eagerly loaded
        fresh_agent = self.agent_execution_repo.get_agent_with_relationships(db, agent_id)
        if not fresh_agent:
            raise HTTPException(status_code=404, detail="Agent not found in database")

        # 8. Build enhanced message + separate image files
        enhanced_message, image_files = self._prepare_message_with_files(message, processed_files)

        session_id_for_cache = session.id if (fresh_agent.has_memory and session) else None
        effective_conv_id = conversation_id or (
            conversation.conversation_id if conversation else None
        )

        # 9. Resolve working directory
        app_config = get_app_config()
        tmp_base = app_config['TMP_BASE_FOLDER']
        if effective_conv_id:
            working_dir = os.path.join(tmp_base, "conversations", str(effective_conv_id))
        else:
            user_id = user_context.get('user_id', 'anonymous') if user_context else 'anonymous'
            app_id_ctx = user_context.get('app_id', 'default') if user_context else 'default'
            session_key = f"agent_{agent_id}_user_{user_id}_app_{app_id_ctx}"
            working_dir = os.path.join(tmp_base, "persistent", session_key)

        # 10. Snapshot working dir so finalize can exclude pre-existing files
        pre_existing_files: set = set()
        if working_dir and os.path.isdir(working_dir):
            pre_existing_files = set(os.listdir(working_dir))

        return AgentExecutionContext(
            agent_id=agent_id,
            agent=agent,
            fresh_agent=fresh_agent,
            enhanced_message=enhanced_message,
            image_files=image_files,
            session=session,
            conversation=conversation,
            effective_conv_id=effective_conv_id,
            session_id_for_cache=session_id_for_cache,
            working_dir=working_dir,
            pre_existing_files=pre_existing_files,
            processed_files=processed_files,
            search_params=search_params,
            user_context=user_context,
        )

    async def _finalize_turn(
        self,
        ctx: AgentExecutionContext,
        raw_response: Any,
        db: Session,
    ) -> Dict[str, Any]:
        """Run all post-processing steps for one agent chat turn.

        1. Sync output files written to the working dir.
        2. Inject file:// markers into the response text.
        3. Parse the response with the agent's output parser.
        4. Update the agent request count.
        5. Touch the session to keep it alive.
        6. Record system LLM usage (SaaS mode).
        7. Increment the conversation message count.

        Args:
            ctx: The context produced by :meth:`_prepare_turn`.
            raw_response: The raw string/dict returned by :meth:`_execute_agent_async`.
            db: Active SQLAlchemy session.

        Returns:
            A dict with keys ``response``, ``agent_id``, ``conversation_id``,
            ``metadata``, ``parsed_response``, ``effective_conv_id``, and
            ``files_data`` (used by the streaming path to emit the ``done`` event).
        """
        import re as _re
        from tools.agentTools import parse_agent_response

        response = raw_response
        files_data: List[Dict[str, Any]] = []

        # 1 + 2. Sync output files and inject markers
        if ctx.working_dir:
            file_service = FileManagementService()
            new_files = await file_service.sync_output_files(
                working_dir=ctx.working_dir,
                agent_id=ctx.agent_id,
                user_context=ctx.user_context,
                conversation_id=(
                    str(ctx.effective_conv_id) if ctx.effective_conv_id else None
                ),
                exclude_filenames=ctx.pre_existing_files,
            )
            if new_files:
                response = _inject_file_markers(response, new_files)
                files_data = [
                    {
                        "file_id": f.file_id,
                        "filename": f.filename,
                        "file_type": f.file_type,
                    }
                    for f in new_files
                ]

        # 3. Parse response
        parsed_response = parse_agent_response(response, ctx.agent)

        # 4. Update request count
        self._update_request_count(ctx.agent, db)

        # 5. Touch session
        if ctx.session:
            await self.session_service.touch_session(ctx.session.id)

        # 6. Record system LLM usage (SaaS mode — no-op for own-key services)
        ai_svc = ctx.fresh_agent.ai_service
        if (
            ai_svc is not None
            and getattr(ai_svc, 'app_id', 'NOT_NULL') is None
            and db
            and ctx.user_context
            and ctx.user_context.get('user_id')
        ):
            try:
                from services.usage_tracking_service import UsageTrackingService
                UsageTrackingService.record_system_llm_call(db, ctx.user_context['user_id'])
            except Exception as _usage_exc:
                logger.warning(
                    "Failed to record system LLM usage: %s", _usage_exc, exc_info=True
                )

        # 7. Update conversation message count
        if ctx.conversation:
            from services.conversation_service import ConversationService

            if isinstance(parsed_response, list):
                try:
                    text_parts = [
                        item.get("text", "")
                        for item in parsed_response
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    last_message_preview = " ".join(text_parts)[:200]
                except Exception:
                    last_message_preview = str(parsed_response)[:200]
            else:
                last_message_preview = (
                    parsed_response[:200]
                    if isinstance(parsed_response, str)
                    else str(parsed_response)[:200]
                )

            last_message_preview = _re.sub(
                r'!\[[^\]]*\]\(file://[^\)]*\)', '[imagen]', last_message_preview
            )
            last_message_preview = _re.sub(
                r'\[📎[^\]]*\]\(file://[^\)]*\)', '[archivo]', last_message_preview
            )
            last_message_preview = last_message_preview.strip() or '[imagen generada]'

            ConversationService.increment_message_count(
                db=db,
                conversation_id=ctx.conversation.conversation_id,
                last_message=last_message_preview,
                increment_by=2,
            )

        return {
            "response": parsed_response,
            "agent_id": ctx.agent_id,
            "conversation_id": (
                ctx.conversation.conversation_id if ctx.conversation else None
            ),
            "metadata": {
                "agent_name": ctx.agent.name,
                "agent_type": ctx.agent.type,
                "files_processed": len(ctx.processed_files),
                "has_memory": ctx.agent.has_memory,
            },
            # Fields used by the streaming path to emit the done event
            "parsed_response": parsed_response,
            "effective_conv_id": ctx.effective_conv_id,
            "files_data": files_data,
        }

    async def execute_agent_ocr(
        self, 
        agent_id: int, 
        pdf_file: UploadFile,
        user_context: Dict = None,
        for_api: bool = False,  # True for public API, False for playground
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute OCR processing - used by both playground and public API
        
        Args:
            agent_id: ID of the OCR agent
            pdf_file: PDF file to process
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Dict containing OCR processing results
        """
        try:
            # Get OCR agent
            agent = self.agent_service.get_agent(db, agent_id, agent_type='ocr_agent')
            if not agent or not isinstance(agent, OCRAgent):
                raise HTTPException(status_code=404, detail="OCR Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Validate PDF file
            if not pdf_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
            
            # Save PDF to temporary location
            temp_pdf_path = await self._save_uploaded_file(pdf_file)
            
            try:
                # Process PDF using existing tools
                result = await self._process_pdf_with_ocr(agent, temp_pdf_path, db)
                
                # Update request count
                self._update_request_count(agent, db)
                
                if for_api:
                    # Public API: Return just the structured content (output parser result)
                    return result.get("content", result)
                else:
                    # Playground: Return full result with metadata for UI
                    content = result.get("content", "")
                    if isinstance(content, dict):
                        import json
                        extracted_text = json.dumps(content, indent=2, ensure_ascii=False)
                    else:
                        extracted_text = str(content)
                    
                    return {
                        "result": result,
                        "agent_id": agent_id,
                        "extracted_text": extracted_text,
                        "metadata": {
                            "agent_name": agent.name,
                            "pdf_filename": pdf_file.filename,
                            "pages_processed": len(result.get("pages", [])),
                            "confidence": result.get("confidence", 0.0)
                        }
                    }
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
                    
        except Exception as e:
            logger.error(f"Error executing OCR agent: {str(e)}")
            raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
    
    async def reset_agent_conversation(
        self, 
        agent_id: int,
        user_context: Dict = None,
        db: Session = None
    ) -> bool:
        """
        Reset conversation - used by both playground and public API
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            True if reset successful
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail=_AGENT_NOT_FOUND)
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Reset session if memory enabled
            if agent.has_memory:
                # Extract conversation_id from user_context if present
                conversation_id = user_context.get("conversation_id")
                
                # IMPORTANT: First get the session to find the session_id before resetting
                # This ensures we can invalidate the checkpointer for the correct session
                from services.agent_cache_service import CheckpointerCacheService
                
                # Get the session to find the session_id (pass conversation_id explicitly)
                session = await self.session_service.get_user_session(agent_id, user_context, conversation_id)
                if session:
                    # Invalidate the checkpointer for this specific session (use async version)
                    await CheckpointerCacheService.invalidate_checkpointer_async(agent_id, session.id)
                    logger.info(f"Invalidated checkpointer for agent {agent_id}, session {session.id}")
                
                # Reset the session object (clears messages and memory)
                # This should be done after invalidating checkpointer to ensure we have the session ID
                await self.session_service.reset_user_session(agent_id, user_context)
            
            # Clear all attached files for this user/agent session
            from services.file_management_service import FileManagementService
            file_service = FileManagementService()
            
            # Get all attached files for this session
            attached_files = await file_service.list_attached_files(agent_id, user_context)
            
            # Remove each file
            for file_data in attached_files:
                try:
                    await file_service.remove_file(
                        file_id=file_data['file_id'],
                        agent_id=agent_id,
                        user_context=user_context
                    )
                    logger.info(f"Removed file {file_data['filename']} during conversation reset")
                except Exception as e:
                    logger.error(f"Error removing file {file_data['file_id']} during reset: {str(e)}")
            
            logger.info(f"Conversation reset for agent {agent_id} - cleared {len(attached_files)} files")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting agent conversation: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
    
    async def get_conversation_history(
        self,
        agent_id: int,
        user_context: Dict = None,
        db: Session = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation history - used by playground to load existing conversation
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            List of messages with role and content
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail=_AGENT_NOT_FOUND)
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Get conversation history if memory enabled
            if agent.has_memory:
                # Get the session to find the session_id
                session = await self.session_service.get_user_session(agent_id, user_context)
                if session:
                    # Get history from checkpointer
                    from services.agent_cache_service import CheckpointerCacheService
                    history = await CheckpointerCacheService.get_conversation_history_async(agent_id, session.id)
                    logger.info(f"Retrieved {len(history)} messages for agent {agent_id}, session {session.id}")
                    
                    # Clean history for frontend display (handle multimodal content)
                    cleaned_history = []
                    for msg in history:
                        if not isinstance(msg, dict):
                            continue
                            
                        content = msg.get("content")
                        parsed_content = content

                        # Some backends store the content as a string representation of the list
                        if isinstance(content, str):
                            stripped_content = content.strip()
                            if stripped_content.startswith("[") and "type" in stripped_content:
                                try:
                                    parsed_content = json.loads(stripped_content)
                                except json.JSONDecodeError:
                                    try:
                                        parsed_content = ast.literal_eval(stripped_content)
                                    except (ValueError, SyntaxError):
                                        parsed_content = content
                        
                        # If content is a list (multimodal structure), extract the text for display
                        if isinstance(parsed_content, list):
                            text_parts = []
                            has_image = False
                            for item in parsed_content:
                                if isinstance(item, dict):
                                    if item.get("type") == "text":
                                        text_parts.append(item.get("text", ""))
                                    elif item.get("type") == "image_url":
                                        has_image = True
                            
                            display_text = " ".join(text_parts)
                            # If we have an image but no text (or just whitespace), add a placeholder
                            if not display_text.strip() and has_image:
                                display_text = "[Imagen adjunta]"
                                
                            # Create a copy to avoid modifying the original cache
                            clean_msg = msg.copy()
                            clean_msg["content"] = display_text
                            cleaned_history.append(clean_msg)
                        else:
                            cleaned_history.append(msg)

                    # Resolve [IMAGE:{block_id}] placeholders to inline file:// markers
                    from services.conversation_service import _resolve_image_placeholders
                    resolved_history = []
                    for msg in cleaned_history:
                        if msg.get("role") == "agent" and isinstance(msg.get("content"), str) and "[IMAGE:" in msg["content"]:
                            resolved_msg = msg.copy()
                            resolved_msg["content"] = await _resolve_image_placeholders(
                                msg["content"],
                                agent_id=agent_id,
                                user_context=user_context,
                                conversation_id=None,
                            )
                            resolved_history.append(resolved_msg)
                        else:
                            resolved_history.append(msg)
                    return resolved_history

            return []

        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            return []
    
    async def _validate_agent_access(self, agent: Agent, user_context: Dict):
        """Validate user has access to the agent"""
        # TODO: Implement proper access validation
        # For now, just log the validation
        logger.info(f"Validating access for agent {agent.agent_id} with context {user_context}")
    
    async def _process_files_for_agent(self, files: List[UploadFile], agent: Agent) -> List[Dict]:
        """Process files for agent consumption using existing PDF tools"""
        processed_files = []
        
        for file in files:
            try:
                # Save file temporarily
                temp_path = await self._save_uploaded_file(file)
                
                # Process based on file type IN THREAD POOL (blocking I/O)
                loop = asyncio.get_event_loop()
                file_data = await loop.run_in_executor(
                    self._executor,
                    self._process_single_file,
                    temp_path, file.filename
                )
                
                if file_data:
                    processed_files.append(file_data)
                
                # Clean up
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {str(e)}")
                continue
        
        return processed_files
    
    def _process_single_file(self, temp_path: str, filename: str) -> Optional[Dict]:
        """Synchronous file processing - called in thread pool"""
        try:
            if filename.lower().endswith('.pdf'):
                # Use existing PDF tools (blocking I/O)
                text_content = extract_text_from_pdf(temp_path)
                return {
                    "filename": filename,
                    "content": text_content,
                    "type": "pdf"
                }
            else:
                # Handle other file types (blocking I/O)
                with open(temp_path, 'r') as f:
                    content = f.read()
                return {
                    "filename": filename,
                    "content": content,
                    "type": "text"
                }
        except Exception as e:
            logger.error(f"Error in _process_single_file: {str(e)}")
            return None
    
    async def _process_pdf_with_ocr(self, agent: OCRAgent, pdf_path: str, db: Session) -> Dict[str, Any]:
        """Process PDF using OCR workflow respecting output parser/data structure"""
        # Run all OCR processing in thread pool (blocking operations: PDF parsing, LLM calls, etc.)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._process_pdf_with_ocr_sync,
            agent, pdf_path, db
        )
        return result
    
    def _process_pdf_with_ocr_sync(self, agent: OCRAgent, pdf_path: str, db: Session) -> Dict[str, Any]:
        """Synchronous OCR processing - called in thread pool"""
        try:
            # Re-load agent with all relationships
            ocr_agent_id = agent.agent_id
            agent = self.agent_execution_repo.get_ocr_agent_with_relationships(db, ocr_agent_id)
            
            if not agent:
                raise ValueError(f"Agent {ocr_agent_id} not found")
            
            # Get output parser if configured - this is CRITICAL for structured output
            pydantic_class = None
            if agent.output_parser_id:
                try:
                    # Get the output parser definition using repository
                    output_parser = self.agent_execution_repo.get_output_parser_by_id(db, agent.output_parser_id)
                    
                    if output_parser and output_parser.fields:
                        logger.info(f"Found output parser: {output_parser.name} with fields: {output_parser.fields}")
                        # Create pydantic model from schema like in original
                        pydantic_class = create_model_from_json_schema(
                            output_parser.fields,
                            output_parser.name
                        )
                        logger.info(f"Output parser model created successfully: {output_parser.name} -> {pydantic_class}")
                    else:
                        logger.warning(f"Output parser {agent.output_parser_id} not found or has no fields")
                    
                except Exception as e:
                    logger.warning(f"Failed to load output parser: {str(e)}")
            
            # Check if PDF has text
            has_text = check_pdf_has_text(pdf_path)
            
            if has_text:
                # Extract text directly
                text_content = extract_text_from_pdf(pdf_path)
                logger.info(f"Extracted text from PDF: {len(text_content)} characters")
                
                # Process with text model and output parser if available
                if agent.text_system_prompt and agent.service_id and pydantic_class:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            logger.info("Processing text with LLM and output parser")
                            # Use the output parser to structure the data
                            structured_data = get_data_from_extracted_text(
                                text_content,
                                text_model,
                                pydantic_class,
                                agent.text_system_prompt,
                                text_content,
                                os.path.basename(pdf_path)
                            )
                            
                            logger.info(f"Structured data result: {structured_data}")
                            
                            return {
                                "method": "text_extraction_with_llm",
                                "content": structured_data,
                                "extracted_text": text_content,
                                "confidence": 0.9
                            }
                    except Exception as e:
                        logger.error(f"Error processing with LLM and output parser: {str(e)}", exc_info=True)
                
                # If no text model or output parser, return raw text
                logger.info("No text model or output parser configured, returning raw text")
                return {
                    "method": "text_extraction",
                    "content": text_content,
                    "extracted_text": text_content,
                    "confidence": 0.9
                }
            else:
                # Convert to images and process with vision
                app_config = get_app_config()
                images_dir = app_config['IMAGES_PATH']
                os.makedirs(images_dir, exist_ok=True)
                
                image_paths = convert_pdf_to_images(pdf_path, images_dir)
                logger.info(f"Converted PDF to {len(image_paths)} images")
                
                # Process images with vision model
                vision_results = []
                for i, image_path in enumerate(image_paths):
                    try:
                        base64_image = convert_image_to_base64(image_path)
                        
                        # Get vision model
                        vision_model = get_llm(agent, is_vision=True)
                        if not vision_model:
                            raise ValueError("Vision model not found")
                        
                        # Extract text from image
                        vision_result = extract_text_from_image(
                            base64_image, 
                            agent.vision_system_prompt, 
                            vision_model, 
                            f"Page {i+1}"
                        )
                        vision_results.append({
                            "page": i + 1,
                            "extracted_text": vision_result
                        })
                        
                        # Clean up image file
                        try:
                            os.remove(image_path)
                        except OSError:
                            pass
                            
                    except Exception as e:
                        logger.warning(f"Error processing image {i+1}: {str(e)}")
                        continue
                
                # Process with text model if available and we have vision results
                if agent.text_system_prompt and agent.service_id and vision_results:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            # Format data with text model using output parser
                            formatted_result = format_data_with_text_llm(
                                vision_results, 
                                text_model, 
                                pydantic_class, 
                                agent.text_system_prompt, 
                                "", 
                                os.path.basename(pdf_path)
                            )
                            
                            # Get final structured document data
                            final_result = get_document_data_from_pages(
                                agent.text_system_prompt,
                                formatted_result,
                                pydantic_class,
                                text_model,
                                "",
                                os.path.basename(pdf_path)
                            )
                            
                            return {
                                "method": "vision_and_text",
                                "content": final_result,
                                "extracted_text": vision_results,
                                "confidence": 0.8
                            }
                    except Exception as e:
                        logger.warning(f"Error processing with text model: {str(e)}")
                
                # Return vision results directly
                return {
                    "method": "vision_only",
                    "content": vision_results,
                    "extracted_text": vision_results,
                    "confidence": 0.7
                }
                
        except Exception as e:
            logger.error(f"Error processing PDF with OCR: {str(e)}")
            raise
    
    def _prepare_message_with_files(self, message: str, processed_files: List[Dict]) -> tuple:
        """
        Build enhanced message with file contents and separate image files.

        Returns:
            Tuple of (enhanced_message, image_files)
        """
        enhanced_message = message
        image_files = []

        if processed_files:
            app_config = get_app_config()
            tmp_base_folder = app_config['TMP_BASE_FOLDER']

            text_files_msg = ""
            for file_data in processed_files:
                if file_data.get('type') == 'image':
                    image_files.append(file_data)
                else:
                    text_files_msg += f"\n\n--- File: {file_data['filename']} (Path: {file_data['file_path']}) ---\n{file_data['content']}\n--- End of {file_data['filename']} ---"

            if text_files_msg:
                enhanced_message += "\n\nFiles base folder is: " + tmp_base_folder
                enhanced_message += "\n\n[Attached files:]" + text_files_msg

        return enhanced_message, image_files

    def _save_generated_image(self, b64_data: str, working_dir: str, block_id: str = None) -> str:
        """Decode a base64 image and save it to working_dir. Returns a status string."""
        import base64
        import time
        try:
            os.makedirs(working_dir, exist_ok=True)
            safe_id = block_id[:48] if block_id else str(int(time.time()))
            filename = f"generated_image_{safe_id}.png"
            dest = os.path.join(working_dir, filename)
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64_data))
            logger.info("Saved generated image to %s", dest)
            return f"[Image saved: {filename}]"
        except Exception as exc:
            logger.error("Failed to save generated image: %s", exc)
            return "[Image generated but could not be saved]"

    def _extract_content_blocks(self, blocks: list, working_dir: Optional[str] = None) -> str:
        """
        Extract a plain-text response from a multimodal content block list.

        Handles:
        - text blocks           → concatenated as-is
        - image_generation_call → base64 result decoded and saved to working_dir;
                                   sync_output_files will register the file afterwards
        - image_url (data URI)  → Gemini native image generation; decoded and saved to
                                   working_dir the same way as image_generation_call
        - anything else         → silently ignored (tool call artefacts, etc.)
        """
        text_parts = []

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    text_parts.append(text)
            elif block_type == "image_generation_call":
                b64_data = block.get("result", "")
                block_id = block.get("id", "")
                label = self._save_generated_image(b64_data, working_dir, block_id) if b64_data and working_dir else "[Image generated]"
                text_parts.append(label)
            elif block_type == "image_url":
                # Gemini native image generation returns inline images as data URIs:
                # {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
                url = (block.get("image_url") or {}).get("url", "")
                if url.startswith("data:image/") and ";base64," in url:
                    import hashlib as _hl
                    import base64 as _b64
                    b64_data = url.split(";base64,", 1)[1]
                    # Use a content hash as stable block_id so history reload can
                    # recompute the same ID and resolve the file via _resolve_image_placeholders
                    img_hash = _hl.sha256(_b64.b64decode(b64_data)).hexdigest()[:16]
                    label = self._save_generated_image(b64_data, working_dir, block_id=img_hash) if working_dir else "[Image generated]"
                    text_parts.append(label)

        return " ".join(text_parts) if text_parts else str(blocks)

    async def _execute_agent_async(
        self,
        fresh_agent: Agent,
        message: str,
        search_params: Dict = None,
        session_id_for_cache: str = None,
        user_context: Dict = None,
        image_files: List[Dict] = None,
        working_dir: Optional[str] = None
    ) -> Any:
        """Execute agent in FastAPI's event loop using shared checkpointer pool.
        
        Returns:
            str for plain text responses, dict/Pydantic model for structured output (v1).
        """
        import langsmith as ls
        from tools.agentTools import create_agent, prepare_agent_config
        from langchain.messages import HumanMessage

        mcp_client = None
        try:
            # Create the agent chain with all tools and capabilities
            agent_chain, langsmith_config, mcp_client = await create_agent(
                fresh_agent, search_params, session_id_for_cache, user_context, working_dir
            )
            
            # Prepare configuration
            config = prepare_agent_config(fresh_agent)
            
            # Add session-specific configuration if memory is enabled
            if fresh_agent.has_memory and session_id_for_cache:
                config["configurable"]["thread_id"] = f"thread_{fresh_agent.agent_id}_{session_id_for_cache}"
                logger.info(f"Using session-aware thread_id: {config['configurable']['thread_id']}")
            else:
                config["configurable"]["thread_id"] = f"thread_{fresh_agent.agent_id}"
            
            # Add the question to config
            config["configurable"]["question"] = message
            
            # Build the HumanMessage (handles text-only and multimodal images)
            from tools.agentTools import build_human_message
            message_payload = build_human_message(fresh_agent, message, image_files or [], user_context)
            
            if langsmith_config:
                from langchain_core.tracers.langchain import LangChainTracer, wait_for_all_tracers
                
                logger.info(
                    f"LangSmith tracing ENABLED for app '{langsmith_config['project_name']}'"
                )
                
                per_app_tracer = LangChainTracer(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                )
                config.setdefault("callbacks", []).append(per_app_tracer)
                
                with ls.tracing_context(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                    enabled=True,
                ):
                    result = await agent_chain.ainvoke({"messages": [message_payload]}, config=config)
                
                try:
                    wait_for_all_tracers()
                except Exception as flush_err:
                    logger.warning(f"Error flushing LangSmith traces: {flush_err}")
            else:
                result = await agent_chain.ainvoke({"messages": [message_payload]}, config=config)

            # LangChain v1: structured output is in 'structured_response' key
            # when create_agent is called with response_format=pydantic_model
            if isinstance(result, dict) and "structured_response" in result:
                structured = result["structured_response"]
                if structured is not None:
                    return structured
            
            # Extract the response from the result messages
            if isinstance(result, dict) and "messages" in result and result["messages"] is not None:
                # Get the last AI message
                messages = result["messages"]
                for msg in reversed(messages):
                    if hasattr(msg, 'content') and msg.content:
                        content = msg.content
                        if isinstance(content, str):
                            return content
                        if isinstance(content, list):
                            return self._extract_content_blocks(content, working_dir)
                        return content
                # Fallback: return the last message content
                if messages:
                    return str(messages[-1].content) if hasattr(messages[-1], 'content') else str(messages[-1])
            
            # If result is a string, return it directly
            if isinstance(result, str):
                return result
                
            # Fallback: convert to string
            return str(result)
        finally:
            # As of langchain-mcp-adapters 0.1.0, MCP client doesn't need manual cleanup
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")
    
    async def _save_uploaded_file(self, file: UploadFile) -> str:
        """Save uploaded file to temporary location"""
        import tempfile
        
        #TODO: we should move this to class initialization? It is repeated in many places.
        # Get TMP_BASE_FOLDER from config
        app_config = get_app_config()
        tmp_base_folder = app_config['TMP_BASE_FOLDER']
        uploads_dir = os.path.join(tmp_base_folder, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Create temporary file in TMP_BASE_FOLDER/uploads
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=uploads_dir)
        
        try:
            # Write file content
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            return temp_file.name
        finally:
            temp_file.close()
    
    def _update_request_count(self, agent: Agent, db: Session):
        """Update agent request count"""
        self.agent_execution_repo.update_agent_request_count(db, agent.agent_id) 