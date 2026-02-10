import os
import asyncio
import ast
import json
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ocr_agent import OCRAgent
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
from services.session_management_service import SessionManagementService
from repositories.agent_execution_repository import AgentExecutionRepository
from utils.logger import get_logger
from utils.config import get_app_config

logger = get_logger(__name__)


class AgentExecutionService:
    """Unified service for agent execution - used by both public and internal APIs"""
    
    # Shared thread pool for blocking I/O operations (file processing, OCR, etc.)
    _executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="agent_exec")
    
    def __init__(self, db: Session = None):
        self.agent_service = AgentService()
        self.session_service = SessionManagementService()
        self.agent_execution_repo = AgentExecutionRepository()
        self.db = db
    
    async def execute_agent_chat_with_file_refs(
        self, 
        agent_id: int, 
        message: str, 
        file_references: List = None,
        search_params: Dict = None,
        user_context: Dict = None,
        conversation_id: int = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute agent chat with persistent file references
        
        Args:
            agent_id: ID of the agent to execute
            message: User message
            file_references: List of FileReference objects from FileManagementService
            search_params: Optional search parameters for silo-based agents
            user_context: User context (api_key, user_id, etc.)
            conversation_id: Optional conversation ID to continue existing conversation
            
        Returns:
            Dict containing agent response and metadata
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Process file references to extract content
            processed_files = []
            if file_references:
                for file_ref in file_references:
                    processed_files.append({
                        "filename": file_ref.filename,
                        "content": file_ref.content,
                        "type": file_ref.file_type,
                        "file_id": file_ref.file_id,
                        "file_path": file_ref.file_path
                    })
            
            # Get or create conversation for memory-enabled agents
            session = None
            conversation = None
            if agent.has_memory:
                from services.conversation_service import ConversationService
                
                # If conversation_id provided, validate and use it
                if conversation_id:
                    conversation = ConversationService.get_conversation(
                        db=db,
                        conversation_id=conversation_id,
                        user_context=user_context,
                        agent_id=agent_id
                    )
                    if not conversation:
                        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
                    
                    # Extract session_id from conversation (without "conv_{agent_id}_" prefix)
                    session_suffix = conversation.session_id.replace(f"conv_{agent_id}_", "")
                    session = await self.session_service.get_user_session(
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=session_suffix
                    )
                else:
                    # Auto-create a conversation if none exists
                    conversation = ConversationService.create_conversation(
                        db=db,
                        agent_id=agent_id,
                        user_context=user_context,
                        title=None  # Auto-generate title
                    )
                    logger.info(f"Auto-created conversation {conversation.conversation_id} for agent {agent_id}")
                    
                    # Extract session_id from conversation (without "conv_{agent_id}_" prefix)
                    session_suffix = conversation.session_id.replace(f"conv_{agent_id}_", "")
                    session = await self.session_service.get_user_session(
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=session_suffix
                    )

            # Re-query agent with all relationships eagerly loaded
            fresh_agent = self.agent_execution_repo.get_agent_with_relationships(db, agent_id)
            if not fresh_agent:
                raise HTTPException(status_code=404, detail="Agent not found in database")

            # Build enhanced message with file contents
            enhanced_message, image_files = self._prepare_message_with_files(message, processed_files)

            # Determine session ID for checkpointer
            session_id_for_cache = session.id if (fresh_agent.has_memory and session) else None

            # Execute agent directly in FastAPI's event loop (shared checkpointer pool)
            response = await self._execute_agent_async(
                fresh_agent, enhanced_message, search_params, session_id_for_cache, user_context, image_files
            )

            # Parse response based on agent's output parser
            from tools.agentTools import parse_agent_response
            parsed_response = parse_agent_response(response, agent)

            # Update request count
            self._update_request_count(agent, db)

            # Update session timestamp to keep it alive
            if session:
                await self.session_service.touch_session(session.id)

            # Update conversation message count if using a specific conversation
            if conversation:
                from services.conversation_service import ConversationService
                # Get last message preview (truncate response if too long)
                last_message_preview = parsed_response[:200] if isinstance(parsed_response, str) else str(parsed_response)[:200]
                
                # Clean message for preview if it's a list (multimodal)
                # This ensures the conversation list shows clean text instead of JSON structure
                if isinstance(parsed_response, list):
                    try:
                        text_parts = []
                        for item in parsed_response:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        if text_parts:
                            last_message_preview = " ".join(text_parts)[:200]
                    except Exception:
                        pass
                
                # Increment by 2 (user message + agent response)
                ConversationService.increment_message_count(
                    db=db,
                    conversation_id=conversation.conversation_id,
                    last_message=last_message_preview,
                    increment_by=2
                )
            
            return {
                "response": parsed_response,
                "agent_id": agent_id,
                "conversation_id": conversation.conversation_id if conversation else None,
                "metadata": {
                    "agent_name": agent.name,
                    "agent_type": agent.type,
                    "files_processed": len(processed_files),
                    "has_memory": agent.has_memory
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing agent chat: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    async def execute_agent_chat(
        self, 
        agent_id: int, 
        message: str, 
        files: List[UploadFile] = None,
        search_params: Dict = None,
        user_context: Dict = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute agent chat - used by both playground and public API
        
        Args:
            agent_id: ID of the agent to execute
            message: User message
            files: Optional file attachments
            search_params: Optional search parameters for silo-based agents
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Dict containing agent response and metadata
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Process files if provided
            processed_files = []
            if files:
                processed_files = await self._process_files_for_agent(files, agent)
            
            # Get user session for memory-enabled agents
            session = None
            if agent.has_memory:
                # Extract conversation_id from user_context to ensure correct session identification
                conversation_id = user_context.get("conversation_id") if user_context else None
                session = await self.session_service.get_user_session(agent_id, user_context, conversation_id)

            # Re-query agent with all relationships eagerly loaded
            fresh_agent = self.agent_execution_repo.get_agent_with_relationships(db, agent_id)
            if not fresh_agent:
                raise HTTPException(status_code=404, detail="Agent not found in database")

            # Build enhanced message with file contents
            enhanced_message, image_files = self._prepare_message_with_files(message, processed_files)

            # Determine session ID for checkpointer
            session_id_for_cache = session.id if (fresh_agent.has_memory and session) else None

            # Execute agent directly in FastAPI's event loop (shared checkpointer pool)
            response = await self._execute_agent_async(
                fresh_agent, enhanced_message, search_params, session_id_for_cache, user_context, image_files
            )

            # Parse response based on agent's output parser
            from tools.agentTools import parse_agent_response
            parsed_response = parse_agent_response(response, agent)
            
            # Update request count
            self._update_request_count(agent, db)
            
            # Update session timestamp to keep it alive
            if session:
                await self.session_service.touch_session(session.id)
            
            return {
                "response": parsed_response,
                "agent_id": agent_id,
                "metadata": {
                    "agent_name": agent.name,
                    "agent_type": agent.type,
                    "files_processed": len(processed_files),
                    "has_memory": agent.has_memory
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing agent chat: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
    
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
                raise HTTPException(status_code=404, detail="Agent not found")
            
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
                raise HTTPException(status_code=404, detail="Agent not found")
            
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
                            
                    return cleaned_history
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            return []
    
    async def _validate_agent_access(self, agent: Agent, user_context: Dict):
        """Validate user has access to the agent"""
        # TODO: Implement proper access validation
        # For now, just log the validation
        logger.info(f"Validating access for agent {agent.agent_id} with context {user_context}")
        pass
    
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
    
    def _process_single_file(self, temp_path: str, filename: str) -> Dict:
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
            agent = self.agent_execution_repo.get_ocr_agent_with_relationships(db, agent.agent_id)
            
            if not agent:
                raise Exception(f"Agent {agent.agent_id} not found")
            
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
                            logger.info(f"Processing text with LLM and output parser")
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
                            raise Exception("Vision model not found")
                        
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
                        except (OSError, FileNotFoundError):
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

    async def _execute_agent_async(
        self,
        fresh_agent: Agent,
        message: str,
        search_params: Dict = None,
        session_id_for_cache: str = None,
        user_context: Dict = None,
        image_files: List[Dict] = None
    ) -> str:
        """Execute agent in FastAPI's event loop using shared checkpointer pool"""
        from tools.agentTools import create_agent, prepare_agent_config
        from langchain_core.messages import HumanMessage

        mcp_client = None
        try:
            # Create the agent chain with all tools and capabilities
            agent_chain, tracer, mcp_client = await create_agent(
                fresh_agent, search_params, session_id_for_cache, user_context
            )
            
            # Prepare configuration with tracer
            config = prepare_agent_config(fresh_agent, tracer)
            
            # Add session-specific configuration if memory is enabled
            if fresh_agent.has_memory and session_id_for_cache:
                config["configurable"]["thread_id"] = f"thread_{fresh_agent.agent_id}_{session_id_for_cache}"
                logger.info(f"Using session-aware thread_id: {config['configurable']['thread_id']}")
            else:
                config["configurable"]["thread_id"] = f"thread_{fresh_agent.agent_id}"
            
            # Add the question to config
            config["configurable"]["question"] = message
            
            # Execute the agent in the SAME event loop as where MCP client was created
            formatted_user_message = fresh_agent.prompt_template.format(question=message)
            
            # Construct message content
            if image_files:
                content = [{"type": "text", "text": formatted_user_message}]
                
                # Get TMP_BASE_FOLDER from config
                app_config = get_app_config()
                tmp_base_folder = app_config['TMP_BASE_FOLDER']
                
                # Check for aict_base_url environment variable (Production Mode)
                aict_base_url = os.getenv('AICT_BASE_URL')
                
                for img in image_files:
                    file_path = img.get('file_path', '')
                    if not file_path:
                        logger.warning(f"Image file has no file_path: {img}")
                        continue
                        
                    # Ensure forward slashes
                    file_path = file_path.replace('\\', '/')
                    if file_path.startswith('/'):
                        file_path = file_path[1:]
                    
                    # If aict_base_url is set, use it (Production Mode)
                    if aict_base_url:
                        # Remove trailing slash if present
                        if aict_base_url.endswith('/'):
                            aict_base_url = aict_base_url[:-1]
                            
                        # Generate signed URL
                        user_email = user_context.get('email') if user_context else None
                        if user_email:
                            from utils.security import generate_signature
                            sig = generate_signature(file_path, user_email)
                            url = f"{aict_base_url}/static/{file_path}?user={user_email}&sig={sig}"
                        else:
                            # Fallback if no user context (should not happen in auth mode)
                            url = f"{aict_base_url}/static/{file_path}"
                            
                        logger.info(f"Adding image to message using public URL: {url}")
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": url}
                        })
                    else:
                        # Fallback to Base64 (Development Mode)
                        # Use Base64 for local development to avoid localhost URL issues
                        try:
                            # Construct full path
                            full_path = os.path.join(tmp_base_folder, file_path)
                            
                            if os.path.exists(full_path):
                                import base64
                                import mimetypes
                                
                                mime_type, _ = mimetypes.guess_type(full_path)
                                if not mime_type:
                                    mime_type = "image/jpeg"
                                    
                                with open(full_path, "rb") as image_file:
                                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    
                                data_url = f"data:{mime_type};base64,{encoded_string}"
                                logger.info(f"Adding image to message as base64 (length: {len(encoded_string)})")
                                
                                content.append({
                                    "type": "image_url",
                                    "image_url": {"url": data_url}
                                })
                            else:
                                # Fallback to URL if file not found locally (should not happen)
                                url = f"http://localhost:8000/static/{file_path}"
                                logger.warning(f"Image file not found at {full_path}, falling back to URL: {url}")
                                content.append({
                                    "type": "image_url",
                                    "image_url": {"url": url}
                                })
                        except Exception as e:
                            logger.error(f"Error processing image for base64: {e}")
                            # Fallback to URL
                            url = f"http://localhost:8000/static/{file_path}"
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": url}
                            })
                
                message_payload = HumanMessage(content=content)
            else:
                message_payload = HumanMessage(content=formatted_user_message)
            
            result = await agent_chain.ainvoke({"messages": [message_payload]}, config=config)
            
            # Extract the response from the result
            if isinstance(result, dict) and "messages" in result:
                # Get the last AI message
                messages = result["messages"]
                for msg in reversed(messages):
                    if hasattr(msg, 'content') and msg.content:
                        return msg.content
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